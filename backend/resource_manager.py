"""
Модуль управления производственными ресурсами
Дата: 2025-12-23
Автор: Claude Sonnet 4.5

Этот модуль отвечает за:
- Расчет доступной мощности ресурсов
- Планирование загрузки цехов
- Определение узких мест (bottlenecks)
- Генерацию рекомендаций по оптимизации
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json


class ResourceManager:
    """Менеджер производственных ресурсов"""

    def __init__(self, db_path: str = 'wiso_golabel.db'):
        self.db_path = db_path

    def get_connection(self):
        """Получить соединение с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ========================================
    # РАСЧЕТ МОЩНОСТЕЙ
    # ========================================

    def calculate_resource_capacity(self, resource_id: int) -> Dict:
        """
        Расчет доступной мощности ресурса

        Формула: Total_Capacity = Quantity × Shifts × Shift_Duration × Efficiency

        Args:
            resource_id: ID ресурса

        Returns:
            {
                'resource_id': 1,
                'resource_name': 'Печь',
                'quantity': 2,
                'shifts_count': 1,
                'shift_duration_min': 480,
                'efficiency': 0.9,
                'total_capacity_min': 864.0,  # 2 × 1 × 480 × 0.9
                'total_capacity_hours': 14.4
            }
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                resource_id,
                resource_name,
                resource_type,
                quantity,
                shifts_count,
                shift_duration_min,
                efficiency,
                (quantity * shifts_count * shift_duration_min * efficiency) AS total_capacity_min
            FROM factory_resources
            WHERE resource_id = ? AND active = 1
        """, (resource_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'resource_id': row['resource_id'],
            'resource_name': row['resource_name'],
            'resource_type': row['resource_type'],
            'quantity': row['quantity'],
            'shifts_count': row['shifts_count'],
            'shift_duration_min': row['shift_duration_min'],
            'efficiency': row['efficiency'],
            'total_capacity_min': float(row['total_capacity_min']),
            'total_capacity_hours': round(float(row['total_capacity_min']) / 60, 2)
        }

    def get_all_resources_capacity(self) -> List[Dict]:
        """Получить мощности всех активных ресурсов"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM v_resource_capacity
        """)

        resources = []
        for row in cursor.fetchall():
            resources.append({
                'resource_id': row['resource_id'],
                'resource_name': row['resource_name'],
                'resource_type': row['resource_type'],
                'quantity': row['quantity'],
                'shifts_count': row['shifts_count'],
                'shift_duration_min': row['shift_duration_min'],
                'efficiency': row['efficiency'],
                'total_capacity_min': float(row['total_capacity_min']),
                'total_capacity_hours': round(float(row['total_capacity_min']) / 60, 2)
            })

        conn.close()
        return resources

    # ========================================
    # ПЛАНИРОВАНИЕ ЗАГРУЗКИ
    # ========================================

    def calculate_production_load(self, production_plan: List[Dict], target_date: str) -> Dict:
        """
        Расчет загрузки ресурсов на основе плана производства

        Args:
            production_plan: План производства [{'article_nr': '05501', 'quantity': 20, 'batches': 2}, ...]
            target_date: Дата производства (YYYY-MM-DD)

        Returns:
            {
                'date': '2025-12-23',
                'resources_load': [
                    {
                        'resource_id': 1,
                        'resource_name': 'Печь',
                        'planned_load_min': 180.0,
                        'available_capacity_min': 864.0,
                        'utilization_percent': 20.8,
                        'status': 'normal',
                        'status_label': '🟢 Норма'
                    }
                ],
                'bottlenecks': [...],
                'recommendations': [...]
            }
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Получение всех ресурсов
        resources = self.get_all_resources_capacity()

        # Инициализация загрузки ресурсов
        resource_load = {}
        for res in resources:
            resource_load[res['resource_id']] = {
                'resource_id': res['resource_id'],
                'resource_name': res['resource_name'],
                'available_capacity_min': res['total_capacity_min'],
                'planned_load_min': 0.0,
                'setup_time_min': 0.0,
                'articles': []
            }

        # Расчет потребления для каждого артикула в плане
        for item in production_plan:
            article_nr = item['article_nr']
            quantity = item.get('quantity', 0)
            batches = item.get('batches', 0)

            # Получение потребления ресурсов для артикула
            cursor.execute("""
                SELECT
                    resource_id,
                    time_needed_min,
                    batch_multiplier,
                    setup_time_min
                FROM product_resource_consumption
                WHERE article_nr = ?
            """, (article_nr,))

            consumptions = cursor.fetchall()

            for cons in consumptions:
                res_id = cons['resource_id']

                if res_id not in resource_load:
                    continue

                # Расчет времени
                time_per_unit = cons['time_needed_min']
                batch_mult = cons['batch_multiplier']
                setup_time = cons['setup_time_min']

                # ВАЖНО: time_needed_min - это время на 1 ШТУКУ, поэтому умножаем на quantity (количество штук)
                # Общее время = (время на единицу × количество штук × множитель) + время настройки
                total_time = (time_per_unit * quantity * batch_mult) + setup_time

                resource_load[res_id]['planned_load_min'] += total_time
                resource_load[res_id]['setup_time_min'] += setup_time
                resource_load[res_id]['articles'].append({
                    'article_nr': article_nr,
                    'quantity': quantity,
                    'batches': batches,
                    'time_needed_min': round(total_time, 2)
                })

        # Расчет процента использования и статуса
        resources_load_list = []
        bottlenecks = []

        for res_id, load_data in resource_load.items():
            planned = load_data['planned_load_min']
            available = load_data['available_capacity_min']

            utilization = (planned / available * 100) if available > 0 else 0

            # Определение статуса
            if utilization < 70:
                status = 'normal'
                status_label = '🟢 Норма'
            elif utilization < 85:
                status = 'warning'
                status_label = '🟡 Предупреждение'
            elif utilization < 100:
                status = 'high'
                status_label = '🟠 Высокая загрузка'
            else:
                status = 'overload'
                status_label = '🔴 Перегрузка'

            load_data['utilization_percent'] = round(utilization, 2)
            load_data['status'] = status
            load_data['status_label'] = status_label

            resources_load_list.append(load_data)

            # Определение узких мест
            if utilization >= 85:
                bottlenecks.append({
                    'resource_id': res_id,
                    'resource_name': load_data['resource_name'],
                    'utilization_percent': round(utilization, 2),
                    'overload_min': round(max(0, planned - available), 2),
                    'severity': 'critical' if utilization >= 100 else 'warning'
                })

            # Запись в историю загрузки
            cursor.execute("""
                INSERT OR REPLACE INTO resource_load_history
                (resource_id, date, planned_load_min, available_capacity_min, utilization_percent, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (res_id, target_date, planned, available, round(utilization, 2), status))

        conn.commit()

        # Генерация рекомендаций
        recommendations = self.generate_recommendations(target_date, resources_load_list, bottlenecks)

        conn.close()

        return {
            'date': target_date,
            'resources_load': resources_load_list,
            'bottlenecks': bottlenecks,
            'recommendations': recommendations
        }

    # ========================================
    # ГЕНЕРАЦИЯ РЕКОМЕНДАЦИЙ
    # ========================================

    def generate_recommendations(self, date: str, resources_load: List[Dict], bottlenecks: List[Dict]) -> List[Dict]:
        """
        Генерация рекомендаций по оптимизации производства

        Args:
            date: Дата производства
            resources_load: Загрузка ресурсов
            bottlenecks: Узкие места

        Returns:
            [
                {
                    'type': 'add_shift',
                    'severity': 'critical',
                    'message': 'Печь перегружена на 120 минут...',
                    'details': {...}
                }
            ]
        """
        recommendations = []
        conn = self.get_connection()
        cursor = conn.cursor()

        for bottleneck in bottlenecks:
            resource_id = bottleneck['resource_id']
            resource_name = bottleneck['resource_name']
            utilization = bottleneck['utilization_percent']
            overload_min = bottleneck['overload_min']

            # Получение данных ресурса
            cursor.execute("""
                SELECT quantity, shifts_count, shift_duration_min, efficiency
                FROM factory_resources
                WHERE resource_id = ?
            """, (resource_id,))

            res_data = cursor.fetchone()

            if not res_data:
                continue

            quantity = res_data['quantity']
            shifts = res_data['shifts_count']
            duration = res_data['shift_duration_min']
            efficiency = res_data['efficiency']

            # Рекомендация 1: Добавить смену
            if overload_min > 0 and shifts < 3:
                # Расчет сколько смен нужно добавить
                capacity_per_shift = quantity * duration * efficiency
                additional_shifts_needed = int((overload_min / capacity_per_shift) + 0.5)

                recommendation = {
                    'type': 'add_shift',
                    'severity': 'critical' if utilization >= 100 else 'warning',
                    'resource_id': resource_id,
                    'message': f'"{resource_name}" перегружен на {overload_min:.0f} минут ({round(overload_min/60, 1)} часов). Рекомендуется добавить {additional_shifts_needed} смену(ы).',
                    'details': {
                        'current_shifts': shifts,
                        'recommended_shifts': min(shifts + additional_shifts_needed, 3),
                        'overload_min': overload_min,
                        'overload_hours': round(overload_min / 60, 2)
                    }
                }
                recommendations.append(recommendation)

                # Запись в БД
                cursor.execute("""
                    INSERT INTO production_recommendations
                    (date, resource_id, recommendation_type, severity, message, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (date, resource_id, 'add_shift', recommendation['severity'],
                      recommendation['message'], json.dumps(recommendation['details'])))

            # Рекомендация 2: Перенести производство на предыдущий день
            if overload_min > 0:
                recommendation = {
                    'type': 'move_to_prev_day',
                    'severity': 'warning',
                    'resource_id': resource_id,
                    'message': f'Альтернатива: Перенести часть производства на предыдущий день, освободив ~{round(overload_min/60, 1)} часов в "{resource_name}".',
                    'details': {
                        'time_to_move_min': overload_min,
                        'time_to_move_hours': round(overload_min / 60, 2)
                    }
                }
                recommendations.append(recommendation)

                cursor.execute("""
                    INSERT INTO production_recommendations
                    (date, resource_id, recommendation_type, severity, message, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (date, resource_id, 'move_to_prev_day', 'warning',
                      recommendation['message'], json.dumps(recommendation['details'])))

            # Рекомендация 3: Увеличить количество оборудования
            if utilization >= 100:
                # Расчет сколько единиц оборудования нужно добавить
                additional_quantity_needed = int((overload_min / (duration * efficiency)) + 0.5)

                recommendation = {
                    'type': 'increase_capacity',
                    'severity': 'info',
                    'resource_id': resource_id,
                    'message': f'Долгосрочная рекомендация: Рассмотреть приобретение {additional_quantity_needed} доп. единиц оборудования "{resource_name}" для увеличения мощности.',
                    'details': {
                        'current_quantity': quantity,
                        'recommended_quantity': quantity + additional_quantity_needed,
                        'additional_needed': additional_quantity_needed
                    }
                }
                recommendations.append(recommendation)

                cursor.execute("""
                    INSERT INTO production_recommendations
                    (date, resource_id, recommendation_type, severity, message, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, (date, resource_id, 'increase_capacity', 'info',
                      recommendation['message'], json.dumps(recommendation['details'])))

        conn.commit()
        conn.close()

        return recommendations

    # ========================================
    # УПРАВЛЕНИЕ РЕСУРСАМИ (CRUD)
    # ========================================

    def update_resource(self, resource_id: int, **kwargs) -> bool:
        """
        Обновление параметров ресурса

        Args:
            resource_id: ID ресурса
            **kwargs: Поля для обновления (quantity, shifts_count, shift_duration_min, efficiency)

        Returns:
            True если успешно, False иначе
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        allowed_fields = ['quantity', 'shifts_count', 'shift_duration_min', 'efficiency', 'description', 'active']
        updates = []
        values = []

        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f"{field} = ?")
                values.append(value)

        if not updates:
            conn.close()
            return False

        updates.append("updated_at = datetime('now')")
        values.append(resource_id)

        sql = f"UPDATE factory_resources SET {', '.join(updates)} WHERE resource_id = ?"

        cursor.execute(sql, values)
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()

        return success

    def add_resource(self, resource_data: Dict) -> bool:
        """
        Добавление нового ресурса

        Args:
            resource_data: Словарь с данными ресурса
                {
                    'resource_name': str,
                    'resource_type': str,
                    'quantity': int,
                    'shifts_count': int,
                    'shift_duration_min': int,
                    'efficiency': float,
                    'description': str (optional)
                }

        Returns:
            True если успешно, False иначе
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO factory_resources
                (resource_name, resource_type, category, quantity, shifts_count,
                 shift_duration_min, efficiency, description, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
            """, (
                resource_data.get('resource_name'),
                resource_data.get('resource_type', 'equipment'),
                resource_data.get('category'),
                resource_data.get('quantity', 1),
                resource_data.get('shifts_count', 1),
                resource_data.get('shift_duration_min', 480),
                resource_data.get('efficiency', 1.0),
                resource_data.get('description', '')
            ))

            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success

        except Exception as e:
            conn.close()
            print(f"Error adding resource: {e}")
            return False

    def delete_resource(self, resource_id: int) -> bool:
        """
        Удаление ресурса

        Args:
            resource_id: ID ресурса для удаления

        Returns:
            True если успешно, False иначе
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Сначала удаляем связанные записи о потреблении
            cursor.execute("""
                DELETE FROM product_resource_consumption WHERE resource_id = ?
            """, (resource_id,))

            # Удаляем историю загрузки
            cursor.execute("""
                DELETE FROM resource_load_history WHERE resource_id = ?
            """, (resource_id,))

            # Удаляем сам ресурс
            cursor.execute("""
                DELETE FROM factory_resources WHERE resource_id = ?
            """, (resource_id,))

            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success

        except Exception as e:
            conn.close()
            print(f"Error deleting resource: {e}")
            return False

    def get_resource(self, resource_id: int) -> Optional[Dict]:
        """Получить данные ресурса"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM factory_resources WHERE resource_id = ?
        """, (resource_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return dict(row)

    def get_all_resources(self) -> List[Dict]:
        """Получить все ресурсы"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM factory_resources ORDER BY resource_id
        """)

        resources = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return resources

    # ========================================
    # УПРАВЛЕНИЕ ПОТРЕБЛЕНИЕМ РЕСУРСОВ
    # ========================================

    def set_article_resource_consumption(self, article_nr: str, resource_id: int,
                                        time_needed_min: float, batch_multiplier: float = 1.0,
                                        setup_time_min: float = 0.0, comments: str = None) -> bool:
        """
        Установить потребление ресурса для артикула

        Args:
            article_nr: Артикул
            resource_id: ID ресурса
            time_needed_min: Минут на единицу продукции
            batch_multiplier: Множитель для замесов
            setup_time_min: Время на подготовку
            comments: Комментарий

        Returns:
            True если успешно
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO product_resource_consumption
            (article_nr, resource_id, time_needed_min, batch_multiplier, setup_time_min, comments, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (article_nr, resource_id, time_needed_min, batch_multiplier, setup_time_min, comments))

        conn.commit()
        success = cursor.rowcount > 0
        conn.close()

        return success

    def get_article_resource_consumption(self, article_nr: str) -> List[Dict]:
        """Получить потребление ресурсов для артикула"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM v_product_resource_details
            WHERE article_nr = ?
        """, (article_nr,))

        consumptions = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return consumptions

    # ========================================
    # АНАЛИЗ И СТАТИСТИКА
    # ========================================

    def get_resource_load_history(self, resource_id: int, start_date: str, end_date: str) -> List[Dict]:
        """Получить историю загрузки ресурса"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM v_resource_load_status
            WHERE resource_id = ? AND date BETWEEN ? AND ?
            ORDER BY date
        """, (resource_id, start_date, end_date))

        history = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return history

    def get_recommendations_for_date(self, date: str, acknowledged: bool = None) -> List[Dict]:
        """Получить рекомендации для даты"""
        conn = self.get_connection()
        cursor = conn.cursor()

        if acknowledged is None:
            cursor.execute("""
                SELECT * FROM production_recommendations
                WHERE date = ?
                ORDER BY severity DESC, created_at DESC
            """, (date,))
        else:
            ack_value = 1 if acknowledged else 0
            cursor.execute("""
                SELECT * FROM production_recommendations
                WHERE date = ? AND acknowledged = ?
                ORDER BY severity DESC, created_at DESC
            """, (date, ack_value))

        recommendations = []
        for row in cursor.fetchall():
            rec = dict(row)
            if rec['details']:
                rec['details'] = json.loads(rec['details'])
            recommendations.append(rec)

        conn.close()
        return recommendations

    def acknowledge_recommendation(self, recommendation_id: int, username: str) -> bool:
        """Отметить рекомендацию как прочитанную"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE production_recommendations
            SET acknowledged = 1, acknowledged_at = datetime('now'), acknowledged_by = ?
            WHERE recommendation_id = ?
        """, (username, recommendation_id))

        conn.commit()
        success = cursor.rowcount > 0
        conn.close()

        return success


