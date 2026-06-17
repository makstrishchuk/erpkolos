"""
WebSocket API handlers для модуля Zutaten V2

Handlers для интеграции в server_unified.py
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

from .enums import Language
from .database import ZutatenDatabase
from .generator import (
    MultilingualLabelGenerator,
    generate_all_languages,
    generate_label_from_composition,
    generate_all_languages_from_composition,
)
from .calculator import CompositionCalculator
from .nutrition import calculate_nutrition, format_nutrition_for_label
from .models import RecipeIngredient

logger = logging.getLogger(__name__)
request_id = None


class ZutatenAPIHandlers:
    """
    Класс с WebSocket handlers для управления ингредиентами.

    Использование в server_unified.py:
        zutaten_api = ZutatenAPIHandlers(db_path)

        # В handle_message():
        if msg_type == 'get_all_ingredients':
            await zutaten_api.handle_get_all_ingredients(websocket, data)
    """

    def __init__(self, db_path: str):
        """
        Инициализация handlers.

        Args:
            db_path: Путь к базе данных SQLite
        """
        self.db = ZutatenDatabase(db_path)
        self.calculator = CompositionCalculator(self.db)

    @staticmethod
    def _to_float_or_none(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().replace(',', '.')
            if value == '':
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int_or_none(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            if value == '':
                return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _extract_label_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'label_name': str(data.get('label_name') or '').strip(),
            'label_full_name': str(data.get('label_full_name') or '').strip(),
            'barcode': str(data.get('barcode') or '').strip(),
            'weight_grams': self._to_float_or_none(data.get('weight_grams')),
            'shelf_life_days': self._to_int_or_none(data.get('shelf_life_days')),
            'nutrition_energie': str(data.get('nutrition_energie') or '').strip(),
            'nutrition_fett': str(data.get('nutrition_fett') or '').strip(),
            'nutrition_davon_fett': str(data.get('nutrition_davon_fett') or '').strip(),
            'nutrition_kohlenhydrate': str(data.get('nutrition_kohlenhydrate') or '').strip(),
            'nutrition_davon_zucker': str(data.get('nutrition_davon_zucker') or '').strip(),
            'nutrition_eiweiss': str(data.get('nutrition_eiweiss') or '').strip(),
            'nutrition_salz': str(data.get('nutrition_salz') or '').strip(),
        }

    @staticmethod
    def _article_candidates(article_nr: Any) -> list:
        """Build candidate article numbers for fallback matching (e.g. 02216 <-> 2216)."""
        base = str(article_nr or '').strip()
        if not base:
            return []
        candidates = [base]
        if base.isdigit():
            stripped = base.lstrip('0') or '0'
            if stripped not in candidates:
                candidates.append(stripped)
        return candidates

    def _resolve_existing_recipe_article(self, article_nr: Any) -> str:
        """Resolve article number that exists in recipes table, preferring exact value."""
        candidates = self._article_candidates(article_nr)
        if not candidates:
            return str(article_nr or '')
        with self.db.safe_connection() as conn:
            cursor = conn.cursor()
            for cand in candidates:
                cursor.execute('SELECT article_nr FROM recipes WHERE article_nr = ? LIMIT 1', (cand,))
                row = cursor.fetchone()
                if row and row['article_nr']:
                    return str(row['article_nr'])
        return candidates[0]

    def _find_recipe_for_label_with_fallback(self, article_nr: Any, final_weight: Any):
        """
        Try to load recipe-for-label for the requested article and fallback variants.
        Returns tuple: (resolved_article_nr, recipe_or_none)
        """
        candidates = self._article_candidates(article_nr)
        if not candidates:
            return str(article_nr or ''), None
        for cand in candidates:
            recipe = self.db.get_recipe_for_label(cand, final_weight)
            if recipe:
                return cand, recipe
        return candidates[0], None

    def _find_composition_with_fallback(self, article_nr: Any, final_weight: Any):
        """
        Try to calculate composition for requested article and fallback variants.
        Returns tuple: (resolved_article_nr, composition_or_none)
        """
        candidates = self._article_candidates(article_nr)
        if not candidates:
            return str(article_nr or ''), None
        for cand in candidates:
            result = self.calculator.calculate(cand, final_weight)
            if result:
                return cand, result
        return candidates[0], None

    def _find_confirmed_composition_with_fallback(self, article_nr: Any):
        """Find confirmed composition by exact article first, then fallback candidates."""
        candidates = self._article_candidates(article_nr)
        if not candidates:
            return None
        for cand in candidates:
            confirmed = self.db.get_confirmed_composition(cand)
            if confirmed:
                return confirmed
        return None

    # ============================================
    # ALLERGENS
    # ============================================

    async def handle_get_allergens(self, websocket, data: Dict = None) -> None:
        """
        Получить список всех аллергенов.

        Response:
            type: allergens_data
            allergens: [{allergen_id, allergen_code, name_de, name_nl, name_fr, ...}]
        """
        try:
            active_only = data.get('active_only', True) if data else True
            allergens = self.db.get_all_allergens(active_only=active_only)

            response = {
                'type': 'allergens_data',
                'success': True,
                'allergens': [
                    {
                        'allergen_id': a.allergen_id,
                        'allergen_code': a.allergen_code,
                        'name_de': a.name.de,
                        'name_nl': a.name.nl,
                        'name_fr': a.name.fr,
                        'description_de': a.description_de,
                        'sort_order': a.sort_order,
                    }
                    for a in allergens
                ]
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error getting allergens: {e}")
            await websocket.send(json.dumps({
                'type': 'allergens_data',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_save_allergen(self, websocket, data: Dict) -> None:
        """Создать или обновить аллерген."""
        try:
            if not data.get('allergen_code') or not data.get('name_de'):
                await websocket.send(json.dumps({
                    'type': 'allergen_saved',
                    'success': False,
                    'error': 'allergen_code и name_de обязательны'
                }))
                return

            allergen_id = self.db.save_allergen(data)
            await websocket.send(json.dumps({
                'type': 'allergen_saved',
                'success': True,
                'allergen_id': allergen_id
            }))
        except Exception as e:
            logger.error(f"Error saving allergen: {e}")
            await websocket.send(json.dumps({
                'type': 'allergen_saved',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_delete_allergen(self, websocket, data: Dict) -> None:
        """Удалить аллерген (soft delete)."""
        try:
            allergen_id = data.get('allergen_id')
            if not allergen_id:
                await websocket.send(json.dumps({
                    'type': 'allergen_deleted',
                    'success': False,
                    'error': 'allergen_id is required'
                }))
                return

            success = self.db.delete_allergen(allergen_id)
            await websocket.send(json.dumps({
                'type': 'allergen_deleted',
                'success': success
            }))
        except Exception as e:
            logger.error(f"Error deleting allergen: {e}")
            await websocket.send(json.dumps({
                'type': 'allergen_deleted',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    # ============================================
    # ADDITIVE CLASSES
    # ============================================

    async def handle_get_additive_classes(self, websocket, data: Dict = None) -> None:
        """
        Получить список классов добавок.

        Response:
            type: additive_classes_data
            classes: [{class_id, class_code, name_de, name_nl, name_fr, ...}]
        """
        try:
            active_only = data.get('active_only', True) if data else True
            classes = self.db.get_all_additive_classes(active_only=active_only)

            response = {
                'type': 'additive_classes_data',
                'success': True,
                'additive_classes': [
                    {
                        'class_id': c.class_id,
                        'class_code': c.class_code,
                        'name_de': c.name.de,
                        'name_nl': c.name.nl,
                        'name_fr': c.name.fr,
                        'example_e_numbers': c.example_e_numbers,
                        'sort_order': c.sort_order,
                    }
                    for c in classes
                ]
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error getting additive classes: {e}")
            await websocket.send(json.dumps({
                'type': 'additive_classes_data',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_get_zutaten_recipes(self, websocket, data: Dict = None) -> None:
        """
        Получить список рецептов напрямую из таблицы recipes для модулей Zutaten/V2.

        Response:
            type: zutaten_recipes_data
            recipes: [{article_nr, name, active, ...}]
        """
        try:
            active_only = data.get('active_only', True) if data else True
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()
                if active_only:
                    cursor.execute("""
                        SELECT article_nr, name, active, category, label_name, label_full_name
                        FROM recipes
                        WHERE COALESCE(active, 1) = 1
                        ORDER BY article_nr
                    """)
                else:
                    cursor.execute("""
                        SELECT article_nr, name, active, category, label_name, label_full_name
                        FROM recipes
                        ORDER BY article_nr
                    """)
                recipes = [dict(r) for r in cursor.fetchall()]

            await websocket.send(json.dumps({
                'type': 'zutaten_recipes_data',
                'success': True,
                'recipes': recipes,
                'count': len(recipes),
            }))
        except Exception as e:
            logger.error(f"Error getting zutaten recipes: {e}")
            await websocket.send(json.dumps({
                'type': 'zutaten_recipes_data',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    # ============================================
    # INGREDIENTS
    # ============================================

    async def handle_get_all_ingredients(self, websocket, data: Dict = None) -> None:
        """
        Получить список всех ингредиентов.

        Request (optional):
            active_only: bool (default True)

        Response:
            type: ingredients_data
            ingredients: [...]
        """
        try:
            active_only = data.get('active_only', True) if data else True
            ingredients = self.db.get_all_ingredients(active_only=active_only)

            # Собираем суб-ингредиенты для составных ингредиентов
            ingredients_dicts = []
            for i in ingredients:
                d = i.to_dict()
                if i.is_compound:
                    subs = self.db.get_sub_ingredients(i.ingredient_id)
                    d['sub_ingredients'] = [
                        {
                            'child_ingredient_id': s.ingredient.ingredient_id,
                            'ingredient_code': s.ingredient.ingredient_code,
                            'name_de': s.ingredient.name.de,
                            'weight_percentage': s.weight_grams,
                            'sort_order': s.sort_override or 0,
                        }
                        for s in subs
                    ]
                else:
                    d['sub_ingredients'] = []
                ingredients_dicts.append(d)

            response = {
                'type': 'ingredients_data',
                'success': True,
                'count': len(ingredients),
                'ingredients': ingredients_dicts
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error getting ingredients: {e}")
            await websocket.send(json.dumps({
                'type': 'ingredients_data',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_get_ingredient(self, websocket, data: Dict) -> None:
        """
        Получить ингредиент по ID.

        Request:
            ingredient_id: int

        Response:
            type: ingredient_data
            ingredient: {...}
        """
        try:
            ingredient_id = data.get('ingredient_id')

            if not ingredient_id:
                await websocket.send(json.dumps({
                    'type': 'ingredient_data',
                    'success': False,
                    'error': 'ingredient_id is required'
                }))
                return

            ingredient = self.db.get_ingredient_by_id(ingredient_id)

            if not ingredient:
                await websocket.send(json.dumps({
                    'type': 'ingredient_data',
                    'success': False,
                    'error': f'Ingredient {ingredient_id} not found'
                }))
                return

            # Загружаем суб-ингредиенты если это составной ингредиент
            sub_ingredients = []
            if ingredient.is_compound:
                subs = self.db.get_sub_ingredients(ingredient_id)
                sub_ingredients = [
                    {
                        'ingredient_id': s.ingredient.ingredient_id,
                        'ingredient_code': s.ingredient.ingredient_code,
                        'name_de': s.ingredient.name.de,
                        'weight_percentage': s.weight_grams,
                        'sort_order': s.sort_override,
                    }
                    for s in subs
                ]

            response = {
                'type': 'ingredient_data',
                'success': True,
                'ingredient': ingredient.to_dict(),
                'sub_ingredients': sub_ingredients
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error getting ingredient: {e}")
            await websocket.send(json.dumps({
                'type': 'ingredient_data',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_save_ingredient(self, websocket, data: Dict) -> None:
        """
        Создать или обновить ингредиент.

        Request:
            ingredient_id: int (optional, если новый)
            ingredient_code: str
            name_de: str
            name_nl: str (optional)
            name_fr: str (optional)
            declaration_name_de: str (optional) — Deklarationsname for label (overrides name_de)
            declaration_name_nl: str (optional)
            declaration_name_fr: str (optional)
            category: str (optional)
            allergen_id: int (optional)
            additive_class_id: int (optional)
            e_number: str (optional)
            is_compound: bool
            is_nano: bool
            is_oil_fat: bool
            botanical_origin_de/nl/fr: str (optional)
            hydrogenation: str (NONE/PARTLY/FULLY)
            is_added_water: bool
            loss_factor: float
            sub_ingredients: [{child_ingredient_id, weight_percentage, sort_order}] (optional)

        Response:
            type: ingredient_saved
            ingredient_id: int
        """
        try:
            request_id = data.get('request_id')
            # Поддержка вложенной структуры: {"ingredient": {...}} -> плоский dict
            if 'ingredient' in data and isinstance(data['ingredient'], dict):
                data = data['ingredient']

            # Валидация обязательных полей
            if not data.get('ingredient_code'):
                await websocket.send(json.dumps({
                    'type': 'ingredient_saved',
                    'success': False,
                    'error': 'ingredient_code is required',
                    'request_id': request_id
                }))
                return

            if not data.get('name_de'):
                await websocket.send(json.dumps({
                    'type': 'ingredient_saved',
                    'success': False,
                    'error': 'name_de is required',
                    'request_id': request_id
                }))
                return

            # Сохраняем ингредиент
            ingredient_id = self.db.save_ingredient(data)

            # Всегда синхронизируем суб-ингредиенты, чтобы корректно очищать старые связи
            if data.get('is_compound'):
                self.db.save_sub_ingredients(ingredient_id, data.get('sub_ingredients', []))
            else:
                self.db.save_sub_ingredients(ingredient_id, [])

            response = {
                'type': 'ingredient_saved',
                'success': True,
                'ingredient_id': ingredient_id,
                'message': f"Ингредиент {data['ingredient_code']} сохранён",
                'request_id': request_id
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error saving ingredient: {e}")
            await websocket.send(json.dumps({
                'type': 'ingredient_saved',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_delete_ingredient(self, websocket, data: Dict) -> None:
        """
        Удалить ингредиент (soft delete).

        Request:
            ingredient_id: int

        Response:
            type: ingredient_deleted
        """
        try:
            ingredient_id = data.get('ingredient_id')

            if not ingredient_id:
                await websocket.send(json.dumps({
                    'type': 'ingredient_deleted',
                    'success': False,
                    'error': 'ingredient_id is required'
                }))
                return

            success = self.db.delete_ingredient(ingredient_id)

            await websocket.send(json.dumps({
                'type': 'ingredient_deleted',
                'success': success,
                'ingredient_id': ingredient_id
            }))

        except Exception as e:
            logger.error(f"Error deleting ingredient: {e}")
            await websocket.send(json.dumps({
                'type': 'ingredient_deleted',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_search_ingredients(self, websocket, data: Dict) -> None:
        """
        Поиск ингредиентов.

        Request:
            query: str
            category: str (optional)
            limit: int (optional, default 50)

        Response:
            type: ingredients_search_result
            ingredients: [...]
        """
        try:
            query = data.get('query', '')
            category = data.get('category')
            limit = data.get('limit', 50)

            ingredients = self.db.search_ingredients(query, category, limit)

            response = {
                'type': 'ingredients_search_result',
                'success': True,
                'query': query,
                'count': len(ingredients),
                'ingredients': [i.to_dict() for i in ingredients]
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error searching ingredients: {e}")
            await websocket.send(json.dumps({
                'type': 'ingredients_search_result',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    # ============================================
    # RECIPE INGREDIENTS
    # ============================================

    async def handle_get_recipe_ingredients(self, websocket, data: Dict) -> None:
        """
        Получить ингредиенты рецепта.

        Request:
            article_nr: str

        Response:
            type: recipe_ingredients_data
            article_nr: str
            ingredients: [...]
        """
        try:
            article_nr = data.get('article_nr')

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'recipe_ingredients_data',
                    'success': False,
                    'error': 'article_nr is required'
                }))
                return

            ingredients = self.db.get_recipe_ingredients(article_nr)
            # Если legacy-состав пуст, пробуем показать прямые ingredient-узлы из дерева V2.
            if not ingredients:
                tree_nodes = self.db.get_recipe_tree(article_nr)
                pseudo = []
                for n in tree_nodes:
                    if n.child_type != 'ingredient' or not n.child_ingredient_id:
                        continue
                    ing = self.db.get_ingredient_by_id(n.child_ingredient_id)
                    if not ing:
                        continue
                    pseudo.append({
                        'ingredient_id': ing.ingredient_id,
                        'weight_grams': float(n.weight_grams or 0.0),
                        'highlight_quid': bool(n.highlight_quid),
                        'sort_override': n.sort_order,
                        'ingredient': {
                            'ingredient_id': ing.ingredient_id,
                            'ingredient_code': ing.ingredient_code,
                            'name_de': ing.name.de,
                            'name_nl': ing.name.nl,
                            'name_fr': ing.name.fr,
                            'allergen_code': ing.allergen_code,
                            'is_compound': ing.is_compound,
                            'allergen_id': ing.allergen_id,
                            'additive_class_id': ing.additive_class_id,
                            'e_number': ing.e_number,
                        },
                    })
                pseudo.sort(key=lambda x: (x.get('sort_override') if x.get('sort_override') is not None else 999999))
                response = {
                    'type': 'recipe_ingredients_data',
                    'success': True,
                    'article_nr': article_nr,
                    'count': len(pseudo),
                    'ingredients': pseudo
                }
                await websocket.send(json.dumps(response))
                return

            response = {
                'type': 'recipe_ingredients_data',
                'success': True,
                'article_nr': article_nr,
                'count': len(ingredients),
                'ingredients': [i.to_dict() for i in ingredients]
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error getting recipe ingredients: {e}")
            await websocket.send(json.dumps({
                'type': 'recipe_ingredients_data',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_save_recipe_ingredients(self, websocket, data: Dict) -> None:
        """
        Сохранить ингредиенты рецепта.

        Request:
            article_nr: str
            ingredients: [{ingredient_id, weight_grams, highlight_quid, sort_override, notes}]

        Response:
            type: recipe_ingredients_saved
        """
        try:
            article_nr = data.get('article_nr')
            ingredients = data.get('ingredients', [])

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'recipe_ingredients_saved',
                    'success': False,
                    'error': 'article_nr is required'
                }))
                return

            self.db.save_recipe_ingredients(article_nr, ingredients)

            # Синхронизация с V2-деревом:
            # состав из вкладки "Состав рецепта" становится прямыми узлами дерева.
            tree_nodes = []
            for i, ing in enumerate(ingredients):
                ing_id = ing.get('ingredient_id')
                if ing_id is None:
                    continue
                tree_nodes.append({
                    'child_type': 'ingredient',
                    'child_article_nr': None,
                    'child_ingredient_id': ing_id,
                    'weight_grams': float(ing.get('weight_grams') or 0.0),
                    'loss_percent': 0.0,
                    'output_weight_grams': None,
                    'highlight_quid': bool(ing.get('highlight_quid', False)),
                    'sort_order': int(ing.get('sort_override', i) if ing.get('sort_override') is not None else i),
                    'notes': ing.get('notes'),
                })
            self.db.save_recipe_tree(article_nr, tree_nodes)
            self.calculator.invalidate_cache(article_nr)
            self.db.mark_composition_outdated(article_nr)
            self.db.mark_compositions_outdated_for_sub_recipe(article_nr)

            response = {
                'type': 'recipe_ingredients_saved',
                'success': True,
                'article_nr': article_nr,
                'count': len(ingredients),
                'message': f"Сохранено {len(ingredients)} ингредиентов для {article_nr}"
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error saving recipe ingredients: {e}")
            await websocket.send(json.dumps({
                'type': 'recipe_ingredients_saved',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    # ============================================
    # LABEL GENERATION
    # ============================================

    async def handle_generate_zutaten_label(self, websocket, data: Dict) -> None:
        """
        ????????????? ???????? ????????????.

        Request:
            article_nr: str
            language: str (de/nl/fr)
            final_weight_grams: float (optional)

        Response:
            type: zutaten_label_generated
            article_nr: str
            language: str
            label_text: str
            allergens_present: [str]
        """
        try:
            article_nr = data.get('article_nr')
            language_code = data.get('language', 'de')
            final_weight = data.get('final_weight_grams')

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'zutaten_label_generated',
                    'success': False,
                    'error': 'article_nr is required'
                }))
                return

            try:
                language = Language(language_code)
            except ValueError:
                language = Language.DE

            resolved_article_nr, composition = self._find_composition_with_fallback(article_nr, final_weight)
            _, recipe = self._find_recipe_for_label_with_fallback(article_nr, final_weight)

            result = None
            allergens_summary = {}
            allergens_present = []
            label_text = ''
            recipe_name = self.db.get_recipe_name(article_nr) or str(article_nr)
            total_input_weight = 0
            final_product_weight = final_weight or 0
            compliance_issues = []
            etikettenkonform = True

            if composition:
                generated = generate_label_from_composition(composition, language, db=self.db)
                label_text = generated.label_text
                allergens_present = generated.allergens_present
                recipe_name = composition.product_name
                total_input_weight = composition.total_input_weight
                final_product_weight = composition.final_product_weight
                compliance_issues = self.calculator.get_label_compliance_issues(composition, language.value)
                etikettenkonform = len(compliance_issues) == 0

            elif recipe:
                generator = MultilingualLabelGenerator(recipe, language)
                result = generator.generate()
                label_text = result.label_text
                allergens_present = result.allergens_present
                allergens_summary = generator.get_allergens_summary()
                recipe_name = recipe.name
                total_input_weight = recipe.total_input_weight
                final_product_weight = recipe.final_product_weight

            # If manual confirmed composition exists, use it even without recipe ingredients/tree.
            confirmed = self._find_confirmed_composition_with_fallback(article_nr)
            if confirmed:
                if language == Language.NL:
                    confirmed_text = (confirmed.confirmed_text_nl or '').strip()
                elif language == Language.FR:
                    confirmed_text = (confirmed.confirmed_text_fr or '').strip()
                else:
                    confirmed_text = (confirmed.confirmed_text_de or '').strip()
                if confirmed_text:
                    label_text = confirmed_text

            if not label_text:
                await websocket.send(json.dumps({
                    'type': 'zutaten_label_generated',
                    'success': False,
                    'error': f'Recipe {article_nr} not found or has no ingredients'
                }))
                return

            response = {
                'type': 'zutaten_label_generated',
                'success': True,
                'article_nr': article_nr,
                'language': language.value,
                'label_text': label_text,
                'allergens_present': allergens_present,
                'allergens_summary': allergens_summary,
                'recipe_name': recipe_name,
                'total_input_weight': total_input_weight,
                'final_product_weight': final_product_weight,
                'etikettenkonform': etikettenkonform,
                'compliance_issues': compliance_issues,
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error generating label: {e}")
            await websocket.send(json.dumps({
                'type': 'zutaten_label_generated',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))

    async def handle_generate_all_languages(self, websocket, data: Dict) -> None:
        """
        Сгенерировать этикетки на всех языках.

        Request:
            article_nr: str
            final_weight_grams: float (optional)

        Response:
            type: zutaten_labels_all_languages
            article_nr: str
            labels: {de: {...}, nl: {...}, fr: {...}}
        """
        try:
            article_nr = data.get('article_nr')
            final_weight = data.get('final_weight_grams')

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'zutaten_labels_all_languages',
                    'success': False,
                    'error': 'article_nr is required'
                }))
                return

            # Получаем рецепт
            recipe = self.db.get_recipe_for_label(article_nr, final_weight)

            if not recipe:
                await websocket.send(json.dumps({
                    'type': 'zutaten_labels_all_languages',
                    'success': False,
                    'error': f'Recipe {article_nr} not found or has no ingredients'
                }))
                return

            # Генерируем на всех языках
            labels = generate_all_languages(recipe)

            response = {
                'type': 'zutaten_labels_all_languages',
                'success': True,
                'article_nr': article_nr,
                'recipe_name': recipe.name,
                'labels': {
                    lang: {
                        'label_text': label.label_text,
                        'allergens_present': label.allergens_present,
                    }
                    for lang, label in labels.items()
                }
            }

            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error generating all languages: {e}")
            await websocket.send(json.dumps({
                'type': 'zutaten_labels_all_languages',
                'success': False,
                'error': str(e),
                'request_id': request_id
            }))


    # ============================================
    # LABEL PRINTING (ETIKETT)
    # ============================================

    async def handle_get_recipe_label_data(self, websocket, data: Dict) -> None:
        """Получить данные этикетки для рецепта."""
        try:
            article_nr = data.get('article_nr')
            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'recipe_label_data', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            resolved_article_nr = self._resolve_existing_recipe_article(article_nr)
            label_data = self.db.get_recipe_label_data(resolved_article_nr)
            await websocket.send(json.dumps({
                'type': 'recipe_label_data',
                'success': True,
                **label_data
            }))
        except Exception as e:
            logger.error(f"Error getting recipe label data: {e}")
            await websocket.send(json.dumps({
                'type': 'recipe_label_data', 'success': False, 'error': str(e)
            }))

    async def handle_save_recipe_label_data(self, websocket, data: Dict) -> None:
        """Сохранить данные этикетки для рецепта."""
        try:
            article_nr = data.get('article_nr')
            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'recipe_label_saved', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            resolved_article_nr = self._resolve_existing_recipe_article(article_nr)
            save_data = self._extract_label_payload(data)
            self.db.save_recipe_label_data(resolved_article_nr, save_data)
            await websocket.send(json.dumps({
                'type': 'recipe_label_saved', 'success': True,
                'article_nr': resolved_article_nr
            }))
        except Exception as e:
            logger.error(f"Error saving recipe label data: {e}")
            await websocket.send(json.dumps({
                'type': 'recipe_label_saved', 'success': False, 'error': str(e)
            }))

    async def handle_sync_label_from_tree(self, websocket, data: Dict) -> None:
        """
        Актуализация данных этикетки из дерева рецепта.
        - пересчитывает состав (de/nl/fr),
        - обновляет пищевую ценность,
        - сохраняет в таблицу recipes и confirmed_compositions.
        """
        try:
            article_nr = data.get('article_nr')
            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'label_recipe_synchronized', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            requested_weight = self._to_float_or_none(data.get('final_weight_grams'))
            label_article_nr = self._resolve_existing_recipe_article(article_nr)
            current_label_data = self.db.get_recipe_label_data(label_article_nr) or {}
            final_weight = requested_weight
            if final_weight is None:
                final_weight = self._to_float_or_none(current_label_data.get('weight_grams')) or 900.0

            calc_article_nr, result = self._find_composition_with_fallback(article_nr, final_weight)
            if not result:
                await websocket.send(json.dumps({
                    'type': 'label_recipe_synchronized', 'success': False,
                    'error': f'Recipe tree for {article_nr} not found or empty'
                }))
                return

            labels = generate_all_languages_from_composition(result, db=self.db)
            label_de = labels.get('de')
            label_nl = labels.get('nl')
            label_fr = labels.get('fr')

            recipe_name = self.db.get_recipe_name(calc_article_nr) or article_nr
            nutrition_fields = {
                'ENERGIE': '', 'FETT': '', 'DAVON_FETT': '',
                'KOHLENHYDRATE': '', 'DAVON_ZUCKER': '',
                'EIWIESS': '', 'SALZ': ''
            }

            resolved_article_nr, recipe = self._find_recipe_for_label_with_fallback(calc_article_nr, final_weight)
            if recipe and recipe.ingredients:
                nutrition = calculate_nutrition(recipe.ingredients, final_weight)
                if nutrition:
                    nutrition_fields = format_nutrition_for_label(nutrition)

            if not any(str(nutrition_fields.get(k, '')).strip() for k in ['ENERGIE', 'FETT', 'KOHLENHYDRATE']):
                total_kcal = total_kj = total_fat = total_sat = 0.0
                total_carbs = total_sugar = total_protein = total_salt = 0.0
                has_any = False
                for fi in result.flat_ingredients:
                    ing = fi.ingredient
                    w = float(fi.absolute_weight or 0.0)
                    if w <= 0:
                        continue
                    if ing.kcal_per_100g is not None:
                        has_any = True
                        total_kcal += (w / 100.0) * float(ing.kcal_per_100g or 0.0)
                        if ing.kj_per_100g is not None:
                            total_kj += (w / 100.0) * float(ing.kj_per_100g or 0.0)
                        else:
                            total_kj += (w / 100.0) * float(ing.kcal_per_100g or 0.0) * 4.184
                    total_fat += (w / 100.0) * float(ing.fat_per_100g or 0.0)
                    total_sat += (w / 100.0) * float(ing.saturated_fat_per_100g or 0.0)
                    total_carbs += (w / 100.0) * float(ing.carbs_per_100g or 0.0)
                    total_sugar += (w / 100.0) * float(ing.sugar_per_100g or 0.0)
                    total_protein += (w / 100.0) * float(ing.protein_per_100g or 0.0)
                    total_salt += (w / 100.0) * float(ing.salt_per_100g or 0.0)

                if has_any and float(final_weight) > 0:
                    factor = 100.0 / float(final_weight)

                    def _fmt_g(v):
                        return f"{v:.1f} g".replace('.', ',')

                    nutrition_fields = {
                        'ENERGIE': f"{int(round(total_kj * factor))} kJ/{int(round(total_kcal * factor))} Kcal",
                        'FETT': _fmt_g(total_fat * factor),
                        'DAVON_FETT': _fmt_g(total_sat * factor),
                        'KOHLENHYDRATE': _fmt_g(total_carbs * factor),
                        'DAVON_ZUCKER': _fmt_g(total_sugar * factor),
                        'EIWIESS': _fmt_g(total_protein * factor),
                        'SALZ': _fmt_g(total_salt * factor),
                    }

            save_label_data = {
                'label_name': str(current_label_data.get('label_name') or '').strip(),
                'label_full_name': str(current_label_data.get('label_full_name') or '').strip(),
                'barcode': str(current_label_data.get('barcode') or '').strip(),
                'weight_grams': float(final_weight),
                'shelf_life_days': self._to_int_or_none(current_label_data.get('shelf_life_days')),
                'nutrition_energie': str(nutrition_fields.get('ENERGIE') or '').strip(),
                'nutrition_fett': str(nutrition_fields.get('FETT') or '').strip(),
                'nutrition_davon_fett': str(nutrition_fields.get('DAVON_FETT') or '').strip(),
                'nutrition_kohlenhydrate': str(nutrition_fields.get('KOHLENHYDRATE') or '').strip(),
                'nutrition_davon_zucker': str(nutrition_fields.get('DAVON_ZUCKER') or '').strip(),
                'nutrition_eiweiss': str(nutrition_fields.get('EIWIESS') or '').strip(),
                'nutrition_salz': str(nutrition_fields.get('SALZ') or '').strip(),
            }
            self.db.save_recipe_label_data(label_article_nr, save_label_data)

            auto_de = (label_de.label_text if label_de else '').strip()
            self.db.save_confirmed_composition(label_article_nr, {
                'confirmed_text_de': auto_de,
                'confirmed_text_nl': (label_nl.label_text if label_nl else '').strip(),
                'confirmed_text_fr': (label_fr.label_text if label_fr else '').strip(),
                'auto_generated_text_de': auto_de,
                'recipe_hash': result.recipe_hash,
                'confirmed_by': data.get('updated_by', 'auto_sync'),
            })

            await websocket.send(json.dumps({
                'type': 'label_recipe_synchronized',
                'success': True,
                'article_nr': label_article_nr,
                'label_data': self.db.get_recipe_label_data(label_article_nr),
                'labels': {
                    'de': {'label_text': (label_de.label_text if label_de else ''), 'allergens_present': (label_de.allergens_present if label_de else [])},
                    'nl': {'label_text': (label_nl.label_text if label_nl else ''), 'allergens_present': (label_nl.allergens_present if label_nl else [])},
                    'fr': {'label_text': (label_fr.label_text if label_fr else ''), 'allergens_present': (label_fr.allergens_present if label_fr else [])},
                },
                'recipe_hash': result.recipe_hash,
                'message': f'Этикетка {article_nr} актуализирована из дерева рецепта'
            }))
        except Exception as e:
            logger.error(f"Error syncing label from tree: {e}")
            await websocket.send(json.dumps({
                'type': 'label_recipe_synchronized', 'success': False, 'error': str(e)
            }))

    async def handle_get_label_settings(self, websocket, data: Dict = None) -> None:
        """Получить настройки этикеток (SPUREN и др.)."""
        try:
            settings = self.db.get_label_settings()
            await websocket.send(json.dumps({
                'type': 'label_settings_data',
                'success': True,
                'settings': settings
            }))
        except Exception as e:
            logger.error(f"Error getting label settings: {e}")
            await websocket.send(json.dumps({
                'type': 'label_settings_data', 'success': False, 'error': str(e)
            }))

    async def handle_save_label_setting(self, websocket, data: Dict) -> None:
        """Сохранить настройку этикетки."""
        try:
            key = data.get('setting_key')
            value = data.get('setting_value', '')
            if not key:
                await websocket.send(json.dumps({
                    'type': 'label_setting_saved', 'success': False,
                    'error': 'setting_key is required'
                }))
                return

            self.db.save_label_setting(key, value)
            await websocket.send(json.dumps({
                'type': 'label_setting_saved', 'success': True, 'setting_key': key
            }))
        except Exception as e:
            logger.error(f"Error saving label setting: {e}")
            await websocket.send(json.dumps({
                'type': 'label_setting_saved', 'success': False, 'error': str(e)
            }))

    # Маппинг регионов на шаблоны
    ETIKETT_TEMPLATES = {
        'DE (+7°C)': ('DE+7.ezpx', r'\\server01\DATA\WISO_GOLABEL\etiketten\test'),
        'DE (-18°C)': ('DE-18.ezpx', r'\\server01\DATA\WISO_GOLABEL\etiketten\test'),
    }

    async def handle_print_etikett(self, websocket, data: Dict) -> None:
        """
        Собрать все данные этикетки и отправить клиенту для печати через GoLabel.
        """
        try:
            article_nr = data.get('article_nr')
            language_code = data.get('language', 'de')
            region = data.get('region', 'DE (+7°C)')
            print_date_str = data.get('print_date')
            quantity = data.get('quantity', 1)
            manual_label_text = str(data.get('manual_label_text') or '').strip()

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'etikett_print_data', 'success': False,
                    'error': 'article_nr обязателен'
                }))
                return

            # Язык
            try:
                language = Language(language_code)
            except ValueError:
                language = Language.DE

            # 1. Данные этикетки рецепта (можно передать прямо из окна генерации)
            label_article_nr = self._resolve_existing_recipe_article(article_nr)
            incoming_label_data = self._extract_label_payload(data)
            if any(v not in (None, '') for v in incoming_label_data.values()):
                self.db.save_recipe_label_data(label_article_nr, incoming_label_data)

            label_data = self.db.get_recipe_label_data(label_article_nr)
            if not label_data:
                await websocket.send(json.dumps({
                    'type': 'etikett_print_data', 'success': False,
                    'error': f'Рецепт {article_nr} не найден'
                }))
                return

            # 2. Рецепт с ингредиентами
            final_weight = label_data.get('weight_grams') or 900
            resolved_article_nr, recipe = self._find_recipe_for_label_with_fallback(article_nr, final_weight)

            # 3. ZUTATEN текст: используем подтвержденный состав, а если его нет — авто из рецепта.
            zutaten_text = ''
            allergens_present = []
            if recipe and recipe.ingredients:
                generator = MultilingualLabelGenerator(recipe, language)
                result = generator.generate()
                allergens_present = result.allergens_present
                zutaten_text = (result.label_text or '').strip()

            confirmed = self.db.get_confirmed_composition(label_article_nr)
            if not confirmed and resolved_article_nr != label_article_nr:
                confirmed = self.db.get_confirmed_composition(resolved_article_nr)
            if confirmed:
                if language == Language.NL:
                    confirmed_text = (confirmed.confirmed_text_nl or '').strip()
                elif language == Language.FR:
                    confirmed_text = (confirmed.confirmed_text_fr or '').strip()
                else:
                    confirmed_text = (confirmed.confirmed_text_de or '').strip()
                if confirmed_text:
                    zutaten_text = confirmed_text
            if manual_label_text:
                zutaten_text = manual_label_text

            if not zutaten_text:
                await websocket.send(json.dumps({
                    'type': 'etikett_print_data', 'success': False,
                    'error': 'Текст состава пуст. Сначала сформируйте состав во вкладке этикетки.'
                }))
                return

            # 4. Пищевая ценность
            nutrition_fields = {
                'ENERGIE': '', 'FETT': '', 'DAVON_FETT': '',
                'KOHLENHYDRATE': '', 'DAVON_ZUCKER': '',
                'EIWIESS': '', 'SALZ': ''
            }
            if recipe and recipe.ingredients:
                nutrition = calculate_nutrition(recipe.ingredients, final_weight)
                if nutrition:
                    nutrition_fields = format_nutrition_for_label(nutrition)
            # Fallback: если у верхнего состава нет нутриентов, считаем по развернутому составу (внутренности)
            if not any(str(nutrition_fields.get(k, '')).strip() for k in ['ENERGIE', 'FETT', 'KOHLENHYDRATE']):
                try:
                    composition = self.calculator.calculate(article_nr, float(final_weight))
                    if composition and composition.flat_ingredients:
                        total_kcal = total_kj = total_fat = total_sat = total_carbs = total_sugar = total_protein = total_salt = 0.0
                        has_any = False
                        for fi in composition.flat_ingredients:
                            ing = fi.ingredient
                            w = float(fi.absolute_weight or 0.0)
                            if w <= 0:
                                continue
                            if ing.kcal_per_100g is not None:
                                has_any = True
                                total_kcal += (w / 100.0) * float(ing.kcal_per_100g or 0.0)
                                if ing.kj_per_100g is not None:
                                    total_kj += (w / 100.0) * float(ing.kj_per_100g or 0.0)
                                else:
                                    total_kj += (w / 100.0) * float(ing.kcal_per_100g or 0.0) * 4.184
                            total_fat += (w / 100.0) * float(ing.fat_per_100g or 0.0)
                            total_sat += (w / 100.0) * float(ing.saturated_fat_per_100g or 0.0)
                            total_carbs += (w / 100.0) * float(ing.carbs_per_100g or 0.0)
                            total_sugar += (w / 100.0) * float(ing.sugar_per_100g or 0.0)
                            total_protein += (w / 100.0) * float(ing.protein_per_100g or 0.0)
                            total_salt += (w / 100.0) * float(ing.salt_per_100g or 0.0)
                        if has_any and float(final_weight) > 0:
                            factor = 100.0 / float(final_weight)
                            def _fmt_g(v):
                                return f"{v:.1f} g".replace('.', ',')
                            nutrition_fields = {
                                'ENERGIE': f"{int(round(total_kj * factor))} kJ/{int(round(total_kcal * factor))} Kcal",
                                'FETT': _fmt_g(total_fat * factor),
                                'DAVON_FETT': _fmt_g(total_sat * factor),
                                'KOHLENHYDRATE': _fmt_g(total_carbs * factor),
                                'DAVON_ZUCKER': _fmt_g(total_sugar * factor),
                                'EIWIESS': _fmt_g(total_protein * factor),
                                'SALZ': _fmt_g(total_salt * factor),
                            }
                except Exception as _e:
                    logger.warning(f"Nutrition fallback from composition failed: {_e}")

            manual_nutrition_map = {
                'ENERGIE': str(label_data.get('nutrition_energie') or '').strip(),
                'FETT': str(label_data.get('nutrition_fett') or '').strip(),
                'DAVON_FETT': str(label_data.get('nutrition_davon_fett') or '').strip(),
                'KOHLENHYDRATE': str(label_data.get('nutrition_kohlenhydrate') or '').strip(),
                'DAVON_ZUCKER': str(label_data.get('nutrition_davon_zucker') or '').strip(),
                'EIWIESS': str(label_data.get('nutrition_eiweiss') or '').strip(),
                'SALZ': str(label_data.get('nutrition_salz') or '').strip(),
            }
            if any(manual_nutrition_map.values()):
                for field_key, manual_value in manual_nutrition_map.items():
                    if manual_value:
                        nutrition_fields[field_key] = manual_value

            # Для шаблона GoLabel используем формат с пробелом перед единицей, без underscore.
            for k, v in list(nutrition_fields.items()):
                if isinstance(v, str):
                    nutrition_fields[k] = v.replace('_kJ', ' kJ').replace('Kcal', ' Kcal').replace('_g', ' g')
            energie_val = str(nutrition_fields.get('ENERGIE') or '').strip()
            if energie_val:
                energie_val = energie_val.replace(' kJ', 'kJ').replace(' Kcal', 'Kcal').replace(' kcal', 'kcal')
                nutrition_fields['ENERGIE'] = ' '.join(energie_val.split())
            gram_fields = ('FETT', 'DAVON_FETT', 'KOHLENHYDRATE', 'DAVON_ZUCKER', 'EIWIESS', 'SALZ')
            for field_key in gram_fields:
                raw_val = str(nutrition_fields.get(field_key) or '').strip()
                if not raw_val:
                    continue
                low = raw_val.lower()
                if low.endswith('g') or low.endswith('mg') or low.endswith('kg'):
                    continue
                nutrition_fields[field_key] = f"{raw_val} g"

            # 5. SPUREN
            settings = self.db.get_label_settings()
            spuren_enabled = settings.get('spuren_enabled', '1') == '1'
            spuren_text = settings.get('spuren_text_de', '') if spuren_enabled else ''

            # 6. Дата печати
            if print_date_str:
                try:
                    print_date = datetime.strptime(print_date_str, '%d.%m.%y')
                except ValueError:
                    print_date = datetime.now()
            else:
                print_date = datetime.now()

            # 7. VERBRAUCHSDATUM = дата печати + срок хранения
            shelf_life_raw = self._to_int_or_none(label_data.get('shelf_life_days'))
            if shelf_life_raw is None:
                verbrauchsdatum = ''
            else:
                expiry_date = print_date + timedelta(days=shelf_life_raw)
                verbrauchsdatum = expiry_date.strftime('%d.%m.%y')

            # 8. LOT = номер недели + год
            lot = print_date.strftime('%W%Y')

            # 9. Шаблон
            template_info = self.ETIKETT_TEMPLATES.get(
                region, ('DE+7.ezpx', r'\\server01\DATA\WISO_GOLABEL\etiketten\test')
            )
            template_name = template_info[0]
            template_dir = template_info[1]
            template_path = f"{template_dir}\\{template_name}"
            if not os.path.exists(template_path):
                fallback_name, fallback_dir = self.ETIKETT_TEMPLATES.get(
                    'DE (+7°C)', ('DE+7.ezpx', r'\\server01\DATA\WISO_GOLABEL\etiketten\test')
                )
                fallback_path = f"{fallback_dir}\\{fallback_name}"
                logger.warning(
                    "Etikett template not found for region '%s': %s. Fallback to: %s",
                    region, template_path, fallback_path
                )
                template_name = fallback_name
                template_path = fallback_path

            # 10. Регион для CSV
            # Собираем данные для текстового файла GoLabel (позиционные поля ^F00..^F13)
            # Вес всегда печатаем с граммами.
            weight_str = f"{int(label_data['weight_grams'])} g" if label_data.get('weight_grams') else ''
            barcode_raw = str(label_data.get('barcode') or '').strip()
            barcode_digits = ''.join(ch for ch in barcode_raw if ch.isdigit())
            # Для EAN-13 в большинстве шаблонов GoLabel ожидается 12 цифр без check digit.
            # Если в БД хранится 13-значный EAN, отдаем первые 12 (13-я контрольная).
            if len(barcode_digits) == 13:
                barcode_str = barcode_digits[:12]
            else:
                barcode_str = barcode_digits or barcode_raw

            csv_data = {
                'NAME': str(label_data.get('label_name') or ''),
                'KLEINE_NAME': label_data.get('label_full_name') or '',
                'GEWICHT': weight_str,
                'QR_CODE': barcode_str,
                'ZUTATEN': zutaten_text,
                'SPUREN': spuren_text,
                'VERBRAUCHSDATUM': verbrauchsdatum,
                'LOT': lot,
                **nutrition_fields
            }

            await websocket.send(json.dumps({
                'type': 'etikett_print_data',
                'success': True,
                'csv_data': csv_data,
                'template_name': template_name,
                'template_path': template_path,
                'quantity': quantity,
                'article_nr': article_nr,
                'allergens_present': allergens_present,
            }))

        except Exception as e:
            logger.error(f"Error building etikett data: {e}")
            await websocket.send(json.dumps({
                'type': 'etikett_print_data', 'success': False, 'error': str(e)
            }))


    # ============================================
    # RECIPE TREE (Рекурсивное дерево рецептов)
    # ============================================

    async def handle_get_recipe_tree(self, websocket, data: Dict) -> None:
        """
        Получить дерево рецепта (прямые потомки, один уровень).

        Request:
            article_nr: str

        Response:
            type: recipe_tree_data
            article_nr: str
            nodes: [...]
        """
        try:
            article_nr = data.get('article_nr')
            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'recipe_tree_data', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            nodes = self.db.get_recipe_tree(article_nr)
            recipe_name = self.db.get_recipe_name(article_nr)

            response = {
                'type': 'recipe_tree_data',
                'success': True,
                'article_nr': article_nr,
                'recipe_name': recipe_name,
                'count': len(nodes),
                'nodes': [n.to_dict() for n in nodes],
            }
            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error getting recipe tree: {e}")
            await websocket.send(json.dumps({
                'type': 'recipe_tree_data', 'success': False, 'error': str(e)
            }))

    async def handle_get_recipe_tree_full(self, websocket, data: Dict) -> None:
        """
        Получить полное дерево рецепта рекурсивно (все уровни, с названиями).

        Request:
            article_nr: str

        Response:
            type: recipe_tree_full_data
            article_nr: str
            tree: [{...children: [...]}]
        """
        try:
            article_nr = data.get('article_nr')
            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'recipe_tree_full_data', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            tree = self.db.get_recipe_tree_full(article_nr)
            # Автозаполнение V2-дерева для старых рецептов из legacy состава.
            if not tree:
                legacy = self.db.get_recipe_ingredients(article_nr)
                if legacy:
                    bootstrap_nodes = []
                    for idx, ri in enumerate(legacy):
                        bootstrap_nodes.append({
                            'child_type': 'ingredient',
                            'child_article_nr': None,
                            'child_ingredient_id': ri.ingredient.ingredient_id,
                            'weight_grams': float(ri.weight_grams or 0.0),
                            'loss_percent': 0.0,
                            'output_weight_grams': None,
                            'highlight_quid': bool(ri.highlight_quid),
                            'sort_order': int(ri.sort_override if ri.sort_override is not None else idx),
                            'notes': None,
                        })
                    self.db.save_recipe_tree(article_nr, bootstrap_nodes)
                    self.calculator.invalidate_cache(article_nr)
                    tree = self.db.get_recipe_tree_full(article_nr)
                else:
                    # Если это код составного ингредиента — строим дерево из sub_ingredients.
                    compound = self.db.get_ingredient_by_code(article_nr)
                    if compound and compound.is_compound:
                        subs = self.db.get_sub_ingredients(compound.ingredient_id)
                        if subs:
                            bootstrap_nodes = []
                            for idx, sub in enumerate(subs):
                                bootstrap_nodes.append({
                                    'child_type': 'ingredient',
                                    'child_article_nr': None,
                                    'child_ingredient_id': sub.ingredient.ingredient_id,
                                    'weight_grams': float(sub.weight_grams or 0.0),
                                    'loss_percent': 0.0,
                                    'output_weight_grams': None,
                                    'highlight_quid': bool(sub.highlight_quid),
                                    'sort_order': int(sub.sort_override if sub.sort_override is not None else idx),
                                    'notes': 'auto:from_compound_subs',
                                })
                            self.db.save_recipe_tree(article_nr, bootstrap_nodes)
                            self.calculator.invalidate_cache(article_nr)
                            tree = self.db.get_recipe_tree_full(article_nr)
            recipe_name = self.db.get_recipe_name(article_nr)

            response = {
                'type': 'recipe_tree_full_data',
                'success': True,
                'article_nr': article_nr,
                'recipe_name': recipe_name,
                'tree': tree,
            }
            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error getting full recipe tree: {e}")
            await websocket.send(json.dumps({
                'type': 'recipe_tree_full_data', 'success': False, 'error': str(e)
            }))

    async def handle_save_recipe_tree(self, websocket, data: Dict) -> None:
        """
        Сохранить дерево рецепта (полная перезапись прямых потомков).

        Request:
            article_nr: str
            nodes: [{child_type, child_article_nr, child_ingredient_id,
                     weight_grams, loss_percent, output_weight_grams,
                     highlight_quid, sort_order, notes}]

        Response:
            type: recipe_tree_saved
        """
        try:
            article_nr = data.get('article_nr')
            nodes = data.get('nodes', [])

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'recipe_tree_saved', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            self.db.save_recipe_tree(article_nr, nodes)

            # Сброс кэша калькулятора
            self.calculator.invalidate_cache(article_nr)

            # Пометить подтвержденный состав как устаревший
            self.db.mark_composition_outdated(article_nr)
            # Также пометить все рецепты, использующие этот как под-рецепт
            self.db.mark_compositions_outdated_for_sub_recipe(article_nr)

            response = {
                'type': 'recipe_tree_saved',
                'success': True,
                'article_nr': article_nr,
                'count': len(nodes),
                'message': f"Сохранено {len(nodes)} узлов для рецепта {article_nr}"
            }
            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error saving recipe tree: {e}")
            await websocket.send(json.dumps({
                'type': 'recipe_tree_saved', 'success': False, 'error': str(e)
            }))

    async def handle_add_tree_node(self, websocket, data: Dict) -> None:
        """
        Добавить один узел в дерево рецепта.

        Request:
            article_nr: str
            node: {child_type, child_article_nr|child_ingredient_id,
                   weight_grams, loss_percent, ...}

        Response:
            type: tree_node_added
            node_id: int
        """
        try:
            article_nr = data.get('article_nr')
            node = data.get('node', data)  # Поддержка плоской структуры

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'tree_node_added', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            node_id = self.db.add_tree_node(article_nr, node)
            self.calculator.invalidate_cache(article_nr)
            self.db.mark_composition_outdated(article_nr)

            await websocket.send(json.dumps({
                'type': 'tree_node_added',
                'success': True,
                'node_id': node_id,
                'article_nr': article_nr,
            }))

        except Exception as e:
            logger.error(f"Error adding tree node: {e}")
            await websocket.send(json.dumps({
                'type': 'tree_node_added', 'success': False, 'error': str(e)
            }))

    async def handle_update_tree_node(self, websocket, data: Dict) -> None:
        """
        Обновить узел дерева рецепта.

        Request:
            node_id: int
            weight_grams: float
            loss_percent: float (optional)
            ...

        Response:
            type: tree_node_updated
        """
        try:
            node_id = data.get('node_id')
            if not node_id:
                await websocket.send(json.dumps({
                    'type': 'tree_node_updated', 'success': False,
                    'error': 'node_id is required'
                }))
                return

            success = self.db.update_tree_node(node_id, data)

            # Сброс кэша для всех затронутых рецептов
            self.calculator.invalidate_cache()

            await websocket.send(json.dumps({
                'type': 'tree_node_updated',
                'success': success,
                'node_id': node_id,
            }))

        except Exception as e:
            logger.error(f"Error updating tree node: {e}")
            await websocket.send(json.dumps({
                'type': 'tree_node_updated', 'success': False, 'error': str(e)
            }))

    async def handle_delete_tree_node(self, websocket, data: Dict) -> None:
        """
        Удалить узел дерева рецепта.

        Request:
            node_id: int

        Response:
            type: tree_node_deleted
        """
        try:
            node_id = data.get('node_id')
            if not node_id:
                await websocket.send(json.dumps({
                    'type': 'tree_node_deleted', 'success': False,
                    'error': 'node_id is required'
                }))
                return

            success = self.db.delete_tree_node(node_id)
            self.calculator.invalidate_cache()

            await websocket.send(json.dumps({
                'type': 'tree_node_deleted',
                'success': success,
                'node_id': node_id,
            }))

        except Exception as e:
            logger.error(f"Error deleting tree node: {e}")
            await websocket.send(json.dumps({
                'type': 'tree_node_deleted', 'success': False, 'error': str(e)
            }))

    # ============================================
    # COMPOSITION CALCULATION (Расчет состава)
    # ============================================

    async def handle_calculate_composition(self, websocket, data: Dict) -> None:
        """
        Рассчитать полный состав продукта (рекурсивное развертывание).

        Это основной handler для двухоконного интерфейса.
        Возвращает автоматически рассчитанный состав (левая панель).

        Request:
            article_nr: str
            final_weight_grams: float (optional)
            language: str (optional, default 'de')

        Response:
            type: composition_calculated
            composition: {article_nr, product_name, ingredients: [...], ...}
            label_text: str
            confirmed: {text, is_outdated, ...} | null
        """
        try:
            article_nr = data.get('article_nr')
            final_weight = data.get('final_weight_grams')
            language_code = data.get('language', 'de')

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'composition_calculated', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            # Рассчитываем состав
            resolved_article_nr, result = self._find_composition_with_fallback(article_nr, final_weight)
            if not result:
                await websocket.send(json.dumps({
                    'type': 'composition_calculated', 'success': False,
                    'error': f'Recipe {article_nr} not found or has no tree structure'
                }))
                return

            # Генерируем текст этикетки
            try:
                lang = Language(language_code)
            except ValueError:
                lang = Language.DE

            label = generate_label_from_composition(result, lang, db=self.db)
            compliance_issues = self.calculator.get_label_compliance_issues(result, language_code)
            compliance_issues_detail = self.calculator.get_label_compliance_issues_detailed(result, language_code)
            label_compact_info = self.calculator.generate_label_text_compact(result, language_code)

            # Nutrition debug from calculated flat composition (absolute weights).
            nutrition_debug_items = []
            nutrition_totals = {}
            try:
                pseudo_ingredients = []
                for fi in (result.flat_ingredients or []):
                    pseudo_ingredients.append(RecipeIngredient(
                        ingredient=fi.ingredient,
                        weight_grams=float(fi.absolute_weight or 0.0),
                        highlight_quid=False,
                        sort_override=None,
                    ))

                nutrition = calculate_nutrition(pseudo_ingredients, float(result.final_product_weight or 0.0))
                if nutrition:
                    nutrition_totals = {
                        'energy_kj': nutrition.energy_kj,
                        'energy_kcal': nutrition.energy_kcal,
                        'fat': nutrition.fat,
                        'saturated_fat': nutrition.saturated_fat,
                        'carbs': nutrition.carbs,
                        'sugar': nutrition.sugar,
                        'protein': nutrition.protein,
                        'salt': nutrition.salt,
                    }

                # Ингредиенты без данных о пищевой ценности (причина занижения kcal).
                # Если kcal_per_100g = NULL → вклад в энергию = 0.
                nutrition_missing_data = []
                for fi in (result.flat_ingredients or []):
                    ing = fi.ingredient
                    w = float(fi.absolute_weight or 0.0)
                    if w > 0 and ing.kcal_per_100g is None:
                        nutrition_missing_data.append({
                            'name': str(ing.name.de or ing.ingredient_code or ''),
                            'weight_grams': round(w, 2),
                            'weight_pct': round(w / float(result.final_product_weight or 1.0) * 100, 1),
                        })
                nutrition_totals['missing_data_ingredients'] = nutrition_missing_data

                for fi in (result.flat_ingredients or []):
                        ing = fi.ingredient
                        w = float(fi.absolute_weight or 0.0)
                        if w <= 0:
                            continue

                        k = (w / 100.0)
                        raw_kj = (k * (ing.kj_per_100g or ((ing.kcal_per_100g or 0.0) * 4.184))) if (
                            ing.kj_per_100g is not None or ing.kcal_per_100g is not None
                        ) else 0.0
                        raw_kcal = (k * (ing.kcal_per_100g or 0.0)) if ing.kcal_per_100g is not None else 0.0
                        raw_fat = k * (ing.fat_per_100g or 0.0)
                        raw_sat = k * (ing.saturated_fat_per_100g or 0.0)
                        raw_carbs = k * (ing.carbs_per_100g or 0.0)
                        raw_sugar = k * (ing.sugar_per_100g or 0.0)
                        raw_protein = k * (ing.protein_per_100g or 0.0)
                        raw_salt = k * (ing.salt_per_100g or 0.0)

                        if any([
                            raw_kj, raw_kcal, raw_fat, raw_sat, raw_carbs, raw_sugar, raw_protein, raw_salt
                        ]):
                            nutrition_debug_items.append({
                                'name': str(ing.name.de or ing.ingredient_code or ''),
                                'weight_grams': round(w, 2),
                                'energy_kj_raw': round(raw_kj, 2),
                                'energy_kcal_raw': round(raw_kcal, 2),
                                'fat_raw': round(raw_fat, 3),
                                'saturated_fat_raw': round(raw_sat, 3),
                                'carbs_raw': round(raw_carbs, 3),
                                'sugar_raw': round(raw_sugar, 3),
                                'protein_raw': round(raw_protein, 3),
                                'salt_raw': round(raw_salt, 3),
                            })
            except Exception as _nex:
                logger.warning(f"Nutrition debug build failed: {_nex}")

            # Получаем подтвержденный состав
            confirmed = self.db.get_confirmed_composition(article_nr)
            if not confirmed and resolved_article_nr != article_nr:
                confirmed = self.db.get_confirmed_composition(resolved_article_nr)

            # Проверяем актуальность: сравниваем хеш
            confirmed_data = None
            if confirmed:
                is_outdated = confirmed.is_outdated or (
                    confirmed.recipe_hash and confirmed.recipe_hash != result.recipe_hash
                )
                # Если хеш не совпадает, помечаем как устаревший
                if is_outdated and not confirmed.is_outdated:
                    self.db.mark_composition_outdated(confirmed.article_nr)

                confirmed_data = confirmed.to_dict()
                confirmed_data['is_outdated'] = is_outdated

            response = {
                'type': 'composition_calculated',
                'success': True,
                'composition': result.to_dict(),
                'label_text': label.label_text,
                'label_text_compact': label_compact_info.get('compact'),
                'label_was_shortened': label_compact_info.get('was_shortened', False),
                'label_chars_count': label_compact_info.get('chars_full', 0),
                'label_compact_chars_count': label_compact_info.get('chars_compact'),
                'label_debug_items': self.calculator.get_label_debug_items(result, language_code),
                'etikettenkonform': len(compliance_issues) == 0,
                'compliance_issues': compliance_issues,
                'compliance_issues_detail': compliance_issues_detail,
                'allergens_present': label.allergens_present,
                'recipe_hash': result.recipe_hash,
                'confirmed': confirmed_data,
                'nutrition_totals': nutrition_totals,
                'nutrition_debug_items': nutrition_debug_items,
            }
            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error calculating composition: {e}")
            await websocket.send(json.dumps({
                'type': 'composition_calculated', 'success': False, 'error': str(e)
            }))

    async def handle_calculate_composition_all_languages(self, websocket, data: Dict) -> None:
        """
        Рассчитать состав и сгенерировать этикетки на всех языках.

        Request:
            article_nr: str
            final_weight_grams: float (optional)

        Response:
            type: composition_all_languages
            labels: {de: ..., nl: ..., fr: ...}
        """
        try:
            article_nr = data.get('article_nr')
            final_weight = data.get('final_weight_grams')

            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'composition_all_languages', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            _, result = self._find_composition_with_fallback(article_nr, final_weight)
            if not result:
                await websocket.send(json.dumps({
                    'type': 'composition_all_languages', 'success': False,
                    'error': f'Recipe {article_nr} not found'
                }))
                return

            labels = generate_all_languages_from_composition(result, db=self.db)

            response = {
                'type': 'composition_all_languages',
                'success': True,
                'article_nr': article_nr,
                'recipe_name': result.product_name,
                'labels': {
                    lang: {
                        'label_text': label.label_text,
                        'allergens_present': label.allergens_present,
                    }
                    for lang, label in labels.items()
                }
            }
            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error calculating all languages: {e}")
            await websocket.send(json.dumps({
                'type': 'composition_all_languages', 'success': False, 'error': str(e)
            }))

    # ============================================
    # CONFIRMED COMPOSITIONS (Подтверждение состава)
    # ============================================

    async def handle_get_confirmed_composition(self, websocket, data: Dict) -> None:
        """
        Получить подтвержденный состав для артикула.

        Request:
            article_nr: str

        Response:
            type: confirmed_composition_data
        """
        try:
            article_nr = data.get('article_nr')
            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'confirmed_composition_data', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            confirmed = self.db.get_confirmed_composition(article_nr)

            response = {
                'type': 'confirmed_composition_data',
                'success': True,
                'article_nr': article_nr,
                'confirmed': confirmed.to_dict() if confirmed else None,
            }
            await websocket.send(json.dumps(response))

        except Exception as e:
            logger.error(f"Error getting confirmed composition: {e}")
            await websocket.send(json.dumps({
                'type': 'confirmed_composition_data', 'success': False, 'error': str(e)
            }))

    async def handle_confirm_composition(self, websocket, data: Dict) -> None:
        """
        Подтвердить (сохранить) ручной состав для этикетки.

        Request:
            article_nr: str
            confirmed_text_de: str
            confirmed_text_nl: str (optional)
            confirmed_text_fr: str (optional)
            confirmed_by: str (optional)

        Response:
            type: composition_confirmed
        """
        try:
            article_nr = data.get('article_nr')
            if not article_nr:
                await websocket.send(json.dumps({
                    'type': 'composition_confirmed', 'success': False,
                    'error': 'article_nr is required'
                }))
                return

            if not data.get('confirmed_text_de'):
                await websocket.send(json.dumps({
                    'type': 'composition_confirmed', 'success': False,
                    'error': 'confirmed_text_de is required'
                }))
                return

            # Рассчитываем текущий хеш и автотекст
            result = self.calculator.calculate(article_nr)
            recipe_hash = result.recipe_hash if result else ''
            auto_text = ''
            if result:
                label = generate_label_from_composition(result, Language.DE, db=self.db)
                auto_text = label.label_text

            save_data = {
                'confirmed_text_de': data.get('confirmed_text_de'),
                'confirmed_text_nl': data.get('confirmed_text_nl'),
                'confirmed_text_fr': data.get('confirmed_text_fr'),
                'auto_generated_text_de': auto_text,
                'recipe_hash': recipe_hash,
                'confirmed_by': data.get('confirmed_by', ''),
            }

            record_id = self.db.save_confirmed_composition(article_nr, save_data)

            await websocket.send(json.dumps({
                'type': 'composition_confirmed',
                'success': True,
                'article_nr': article_nr,
                'id': record_id,
                'message': f'Состав для {article_nr} подтвержден'
            }))

        except Exception as e:
            logger.error(f"Error confirming composition: {e}")
            await websocket.send(json.dumps({
                'type': 'composition_confirmed', 'success': False, 'error': str(e)
            }))

    async def handle_invalidate_composition_cache(self, websocket, data: Dict) -> None:
        """
        Сброс кэша калькулятора.

        Request:
            article_nr: str (optional, если не указан — сброс всего кэша)

        Response:
            type: composition_cache_invalidated
        """
        try:
            article_nr = data.get('article_nr')
            self.calculator.invalidate_cache(article_nr)

            await websocket.send(json.dumps({
                'type': 'composition_cache_invalidated',
                'success': True,
                'article_nr': article_nr,
            }))

        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            await websocket.send(json.dumps({
                'type': 'composition_cache_invalidated', 'success': False, 'error': str(e)
            }))


# ============================================
# ROUTE MAPPING
# ============================================

def get_zutaten_message_handlers(api: ZutatenAPIHandlers) -> Dict[str, callable]:
    """
    Возвращает маппинг типов сообщений на handlers.

    Использование в server_unified.py:
        zutaten_handlers = get_zutaten_message_handlers(zutaten_api)

        # В handle_message():
        if msg_type in zutaten_handlers:
            await zutaten_handlers[msg_type](websocket, data)
    """
    return {
        # Справочники
        'get_allergens': api.handle_get_allergens,
        'save_allergen': api.handle_save_allergen,
        'delete_allergen': api.handle_delete_allergen,
        'get_additive_classes': api.handle_get_additive_classes,
        'get_zutaten_recipes': api.handle_get_zutaten_recipes,

        # Ингредиенты
        'get_all_ingredients': api.handle_get_all_ingredients,
        'get_ingredient': api.handle_get_ingredient,
        'save_ingredient': api.handle_save_ingredient,
        'delete_ingredient': api.handle_delete_ingredient,
        'search_ingredients': api.handle_search_ingredients,

        # Ингредиенты рецепта (legacy — плоская структура)
        'get_recipe_ingredients': api.handle_get_recipe_ingredients,
        'save_recipe_ingredients': api.handle_save_recipe_ingredients,

        # Генерация этикеток (legacy — из плоской структуры)
        'generate_zutaten_label': api.handle_generate_zutaten_label,
        'generate_all_languages': api.handle_generate_all_languages,

        # Печать этикеток (Etikett)
        'print_etikett': api.handle_print_etikett,
        'get_recipe_label_data': api.handle_get_recipe_label_data,
        'save_recipe_label_data': api.handle_save_recipe_label_data,
        'sync_label_from_tree': api.handle_sync_label_from_tree,
        'get_label_settings': api.handle_get_label_settings,
        'save_label_setting': api.handle_save_label_setting,

        # === V2: Рекурсивное дерево рецептов ===
        'get_recipe_tree': api.handle_get_recipe_tree,
        'get_recipe_tree_full': api.handle_get_recipe_tree_full,
        'save_recipe_tree': api.handle_save_recipe_tree,
        'add_tree_node': api.handle_add_tree_node,
        'update_tree_node': api.handle_update_tree_node,
        'delete_tree_node': api.handle_delete_tree_node,

        # === V2: Расчет состава (рекурсивный) ===
        'calculate_composition': api.handle_calculate_composition,
        'calculate_composition_all_languages': api.handle_calculate_composition_all_languages,
        'invalidate_composition_cache': api.handle_invalidate_composition_cache,

        # === V2: Подтверждение состава ===
        'get_confirmed_composition': api.handle_get_confirmed_composition,
        'confirm_composition': api.handle_confirm_composition,
    }
