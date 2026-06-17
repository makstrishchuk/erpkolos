#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd
import logging
import time
import shutil
import os
import json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class WisoCSVMonitor:
    def __init__(self, csv_path: Path, db, logistics_manager, callback, sessions=None):
        self.csv_path = csv_path
        self.db = db
        self.logistics_manager = logistics_manager
        self.callback = callback
        self.sessions = sessions

        self.archive_dir = self.csv_path.parent / "Archive"
        self.archive_dir.mkdir(exist_ok=True)
        self.file_size = None
        self.file_stable_since = None

        # КАРТА КОЛОНОК (Добавлена total_value)
        self.col_map = {
            'order_id': 'AuftragsNr',
            'date': 'Auftragsdatum',
            'client_id': 'KundenNr',
            'name': 'Nachname_Firmenname',
            'name_add': 'Namenszusatz',
            'address': 'Strasse',
            'plz': 'PLZ',
            'city': 'Ort',
            'art_nr': 'P_ArtikelNr',
            'art_name': 'P_Artikeltext',
            'qty': 'P_Anzahl',
            'order_total': 'SummeNetto'  # <-- ОБЩАЯ СУММА ЗАКАЗА (нетто)
        }

    def clean_id(self, val):
        """Очистка ID (ваша версия + защита от точек)"""
        if pd.isna(val): return ""
        s = str(val).strip()
        if s.endswith('.0'): s = s[:-2]
        return s.replace('.', '').replace(',', '').replace(' ', '').replace('\xa0', '')

    def clean_str(self, val):
        if pd.isna(val): return ""
        return str(val).replace('\xa0', '').strip()

    def clean_money(self, val):
        """Парсинг денег (1.200,50 -> 1200.50, 1 680.00 -> 1680.00)"""
        if pd.isna(val): return 0.0
        s = str(val).strip()
        # Убираем валюту и все виды пробелов (обычные и неразрывные \xa0)
        s = s.replace('€', '').replace('EUR', '').replace(' ', '').replace('\xa0', '').strip()
        # Убираем разделитель тысяч (точка) и меняем запятую на точку
        s = s.replace('.', '').replace(',', '.')
        try:
            return float(s)
        except ValueError as e:
            logger.warning(f"Could not parse money value: '{val}' -> '{s}': {e}")
            return 0.0

    def is_file_ready(self):
        try:
            if not self.csv_path.exists(): return False
            current_size = self.csv_path.stat().st_size
            current_time = time.time()
            if self.file_size is None or self.file_size != current_size:
                self.file_size = current_size
                self.file_stable_since = current_time
                return False
            return (current_time - self.file_stable_since) >= 3.0
        except: return False

    def scan(self):
        if self.csv_path.exists() and self.is_file_ready():
            if self.process_csv():
                self.archive_file()
                self.file_size = None

    def archive_file(self):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = self.archive_dir / f"export_{timestamp}.csv"

            # Используем копирование вместо move для избежания блокировки
            shutil.copy2(self.csv_path, target_path)

            # Ждём немного и пробуем удалить оригинал
            time.sleep(0.5)
            try:
                os.remove(self.csv_path)
                logger.info(f"File archived and removed: {target_path.name}")
            except Exception as e:
                # Если не удалось удалить - не критично, архив создан
                logger.warning(f"Could not remove source file (may be locked): {e}")
        except Exception as e:
            logger.error(f"Archive error: {e}")

    def update_order_if_changed(self, order_id, new_order_data):
        try:
            current_order = self.db.get_order(order_id)
            if not current_order: return False

            # Проверяем старый формат или плоский
            current_data = current_order.get('data', current_order)
            current_artikel = current_data.get('artikel', [])
            new_artikel = new_order_data.get('artikel', [])

            changes_detected = False
            updates = {}

            # 1. ПРОВЕРКА СУММЫ (НОВОЕ)
            # Безопасное преобразование с обработкой строк с пробелами
            old_val = current_data.get('total_value', 0)
            if isinstance(old_val, str):
                old_sum = self.clean_money(old_val)
            else:
                old_sum = float(old_val)

            new_sum = float(new_order_data.get('total_value', 0))

            if abs(old_sum - new_sum) > 0.01:
                # Сумма изменилась -> обновляем её и пересчитываем маршрут
                updates['total_value'] = new_sum

                # Пересчёт маршрута с новой суммой (НО НЕ ТРОГАЕМ даты если установлены вручную)
                kunden_nr = current_data.get('kunden_nr', '')
                order_date = current_data.get('date', '')
                if kunden_nr and order_date:
                    logistics = self.logistics_manager.calculate_dates(order_date, kunden_nr, order_value=new_sum)
                    updates['route_id'] = logistics.get('route_id')
                    updates['route_name'] = logistics.get('route_name')
                    if not current_data.get('is_manual_date'):
                        updates['delivery_date'] = logistics.get('delivery_date')
                        updates['production_date'] = logistics.get('production_date')
                    else:
                        logger.info(f"Order {order_id}: keeping manual date {current_data.get('delivery_date')} (is_manual_date=True)")
                    logger.info(f"Order {order_id}: sum changed {old_sum}€ → {new_sum}€, route recalculated → {logistics.get('route_id')}")

                changes_detected = True

            # 2. ПРОВЕРКА АРТИКУЛОВ
            cur_map = {self.clean_id(a.get('artikel_nr')): float(a.get('menge', 0)) for a in current_artikel}
            new_map = {self.clean_id(a.get('artikel_nr')): float(a.get('menge', 0)) for a in new_artikel}

            if cur_map != new_map:
                changes_detected = True
                updated_artikel = []
                for n_art in new_artikel:
                    n_nr = self.clean_id(n_art.get('artikel_nr'))
                    existing = next((a for a in current_artikel if self.clean_id(a.get('artikel_nr')) == n_nr), None)
                    if existing:
                        upd = existing.copy()
                        upd['menge'] = n_art['menge']
                        if float(upd.get('picked', 0)) > upd['menge']: upd['picked'] = upd['menge']
                        upd['checked'] = (float(upd.get('picked', 0)) >= upd['menge'])
                        updated_artikel.append(upd)
                    else:
                        updated_artikel.append(n_art)
                
                updates['artikel'] = updated_artikel

            if changes_detected:
                self.db.update_order(order_id, updates)
                if self.sessions:
                    import asyncio
                    asyncio.create_task(self.sessions.broadcast_to_all({
                        'type': 'order_updated',
                        'order_id': order_id,
                        'update': updates
                    }))
                return True
            return False
        except Exception as e:
            logger.error(f"Update error {order_id}: {e}")
            return False

    def broadcast_sync_status(self, status: str, current: int = 0, total: int = 0, message: str = ""):
        """Отправка статуса синхронизации всем клиентам"""
        if not self.sessions:
            return
        try:
            import asyncio
            msg = {
                'type': f'sync_{status}',  # sync_start, sync_progress, sync_complete, sync_error
                'current': current,
                'total': total,
                'message': message
            }
            asyncio.create_task(self.sessions.broadcast_to_all(msg))
        except Exception as e:
            logger.warning(f"Failed to broadcast sync status: {e}")

    def process_csv(self):
        try:
            try:
                df = pd.read_csv(self.csv_path, sep=';', encoding='latin1', dtype=str)
            except:
                df = pd.read_csv(self.csv_path, sep=';', encoding='utf-8-sig', dtype=str)

            df.columns = df.columns.str.strip()
            col_id = self.col_map['order_id']
            groups = df.dropna(subset=[col_id]).groupby(col_id)
            total_orders = len(groups)
            new_count = 0
            processed = 0

            # Отправляем начало синхронизации
            self.broadcast_sync_status('start', 0, total_orders, f"Загрузка {total_orders} заказов...")
            logger.info(f"[SYNC] Starting CSV import: {total_orders} orders")

            for order_nr_raw, group in groups:
                # Очистка ID
                order_nr = self.clean_id(order_nr_raw)
                if not order_nr: continue
                full_order_id = f"AB-{order_nr}"

                head = group.iloc[0]
                k_nr = self.clean_id(head.get(self.col_map['client_id']))
                k_name = f"{self.clean_str(head.get(self.col_map['name']))} {self.clean_str(head.get(self.col_map['name_add']))}".strip()
                addr = f"{self.clean_str(head.get(self.col_map['address']))}, {self.clean_str(head.get(self.col_map['plz']))} {self.clean_str(head.get(self.col_map['city']))}".strip(', ')

                try:
                    raw_d = self.clean_str(head.get(self.col_map['date'])).split(' ')[0]
                    order_date = datetime.strptime(raw_d, "%d.%m.%Y").strftime("%Y-%m-%d")
                except: order_date = datetime.now().strftime("%Y-%m-%d")

                # --- РАСЧЕТ СУММЫ (ИСПРАВЛЕННОЕ) ---
                # Берем общую сумму из первой строки (SummeNetto одинаково для всего заказа)
                total_value = self.clean_money(head.get(self.col_map['order_total'], 0))
                artikel_list = []

                for idx, row in enumerate(group.to_dict('records'), 1):
                    art_nr = self.clean_id(row.get(self.col_map['art_nr']))
                    if not art_nr: continue

                    # Очищаем количество от пробелов (обычных и неразрывных)
                    qty_str = str(row.get(self.col_map['qty'], '0')).replace(',', '.').replace(' ', '').replace('\xa0', '')
                    qty = float(qty_str)

                    if qty > 0:
                        name = self.clean_str(row.get(self.col_map['art_name']))
                        artikel_list.append({
                            'pos': idx, 'artikel_nr': art_nr, 'nummer': art_nr,
                            'name': name, 'beschreibung': name, 'menge': qty,
                            'picked': 0, 'checked': False
                        })

                if not artikel_list: continue

                # Расчет логистики (передаем сумму для правил выбора маршрута)
                logistics = self.logistics_manager.calculate_dates(order_date, k_nr, order_value=total_value)

                order_data = {
                    'auftrag_nr': order_nr, 'kunden_nr': k_nr, 'kunde': k_name,
                    'address': addr, 'date': order_date,
                    'total_value': round(total_value, 2), # <-- Записываем сумму
                    'delivery_date': logistics['delivery_date'],
                    'production_date': logistics['production_date'],
                    'route_id': logistics['route_id'], 'route_name': logistics['route_name'],
                    'artikel': artikel_list, 'status': 'pending', 'printed': False,
                    'is_auftrag': True, 'warehouse_id': '1', 'boxes_count': 0
                }

                if self.db.order_exists(full_order_id, order_data=order_data):
                    self.update_order_if_changed(full_order_id, order_data)
                else:
                    self.callback(order_data)
                    new_count += 1
                    logger.info(f"Imported: {full_order_id} (€{total_value})")

                # Обновляем прогресс каждые 5 заказов или в конце
                processed += 1
                if processed % 5 == 0 or processed == total_orders:
                    self.broadcast_sync_status('progress', processed, total_orders,
                                               f"Обработано {processed}/{total_orders}")

            # Отправляем завершение синхронизации
            self.broadcast_sync_status('complete', total_orders, total_orders,
                                       f"Загружено {new_count} новых заказов")
            logger.info(f"[SYNC] CSV import complete: {new_count} new, {processed} total")

            if new_count > 0:
                logger.info(f"Batch finished: {new_count} new orders.")
            return True
        except Exception as e:
            # Отправляем ошибку синхронизации
            self.broadcast_sync_status('error', 0, 0, str(e))
            logger.error(f"[SYNC] CSV error: {e}", exc_info=True)
            return False