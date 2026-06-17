"""
CRUD операции для модуля Zutaten V2
"""

import sqlite3
import logging
import json
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from .enums import Language, HydrogenationStatus
from .models import (
    TranslatedText,
    IngredientMaster,
    RecipeIngredient,
    RecipeForLabel,
    AllergenReference,
    AdditiveClass,
    RecipeTreeNode,
    ConfirmedComposition,
)

logger = logging.getLogger(__name__)


class ZutatenDatabase:
    """Класс для работы с таблицами ингредиентов"""

    def __init__(self, db_path: str):
        """
        Инициализация подключения к БД.

        Args:
            db_path: Путь к файлу SQLite базы данных
        """
        self.db_path = db_path
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """Применяет недостающие колонки (идемпотентно)."""
        new_columns = [
            ("declaration_name_de", "TEXT"),
            ("declaration_name_nl", "TEXT"),
            ("declaration_name_fr", "TEXT"),
        ]
        with self.safe_connection() as conn:
            for col_name, col_type in new_columns:
                try:
                    conn.execute(
                        f"ALTER TABLE ingredients_master ADD COLUMN {col_name} {col_type}"
                    )
                    conn.commit()
                    logger.info("Schema: added column ingredients_master.%s", col_name)
                except Exception:
                    pass  # Column already exists

    def get_connection(self) -> sqlite3.Connection:
        """Получить соединение с БД"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=15,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def safe_connection(self):
        """Контекстный менеджер — гарантирует закрытие соединения."""
        conn = self.get_connection()
        try:
            yield conn
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ============================================
    # ALLERGENS (Аллергены)
    # ============================================

    def get_all_allergens(self, active_only: bool = True) -> List[AllergenReference]:
        """Получить все аллергены"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT allergen_id, allergen_code, name_de, name_nl, name_fr,
                       description_de, sort_order, active
                FROM allergens_reference
            '''
            if active_only:
                query += ' WHERE active = 1'
            query += ' ORDER BY sort_order'
            cursor.execute(query)

            result = []
            for row in cursor.fetchall():
                result.append(AllergenReference(
                    allergen_id=row['allergen_id'],
                    allergen_code=row['allergen_code'],
                    name=TranslatedText(
                        de=row['name_de'],
                        nl=row['name_nl'],
                        fr=row['name_fr']
                    ),
                    description_de=row['description_de'],
                    sort_order=row['sort_order'],
                    active=bool(row['active'])
                ))

            return result

    def get_allergen_by_id(self, allergen_id: int) -> Optional[AllergenReference]:
        """Получить аллерген по ID"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT allergen_id, allergen_code, name_de, name_nl, name_fr,
                       description_de, sort_order, active
                FROM allergens_reference
                WHERE allergen_id = ?
            ''', (allergen_id,))

            row = cursor.fetchone()

            if not row:
                return None

            return AllergenReference(
                allergen_id=row['allergen_id'],
                allergen_code=row['allergen_code'],
                name=TranslatedText(
                    de=row['name_de'],
                    nl=row['name_nl'],
                    fr=row['name_fr']
                ),
                description_de=row['description_de'],
                sort_order=row['sort_order'],
                active=bool(row['active'])
            )

    def save_allergen(self, data: Dict[str, Any]) -> int:
        """Создать или обновить аллерген. Возвращает allergen_id."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            allergen_id = data.get('allergen_id')
            if allergen_id:
                cursor.execute('''
                    UPDATE allergens_reference
                    SET allergen_code=?, name_de=?, name_nl=?, name_fr=?,
                        description_de=?, sort_order=?
                    WHERE allergen_id=?
                ''', (
                    data['allergen_code'], data['name_de'],
                    data.get('name_nl', ''), data.get('name_fr', ''),
                    data.get('description_de', ''), data.get('sort_order', 0),
                    allergen_id
                ))
            else:
                cursor.execute('''
                    INSERT INTO allergens_reference
                    (allergen_code, name_de, name_nl, name_fr, description_de, sort_order, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'))
                ''', (
                    data['allergen_code'], data['name_de'],
                    data.get('name_nl', ''), data.get('name_fr', ''),
                    data.get('description_de', ''), data.get('sort_order', 0)
                ))
                allergen_id = cursor.lastrowid
            conn.commit()
            return allergen_id

    def delete_allergen(self, allergen_id: int) -> bool:
        """Soft-delete аллергена"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE allergens_reference SET active=0 WHERE allergen_id=?', (allergen_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ============================================
    # ADDITIVE CLASSES (Классы добавок)
    # ============================================

    def get_all_additive_classes(self, active_only: bool = True) -> List[AdditiveClass]:
        """Получить все классы добавок"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT class_id, class_code, name_de, name_nl, name_fr,
                       example_e_numbers, sort_order, active
                FROM additive_classes
            '''
            if active_only:
                query += ' WHERE active = 1'
            query += ' ORDER BY sort_order'
            cursor.execute(query)

            result = []
            for row in cursor.fetchall():
                result.append(AdditiveClass(
                    class_id=row['class_id'],
                    class_code=row['class_code'],
                    name=TranslatedText(
                        de=row['name_de'],
                        nl=row['name_nl'],
                        fr=row['name_fr']
                    ),
                    example_e_numbers=row['example_e_numbers'],
                    sort_order=row['sort_order'],
                    active=bool(row['active'])
                ))

            return result

    # ============================================
    # INGREDIENTS (Ингредиенты)
    # ============================================

    def get_all_ingredients(self, active_only: bool = True) -> List[IngredientMaster]:
        """Получить все ингредиенты"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT i.*,
                       a.allergen_code, a.name_de as allergen_name_de, a.name_nl as allergen_name_nl, a.name_fr as allergen_name_fr,
                       c.class_code, c.name_de as class_name_de, c.name_nl as class_name_nl, c.name_fr as class_name_fr
                FROM ingredients_master i
                LEFT JOIN allergens_reference a ON i.allergen_id = a.allergen_id
                LEFT JOIN additive_classes c ON i.additive_class_id = c.class_id
            '''

            if active_only:
                query += ' WHERE i.active = 1'

            query += ' ORDER BY i.name_de'

            cursor.execute(query)

            result = []
            for row in cursor.fetchall():
                result.append(self._row_to_ingredient(row))

            return result

    def get_ingredient_by_id(self, ingredient_id: int) -> Optional[IngredientMaster]:
        """Получить ингредиент по ID"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT i.*,
                       a.allergen_code, a.name_de as allergen_name_de, a.name_nl as allergen_name_nl, a.name_fr as allergen_name_fr,
                       c.class_code, c.name_de as class_name_de, c.name_nl as class_name_nl, c.name_fr as class_name_fr
                FROM ingredients_master i
                LEFT JOIN allergens_reference a ON i.allergen_id = a.allergen_id
                LEFT JOIN additive_classes c ON i.additive_class_id = c.class_id
                WHERE i.ingredient_id = ?
            ''', (ingredient_id,))

            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_ingredient(row)

    def get_ingredient_by_code(self, ingredient_code: str) -> Optional[IngredientMaster]:
        """Получить ингредиент по коду"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT i.*,
                       a.allergen_code, a.name_de as allergen_name_de, a.name_nl as allergen_name_nl, a.name_fr as allergen_name_fr,
                       c.class_code, c.name_de as class_name_de, c.name_nl as class_name_nl, c.name_fr as class_name_fr
                FROM ingredients_master i
                LEFT JOIN allergens_reference a ON i.allergen_id = a.allergen_id
                LEFT JOIN additive_classes c ON i.additive_class_id = c.class_id
                WHERE i.ingredient_code = ?
            ''', (ingredient_code,))

            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_ingredient(row)

    def save_ingredient(self, data: Dict[str, Any]) -> int:
        """
        Создать или обновить ингредиент.

        Args:
            data: Словарь с данными ингредиента

        Returns:
            ID ингредиента
        """
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            ingredient_id = data.get('ingredient_id')
            code_normalized = str(data.get('ingredient_code', '')).strip()

            # Upsert по коду: если создают "новый" ингредиент с уже существующим code,
            # обновляем существующую запись вместо UNIQUE ошибки.
            if not ingredient_id and code_normalized:
                cursor.execute(
                    '''
                    SELECT ingredient_id
                    FROM ingredients_master
                    WHERE lower(trim(ingredient_code)) = lower(trim(?))
                    ORDER BY ingredient_id
                    LIMIT 1
                    ''',
                    (code_normalized,)
                )
                existing = cursor.fetchone()
                if existing:
                    ingredient_id = existing['ingredient_id']
                    logger.info(
                        f"Ingredient code {code_normalized} already exists; "
                        f"switching save to UPDATE (ID: {ingredient_id})"
                    )

            allergen_ids = data.get('allergen_ids') or []
            if not isinstance(allergen_ids, list):
                allergen_ids = []
            allergen_ids = [int(aid) for aid in allergen_ids if aid is not None]
            allergen_ids_json = json.dumps(sorted(set(allergen_ids)), ensure_ascii=False)

            decl_de = data.get('declaration_name_de') or None
            decl_nl = data.get('declaration_name_nl') or None
            decl_fr = data.get('declaration_name_fr') or None

            if ingredient_id:
                # UPDATE
                cursor.execute('''
                    UPDATE ingredients_master SET
                        ingredient_code = ?,
                        name_de = ?, name_nl = ?, name_fr = ?,
                        category = ?, is_compound = ?, expand_sub_ingredients_only = ?, compound_total_grams = ?,
                        allergen_id = ?, allergen_ids = ?, additive_class_id = ?, e_number = ?,
                        is_nano = ?, is_oil_fat = ?,
                        botanical_origin_de = ?, botanical_origin_nl = ?, botanical_origin_fr = ?,
                        hydrogenation = ?, is_added_water = ?, loss_factor = ?,
                        kcal_per_100g = ?, kj_per_100g = ?,
                        fat_per_100g = ?, saturated_fat_per_100g = ?,
                        carbs_per_100g = ?, sugar_per_100g = ?,
                        protein_per_100g = ?, salt_per_100g = ?,
                        declaration_name_de = ?, declaration_name_nl = ?, declaration_name_fr = ?,
                        notes = ?, active = ?, updated_at = ?
                    WHERE ingredient_id = ?
                ''', (
                    data['ingredient_code'],
                    data['name_de'], data.get('name_nl'), data.get('name_fr'),
                    data.get('category'), int(data.get('is_compound', False)),
                    int(data.get('expand_sub_ingredients_only', False)), data.get('compound_total_grams'),
                    data.get('allergen_id'), allergen_ids_json, data.get('additive_class_id'), data.get('e_number'),
                    int(data.get('is_nano', False)), int(data.get('is_oil_fat', False)),
                    data.get('botanical_origin_de'), data.get('botanical_origin_nl'), data.get('botanical_origin_fr'),
                    data.get('hydrogenation', 'NONE'), int(data.get('is_added_water', False)),
                    data.get('loss_factor', 0.0),
                    data.get('kcal_per_100g'), data.get('kj_per_100g'),
                    data.get('fat_per_100g'), data.get('saturated_fat_per_100g'),
                    data.get('carbs_per_100g'), data.get('sugar_per_100g'),
                    data.get('protein_per_100g'), data.get('salt_per_100g'),
                    decl_de, decl_nl, decl_fr,
                    data.get('notes'), int(data.get('active', True)), now,
                    ingredient_id
                ))
            else:
                # INSERT
                cursor.execute('''
                    INSERT INTO ingredients_master (
                        ingredient_code, name_de, name_nl, name_fr,
                        category, is_compound, expand_sub_ingredients_only, compound_total_grams,
                        allergen_id, allergen_ids, additive_class_id, e_number,
                        is_nano, is_oil_fat, botanical_origin_de, botanical_origin_nl, botanical_origin_fr,
                        hydrogenation, is_added_water, loss_factor,
                        kcal_per_100g, kj_per_100g,
                        fat_per_100g, saturated_fat_per_100g,
                        carbs_per_100g, sugar_per_100g,
                        protein_per_100g, salt_per_100g,
                        declaration_name_de, declaration_name_nl, declaration_name_fr,
                        notes, active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['ingredient_code'],
                    data['name_de'], data.get('name_nl'), data.get('name_fr'),
                    data.get('category'), int(data.get('is_compound', False)),
                    int(data.get('expand_sub_ingredients_only', False)), data.get('compound_total_grams'),
                    data.get('allergen_id'), allergen_ids_json, data.get('additive_class_id'), data.get('e_number'),
                    int(data.get('is_nano', False)), int(data.get('is_oil_fat', False)),
                    data.get('botanical_origin_de'), data.get('botanical_origin_nl'), data.get('botanical_origin_fr'),
                    data.get('hydrogenation', 'NONE'), int(data.get('is_added_water', False)),
                    data.get('loss_factor', 0.0),
                    data.get('kcal_per_100g'), data.get('kj_per_100g'),
                    data.get('fat_per_100g'), data.get('saturated_fat_per_100g'),
                    data.get('carbs_per_100g'), data.get('sugar_per_100g'),
                    data.get('protein_per_100g'), data.get('salt_per_100g'),
                    decl_de, decl_nl, decl_fr,
                    data.get('notes'), int(data.get('active', True)), now, now
                ))
                ingredient_id = cursor.lastrowid

            conn.commit()

            logger.info(f"Saved ingredient: {data['ingredient_code']} (ID: {ingredient_id})")
            return ingredient_id

    def delete_ingredient(self, ingredient_id: int) -> bool:
        """Удалить ингредиент навсегда (hard delete) с очисткой связанных ссылок."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            # 1) Удаляем связи в под-ингредиентах (и как parent, и как child)
            cursor.execute(
                'DELETE FROM ingredient_sub_ingredients WHERE parent_ingredient_id = ? OR child_ingredient_id = ?',
                (ingredient_id, ingredient_id)
            )

            # 2) Удаляем из составов рецептов (legacy)
            cursor.execute('DELETE FROM recipe_ingredients WHERE ingredient_id = ?', (ingredient_id,))

            # 3) Удаляем из рекурсивного дерева рецептов V2
            cursor.execute('DELETE FROM zutaten_v2_recipe_tree WHERE child_ingredient_id = ?', (ingredient_id,))

            # 4) Удаляем сам ингредиент
            cursor.execute('DELETE FROM ingredients_master WHERE ingredient_id = ?', (ingredient_id,))
            affected = cursor.rowcount
            conn.commit()

            return affected > 0

    # ============================================
    # SUB-INGREDIENTS (Суб-ингредиенты)
    # ============================================

    def get_sub_ingredients(self, parent_ingredient_id: int) -> List[RecipeIngredient]:
        """Получить суб-ингредиенты для составного ингредиента"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT si.*, i.*,
                       a.allergen_code, a.name_de as allergen_name_de, a.name_nl as allergen_name_nl, a.name_fr as allergen_name_fr,
                       c.class_code, c.name_de as class_name_de, c.name_nl as class_name_nl, c.name_fr as class_name_fr
                FROM ingredient_sub_ingredients si
                JOIN ingredients_master i ON si.child_ingredient_id = i.ingredient_id
                LEFT JOIN allergens_reference a ON i.allergen_id = a.allergen_id
                LEFT JOIN additive_classes c ON i.additive_class_id = c.class_id
                WHERE si.parent_ingredient_id = ?
                ORDER BY si.sort_order, si.weight_percentage DESC
            ''', (parent_ingredient_id,))

            result = []
            for row in cursor.fetchall():
                ingredient = self._row_to_ingredient(row)
                result.append(RecipeIngredient(
                    ingredient=ingredient,
                    weight_grams=row['weight_percentage'],
                    highlight_quid=False,
                    sort_override=row['sort_order']
                ))

            return result

    def save_sub_ingredients(self, parent_ingredient_id: int, sub_ingredients: List[Dict]) -> None:
        """
        Сохранить суб-ингредиенты для составного ингредиента.

        Args:
            parent_ingredient_id: ID родительского ингредиента
            sub_ingredients: Список словарей с child_ingredient_id, weight_percentage, sort_order
        """
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # Удаляем старые связи
            cursor.execute('DELETE FROM ingredient_sub_ingredients WHERE parent_ingredient_id = ?',
                          (parent_ingredient_id,))

            # Добавляем новые
            for sub in sub_ingredients:
                cursor.execute('''
                    INSERT INTO ingredient_sub_ingredients
                    (parent_ingredient_id, child_ingredient_id, weight_percentage, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    parent_ingredient_id,
                    sub['child_ingredient_id'],
                    sub.get('weight_grams', sub.get('weight_percentage', 0)),
                    sub.get('sort_order', 0),
                    now, now
                ))

            conn.commit()

    # ============================================
    # RECIPE INGREDIENTS (Ингредиенты рецепта)
    # ============================================

    def get_recipe_ingredients(self, article_nr: str) -> List[RecipeIngredient]:
        """Получить ингредиенты рецепта"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT ri.*, i.*,
                       a.allergen_code, a.name_de as allergen_name_de, a.name_nl as allergen_name_nl, a.name_fr as allergen_name_fr,
                       c.class_code, c.name_de as class_name_de, c.name_nl as class_name_nl, c.name_fr as class_name_fr
                FROM recipe_ingredients ri
                JOIN ingredients_master i ON ri.ingredient_id = i.ingredient_id
                LEFT JOIN allergens_reference a ON i.allergen_id = a.allergen_id
                LEFT JOIN additive_classes c ON i.additive_class_id = c.class_id
                WHERE ri.article_nr = ?
                ORDER BY ri.sort_override, ri.weight_grams DESC
            ''', (article_nr,))

            result = []
            for row in cursor.fetchall():
                ingredient = self._row_to_ingredient(row)

                # Загружаем суб-ингредиенты если это составной ингредиент
                if ingredient.is_compound:
                    ingredient.sub_ingredients = self.get_sub_ingredients(ingredient.ingredient_id)

                result.append(RecipeIngredient(
                    ingredient=ingredient,
                    weight_grams=row['weight_grams'],
                    highlight_quid=bool(row['highlight_quid']),
                    sort_override=row['sort_override']
                ))

            return result

    def save_recipe_ingredients(self, article_nr: str, ingredients: List[Dict]) -> None:
        """
        Сохранить ингредиенты рецепта.

        Args:
            article_nr: Артикул рецепта
            ingredients: Список словарей с ingredient_id, weight_grams, highlight_quid, sort_override
        """
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # Удаляем старые связи
            cursor.execute('DELETE FROM recipe_ingredients WHERE article_nr = ?', (article_nr,))

            # Агрегируем дубли по ingredient_id:
            # вес суммируется, QUID сохраняется если включён хотя бы в одной строке.
            aggregated: Dict[int, Dict[str, Any]] = {}
            order = 0
            for ing in ingredients:
                ing_id = ing.get('ingredient_id')
                if ing_id is None:
                    continue
                if ing_id not in aggregated:
                    aggregated[ing_id] = {
                        'ingredient_id': ing_id,
                        'weight_grams': float(ing.get('weight_grams') or 0.0),
                        'highlight_quid': bool(ing.get('highlight_quid', False)),
                        'sort_override': ing.get('sort_override', order),
                        'notes': ing.get('notes')
                    }
                    order += 1
                else:
                    aggregated[ing_id]['weight_grams'] += float(ing.get('weight_grams') or 0.0)
                    aggregated[ing_id]['highlight_quid'] = (
                        aggregated[ing_id]['highlight_quid'] or bool(ing.get('highlight_quid', False))
                    )
                    if aggregated[ing_id].get('notes') in (None, ''):
                        aggregated[ing_id]['notes'] = ing.get('notes')

            # Добавляем новые
            for ing in aggregated.values():
                cursor.execute('''
                    INSERT INTO recipe_ingredients
                    (article_nr, ingredient_id, weight_grams, highlight_quid, sort_override, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    article_nr,
                    ing['ingredient_id'],
                    ing['weight_grams'],
                    int(ing.get('highlight_quid', False)),
                    ing.get('sort_override'),
                    ing.get('notes'),
                    now, now
                ))

            conn.commit()
            logger.info(f"Saved {len(aggregated)} unique ingredients for recipe {article_nr}")

    def get_recipe_for_label(self, article_nr: str, final_weight: float = None) -> Optional[RecipeForLabel]:
        """
        Получить рецепт с ингредиентами для генерации этикетки.

        Args:
            article_nr: Артикул рецепта
            final_weight: Вес готового продукта (если не указан, берётся сумма входных весов * 0.9)
        """
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            # Получаем название рецепта
            cursor.execute('SELECT name FROM recipes WHERE article_nr = ?', (article_nr,))
            row = cursor.fetchone()

            if not row:
                return None

            recipe_name = row['name'] or article_nr

        # Получаем ингредиенты
        ingredients = self.get_recipe_ingredients(article_nr)

        if not ingredients:
            return None

        total_input = sum(i.weight_grams for i in ingredients)

        # Если вес не указан, считаем 90% от входного (типичная усушка)
        if final_weight is None:
            final_weight = total_input * 0.9

        return RecipeForLabel(
            article_nr=article_nr,
            name=recipe_name,
            ingredients=ingredients,
            final_product_weight=final_weight
        )

    # ============================================
    # LABEL SETTINGS & RECIPE LABEL DATA
    # ============================================

    def get_label_settings(self) -> dict:
        """Получить все настройки этикеток как словарь {key: value}"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT setting_key, setting_value FROM label_settings")
                result = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
            except Exception:
                result = {}
            return result

    def save_label_setting(self, key: str, value: str) -> bool:
        """Сохранить настройку этикетки (upsert)"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('''
                INSERT OR REPLACE INTO label_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, value, now))
            conn.commit()
            return True

    def get_recipe_label_data(self, article_nr: str) -> dict:
        """Получить данные этикетки рецепта"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT article_nr, name, label_name, label_full_name, barcode,
                           weight_grams, shelf_life_days,
                           nutrition_energie, nutrition_fett, nutrition_davon_fett,
                           nutrition_kohlenhydrate, nutrition_davon_zucker,
                           nutrition_eiweiss, nutrition_salz
                    FROM recipes WHERE article_nr = ?
                ''', (article_nr,))
            except sqlite3.OperationalError:
                cursor.execute('''
                    SELECT article_nr, name, label_name, label_full_name, barcode,
                           weight_grams, shelf_life_days
                    FROM recipes WHERE article_nr = ?
                ''', (article_nr,))
            row = cursor.fetchone()
            if not row:
                return {}
            result = dict(row)
            result['label_name'] = '' if result.get('label_name') is None else str(result.get('label_name'))
            result['label_full_name'] = '' if result.get('label_full_name') is None else str(result.get('label_full_name'))
            result['barcode'] = '' if result.get('barcode') is None else str(result.get('barcode'))

            for key in (
                'nutrition_energie', 'nutrition_fett', 'nutrition_davon_fett',
                'nutrition_kohlenhydrate', 'nutrition_davon_zucker',
                'nutrition_eiweiss', 'nutrition_salz'
            ):
                result[key] = str(result.get(key) or '').strip()

            return result

    def save_recipe_label_data(self, article_nr: str, data: dict) -> bool:
        """Сохранить данные этикетки рецепта"""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    UPDATE recipes SET
                        label_name = ?, label_full_name = ?, barcode = ?,
                        weight_grams = ?, shelf_life_days = ?,
                        nutrition_energie = ?, nutrition_fett = ?, nutrition_davon_fett = ?,
                        nutrition_kohlenhydrate = ?, nutrition_davon_zucker = ?,
                        nutrition_eiweiss = ?, nutrition_salz = ?,
                        updated_at = ?
                    WHERE article_nr = ?
                ''', (
                    data.get('label_name'), data.get('label_full_name'), data.get('barcode'),
                    data.get('weight_grams'), data.get('shelf_life_days'),
                    data.get('nutrition_energie'), data.get('nutrition_fett'), data.get('nutrition_davon_fett'),
                    data.get('nutrition_kohlenhydrate'), data.get('nutrition_davon_zucker'),
                    data.get('nutrition_eiweiss'), data.get('nutrition_salz'),
                    datetime.now().isoformat(), article_nr
                ))
            except sqlite3.OperationalError:
                cursor.execute('''
                    UPDATE recipes SET
                        label_name = ?, label_full_name = ?, barcode = ?,
                        weight_grams = ?, shelf_life_days = ?,
                        updated_at = ?
                    WHERE article_nr = ?
                ''', (
                    data.get('label_name'), data.get('label_full_name'), data.get('barcode'),
                    data.get('weight_grams'), data.get('shelf_life_days'),
                    datetime.now().isoformat(), article_nr
                ))
            conn.commit()
            return True

    # ============================================
    # HELPER METHODS
    # ============================================

    def _row_to_ingredient(self, row: sqlite3.Row) -> IngredientMaster:
        """Конвертировать строку БД в объект IngredientMaster"""
        # Multiple allergens (JSON array of IDs)
        allergen_ids = []
        if 'allergen_ids' in row.keys() and row['allergen_ids']:
            try:
                parsed = json.loads(row['allergen_ids'])
                if isinstance(parsed, list):
                    allergen_ids = [int(aid) for aid in parsed if aid is not None]
            except Exception:
                allergen_ids = []
        if row['allergen_id'] and row['allergen_id'] not in allergen_ids:
            allergen_ids.append(int(row['allergen_id']))

        # Botanical origin
        botanical_origin = None
        if row['botanical_origin_de']:
            botanical_origin = TranslatedText(
                de=row['botanical_origin_de'],
                nl=row['botanical_origin_nl'],
                fr=row['botanical_origin_fr']
            )

        # Allergen name
        allergen_name = None
        if row['allergen_id']:
            allergen_name = TranslatedText(
                de=row['allergen_name_de'],
                nl=row['allergen_name_nl'],
                fr=row['allergen_name_fr']
            )

        # Additive class name
        additive_class_name = None
        if row['additive_class_id']:
            additive_class_name = TranslatedText(
                de=row['class_name_de'],
                nl=row['class_name_nl'],
                fr=row['class_name_fr']
            )

        # Declaration name (Deklarationsname) — overrides display name on label
        declaration_name = None
        row_keys = row.keys()
        if 'declaration_name_de' in row_keys and row['declaration_name_de']:
            declaration_name = TranslatedText(
                de=row['declaration_name_de'],
                nl=row['declaration_name_nl'] if 'declaration_name_nl' in row_keys else None,
                fr=row['declaration_name_fr'] if 'declaration_name_fr' in row_keys else None,
            )

        return IngredientMaster(
            ingredient_id=row['ingredient_id'],
            ingredient_code=row['ingredient_code'],
            name=TranslatedText(
                de=row['name_de'],
                nl=row['name_nl'],
                fr=row['name_fr']
            ),
            category=row['category'],
            is_compound=bool(row['is_compound']),
            expand_sub_ingredients_only=bool(row['expand_sub_ingredients_only']) if 'expand_sub_ingredients_only' in row_keys else False,
            compound_total_grams=row['compound_total_grams'] if 'compound_total_grams' in row_keys else None,
            declaration_name=declaration_name,
            allergen_id=row['allergen_id'],
            allergen_ids=sorted(set(allergen_ids)),
            allergen_code=row['allergen_code'] if row['allergen_id'] else None,
            allergen_name=allergen_name,
            additive_class_id=row['additive_class_id'],
            additive_class_code=row['class_code'] if row['additive_class_id'] else None,
            additive_class_name=additive_class_name,
            e_number=row['e_number'],
            is_nano=bool(row['is_nano']),
            is_oil_fat=bool(row['is_oil_fat']),
            botanical_origin=botanical_origin,
            hydrogenation=HydrogenationStatus(row['hydrogenation']) if row['hydrogenation'] else HydrogenationStatus.NONE,
            is_added_water=bool(row['is_added_water']),
            loss_factor=row['loss_factor'] or 0.0,
            kcal_per_100g=row['kcal_per_100g'],
            kj_per_100g=row['kj_per_100g'] if 'kj_per_100g' in row.keys() else None,
            fat_per_100g=row['fat_per_100g'],
            saturated_fat_per_100g=row['saturated_fat_per_100g'] if 'saturated_fat_per_100g' in row.keys() else None,
            carbs_per_100g=row['carbs_per_100g'],
            sugar_per_100g=row['sugar_per_100g'] if 'sugar_per_100g' in row.keys() else None,
            protein_per_100g=row['protein_per_100g'],
            salt_per_100g=row['salt_per_100g'],
            notes=row['notes'],
            active=bool(row['active']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )

    def search_ingredients(self, query: str, category: str = None, limit: int = 50) -> List[IngredientMaster]:
        """
        Поиск ингредиентов по названию.

        Args:
            query: Строка поиска
            category: Фильтр по категории (опционально)
            limit: Максимальное количество результатов
        """
        with self.safe_connection() as conn:
            cursor = conn.cursor()

            sql = '''
                SELECT i.*,
                       a.allergen_code, a.name_de as allergen_name_de, a.name_nl as allergen_name_nl, a.name_fr as allergen_name_fr,
                       c.class_code, c.name_de as class_name_de, c.name_nl as class_name_nl, c.name_fr as class_name_fr
                FROM ingredients_master i
                LEFT JOIN allergens_reference a ON i.allergen_id = a.allergen_id
                LEFT JOIN additive_classes c ON i.additive_class_id = c.class_id
                WHERE i.active = 1
                AND (i.name_de LIKE ? OR i.name_nl LIKE ? OR i.name_fr LIKE ? OR i.ingredient_code LIKE ?)
            '''

            params = [f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%']

            if category:
                sql += ' AND i.category = ?'
                params.append(category)

            sql += f' ORDER BY i.name_de LIMIT {limit}'

            cursor.execute(sql, params)

            result = []
            for row in cursor.fetchall():
                result.append(self._row_to_ingredient(row))

            return result

    # ============================================
    # RECIPE TREE (Дерево рецептов — рекурсивная структура)
    # ============================================

    def get_recipe_tree(self, parent_article_nr: str) -> List[RecipeTreeNode]:
        """Получить прямых потомков рецепта (один уровень)."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, parent_article_nr, child_type, child_article_nr,
                       child_ingredient_id, weight_grams, loss_percent,
                       output_weight_grams, highlight_quid, sort_order, notes
                FROM zutaten_v2_recipe_tree
                WHERE parent_article_nr = ?
                ORDER BY sort_order, id
            ''', (parent_article_nr,))

            result = []
            for row in cursor.fetchall():
                result.append(RecipeTreeNode(
                    id=row['id'],
                    parent_article_nr=row['parent_article_nr'],
                    child_type=row['child_type'],
                    child_article_nr=row['child_article_nr'],
                    child_ingredient_id=row['child_ingredient_id'],
                    weight_grams=row['weight_grams'],
                    loss_percent=row['loss_percent'] or 0.0,
                    output_weight_grams=row['output_weight_grams'],
                    highlight_quid=bool(row['highlight_quid']),
                    sort_order=row['sort_order'] or 0,
                    notes=row['notes'],
                ))
            return result

    def save_recipe_tree(self, parent_article_nr: str, nodes: List[Dict]) -> None:
        """
        Сохранить дерево рецепта (полная перезапись прямых потомков).

        Args:
            parent_article_nr: Артикул родительского рецепта
            nodes: Список узлов [{child_type, child_article_nr, child_ingredient_id,
                                   weight_grams, loss_percent, output_weight_grams,
                                   highlight_quid, sort_order, notes}]
        """
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # Удаляем старые прямые потомки
            cursor.execute(
                'DELETE FROM zutaten_v2_recipe_tree WHERE parent_article_nr = ?',
                (parent_article_nr,)
            )

            # Вставляем новые
            for node in nodes:
                cursor.execute('''
                    INSERT INTO zutaten_v2_recipe_tree
                    (parent_article_nr, child_type, child_article_nr, child_ingredient_id,
                     weight_grams, loss_percent, output_weight_grams,
                     highlight_quid, sort_order, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    parent_article_nr,
                    node['child_type'],
                    node.get('child_article_nr'),
                    node.get('child_ingredient_id'),
                    node['weight_grams'],
                    node.get('loss_percent', 0.0),
                    node.get('output_weight_grams'),
                    int(node.get('highlight_quid', False)),
                    node.get('sort_order', 0),
                    node.get('notes'),
                    now, now
                ))

            conn.commit()
            logger.info(f"Saved {len(nodes)} tree nodes for recipe {parent_article_nr}")

    def add_tree_node(self, parent_article_nr: str, node: Dict) -> int:
        """Добавить один узел в дерево рецепта. Возвращает id."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute('''
                INSERT INTO zutaten_v2_recipe_tree
                (parent_article_nr, child_type, child_article_nr, child_ingredient_id,
                 weight_grams, loss_percent, output_weight_grams,
                 highlight_quid, sort_order, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                parent_article_nr,
                node['child_type'],
                node.get('child_article_nr'),
                node.get('child_ingredient_id'),
                node['weight_grams'],
                node.get('loss_percent', 0.0),
                node.get('output_weight_grams'),
                int(node.get('highlight_quid', False)),
                node.get('sort_order', 0),
                node.get('notes'),
                now, now
            ))
            conn.commit()
            return cursor.lastrowid

    def update_tree_node(self, node_id: int, data: Dict) -> bool:
        """Обновить узел дерева по ID."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute('''
                UPDATE zutaten_v2_recipe_tree SET
                    weight_grams = ?, loss_percent = ?, output_weight_grams = ?,
                    highlight_quid = ?, sort_order = ?, notes = ?, updated_at = ?
                WHERE id = ?
            ''', (
                data['weight_grams'],
                data.get('loss_percent', 0.0),
                data.get('output_weight_grams'),
                int(data.get('highlight_quid', False)),
                data.get('sort_order', 0),
                data.get('notes'),
                now, node_id
            ))
            conn.commit()
            return cursor.rowcount > 0

    def delete_tree_node(self, node_id: int) -> bool:
        """Удалить узел дерева по ID."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM zutaten_v2_recipe_tree WHERE id = ?', (node_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_recipe_tree_full(self, parent_article_nr: str) -> List[Dict]:
        """
        Получить дерево рецепта с названиями ингредиентов и вложенных рецептов.

        Возвращает обогащенный список узлов с display_name.
        """
        nodes = self.get_recipe_tree(parent_article_nr)
        result = []

        for node in nodes:
            node_dict = node.to_dict()

            if node.child_type == 'ingredient' and node.child_ingredient_id:
                ingredient = self.get_ingredient_by_id(node.child_ingredient_id)
                if ingredient:
                    node_dict['display_name'] = ingredient.name.de
                    node_dict['ingredient'] = ingredient.to_dict()
                    # Для составных ингредиентов показываем связи с суб-ингредиентами
                    # как вложенные "виртуальные" узлы в дизайнере.
                    if ingredient.is_compound:
                        subs = self.get_sub_ingredients(ingredient.ingredient_id)
                        children = []
                        for idx, sub in enumerate(subs):
                            sub_ing = sub.ingredient
                            children.append({
                                'id': f"sub_{ingredient.ingredient_id}_{sub_ing.ingredient_id}_{idx}",
                                'parent_article_nr': parent_article_nr,
                                'child_type': 'ingredient',
                                'child_article_nr': None,
                                'child_ingredient_id': sub_ing.ingredient_id,
                                'weight_grams': float(sub.weight_grams or 0.0),
                                'loss_percent': 0.0,
                                'output_weight_grams': None,
                                'highlight_quid': False,
                                'sort_order': int(sub.sort_override if sub.sort_override is not None else idx),
                                'notes': 'auto:sub_ingredient',
                                'display_name': sub_ing.name.de,
                                'ingredient': sub_ing.to_dict(),
                            })
                        if children:
                            node_dict['children'] = children
                else:
                    node_dict['display_name'] = f'[Ингредиент #{node.child_ingredient_id}]'

            elif node.child_type == 'recipe' and node.child_article_nr:
                recipe_name = self.get_recipe_name(node.child_article_nr)
                node_dict['display_name'] = recipe_name or node.child_article_nr
                # Рекурсивно загружаем потомков
                node_dict['children'] = self.get_recipe_tree_full(node.child_article_nr)

            result.append(node_dict)

        return result

    def get_recipe_name(self, article_nr: str) -> Optional[str]:
        """Получить название рецепта по артикулу."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT name FROM recipes WHERE article_nr = ?', (article_nr,))
            row = cursor.fetchone()
            if row and row['name']:
                return row['name']
            # Fallback: артикул может быть кодом составного ингредиента.
            cursor.execute('SELECT name_de FROM ingredients_master WHERE ingredient_code = ? LIMIT 1', (article_nr,))
            row = cursor.fetchone()
            return row['name_de'] if row and row['name_de'] else None

    def get_recipes_using_ingredient(self, ingredient_id: int) -> List[str]:
        """Найти все рецепты, использующие данный ингредиент (прямо или через дерево)."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT parent_article_nr
                FROM zutaten_v2_recipe_tree
                WHERE child_type = 'ingredient' AND child_ingredient_id = ?
            ''', (ingredient_id,))
            return [row['parent_article_nr'] for row in cursor.fetchall()]

    def get_recipes_using_sub_recipe(self, child_article_nr: str) -> List[str]:
        """Найти все рецепты, использующие данный под-рецепт."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT parent_article_nr
                FROM zutaten_v2_recipe_tree
                WHERE child_type = 'recipe' AND child_article_nr = ?
            ''', (child_article_nr,))
            return [row['parent_article_nr'] for row in cursor.fetchall()]

    # ============================================
    # CONFIRMED COMPOSITIONS (Подтвержденные составы)
    # ============================================

    def get_confirmed_composition(self, article_nr: str) -> Optional[ConfirmedComposition]:
        """Получить подтвержденный состав для артикула."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, article_nr, confirmed_text_de, confirmed_text_nl, confirmed_text_fr,
                       auto_generated_text_de, recipe_hash, confirmed_by, confirmed_at,
                       is_outdated
                FROM zutaten_v2_confirmed_compositions
                WHERE article_nr = ?
            ''', (article_nr,))

            row = cursor.fetchone()
            if not row:
                return None

            return ConfirmedComposition(
                id=row['id'],
                article_nr=row['article_nr'],
                confirmed_text_de=row['confirmed_text_de'],
                confirmed_text_nl=row['confirmed_text_nl'],
                confirmed_text_fr=row['confirmed_text_fr'],
                auto_generated_text_de=row['auto_generated_text_de'],
                recipe_hash=row['recipe_hash'],
                confirmed_by=row['confirmed_by'],
                confirmed_at=row['confirmed_at'],
                is_outdated=bool(row['is_outdated']),
            )

    def save_confirmed_composition(self, article_nr: str, data: Dict) -> int:
        """
        Сохранить подтвержденный состав (upsert).

        Args:
            article_nr: Артикул
            data: {confirmed_text_de, confirmed_text_nl, confirmed_text_fr,
                   auto_generated_text_de, recipe_hash, confirmed_by}

        Returns:
            ID записи
        """
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute(
                'SELECT id FROM zutaten_v2_confirmed_compositions WHERE article_nr = ?',
                (article_nr,)
            )
            existing = cursor.fetchone()

            if existing:
                cursor.execute('''
                    UPDATE zutaten_v2_confirmed_compositions SET
                        confirmed_text_de = ?, confirmed_text_nl = ?, confirmed_text_fr = ?,
                        auto_generated_text_de = ?, recipe_hash = ?,
                        confirmed_by = ?, confirmed_at = ?,
                        is_outdated = 0, updated_at = ?
                    WHERE article_nr = ?
                ''', (
                    data.get('confirmed_text_de'),
                    data.get('confirmed_text_nl'),
                    data.get('confirmed_text_fr'),
                    data.get('auto_generated_text_de'),
                    data.get('recipe_hash'),
                    data.get('confirmed_by'),
                    now, now, article_nr
                ))
                conn.commit()
                return existing['id']
            else:
                cursor.execute('''
                    INSERT INTO zutaten_v2_confirmed_compositions
                    (article_nr, confirmed_text_de, confirmed_text_nl, confirmed_text_fr,
                     auto_generated_text_de, recipe_hash, confirmed_by, confirmed_at,
                     is_outdated, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ''', (
                    article_nr,
                    data.get('confirmed_text_de'),
                    data.get('confirmed_text_nl'),
                    data.get('confirmed_text_fr'),
                    data.get('auto_generated_text_de'),
                    data.get('recipe_hash'),
                    data.get('confirmed_by'),
                    now, now, now
                ))
                conn.commit()
                return cursor.lastrowid

    def mark_composition_outdated(self, article_nr: str) -> bool:
        """Пометить подтвержденный состав как устаревший."""
        with self.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE zutaten_v2_confirmed_compositions
                SET is_outdated = 1, updated_at = ?
                WHERE article_nr = ?
            ''', (datetime.now().isoformat(), article_nr))
            conn.commit()
            return cursor.rowcount > 0

    def mark_compositions_outdated_for_ingredient(self, ingredient_id: int) -> int:
        """
        Пометить как устаревшие все подтвержденные составы рецептов,
        использующих данный ингредиент.

        Returns:
            Количество помеченных записей
        """
        affected_recipes = self.get_recipes_using_ingredient(ingredient_id)
        count = 0
        for article_nr in affected_recipes:
            if self.mark_composition_outdated(article_nr):
                count += 1
        return count

    def mark_compositions_outdated_for_sub_recipe(self, child_article_nr: str) -> int:
        """
        Пометить как устаревшие все подтвержденные составы рецептов,
        использующих данный под-рецепт.

        Returns:
            Количество помеченных записей
        """
        affected_recipes = self.get_recipes_using_sub_recipe(child_article_nr)
        count = 0
        for article_nr in affected_recipes:
            if self.mark_composition_outdated(article_nr):
                count += 1
        return count
