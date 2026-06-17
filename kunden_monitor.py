#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd
import logging
import shutil
import time
import re
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class KundenCSVMonitor:
    def __init__(self, csv_path: Path, db):
        self.csv_path = csv_path
        self.db = db
        self.archive_dir = self.csv_path.parent / "Archive"
        self.archive_dir.mkdir(exist_ok=True)
        
        self.col_map = {
            'id': 'KUNDENNUMMER',
            'name': 'NACHNAMEFIRMA',
            'street': 'STRASSE',
            'plz': 'PLZ',
            'city': 'ORT'
        }

    def clean_val(self, val):
        if pd.isna(val) or str(val).lower() == 'nan': return ""
        return str(val).replace('\xa0', ' ').strip()

    def clean_id(self, val):
        """Удаляет всё, кроме цифр (чтобы '10 811' стало '10811')"""
        if pd.isna(val): return ""
        return re.sub(r'\D', '', str(val))

    def get_smart_logic(self, plz, name, street):
        """Определяет параметры для интерфейса"""
        plz = str(plz).split('.')[0].strip().zfill(5)
        name_str = str(name).lower()
        street_str = str(street).lower()
        
        # Точные строки для вашей программы
        POINT_SHOP = "Geschäft (Магазин)"
        POINT_WH = "Lager (Склад)"
        TRANS_AUTO = "Eigenes Auto"
        TRANS_SPED = "Spedition"

        point_type = POINT_SHOP
        transport = TRANS_AUTO
        
        # Ключевые слова для определения склада
        wh_keywords = ['lager', 'zentrallager', 'logistik', 'sw-log', 'monolith', 'distribution', 'hub']
        
        # Исправлено: корректное использование переменной kw
        if any(kw in name_str for kw in wh_keywords) or any(kw in street_str for kw in wh_keywords):
            point_type = POINT_WH
            transport = TRANS_SPED

        # Определение маршрута
        route_id = "free"
        if plz and plz != "00nan":
            p1 = plz[0]
            p2 = plz[:2]
            if p2 in ['98', '99'] or p1 in ['0', '1'] or plz.startswith('06'):
                route_id = "ost"
            elif p1 in ['2', '3']:
                # Бельгия (4 знака на 2)
                if len(plz.lstrip('0')) == 4 and p1 == '2':
                    route_id = "west"
                else:
                    route_id = "op_n-nord"
            elif p1 == '4': route_id = "op_w-nord"
            elif p1 == '5': route_id = "op_w-west"
            elif p1 in ['6', '7', '8']: route_id = "op_süd"
            elif p1 == '9': route_id = "süd"

        return route_id, point_type, transport

    def process_csv(self):
        try:
            # Чтение файла
            try:
                df = pd.read_csv(self.csv_path, sep=';', encoding='latin1', dtype=str)
            except:
                df = pd.read_csv(self.csv_path, sep=';', encoding='utf-8-sig', dtype=str)

            df.columns = df.columns.str.strip().str.upper()
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()

                # --- ШАГ 1: Запоминаем существующих клиентов ---
                cursor.execute("SELECT client_id FROM client_routes")
                existing_ids = {row[0] for row in cursor.fetchall()}
                logger.info(f"Существующих клиентов: {len(existing_ids)}")

                # --- ШАГ 2: ПОЛНАЯ ОЧИСТКА ---
                logger.info("Удаление всех записей для полной перезагрузки базы клиентов...")
                cursor.execute("DELETE FROM client_routes")

                inserted = 0
                new_count = 0
                now = datetime.now().isoformat()

                # --- ШАГ 3: ЗАГРУЗКА с пометкой NEW ---
                for _, row in df.iterrows():
                    client_id = self.clean_id(row.get(self.col_map['id']))
                    if not client_id: continue

                    name = self.clean_val(row.get(self.col_map['name']))
                    street = self.clean_val(row.get(self.col_map['street']))
                    plz = self.clean_val(row.get(self.col_map['plz']))
                    city = self.clean_val(row.get(self.col_map['city']))

                    route_id, point_type, transport = self.get_smart_logic(plz, name, street)

                    # Определяем: это новый клиент или существовавший?
                    is_new = 1 if client_id not in existing_ids else 0
                    if is_new:
                        new_count += 1

                    # Выполнение вставки
                    cursor.execute("""
                        INSERT INTO client_routes
                        (client_id, client_name, route_id, address, plz, city, transport_type, delivery_point, is_new, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (client_id, name, route_id, street, plz, city, transport, point_type, is_new, now))

                    inserted += 1

                conn.commit()
                logger.info(f"УСПЕХ! База перезагружена. Клиентов: {inserted}, НОВЫХ: {new_count}")
            return True
        except Exception as e:
            logger.error(f"Ошибка в процессе обработки: {e}", exc_info=True)
            return False

    def scan(self):
        if not self.csv_path.exists(): return
        time.sleep(1)
        if self.process_csv():
            self.archive_file()

    def archive_file(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.archive_dir / f"kunden_final_sync_{ts}.csv"
        shutil.move(self.csv_path, target)