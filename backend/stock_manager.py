#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock Manager Module for WISO GoLabel ERP System
Handles virtual stock management for smart production planning
"""

import os
import json
import math
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class VirtualStockManager:
    """
    Управление виртуальными запасами для умного планирования производства
    Отслеживает остатки тортов и теста по дням с автоматическим переносом
    """
    def __init__(self, stock_file='stock_state.json', database=None):
        self.stock_file = stock_file
        self.stock_data = self._load_stock()
        self.db = database  # Доступ к базе данных для daily_stock_reports

    def _load_stock(self):
        """Загрузить запасы из JSON файла"""
        if os.path.exists(self.stock_file):
            try:
                with open(self.stock_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки запасов: {e}")
                return {}
        return {}

    def _save_stock(self):
        """Сохранить запасы в JSON файл"""
        try:
            with open(self.stock_file, 'w', encoding='utf-8') as f:
                json.dump(self.stock_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения запасов: {e}")

    def get_stock(self, date_str, article_nr):
        """
        Получить запас для артикула на дату
        НОВАЯ ЛОГИКА: Сначала проверяем daily_stock_reports (отчет кладовщика),
        если нет - используем виртуальный запас из JSON
        """
        # Приоритет 1: Отчет кладовщика из базы данных
        if self.db:
            try:
                stock_from_report = self.db.get_stock_for_date(article_nr, date_str)
                if stock_from_report > 0:
                    logger.debug(f"Using daily stock report for {article_nr} on {date_str}: {stock_from_report}")
                    return float(stock_from_report)
            except Exception as e:
                logger.warning(f"Error getting stock from daily report: {e}")

        # Приоритет 2: Виртуальный запас из JSON (старая логика)
        if date_str not in self.stock_data:
            return 0.0
        if article_nr not in self.stock_data[date_str]:
            return 0.0
        return float(self.stock_data[date_str][article_nr].get('cakes', 0))

    def set_stock(self, date_str, article_nr, cakes, batches=0, dough_id=None, dough_name=None):
        """Установить запас для артикула на дату"""
        if date_str not in self.stock_data:
            self.stock_data[date_str] = {}

        self.stock_data[date_str][article_nr] = {
            'cakes': round(cakes, 2),
            'batches': round(batches, 2),
            'dough_id': dough_id,
            'dough_name': dough_name,
            'updated_at': datetime.now().isoformat()
        }
        self._save_stock()

    def get_all_stock_for_date(self, date_str):
        """Получить все запасы на дату"""
        return self.stock_data.get(date_str, {})

    def calculate_net_demand(self, gross_demand, available_stock):
        """Рассчитать чистый спрос с учетом запасов"""
        return max(0, gross_demand - available_stock)

    def calculate_surplus(self, produced, net_demand):
        """Рассчитать остаток после производства"""
        return max(0, produced - net_demand)

    def round_to_batches(self, quantity, items_per_batch):
        """
        Округлить до полных замесов (партий).
        Всегда округляем ВВЕРХ до целого числа партий.
        Минимум - 1 партия (даже если запрошено меньше).
        """
        if items_per_batch <= 0:
            return 0, 0
        if quantity <= 0:
            return 0, 0

        # Округляем ВВЕРХ до целого числа партий (используем math.ceil)
        batches_needed = quantity / items_per_batch
        batches_rounded = max(1, math.ceil(batches_needed))  # Минимум 1 партия

        # Итоговое количество изделий = кратно партии
        total_produced = batches_rounded * items_per_batch

        return batches_rounded, total_produced

    def clear_old_stock(self, days_to_keep=30):
        """Очистить старые запасы"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).date()
        cutoff_str = cutoff_date.strftime('%Y-%m-%d')

        dates_to_remove = [d for d in self.stock_data.keys() if d < cutoff_str]
        for date in dates_to_remove:
            del self.stock_data[date]

        if dates_to_remove:
            logger.info(f"Очищено {len(dates_to_remove)} старых записей запасов")
            self._save_stock()