# ========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================

def format_time(minutes: float) -> str:
    """Форматирование времени в читаемый вид"""
    hours = int(minutes // 60)
    mins = int(minutes % 60)

    if hours > 0:
        return f"{hours}ч {mins}мин"
    else:
        return f"{mins}мин"


def get_status_color(utilization_percent: float) -> str:
    """Получить цвет статуса по проценту загрузки"""
    if utilization_percent < 70:
        return '#2ecc71'  # Зеленый
    elif utilization_percent < 85:
        return '#f39c12'  # Желтый
    elif utilization_percent < 100:
        return '#e67e22'  # Оранжевый
    else:
        return '#e74c3c'  # Красный


# ========================================
# ТЕСТИРОВАНИЕ
# ========================================

if __name__ == '__main__':
    # Пример использования
    manager = ResourceManager()

    print("=== МОЩНОСТИ РЕСУРСОВ ===")
    resources = manager.get_all_resources_capacity()
    for res in resources:
        print(f"{res['resource_name']}: {res['total_capacity_hours']} часов/день "
              f"({res['quantity']} × {res['shifts_count']} смен × {res['shift_duration_min']/60}ч × {res['efficiency']*100}%)")

    print("\n=== ПРИМЕР ПЛАНА ПРОИЗВОДСТВА ===")
    test_plan = [
        {'article_nr': '05501', 'quantity': 20, 'batches': 2}
    ]

    result = manager.calculate_production_load(test_plan, '2025-12-23')

    print(f"\nДата: {result['date']}")
    print("\nЗагрузка ресурсов:")
    for load in result['resources_load']:
        print(f"  {load['resource_name']}: {load['utilization_percent']}% "
              f"({load['planned_load_min']:.0f}/{load['available_capacity_min']:.0f} мин) "
              f"{load['status_label']}")

    if result['bottlenecks']:
        print("\n⚠️ УЗКИЕ МЕСТА:")
        for bn in result['bottlenecks']:
            print(f"  - {bn['resource_name']}: {bn['utilization_percent']}% (перегруз {bn['overload_min']:.0f} мин)")

    if result['recommendations']:
        print("\n💡 РЕКОМЕНДАЦИИ:")
        for rec in result['recommendations']:
            print(f"  {rec['message']}")
