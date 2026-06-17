#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monolith API Order Monitor
Загружает заказы из API Monolith (CSV формат) и импортирует в систему.
Мониторинг каждые 10 минут.
"""

import asyncio
import logging
import io
import csv
import re
import time
import ssl
import tempfile
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

# URL API для получения заказов (CSV формат, разделитель ;)
API_URL = "https://api.monolith-gruppe.de/api/ZolotojKolos/getAllOrders/5/csv"

# Интервал опроса в секундах (10 минут)
POLL_INTERVAL = 600


class ApiOrderMonitor:
    """
    Мониторинг заказов через API Monolith.

    Паттерн аналогичен WisoCSVMonitor:
    - __init__(db, logistics_manager, callback, sessions)
    - scan() вызывается в async loop
    - callback(order_data) для каждого нового заказа
    """

    def __init__(self, db, logistics_manager, callback, sessions=None):
        self.db = db
        self.logistics_manager = logistics_manager
        self.callback = callback  # server.on_new_api_order
        self.sessions = sessions

        self.api_url = API_URL
        self.last_fetch_time = None
        self.poll_interval = POLL_INTERVAL

        # Кэши (обновляются при каждом scan)
        self._monolith_client_cache = {}   # {monolith_id: wiso_client_id}
        self._client_info_cache = {}       # {monolith_id: {client_id, client_name, address, ...}}
        self._client_names_cache = {}      # {normalized_name: client_id} для поиска по имени
        self._article_mapping_cache = {}   # {monolith_art_nr: {wiso_nr, unit_price}}
        self._recipe_price_cache = {}      # {wiso_art_nr: unit_price}

    # ============================================
    # ОСНОВНОЙ ЦИКЛ
    # ============================================

    def scan(self):
        """Вызывается периодически. Проверяет интервал, загружает данные."""
        now = time.time()
        if self.last_fetch_time and (now - self.last_fetch_time) < self.poll_interval:
            return

        try:
            self._refresh_caches()
            csv_data = self._fetch_api()
            if csv_data:
                self._process_csv(csv_data)
            self.last_fetch_time = time.time()
        except Exception as e:
            logger.error(f"[API_MONITOR] Ошибка сканирования: {e}", exc_info=True)
            self.broadcast_sync_status('error', 0, 0, str(e))
            self.last_fetch_time = time.time()  # Не спамим при ошибках

    # ============================================
    # ЗАГРУЗКА ДАННЫХ
    # ============================================

    def _describe_remote_cert_window(self) -> str:
        """Return short certificate validity window for API host (best-effort)."""
        try:
            host = self.api_url.split('/')[2]
            pem = ssl.get_server_certificate((host, 443))
            fd, cert_path = tempfile.mkstemp(suffix='.pem')
            os.close(fd)
            try:
                with open(cert_path, 'w', encoding='ascii') as f:
                    f.write(pem)
                info = ssl._ssl._test_decode_cert(cert_path)
                not_before = str(info.get('notBefore') or '?')
                not_after = str(info.get('notAfter') or '?')
                return f"TLS cert window: notBefore={not_before}, notAfter={not_after}"
            finally:
                try:
                    os.remove(cert_path)
                except Exception:
                    pass
        except Exception:
            return "TLS cert window: unknown"

    def _fetch_api(self) -> Optional[str]:
        """Загрузка CSV из API Monolith через HTTP GET."""
        try:
            req = Request(self.api_url, headers={'User-Agent': 'WisoGoLabel/1.0'})
            with urlopen(req, timeout=30) as response:
                raw = response.read()
                # Пробуем UTF-8, потом latin1
                for enc in ('utf-8', 'latin1'):
                    try:
                        data = raw.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    data = raw.decode('utf-8', errors='replace')

                logger.info(f"[API_MONITOR] Загружено {len(data)} байт из API")
                return data
        except (URLError, HTTPError) as e:
            reason = getattr(e, 'reason', e)
            if isinstance(reason, ssl.SSLCertVerificationError):
                cert_diag = self._describe_remote_cert_window()
                logger.error(
                    f"[API_MONITOR] Ошибка HTTP (SSL certificate verify): {reason}. {cert_diag}. "
                    f"С высокой вероятностью проблема на стороне сертификата API-сервера."
                )
                return None
            logger.error(f"[API_MONITOR] Ошибка HTTP: {e}")
            return None
        except ssl.SSLCertVerificationError as e:
            cert_diag = self._describe_remote_cert_window()
            logger.error(
                f"[API_MONITOR] SSL verify failed: {e}. {cert_diag}. "
                f"С высокой вероятностью проблема на стороне сертификата API-сервера."
            )
            return None
        except Exception as e:
            logger.error(f"[API_MONITOR] Ошибка загрузки: {e}")
            return None

    # ============================================
    # КЭШИРОВАНИЕ МАППИНГОВ
    # ============================================

    def _refresh_caches(self):
        """Загрузка таблиц маппингов из БД в память."""
        with self.db.safe_connection() as conn:
            cursor = conn.cursor()

            # 1. Маппинг клиентов: monolith_client_id -> wiso client_id
            try:
                cursor.execute("""
                    SELECT monolith_client_id, client_id, client_name, address, plz, city
                    FROM client_routes
                    WHERE monolith_client_id IS NOT NULL AND monolith_client_id != ''
                """)
                self._monolith_client_cache = {}
                self._client_info_cache = {}
                for row in cursor.fetchall():
                    m_id = str(row['monolith_client_id']).strip()
                    self._monolith_client_cache[m_id] = row['client_id']
                    self._client_info_cache[m_id] = {
                        'client_id': row['client_id'],
                        'client_name': row['client_name'] or '',
                        'address': row['address'] or '',
                        'plz': row['plz'] or '',
                        'city': row['city'] or '',
                    }
            except Exception as e:
                logger.warning(f"[API_MONITOR] Ошибка загрузки кэша клиентов: {e}")

            # 2. Все клиенты по нормализованному имени (для автоматического сопоставления)
            try:
                cursor.execute("SELECT client_id, client_name FROM client_routes")
                self._client_names_cache = {}
                for row in cursor.fetchall():
                    name = row['client_name'] or ''
                    normalized = self._normalize_store_name(name)
                    if normalized:
                        self._client_names_cache[normalized] = row['client_id']
            except Exception as e:
                logger.warning(f"[API_MONITOR] Ошибка загрузки кэша имён: {e}")

            # 3. Маппинг артикулов: monolith_art_nr -> {wiso_nr, unit_price}
            try:
                cursor.execute("SELECT monolith_article_nr, wiso_article_nr, unit_price FROM article_mapping")
                self._article_mapping_cache = {
                    row['monolith_article_nr']: {
                        'wiso_nr': row['wiso_article_nr'],
                        'unit_price': float(row['unit_price'] or 0.0)
                    } for row in cursor.fetchall()
                }
            except Exception as e:
                logger.warning(f"[API_MONITOR] Ошибка загрузки маппинга артикулов: {e}")

            # 4. Цены из рецептов (fallback)
            try:
                cursor.execute("SELECT article_nr, unit_price FROM recipes WHERE unit_price > 0")
                self._recipe_price_cache = {
                    row['article_nr']: float(row['unit_price']) for row in cursor.fetchall()
                }
            except Exception as e:
                logger.warning(f"[API_MONITOR] Ошибка загрузки цен рецептов: {e}")
        logger.debug(f"[API_MONITOR] Кэш: {len(self._monolith_client_cache)} клиентов, "
                      f"{len(self._article_mapping_cache)} артикулов, "
                      f"{len(self._recipe_price_cache)} цен")

    # ============================================
    # ОБРАБОТКА CSV
    # ============================================

    def _process_csv(self, csv_data: str):
        """Парсинг CSV из API и создание заказов."""
        reader = csv.DictReader(io.StringIO(csv_data), delimiter=';')

        # Группируем строки по order_id
        orders_grouped: Dict[str, List[dict]] = {}
        for row in reader:
            oid = row.get('order_id', '').strip()
            if oid:
                orders_grouped.setdefault(oid, []).append(row)

        total_orders = len(orders_grouped)
        new_count = 0
        processed = 0

        self.broadcast_sync_status('start', 0, total_orders,
                                    f"API: Загрузка {total_orders} заказов...")
        logger.info(f"[API_MONITOR] Начало обработки: {total_orders} заказов")

        for order_id_raw, rows in orders_grouped.items():
            full_order_id = f"MO-{order_id_raw}"

            head = rows[0]
            monolith_client_id = head.get('customer_id', '').strip()
            customer_name = head.get('customer_name', '').strip()

            # Сборка списка артикулов и расчёт суммы (нужно ДО проверки дубликатов)
            artikel_list, total_value = self._build_artikel_list(rows)

            if not artikel_list:
                processed += 1
                continue

            # Дедупликация — пропускаем уже существующие (включая кросс-проверку AB↔MO)
            preliminary_data = {'kunde': customer_name, 'artikel': artikel_list}
            if self.db.order_exists(full_order_id, order_data=preliminary_data):
                processed += 1
                continue

            # Поиск WISO клиента
            wiso_client_id, client_info = self._resolve_client(monolith_client_id, customer_name)

            # Парсинг даты (YYYY-MM-DD HH:MM:SS -> YYYY-MM-DD)
            order_date = self._parse_api_date(head.get('order_dt', ''))

            # Адрес из client_routes (в API нет адреса)
            address = ''
            if client_info:
                addr_parts = [
                    client_info.get('address', ''),
                    client_info.get('plz', ''),
                    client_info.get('city', '')
                ]
                address = ', '.join(p for p in addr_parts if p).strip(', ')

            # Расчёт логистики (используем wiso_client_id для поиска маршрута)
            lookup_client = wiso_client_id if wiso_client_id else monolith_client_id
            logistics = self.logistics_manager.calculate_dates(
                order_date, lookup_client, order_value=total_value
            )

            # Формируем order_data (та же структура что и WisoCSVMonitor)
            order_data = {
                'auftrag_nr': order_id_raw,
                'kunden_nr': wiso_client_id or monolith_client_id,
                'monolith_client_id': monolith_client_id,
                'kunde': customer_name,
                'address': address,
                'date': order_date,
                'total_value': round(total_value, 2),
                'delivery_date': logistics['delivery_date'],
                'production_date': logistics['production_date'],
                'route_id': logistics['route_id'],
                'route_name': logistics['route_name'],
                'artikel': artikel_list,
                'status': 'pending',
                'printed': False,
                'is_auftrag': True,
                'is_api_order': True,
                'is_api_new': True,
                'warehouse_id': '1',
                'boxes_count': 0,
                'source': 'monolith_api',
                'unmapped_client': not bool(wiso_client_id),
            }

            self.callback(order_data)
            new_count += 1

            processed += 1
            if processed % 5 == 0 or processed == total_orders:
                self.broadcast_sync_status('progress', processed, total_orders,
                                            f"Обработано {processed}/{total_orders}")

        self.broadcast_sync_status('complete', total_orders, total_orders,
                                    f"Загружено {new_count} новых заказов из API")
        logger.info(f"[API_MONITOR] Завершено: {new_count} новых, {processed} всего")

    # ============================================
    # МАППИНГ КЛИЕНТОВ
    # ============================================

    def _resolve_client(self, monolith_client_id: str, customer_name: str) -> Tuple[str, dict]:
        """
        Поиск WISO клиента по Monolith ID или имени.

        Порядок:
        1. Точный маппинг по monolith_client_id
        2. Поиск по нормализованному имени (Mix Markt 001 vs Mix Markt 01)
        3. Если найден по имени — автоматически сохраняем monolith_client_id

        Returns: (wiso_client_id, client_info_dict) или ('', {})
        """
        # 1. Точный маппинг
        wiso_id = self._monolith_client_cache.get(monolith_client_id, '')
        if wiso_id:
            return wiso_id, self._client_info_cache.get(monolith_client_id, {})

        # 2. Поиск по нормализованному имени
        normalized_api_name = self._normalize_store_name(customer_name)
        if normalized_api_name:
            found_client_id = self._client_names_cache.get(normalized_api_name, '')
            if found_client_id:
                # Автосохранение маппинга для будущих быстрых поисков
                self._auto_save_monolith_mapping(found_client_id, monolith_client_id, customer_name)
                logger.info(f"[API_MONITOR] Автоматическое сопоставление: "
                           f"Monolith '{customer_name}' (ID:{monolith_client_id}) -> WISO {found_client_id}")
                return found_client_id, {}

        # 3. Не найден
        logger.warning(f"[API_MONITOR] Клиент не найден: '{customer_name}' (Monolith ID: {monolith_client_id})")
        return '', {}

    def _normalize_store_name(self, name: str) -> str:
        """
        Нормализация имён магазинов для сопоставления.

        Примеры:
        - 'Mix Markt 001' -> 'mix markt 1'
        - 'Mix Markt 01'  -> 'mix markt 1'
        - 'Prima Markt 10, Inh. Alex Jurgen Bayer' -> 'prima markt 10'
        """
        if not name:
            return ''
        name = name.lower().strip()
        # Убираем всё после запятой (часто это "Inh. ...")
        if ',' in name:
            name = name.split(',')[0].strip()
        # Убираем ведущие нули из номеров: 001 -> 1, 01 -> 1
        name = re.sub(r'\b0+(\d+)', r'\1', name)
        # Нормализуем пробелы
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _auto_save_monolith_mapping(self, wiso_client_id: str, monolith_client_id: str, customer_name: str):
        """Автоматическое сохранение маппинга monolith_client_id в БД."""
        try:
            with self.db.safe_connection() as conn:
                conn.execute(
                    "UPDATE client_routes SET monolith_client_id = ?, updated_at = ? WHERE client_id = ?",
                    (monolith_client_id, datetime.now().isoformat(), wiso_client_id)
                )
                conn.commit()

            # Обновляем кэш
            self._monolith_client_cache[monolith_client_id] = wiso_client_id
            self._client_info_cache[monolith_client_id] = {
                'client_id': wiso_client_id,
                'client_name': customer_name,
                'address': '', 'plz': '', 'city': ''
            }
        except Exception as e:
            logger.error(f"[API_MONITOR] Ошибка автосохранения маппинга: {e}")

    # ============================================
    # МАППИНГ АРТИКУЛОВ + РАСЧЁТ ЦЕНЫ
    # ============================================

    def _build_artikel_list(self, rows: List[dict]) -> Tuple[list, float]:
        """
        Сборка списка артикулов из строк API.
        Маппинг номеров Monolith -> WISO.
        Расчёт total_value из unit_price * quantity.

        Returns: (artikel_list, total_value)
        """
        artikel_list = []
        total_value = 0.0

        for idx, row in enumerate(rows, 1):
            monolith_nr = row.get('item_nr', '').strip()
            if not monolith_nr:
                continue

            # Парсинг количества
            qty_str = row.get('quantity', '0').strip().replace(',', '.')
            try:
                qty = float(qty_str)
            except ValueError:
                qty = 0.0

            if qty <= 0:
                continue

            api_name = row.get('item_name', '').strip()
            unit = row.get('unit', '').strip()

            # Маппинг номера артикула
            mapping = self._article_mapping_cache.get(monolith_nr)
            if mapping:
                wiso_nr = mapping['wiso_nr']
                unit_price = mapping['unit_price']
            else:
                # Нет маппинга: используем номер Monolith как есть (с padding до 5 цифр)
                wiso_nr = monolith_nr.zfill(5) if monolith_nr.isdigit() else monolith_nr
                unit_price = 0.0

            # Fallback: цена из таблицы рецептов
            if unit_price <= 0:
                unit_price = self._recipe_price_cache.get(wiso_nr, 0.0)

            line_total = unit_price * qty
            total_value += line_total

            artikel_list.append({
                'pos': idx,
                'artikel_nr': wiso_nr,
                'nummer': wiso_nr,
                'monolith_artikel_nr': monolith_nr,
                'name': api_name,
                'beschreibung': api_name,
                'menge': qty,
                'einheit': unit,
                'unit_price': round(unit_price, 2),
                'picked': 0,
                'checked': False,
            })

        return artikel_list, round(total_value, 2)

    # ============================================
    # УТИЛИТЫ
    # ============================================

    def _parse_api_date(self, date_str: str) -> str:
        """Парсинг 'YYYY-MM-DD HH:MM:SS' -> 'YYYY-MM-DD'."""
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return datetime.now().strftime("%Y-%m-%d")

    def broadcast_sync_status(self, status: str, current: int = 0, total: int = 0, message: str = ""):
        """Отправка статуса синхронизации всем клиентам.
        ВАЖНО: вызывается из executor-треда, поэтому используем сохранённый _event_loop.
        """
        if not self.sessions:
            return
        try:
            msg = {
                'type': f'api_sync_{status}',
                'current': current,
                'total': total,
                'message': message
            }
            loop = getattr(self, '_event_loop', None)
            if loop:
                loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self.sessions.broadcast_to_all(msg)
                )
        except Exception as e:
            logger.warning(f"[API_MONITOR] Ошибка broadcast: {e}")
