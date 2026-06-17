#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logistics Manager для расчёта дат производства и доставки
Использует данные из таблиц logistics_routes и client_routes
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
import json

logger = logging.getLogger(__name__)


class LogisticsManager:
    """
    Менеджер логистики для автоматического расчёта дат производства и доставки

    Логика:
    1. Получает номер клиента (kunden_nr)
    2. Находит назначенный маршрут клиента из БД (client_routes)
    3. Получает правила маршрута (delivery_days, lead_time, is_manual)
    4. Рассчитывает:
       - production_date = order_date + lead_time
       - delivery_date = следующий доступный день доставки после production_date
    """

    def __init__(self, db, resource_manager=None):
        """
        Args:
            db: Database instance для получения данных логистики
            resource_manager: ResourceManager instance для проверки мощности производства
        """
        self.db = db
        self.resource_manager = resource_manager
        self.routes_cache = {}  # Кеш маршрутов {route_id: route_data}
        self.client_routes_cache = {}  # Кеш назначений {kunden_nr: route_id}
        self.cache_timestamp = None
        self.cache_ttl = 300  # TTL кеша 5 минут

        logger.info("Logistics Manager initialized with ResourceManager support")

    def refresh_cache(self):
        """Обновить кеш данных логистики из базы"""
        try:
            logistics_data = self.db.get_all_logistics()

            # Обновляем кеш маршрутов
            self.routes_cache = {
                route['route_id']: route
                for route in logistics_data['routes']
            }

            # Добавляем дефолтный маршрут 'free' для клиентов без маршрута
            if 'free' not in self.routes_cache:
                self.routes_cache['free'] = {
                    'route_id': 'free',
                    'route_name': 'Свободные заказы',
                    'delivery_days': json.dumps([]),  # Пустой список = ручной режим
                    'lead_time_days': 1,
                    'is_manual': 1,  # Ручной режим
                    'color': '#808080'
                }
                logger.debug("Added default 'free' route to cache")

            # Обновляем кеш назначений клиентов
            self.client_routes_cache = {
                client['client_id']: client['route_id']
                for client in logistics_data['clients']
            }

            self.cache_timestamp = datetime.now()
            logger.debug(f"Logistics cache refreshed: {len(self.routes_cache)} routes, {len(self.client_routes_cache)} clients")

        except Exception as e:
            logger.error(f"Error refreshing logistics cache: {e}")

    def get_client_route(self, kunden_nr: str) -> Optional[Dict]:
        """
        Получить данные маршрута для клиента

        Args:
            kunden_nr: Номер клиента

        Returns:
            Словарь с данными маршрута или None
        """
        # Проверяем TTL кеша
        if self.cache_timestamp is None or \
           (datetime.now() - self.cache_timestamp).total_seconds() > self.cache_ttl:
            self.refresh_cache()

        # Нормализуем номер клиента (убираем пробелы, ведущие нули)
        kunden_nr_clean = str(kunden_nr).strip()
        kunden_nr_normalized = str(int(kunden_nr_clean)) if kunden_nr_clean.isdigit() else kunden_nr_clean

        # Ищем route_id клиента (пробуем оба варианта номера)
        route_id = self.client_routes_cache.get(kunden_nr_clean) or \
                   self.client_routes_cache.get(kunden_nr_normalized)

        if not route_id:
            logger.debug(f"No route found for client {kunden_nr}, using 'free' route")
            route_id = 'free'  # По умолчанию - свободные заказы

        # Получаем данные маршрута
        route_data = self.routes_cache.get(route_id)
        if not route_data:
            logger.warning(f"Route {route_id} not found in cache, returning None")
            return None

        return route_data

    def get_workdays_from_settings(self) -> list:
        """
        Получить рабочие дни из настроек плана производства

        Returns:
            Список номеров дней недели (0=Пн, 6=Вс), например: [0, 1, 2, 3, 4]
        """
        try:
            import json
            # Получаем глобальные настройки (user_id = NULL)
            settings = self.db.get_plan_settings(user_id=None)

            if not settings:
                # По умолчанию: пн-пт
                logger.debug("No workdays settings found, using default Mon-Fri")
                return [0, 1, 2, 3, 4]

            workdays_str = settings.get('workdays', '["monday", "tuesday", "wednesday", "thursday", "friday"]')
            workdays_names = json.loads(workdays_str)

            # Преобразуем названия дней в номера
            day_map = {
                'monday': 0,
                'tuesday': 1,
                'wednesday': 2,
                'thursday': 3,
                'friday': 4,
                'saturday': 5,
                'sunday': 6
            }

            workdays = [day_map[day.lower()] for day in workdays_names if day.lower() in day_map]
            logger.debug(f"Workdays from settings: {workdays}")
            return workdays

        except Exception as e:
            logger.error(f"Error getting workdays from settings: {e}")
            return [0, 1, 2, 3, 4]  # По умолчанию пн-пт

    def find_next_available_production_day(self, start_date: datetime, check_capacity: bool = True) -> datetime:
        """
        Найти ближайший доступный РАБОЧИЙ день для производства с учетом:
        - Рабочих дней из настроек плана
        - Мощности производства через ResourceManager

        Args:
            start_date: Дата начала поиска
            check_capacity: Проверять ли загруженность производства (по умолчанию True)

        Returns:
            Дата ближайшего доступного дня производства
        """
        current = start_date
        max_iterations = 30  # Защита от бесконечного цикла (месяц макс)

        # Получаем рабочие дни из настроек плана
        workdays = self.get_workdays_from_settings()

        for _ in range(max_iterations):
            # Проверка 1: Это рабочий день согласно настройкам?
            if current.weekday() in workdays:
                # Проверка 2: Есть ли свободная мощность производства?
                if check_capacity and self.resource_manager:
                    capacity_info = self.check_production_capacity_with_resources(current.strftime('%Y-%m-%d'))
                    if capacity_info['has_capacity']:
                        logger.debug(f"Production day found: {current.date()} (utilization: {capacity_info.get('utilization_percent', 0):.1f}%)")
                        return current
                    else:
                        logger.debug(f"Production {current.date()} is at capacity ({capacity_info.get('utilization_percent', 0):.1f}%), trying next day")
                else:
                    # Если не проверяем мощность - просто возвращаем первый рабочий день
                    return current

            current += timedelta(days=1)

        # Если не нашли за месяц - возвращаем что есть
        logger.warning(f"Could not find available production day in {max_iterations} days")
        return start_date

    def check_production_capacity_with_resources(self, production_date: str) -> Dict:
        """
        Проверить загруженность производства через ResourceManager

        Args:
            production_date: Дата производства в формате 'YYYY-MM-DD'

        Returns:
            Dict с информацией: {
                'has_capacity': bool,  # Есть ли свободная мощность
                'utilization_percent': float,  # Средний % загрузки ресурсов
                'bottlenecks': list,  # Узкие места (ресурсы >90%)
                'total_orders': int  # Кол-во заказов на эту дату
            }
        """
        try:
            if not self.resource_manager:
                # Fallback: простая проверка по количеству заказов
                orders_count = self.db.count_orders_by_production_date(production_date)
                MAX_DAILY_CAPACITY = 100
                return {
                    'has_capacity': orders_count < MAX_DAILY_CAPACITY,
                    'utilization_percent': (orders_count / MAX_DAILY_CAPACITY) * 100,
                    'bottlenecks': [],
                    'total_orders': orders_count
                }

            # Получаем план производства на эту дату
            # TODO: Нужен метод db.get_production_plan_for_date(date)
            # Пока используем упрощенную логику
            orders_count = self.db.count_orders_by_production_date(production_date)

            # Если нет заказов - есть место
            if orders_count == 0:
                return {
                    'has_capacity': True,
                    'utilization_percent': 0,
                    'bottlenecks': [],
                    'total_orders': 0
                }

            # Получаем все заказы на эту дату и считаем загрузку
            orders = self.db.get_orders_by_production_date(production_date)

            # Формируем план для ResourceManager
            production_plan = []
            for order in orders:
                order_data = json.loads(order['order_data']) if isinstance(order['order_data'], str) else order['order_data']
                artikel = order_data.get('artikel', [])
                for art in artikel:
                    production_plan.append({
                        'article_nr': art.get('artikel_nr', art.get('nummer', '')),
                        'quantity': art.get('menge', 0),
                        'batches': 1  # Упрощение
                    })

            # Рассчитываем загрузку через ResourceManager
            load_info = self.resource_manager.calculate_production_load(production_plan, production_date)

            # Анализируем результат
            resources_load = load_info.get('resources_load', [])
            if not resources_load:
                return {
                    'has_capacity': True,
                    'utilization_percent': 0,
                    'bottlenecks': [],
                    'total_orders': orders_count
                }

            # Вычисляем среднюю загрузку
            avg_utilization = sum(r['utilization_percent'] for r in resources_load) / len(resources_load)

            # Находим узкие места (>90% загрузки)
            bottlenecks = [r for r in resources_load if r['utilization_percent'] > 90]

            # Есть место, если средняя загрузка < 90% И нет узких мест
            has_capacity = avg_utilization < 90 and len(bottlenecks) == 0

            return {
                'has_capacity': has_capacity,
                'utilization_percent': avg_utilization,
                'bottlenecks': [b['resource_name'] for b in bottlenecks],
                'total_orders': orders_count
            }

        except Exception as e:
            logger.error(f"Error checking production capacity: {e}", exc_info=True)
            return {
                'has_capacity': True,  # По умолчанию считаем, что есть место
                'utilization_percent': 0,
                'bottlenecks': [],
                'total_orders': 0
            }

    def find_next_delivery_day(self, start_date: datetime, delivery_days: list, include_start: bool = False) -> datetime:
        """
        Найти следующий доступный день доставки ПОСЛЕ даты производства

        Args:
            start_date: Дата начала поиска (обычно production_date)
            delivery_days: Список дней недели для доставки (0=Пн, 6=Вс)

        Returns:
            Дата следующей доставки
        """
        if not delivery_days:
            # Ручной режим - доставка на следующий день
            return start_date if include_start else (start_date + timedelta(days=1))

        # По умолчанию ищем со следующего дня, но для маршрутов с lead_time=0
        # допускаем отгрузку "день-в-день" (include_start=True).
        current = start_date if include_start else (start_date + timedelta(days=1))
        max_iterations = 14  # Защита от бесконечного цикла (2 недели макс)

        for _ in range(max_iterations):
            # weekday() возвращает 0=Пн, 6=Вс (совпадает с нашей системой)
            if current.weekday() in delivery_days:
                return current
            current += timedelta(days=1)

        # Если не нашли - берём первый доступный день
        logger.warning(f"Could not find delivery day in {max_iterations} days, using first available")
        return start_date if include_start else (start_date + timedelta(days=1))

    def calculate_dates(self, order_date_str, kunden_nr, order_value=0.0):
        """
        Рассчитать дату доставки и производства.
        Теперь учитывает СУММУ заказа для выбора маршрута.
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 1. Получаем настройки клиента
        kunden_nr_str = str(kunden_nr or '').strip()
        kunden_nr_norm = kunden_nr_str.lstrip('0') or kunden_nr_str
        cursor.execute(
            """
            SELECT route_id, route_rules
            FROM client_routes
            WHERE
                client_id IN (?, ?)
                OR monolith_client_id IN (?, ?)
            LIMIT 1
            """,
            (kunden_nr_str, kunden_nr_norm, kunden_nr_str, kunden_nr_norm)
        )
        row = cursor.fetchone()
        conn.close()

        assigned_route = 'free' # Маршрут по умолчанию
        route_rules = []

        if row:
            assigned_route = row['route_id'] or 'free'
            if row['route_rules']:
                try:
                    import json
                    route_rules = json.loads(row['route_rules'])
                except: pass

        # 2. ВЫБОР МАРШРУТА ПО СУММЕ (ИНТЕЛЛЕКТУАЛЬНЫЙ)
        selected_route = assigned_route # Начинаем с дефолтного

        if route_rules and order_value > 0:
            # Сортируем правила от большей суммы к меньшей
            # Пример: [500€ -> Route A], [300€ -> Route B], [0€ -> Route C]
            # Если заказ 400€, он не пройдет 500, но попадет в 300 -> Route B.
            route_rules.sort(key=lambda x: float(x.get('limit', 0)), reverse=True)
            
            for rule in route_rules:
                limit = float(rule.get('limit', 0))
                target_route = rule.get('route_id')
                
                if order_value >= limit:
                    selected_route = target_route
                    # print(f"Logistics: Client {kunden_nr} ({order_value}€) -> Rule >{limit} -> {selected_route}")
                    break

        # 3. Получаем данные самого маршрута (дни доставки)
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT route_name, delivery_days, lead_time, is_manual FROM logistics_routes WHERE route_id = ?", (selected_route,))
        route_data = cursor.fetchone()
        conn.close()

        if not route_data:
            # Если маршрут не найден, используем 'free' (ручной)
            return {
                'delivery_date': '',
                'production_date': order_date_str, # Временная заглушка
                'route_id': 'free',
                'route_name': 'Свободный (Нет данных)'
            }

        # ... (ДАЛЕЕ ВАШ СТАРЫЙ КОД РАСЧЕТА ДНЕЙ НЕДЕЛИ) ...
        # (Ниже я привожу полный код функции, чтобы вы просто скопировали всё целиком)
        
        delivery_days = []
        try:
            delivery_days = json.loads(route_data['delivery_days'])
        except: pass
        
        lead_time = route_data['lead_time']
        
        # Парсим дату заказа
        from datetime import datetime, timedelta
        try:
            order_dt = datetime.strptime(order_date_str, "%Y-%m-%d").date()
        except:
            order_dt = datetime.now().date()

        # Правило 14:00: если заказ зашёл после 14:00 и дата заказа — сегодня,
        # сдвигаем старт расчёта на следующий день (заказ попадёт на следующую
        # возможную дату доставки по маршруту).
        now = datetime.now()
        if order_dt == now.date() and now.hour >= 14:
            order_dt = order_dt + timedelta(days=1)
            import logging
            logging.getLogger(__name__).info(
                "Order cutoff 14:00 applied: order_date shifted to %s (received at %s)",
                order_dt, now.strftime("%H:%M")
            )

        # Рассчитываем дату производства (ближайший рабочий день, БЕЗ проверки мощностей)
        start_production = datetime.combine(order_dt, datetime.min.time()) + timedelta(days=lead_time)
        production_dt = self.find_next_available_production_day(start_production, check_capacity=False)

        # Рассчитываем дату доставки
        if not delivery_days:
            # Ручной маршрут: следующий рабочий день после производства
            final_delivery_dt = self.find_next_available_production_day(production_dt + timedelta(days=1), check_capacity=False)
        else:
            # Автоматический маршрут:
            # при lead_time=0 допускаем доставку в этот же день, если день маршрута подходит.
            final_delivery_dt = self.find_next_delivery_day(
                production_dt,
                delivery_days,
                include_start=(int(lead_time or 0) <= 0)
            )

        final_delivery_date = final_delivery_dt.date()
        production_date = production_dt.date()

        return {
            'delivery_date': final_delivery_date.strftime("%Y-%m-%d"),
            'production_date': production_date.strftime("%Y-%m-%d"),
            'route_id': selected_route,
            'route_name': route_data['route_name']
        }
