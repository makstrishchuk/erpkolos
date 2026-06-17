#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import math
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class ProductionPlanner:
    def __init__(self, database, resource_manager, stock_manager):
        self.db = database
        self.resource_manager = resource_manager
        self.stock_manager = stock_manager
        logger.info("ProductionPlanner initialized")

    def calculate_minutes_needed(self, article_nr: str, qty: float, recipes: dict,
                                components_db: dict, extra_resources: dict) -> dict:
        """Расчет загрузки ресурсов"""
        load_map = {}
        clean_nr = str(article_nr).strip().zfill(5) if str(article_nr).isdigit() else str(article_nr)

        if clean_nr not in recipes or qty <= 0: return load_map

        rec = recipes[clean_nr]
        dough_id = rec.get('dough_id')

        # 1. ТЕСТО
        if dough_id and dough_id in components_db:
            comp = components_db[dough_id]
            items_tray = float(rec.get('items_per_tray') or 1.0)
            batch_size = float(comp.get('batch_size') or 1.0)
            time_per = float(comp.get('production_time_min') or 0.0)
            res_id = comp.get('resource_id')
            
            per_batch = items_tray * batch_size
            if per_batch > 0 and time_per > 0:
                batches = math.ceil(qty / per_batch)
                if res_id: load_map[res_id] = load_map.get(res_id, 0) + (batches * time_per)

        # 2. ДОП РЕСУРСЫ
        if clean_nr in extra_resources:
            for rid, t in extra_resources[clean_nr].items():
                load_map[rid] = load_map.get(rid, 0) + (qty * t)
        
        return load_map

    def get_production_date(self, delivery_date, workdays_indices: list):
        """Определяет дату производства, пропуская выходные назад"""
        prod_date = delivery_date - timedelta(days=1)
        if not workdays_indices: return prod_date
        
        for _ in range(14):
            if prod_date.weekday() in workdays_indices: return prod_date
            prod_date -= timedelta(days=1)
            
        return delivery_date - timedelta(days=1)

    def sync_picking_to_facts(self, conn, date_str: str):
        """Синхронизация факта со склада"""
        try:
            conn.execute("DROP TABLE IF EXISTS temp_picking_stats")
            conn.execute("""
                CREATE TEMP TABLE temp_picking_stats AS
                SELECT
                    CASE WHEN length(op.artikel_nr) < 5 THEN printf('%05d', op.artikel_nr) ELSE op.artikel_nr END as clean_art,
                    SUM(op.picked_qty) as picked_total
                FROM order_picking op
                JOIN orders o ON op.order_id = o.order_id
                WHERE op.picked_qty > 0 
                AND COALESCE(o.production_date, date(o.delivery_date, '-1 day')) = ?
                GROUP BY clean_art
            """, (date_str,))

            conn.execute("""
                INSERT INTO production_facts (date, article_nr, fact_qty)
                SELECT ?, clean_art, picked_total FROM temp_picking_stats WHERE picked_total > 0
                ON CONFLICT(date, article_nr) DO UPDATE SET fact_qty = MAX(production_facts.fact_qty, excluded.fact_qty)
            """, (date_str,))
            
            conn.execute("DROP TABLE IF EXISTS temp_picking_stats")
            conn.commit()
        except Exception as e:
            print(f"Sync error: {e}")

    def get_historical_sales(self, conn, target_date):
        """
        ПРОГНОЗ ПО НОМЕРУ НЕДЕЛИ (Год назад)
        Возвращает: {article_nr: avg_daily_quantity}
        """
        # 1. Вычисляем текущую неделю
        curr_year, curr_week, _ = target_date.isocalendar()
        
        # 2. Ищем данные за ту же неделю ПРОШЛОГО года
        # (Если сейчас 1-я неделя 2026, ищем 1-ю неделю 2025)
        # Если такой нет, можно поискать соседние (сглаживание)
        
        last_year = curr_year - 1
        
        cursor = conn.cursor()
        
        # Проверяем, есть ли таблица (создастся при первом импорте, но на всякий случай)
        try:
            cursor.execute("SELECT article_nr, quantity FROM weekly_sales_history WHERE year=? AND week=?", (last_year, curr_week))
            rows = cursor.fetchall()
        except:
            return {} # Таблицы нет или пусто

        history = {}
        
        # Количество рабочих дней для деления недельного объема
        # (Можно брать из настроек, но 5 - стандарт для прогноза)
        work_days_count = 5 
        
        for row in rows:
            art = str(row[0]).strip().zfill(5)
            weekly_qty = float(row[1])
            
            # Если в прошлом году был возврат (-8 штук), прогноз = 0
            if weekly_qty < 0: weekly_qty = 0
            
            # Превращаем недельный объем в дневной (усредняем)
            daily_avg = weekly_qty / work_days_count
            
            history[art] = daily_avg
            
        return history

    def calculate_daily_plan(self, conn, target_date, context=None, skip_weekend_shift=False):
        """
        ДНЕВНОЙ ПЛАН v10 - Синхронизирован с недельным планом.
        Рассчитывает недельный план, затем возвращает данные для конкретного дня.
        """
        target_str = target_date.strftime('%Y-%m-%d')
        self.sync_picking_to_facts(conn, target_str)
        cursor = conn.cursor()

        # --- 1. ЗАГРУЗКА ДАННЫХ ---
        workdays = context.get('workdays') if context else None

        if context and 'recipes' in context:
            recipes = context['recipes']
            all_orders = context['all_orders']
            resources_map = context['resources_map']
            components_db = context['components_db']
            extra_resources = context.get('extra_resources', {})
        else:
            if not workdays:
                try:
                    cursor.execute("SELECT setting_value FROM plan_settings WHERE setting_key='workdays' AND user_id IS NULL")
                    row = cursor.fetchone()
                    workdays = json.loads(row[0]) if row else ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
                except:
                    workdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']

            cursor.execute("SELECT * FROM factory_resources")
            resources_map = {r['resource_id']: dict(r) for r in cursor.fetchall()}
            cursor.execute("SELECT * FROM dough_types")
            components_db = {r['dough_id']: dict(r) for r in cursor.fetchall()}
            recipes = {}
            cursor.execute("SELECT * FROM recipes WHERE active=1")
            for r in cursor.fetchall():
                recipes[str(r['article_nr']).strip().zfill(5)] = dict(r)
            all_orders = self.db.get_all_orders()
            extra_resources = {}
            try:
                cursor.execute("SELECT article_nr, resource_id, time_needed_min FROM product_resource_consumption")
                for row in cursor.fetchall():
                    an = str(row['article_nr']).strip().zfill(5)
                    rid = row['resource_id']
                    if an not in extra_resources:
                        extra_resources[an] = {}
                    extra_resources[an][rid] = float(row['time_needed_min'])
            except:
                pass

        day_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
        work_indices = [day_map[d] for d in workdays if d in day_map]
        num_workdays = len(work_indices) or 5

        empty_res = {'production_items': [], 'totals': {'cakes': 0, 'batches': 0}, 'dough_summary': [], 'resource_load': [], 'bottlenecks': [], 'stock_info': {}, 'simulation_start': target_str}

        # Проверяем что день рабочий
        if target_date.weekday() not in work_indices:
            return empty_res

        # --- 2. ОПРЕДЕЛЯЕМ ПОНЕДЕЛЬНИК НЕДЕЛИ ---
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)
        target_day_idx = target_date.weekday()

        # --- 3. ЗАГРУЖАЕМ ПРОГНОЗ НА НЕДЕЛЮ ---
        curr_year, curr_week, _ = target_date.isocalendar()
        last_year = curr_year - 1
        weekly_forecast = {}
        try:
            cursor.execute("SELECT article_nr, quantity FROM weekly_sales_history WHERE year=? AND week=?", (last_year, curr_week))
            for row in cursor.fetchall():
                art = str(row['article_nr']).strip().zfill(5)
                qty = float(row['quantity']) if row['quantity'] and row['quantity'] > 0 else 0
                weekly_forecast[art] = int(qty)  # Чистый прогноз (буфер +10% в формуле)
        except:
            pass

        # --- 4. СОБИРАЕМ ВСЕ ЗАКАЗЫ НА НЕДЕЛЮ ---
        weekly_orders = {}
        for order in all_orders:
            d_str = order.get('delivery_date')
            if not d_str:
                continue
            try:
                d_date = datetime.strptime(d_str, "%Y-%m-%d").date()
            except:
                continue
            if week_start <= d_date <= week_end + timedelta(days=1):
                for art in order.get('artikel', []):
                    an = str(art.get('artikel_nr') or art.get('nummer', '')).strip().zfill(5)
                    if an not in recipes:
                        continue
                    qty = float(art.get('menge', 0))
                    if qty > 0:
                        weekly_orders[an] = weekly_orders.get(an, 0) + qty

        # --- 5. ЗАГРУЖАЕМ ТЕКУЩИЕ ОСТАТКИ ---
        current_stock = {}
        if context and 'simulated_stocks' in context:
            # Недельный план передаёт симулированные остатки — используем их
            current_stock = context['simulated_stocks'].copy()
        else:
            try:
                # Для каждого артикула берём самую свежую РУЧНУЮ запись (не System)
                stock_cutoff = week_end.strftime('%Y-%m-%d')
                cursor.execute("""
                    SELECT d.article_nr, d.quantity
                    FROM daily_stock_reports d
                    WHERE d.date = (
                        SELECT MAX(d2.date)
                        FROM daily_stock_reports d2
                        WHERE d2.article_nr = d.article_nr
                        AND d2.date <= ?
                        AND d2.last_editor IS NOT NULL
                        AND d2.last_editor != 'System'
                    )
                """, (stock_cutoff,))
                for row in cursor.fetchall():
                    art = str(row['article_nr']).strip().zfill(5)
                    current_stock[art] = float(row['quantity'])
            except:
                pass

        # --- 6. РАССЧИТЫВАЕМ НЕДЕЛЬНЫЙ ПЛАН И РАСПРЕДЕЛЯЕМ ПО ДНЯМ ---
        plan_by_day = {i: {} for i in range(7)}
        forecast_data = {}
        all_articles = set(weekly_forecast.keys()) | set(weekly_orders.keys())

        def round_to_batch(qty, art_nr):
            recipe = recipes.get(art_nr, {})
            min_batch = int(recipe.get('min_batch_size', 1) or 1)
            if min_batch <= 1:
                return int(qty)
            batches = math.ceil(qty / min_batch)
            return batches * min_batch

        for art in all_articles:
            if art not in recipes:
                continue

            total_orders = weekly_orders.get(art, 0)
            total_forecast = weekly_forecast.get(art, 0)

            # ФОРМУЛА: MAX(прогноз, заказы) * 1.10
            base_need = max(total_forecast, total_orders)
            weekly_need = math.ceil(base_need * 1.10)  # Всегда +10%

            if weekly_need <= 0:
                continue

            # Вычитаем остатки, но добавляем минимальный запас
            stock = current_stock.get(art, 0)
            recipe = recipes.get(art, {})
            min_stock = float(recipe.get('min_stock_level', 0) or 0)

            # Формула: нужно произвести = потребность - остаток + мин.запас
            weekly_to_produce = weekly_need - stock + min_stock

            if weekly_to_produce <= 0:
                continue  # На складе достаточно даже с учетом мин.запаса!

            weekly_to_produce = round_to_batch(weekly_to_produce, art)

            # Сохраняем дневной прогноз для отображения
            forecast_data[art] = int(weekly_to_produce / num_workdays)

            # Равномерное распределение по рабочим дням
            recipe = recipes.get(art, {})
            min_batch = int(recipe.get('min_batch_size', 1) or 1)
            total_batches = math.ceil(weekly_to_produce / min_batch) if min_batch > 0 else weekly_to_produce
            batches_per_day = total_batches // num_workdays
            extra_batches = total_batches % num_workdays

            for idx, day_idx in enumerate(work_indices):
                day_batches = batches_per_day
                if idx < extra_batches:
                    day_batches += 1
                day_qty = day_batches * min_batch
                if day_qty > 0:
                    plan_by_day[day_idx][art] = day_qty

        # --- 7. БЕРЕМ ДАННЫЕ ДЛЯ КОНКРЕТНОГО ДНЯ ---
        demand_mandatory = plan_by_day.get(target_day_idx, {})

        # --- 8. ПОЛУЧАЕМ ФАКТ И СТРОИМ ИТОГИ ---
        cursor.execute("SELECT article_nr, fact_qty FROM production_facts WHERE date=?", (target_str,))
        facts = {row['article_nr']: float(row['fact_qty']) for row in cursor.fetchall()}

        # Получаем остатки для отображения
        def get_display_stock(art):
            if context and 'simulated_stocks' in context:
                return context['simulated_stocks'].get(art, 0.0)
            # Берём самую свежую РУЧНУЮ запись (не System)
            cursor.execute("""
                SELECT quantity FROM daily_stock_reports
                WHERE article_nr = ? AND date = (
                    SELECT MAX(date) FROM daily_stock_reports
                    WHERE article_nr = ? AND date <= ?
                    AND last_editor IS NOT NULL AND last_editor != 'System'
                )
            """, (art, art, target_str))
            r = cursor.fetchone()
            return float(r[0]) if r else 0.0

        # --- 9. СТРОИМ ИТОГОВЫЙ СПИСОК ---
        prod_list = []
        dough_agg = {}
        components_agg = {}
        current_load = {}
        all_ans = set(list(demand_mandatory.keys()) + list(forecast_data.keys()))

        for an in all_ans:
            if an not in recipes: continue
            rec = recipes[an]
            # Пропускаем товары без названия (из истории, но не в текущей базе)
            name = rec.get('name', '')
            if not name or name == 'Unknown':
                continue
            pq = demand_mandatory.get(an, 0)  # План на день = из распределения по дням
            fq = facts.get(an, 0)
            st = get_display_stock(an)
            dem = demand_mandatory.get(an, 0)
            fore = forecast_data.get(an, 0)

            actual = fq if fq > 0 else pq
            surplus = max(0, (st + actual) - dem)

            # Расчет загрузки ресурсов
            if actual > 0:
                load = self.calculate_minutes_needed(an, actual, recipes, components_db, extra_resources)
                for rid, m in load.items():
                    current_load[rid] = current_load.get(rid, 0) + m

            batches = 0
            dname = "-"
            did = rec.get('dough_id')
            if did and did in components_db:
                c = components_db[did]
                dname = c['name']
                pb = float(rec.get('items_per_tray',1)) * float(c.get('batch_size',1))
                if pb > 0 and actual > 0:
                    batches = actual / pb
                    dough_agg[dname] = dough_agg.get(dname, 0) + batches
                    if did not in components_agg:
                        components_agg[did] = {'name': dname, 'type': 'Тесто (Осн)', 'qty_needed': 0, 'unit': 'замес', 'batches': 0.0}
                    components_agg[did]['batches'] += batches

            if actual > 0:
                comp_str = rec.get('composition')
                if comp_str:
                    try:
                        comps = json.loads(comp_str)
                        for comp in comps:
                            c_name = comp.get('component', 'Unknown')
                            c_qty = float(comp.get('quantity', 0))
                            c_unit = comp.get('unit', '')
                            total_qty = actual * c_qty
                            if c_name not in components_agg:
                                components_agg[c_name] = {'name': c_name, 'type': 'Компонент', 'qty_needed': 0.0, 'unit': c_unit, 'batches': 0.0}
                            components_agg[c_name]['qty_needed'] += total_qty
                    except: pass

            prod_list.append({
                'article_nr': an, 'name': rec['name'], 'category': rec.get('category',''),
                'forecast': int(fore),
                'available_stock': int(st), 'net_demand': int(dem), 'quantity': int(pq),
                'fact_qty': int(fq), 'batches': math.ceil(batches), 'surplus': int(surplus),
                'dough_name': dname
            })

        try: conn.commit()
        except: pass

        components_list = []
        for cid, data in components_agg.items():
            if data['batches'] > 0: data['batches'] = math.ceil(data['batches'] * 10) / 10
            components_list.append(data)

        dough_summary = [{'dough_name': k, 'batches': math.ceil(v)} for k,v in dough_agg.items()]

        # Загрузка ресурсов
        res_list = []
        for rid, m in current_load.items():
            if rid not in resources_map: continue
            r = resources_map[rid]
            nominal_cap = r['quantity'] * r['shifts_count'] * r['shift_duration_min']
            pct = (m / nominal_cap * 100) if nominal_cap > 0 else 0
            st = 'normal'
            if pct > 100: st = 'overload'
            res_list.append({
                'resource_name': r['resource_name'], 'planned_load_min': int(m),
                'available_capacity_min': int(nominal_cap), 'utilization_percent': round(pct, 1),
                'status': st, 'status_label': f"{int(pct)}%"
            })

        return {
            'production_items': sorted(prod_list, key=lambda x: x['category']),
            'totals': {'cakes': sum(x['quantity'] for x in prod_list), 'batches': sum(x['batches'] for x in dough_summary)},
            'dough_summary': sorted(dough_summary, key=lambda x: x['dough_name']),
            'components_plan': sorted(components_list, key=lambda x: x['name']),
            'resource_load': sorted(res_list, key=lambda x: x['utilization_percent'], reverse=True),
            'bottlenecks': [], 'recommendations': [], 'stock_info': {}, 'simulation_start': target_str
        }

    def calculate_weekly_plan(self, conn, start_date, context):
        day_keys = ['mo', 'di', 'mi', 'do', 'fr', 'sa', 'so']
        weekly_results = []
        simulated_stocks = {}
        cursor = conn.cursor()
        try:
            # Для каждого артикула берём самую свежую РУЧНУЮ запись (не System)
            stock_cutoff = (start_date - timedelta(days=1)).strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT d.article_nr, d.quantity
                FROM daily_stock_reports d
                WHERE d.date = (
                    SELECT MAX(d2.date)
                    FROM daily_stock_reports d2
                    WHERE d2.article_nr = d.article_nr
                    AND d2.date <= ?
                    AND d2.last_editor IS NOT NULL
                    AND d2.last_editor != 'System'
                )
            """, (stock_cutoff,))
            for row in cursor.fetchall():
                art = str(row[0]).zfill(5)
                simulated_stocks[art] = float(row[1])
        except:
            pass

        for i in range(7):
            current_day = start_date + timedelta(days=i)
            day_key = day_keys[i]
            context['simulated_stocks'] = simulated_stocks.copy()
            day_result = self.calculate_daily_plan(conn, current_day, context=context)
            if day_result.get('production_items'):
                for item in day_result['production_items']:
                    simulated_stocks[item['article_nr']] = item['surplus']
            weekly_results.append((day_key, day_result))
        return weekly_results