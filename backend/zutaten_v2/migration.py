"""
Скрипт миграции данных для Zutaten V2

Мигрирует данные из recipes.composition (JSON) в новые таблицы:
- ingredients_master
- recipe_ingredients

Использование:
    python -m backend.zutaten_v2.migration --db-path wiso_golabel.db
"""

import sqlite3
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ZutatenMigration:
    """Класс для миграции данных ингредиентов"""

    # Маппинг известных ингредиентов на allergen_id
    KNOWN_ALLERGENS = {
        # Мука (глютен)
        'mehl': 'GLUTEN',
        'weizenmehl': 'GLUTEN',
        'roggenmehl': 'GLUTEN',
        'dinkelmehl': 'GLUTEN',
        'flour': 'GLUTEN',

        # Яйца
        'ei': 'EGGS',
        'eier': 'EGGS',
        'eigelb': 'EGGS',
        'eiweiss': 'EGGS',
        'vollei': 'EGGS',
        'egg': 'EGGS',

        # Молочные
        'milch': 'MILK',
        'butter': 'MILK',
        'sahne': 'MILK',
        'rahm': 'MILK',
        'sauerrahm': 'MILK',
        'mascarpone': 'MILK',
        'quark': 'MILK',
        'joghurt': 'MILK',
        'cream': 'MILK',
        'frischkäse': 'MILK',
        'kondensmilch': 'MILK',
        'milchpulver': 'MILK',

        # Орехи
        'mandel': 'NUTS',
        'haselnuss': 'NUTS',
        'walnuss': 'NUTS',
        'pistazie': 'NUTS',
        'almond': 'NUTS',
        'hazelnut': 'NUTS',
        'walnut': 'NUTS',

        # Арахис
        'erdnuss': 'PEANUTS',
        'peanut': 'PEANUTS',

        # Соя
        'soja': 'SOYBEANS',
        'sojalecithin': 'SOYBEANS',

        # Кунжут
        'sesam': 'SESAME',
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.allergen_ids: Dict[str, int] = {}
        self.created_ingredients: Dict[str, int] = {}  # name -> ingredient_id

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_allergen_ids(self):
        """Загрузить маппинг allergen_code -> allergen_id"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT allergen_id, allergen_code FROM allergens_reference")
        for row in cursor.fetchall():
            self.allergen_ids[row['allergen_code']] = row['allergen_id']

        conn.close()
        logger.info(f"Loaded {len(self.allergen_ids)} allergen IDs")

    def detect_allergen(self, ingredient_name: str) -> Optional[int]:
        """Определить аллерген по названию ингредиента"""
        name_lower = ingredient_name.lower()

        for keyword, allergen_code in self.KNOWN_ALLERGENS.items():
            if keyword in name_lower:
                return self.allergen_ids.get(allergen_code)

        return None

    def normalize_ingredient_code(self, name: str) -> str:
        """Создать код ингредиента из названия"""
        import re
        # Убираем спецсимволы, заменяем пробелы на подчеркивания
        code = re.sub(r'[^a-zA-Z0-9äöüÄÖÜß\s]', '', name)
        code = code.strip().upper().replace(' ', '_')
        code = re.sub(r'_+', '_', code)  # Убираем двойные подчеркивания

        # Транслитерация умляутов
        code = code.replace('Ä', 'AE').replace('Ö', 'OE').replace('Ü', 'UE')
        code = code.replace('ß', 'SS')

        return code[:50]  # Ограничиваем длину

    def find_or_create_ingredient(self, cursor: sqlite3.Cursor, name: str) -> int:
        """Найти или создать ингредиент по названию"""
        # Проверяем, не создали ли уже
        if name in self.created_ingredients:
            return self.created_ingredients[name]

        # Ищем по названию
        cursor.execute(
            "SELECT ingredient_id FROM ingredients_master WHERE name_de = ?",
            (name,)
        )
        row = cursor.fetchone()
        if row:
            self.created_ingredients[name] = row['ingredient_id']
            return row['ingredient_id']

        # Создаем новый
        code = self.normalize_ingredient_code(name)

        # Проверяем уникальность кода
        cursor.execute(
            "SELECT COUNT(*) FROM ingredients_master WHERE ingredient_code = ?",
            (code,)
        )
        if cursor.fetchone()[0] > 0:
            # Добавляем суффикс
            import random
            code = f"{code}_{random.randint(100, 999)}"

        allergen_id = self.detect_allergen(name)
        now = datetime.now().isoformat()

        cursor.execute('''
            INSERT INTO ingredients_master
            (ingredient_code, name_de, allergen_id, active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
        ''', (code, name, allergen_id, now, now))

        ingredient_id = cursor.lastrowid
        self.created_ingredients[name] = ingredient_id

        logger.info(f"  Created ingredient: {code} (ID: {ingredient_id})"
                    + (f" [Allergen: {allergen_id}]" if allergen_id else ""))

        return ingredient_id

    def migrate_compositions(self) -> Dict[str, int]:
        """
        Мигрировать данные из recipes.composition в новые таблицы.

        Returns:
            Статистика миграции
        """
        stats = {
            'recipes_processed': 0,
            'recipes_with_composition': 0,
            'ingredients_created': 0,
            'links_created': 0,
            'errors': 0
        }

        conn = self.get_connection()
        cursor = conn.cursor()

        # Загружаем аллергены
        self.load_allergen_ids()

        # Получаем все рецепты с composition
        cursor.execute('''
            SELECT article_nr, name, composition
            FROM recipes
            WHERE composition IS NOT NULL AND composition != ''
        ''')

        recipes = cursor.fetchall()
        logger.info(f"Found {len(recipes)} recipes with composition data")

        for recipe in recipes:
            stats['recipes_processed'] += 1
            article_nr = recipe['article_nr']
            composition_json = recipe['composition']

            try:
                composition = json.loads(composition_json)
                if not composition:
                    continue

                stats['recipes_with_composition'] += 1
                logger.info(f"Processing recipe {article_nr}: {recipe['name']}")

                # Проверяем, нет ли уже данных для этого рецепта
                cursor.execute(
                    "SELECT COUNT(*) FROM recipe_ingredients WHERE article_nr = ?",
                    (article_nr,)
                )
                if cursor.fetchone()[0] > 0:
                    logger.info(f"  Skipping (already has ingredients)")
                    continue

                # Обрабатываем каждый компонент
                now = datetime.now().isoformat()

                for comp in composition:
                    # Поддерживаем разные форматы JSON
                    if isinstance(comp, dict):
                        comp_name = comp.get('component') or comp.get('name') or comp.get('ingredient')
                        quantity = comp.get('quantity') or comp.get('weight') or comp.get('amount') or 0
                    elif isinstance(comp, str):
                        comp_name = comp
                        quantity = 100  # Дефолтный вес
                    else:
                        continue

                    if not comp_name:
                        continue

                    # Нормализуем вес
                    try:
                        weight = float(quantity)
                    except (ValueError, TypeError):
                        weight = 100

                    # Находим или создаем ингредиент
                    ingredient_id = self.find_or_create_ingredient(cursor, comp_name)

                    # Создаем связь
                    try:
                        cursor.execute('''
                            INSERT INTO recipe_ingredients
                            (article_nr, ingredient_id, weight_grams, highlight_quid, created_at, updated_at)
                            VALUES (?, ?, ?, 0, ?, ?)
                        ''', (article_nr, ingredient_id, weight, now, now))
                        stats['links_created'] += 1
                    except sqlite3.IntegrityError:
                        # Уже существует
                        pass

                conn.commit()

            except json.JSONDecodeError as e:
                logger.warning(f"  Invalid JSON in recipe {article_nr}: {e}")
                stats['errors'] += 1
            except Exception as e:
                logger.error(f"  Error processing recipe {article_nr}: {e}")
                stats['errors'] += 1

        # Считаем созданные ингредиенты
        stats['ingredients_created'] = len(self.created_ingredients)

        conn.close()
        return stats

    def add_base_ingredients(self) -> int:
        """
        Добавить базовые ингредиенты для кондитерской, если их нет.

        Returns:
            Количество добавленных ингредиентов
        """
        base_ingredients = [
            # Мука
            ('FLOUR_WHEAT', 'Weizenmehl', 'Tarwemeel', 'Farine de blé', 'flour', 'GLUTEN'),
            ('FLOUR_RYE', 'Roggenmehl', 'Roggemeel', 'Farine de seigle', 'flour', 'GLUTEN'),

            # Сахар
            ('SUGAR_WHITE', 'Zucker', 'Suiker', 'Sucre', 'sugar', None),
            ('SUGAR_POWDERED', 'Puderzucker', 'Poedersuiker', 'Sucre glace', 'sugar', None),
            ('HONEY', 'Honig', 'Honing', 'Miel', 'sugar', None),

            # Яйца
            ('EGG_WHOLE', 'Vollei', 'Heel ei', 'Œuf entier', 'egg', 'EGGS'),
            ('EGG_YOLK', 'Eigelb', 'Eigeel', 'Jaune d\'œuf', 'egg', 'EGGS'),
            ('EGG_WHITE', 'Eiweiß', 'Eiwit', 'Blanc d\'œuf', 'egg', 'EGGS'),

            # Молочные
            ('BUTTER', 'Butter', 'Boter', 'Beurre', 'dairy', 'MILK'),
            ('CREAM', 'Sahne', 'Room', 'Crème', 'dairy', 'MILK'),
            ('SOUR_CREAM', 'Sauerrahm', 'Zure room', 'Crème fraîche', 'dairy', 'MILK'),
            ('MILK', 'Milch', 'Melk', 'Lait', 'dairy', 'MILK'),
            ('MASCARPONE', 'Mascarpone', 'Mascarpone', 'Mascarpone', 'dairy', 'MILK'),

            # Орехи
            ('ALMOND', 'Mandeln', 'Amandelen', 'Amandes', 'nut', 'NUTS'),
            ('HAZELNUT', 'Haselnüsse', 'Hazelnoten', 'Noisettes', 'nut', 'NUTS'),
            ('WALNUT', 'Walnüsse', 'Walnoten', 'Noix', 'nut', 'NUTS'),

            # Шоколад
            ('COCOA_POWDER', 'Kakaopulver', 'Cacaopoeder', 'Poudre de cacao', 'chocolate', None),
            ('CHOCOLATE_DARK', 'Zartbitterschokolade', 'Pure chocolade', 'Chocolat noir', 'chocolate', None),

            # Фрукты
            ('STRAWBERRY', 'Erdbeeren', 'Aardbeien', 'Fraises', 'fruit', None),
            ('RASPBERRY', 'Himbeeren', 'Frambozen', 'Framboises', 'fruit', None),
            ('CHERRY', 'Kirschen', 'Kersen', 'Cerises', 'fruit', None),

            # Прочее
            ('VANILLA_EXTRACT', 'Vanilleextrakt', 'Vanille-extract', 'Extrait de vanille', 'flavoring', None),
            ('SALT', 'Salz', 'Zout', 'Sel', 'other', None),
            ('WATER', 'Wasser', 'Water', 'Eau', 'other', None),
            ('GELATIN', 'Gelatine', 'Gelatine', 'Gélatine', 'other', None),
        ]

        conn = self.get_connection()
        cursor = conn.cursor()

        self.load_allergen_ids()
        now = datetime.now().isoformat()
        added = 0

        for code, de, nl, fr, category, allergen_code in base_ingredients:
            # Проверяем существование
            cursor.execute(
                "SELECT ingredient_id FROM ingredients_master WHERE ingredient_code = ?",
                (code,)
            )
            if cursor.fetchone():
                continue

            allergen_id = self.allergen_ids.get(allergen_code) if allergen_code else None

            cursor.execute('''
                INSERT INTO ingredients_master
                (ingredient_code, name_de, name_nl, name_fr, category, allergen_id,
                 is_added_water, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ''', (code, de, nl, fr, category, allergen_id,
                  1 if code == 'WATER' else 0, now, now))
            added += 1

        conn.commit()
        conn.close()

        logger.info(f"Added {added} base ingredients")
        return added


def run_migration(db_path: str):
    """Запустить миграцию"""
    logger.info(f"Starting migration for database: {db_path}")
    logger.info("=" * 60)

    migration = ZutatenMigration(db_path)

    # 1. Добавляем базовые ингредиенты
    logger.info("\n[1] Adding base ingredients...")
    base_added = migration.add_base_ingredients()
    logger.info(f"    Base ingredients added: {base_added}")

    # 2. Мигрируем данные из composition
    logger.info("\n[2] Migrating recipe compositions...")
    stats = migration.migrate_compositions()

    # Выводим статистику
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  Recipes processed:        {stats['recipes_processed']}")
    logger.info(f"  Recipes with composition: {stats['recipes_with_composition']}")
    logger.info(f"  Ingredients created:      {stats['ingredients_created']}")
    logger.info(f"  Recipe-ingredient links:  {stats['links_created']}")
    logger.info(f"  Errors:                   {stats['errors']}")

    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Zutaten V2 Data Migration')
    parser.add_argument('--db-path', type=str, default='wiso_golabel.db',
                        help='Path to SQLite database')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')

    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        # TODO: Implement dry run mode
    else:
        run_migration(args.db_path)
