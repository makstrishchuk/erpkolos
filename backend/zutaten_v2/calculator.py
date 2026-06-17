"""
CompositionCalculator — рекурсивный калькулятор состава продукта.

Развертывает дерево рецептов (Торт -> Бисквит -> Мука + Сахар + ...)
до уровня сырья, рассчитывает абсолютные веса, группирует одинаковые
ингредиенты и формирует отсортированный список для Zutatenliste.

Правила LMIV EU 1169/2011:
- Art. 18: Сортировка по убыванию веса
- Art. 21: Выделение аллергенов
- Art. 22: QUID проценты
- Annex VII Part A: Расчет воды (порог 5%)
- Annex VII Part E: Составные ингредиенты (правило 2%)
"""

import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .models import (
    CompositionResult,
    FlatIngredient,
    IngredientMaster,
    RecipeTreeNode,
)

logger = logging.getLogger(__name__)

# Максимальная глубина рекурсии (защита от циклов)
MAX_RECURSION_DEPTH = 20

# Порог воды: не указывается если < 5% от готового продукта
WATER_THRESHOLD_PERCENT = 5.0

# Порог для составных ингредиентов (Annex VII Part E, 2%)
COMPOUND_THRESHOLD_PERCENT = 2.0

# Ошибки, при которых этикетка юридически невалидна (блокирующие).
# Остальные — предупреждения, этикетка всё равно генерируется.
BLOCKING_LABEL_ERRORS = frozenset({
    "forbidden_designation_in_final_output",
    "internal_code_in_final_output",
    "forbidden_or_code_like_name_not_expandable",
    "compound_cycle_detected",
})

# Terms that must not appear as legal ingredient designations in final label text.
FORBIDDEN_LABEL_TOKENS = {
    "typ",
    "spezial",
    "rsposg",
    "rspo",
    "sg",
    "kaltcreme",
    "backmischung",
    "backhonig",
}

FORBIDDEN_LABEL_PHRASES = {
    "meister biskuit spezial",
    "dawn kaltcreme 2000 rspo sg",
    "margarine baker's",
    "vollei",
    "backhonig typ blute hell",
}

# Маппинг запрещённых/торговых названий → каноническое название этикетки.
# Если у составного ингредиента запрещённое имя И есть alias — он ПЕРЕИМЕНОВЫВАЕТСЯ
# (не разворачивается), т.е. показывается как "Margarine (Rapsöl, Palmöl, ...)".
# Для НЕ-составных ингредиентов — просто переименовывается без ошибки.
FORBIDDEN_NAME_ALIASES: Dict[str, str] = {
    "margarine baker's": "Margarine",
    "vollei": "Ei",
    "backhonig typ blute hell": "Honig",
}

# Canonical-нормализация имён для дедупликации и вывода.
# После нормализации ингредиенты с одинаковым canonical-именем мёрджируются.
NAME_NORMALIZATIONS: Dict[str, str] = {
    "weißzucker": "Zucker",
    "wasser": "Wasser",
    "modifizieren stärke": "modifizierte Stärke",
    "modifizierte stärke (kartoffel)": "modifizierte Stärke",
    "weizenstärke": "modifizierte Stärke",
}

# Точечные исправления опечаток и кодировок в названиях ингредиентов.
TEXT_CORRECTIONS: List[Tuple[str, str]] = [
    ("Sonn enblume", "Sonnenblume"),
    ("Speisefettsaeuren", "Speisefettsäuren"),
    ("Speisefettsaüren", "Speisefettsäuren"),
    ("Zuckerrübernsirup", "Zuckerrübensirup"),
    ("Modifizieren Stärke", "modifizierte Stärke"),
]


class CompositionCalculator:
    """
    Рекурсивный калькулятор состава продукта.

    Принимает article_nr готового продукта и рассчитывает полный
    развернутый состав с абсолютными весами каждого сырьевого ингредиента.

    Использование:
        calc = CompositionCalculator(db)
        result = calc.calculate('05502')
        # result.flat_ingredients — отсортированный список
        # result.recipe_hash — хеш для детекции изменений
    """

    def __init__(self, db):
        """
        Args:
            db: ZutatenDatabase instance
        """
        self.db = db
        self._cache: Dict[str, Tuple[CompositionResult, float]] = {}
        self._cache_ttl = 300  # 5 минут

    def invalidate_cache(self, article_nr: str = None):
        """Сброс кэша. Если article_nr=None, сбрасывает всё."""
        if article_nr:
            self._cache.pop(article_nr, None)
        else:
            self._cache.clear()

    def calculate(self, article_nr: str, final_weight: float = None) -> Optional[CompositionResult]:
        """
        Основной метод: рассчитывает полный состав продукта.

        Args:
            article_nr: Артикул продукта (торта)
            final_weight: Вес готового продукта (г). Если None — считается из дерева.

        Returns:
            CompositionResult или None если рецепт не найден
        """
        # Проверяем кэш
        cached = self._cache.get(article_nr)
        if cached:
            result, cached_at = cached
            if time.time() - cached_at < self._cache_ttl:
                # Если final_weight изменился, пересчитаем
                if final_weight is None or abs(result.final_product_weight - final_weight) < 0.01:
                    return result

        # Загружаем дерево рецепта
        tree_nodes = self.db.get_recipe_tree(article_nr)
        if not tree_nodes:
            # Fallback: если дерево не заведено, считаем по legacy recipe_ingredients.
            legacy_result = self._calculate_from_legacy_recipe_ingredients(article_nr, final_weight)
            if legacy_result:
                return legacy_result
            # Второй fallback: если это код составного ингредиента.
            return self._calculate_from_compound_ingredient(article_nr, final_weight)

        # Получаем название продукта
        product_name = self.db.get_recipe_name(article_nr) or article_nr

        # Рекурсивно развертываем дерево
        visited: Set[str] = {article_nr}
        raw_ingredients: Dict[int, FlatIngredient] = {}
        max_depth = [0]

        total_input = self._flatten_tree(
            article_nr=article_nr,
            tree_nodes=tree_nodes,
            scale_factor=1.0,
            depth=0,
            visited=visited,
            raw_ingredients=raw_ingredients,
            max_depth=max_depth,
            path=[product_name],
        )

        if not raw_ingredients:
            return None

        # Рассчитываем конечный вес продукта
        if final_weight is None:
            # Считаем на основе потерь: суммируем net_weight всех прямых узлов
            final_weight = self._calculate_final_weight(tree_nodes, total_input)

        # Обработка воды: учитываем испарение
        self._process_water(raw_ingredients, total_input, final_weight)

        # Рассчитываем проценты и сортируем
        flat_list = list(raw_ingredients.values())
        for fi in flat_list:
            fi.percentage = (fi.absolute_weight / final_weight * 100) if final_weight > 0 else 0

        # Сортировка по убыванию веса (Art. 18 LMIV)
        flat_list.sort(key=lambda x: -x.absolute_weight)

        # Генерируем хеш рецепта для детекции изменений
        recipe_hash = self._compute_hash(article_nr, tree_nodes, raw_ingredients)

        result = CompositionResult(
            article_nr=article_nr,
            product_name=product_name,
            flat_ingredients=flat_list,
            total_input_weight=total_input,
            final_product_weight=final_weight,
            recipe_hash=recipe_hash,
            tree_depth=max_depth[0],
        )

        # Кэшируем
        self._cache[article_nr] = (result, time.time())

        return result

    def _calculate_from_legacy_recipe_ingredients(
        self,
        article_nr: str,
        final_weight: float = None,
    ) -> Optional[CompositionResult]:
        """Fallback-расчет состава из recipe_ingredients, когда дерево V2 пустое."""
        legacy_ingredients = self.db.get_recipe_ingredients(article_nr)
        if not legacy_ingredients:
            return None

        product_name = self.db.get_recipe_name(article_nr) or article_nr
        raw_ingredients: Dict[int, FlatIngredient] = {}
        total_input = 0.0

        for rec_ing in legacy_ingredients:
            weight = float(rec_ing.weight_grams or 0.0)
            if weight <= 0:
                continue
            total_input += weight
            self._accumulate_flat_ingredient(
                raw_ingredients=raw_ingredients,
                ingredient=rec_ing.ingredient,
                net_weight=weight,
                highlight_quid=bool(rec_ing.highlight_quid),
                path=[product_name],
            )

        if not raw_ingredients:
            return None

        if final_weight is None:
            final_weight = total_input if total_input > 0 else 1.0

        self._process_water(raw_ingredients, total_input, final_weight)

        flat_list = list(raw_ingredients.values())
        for fi in flat_list:
            fi.percentage = (fi.absolute_weight / final_weight * 100) if final_weight > 0 else 0
        flat_list.sort(key=lambda x: -x.absolute_weight)

        recipe_hash = self._compute_hash(article_nr, [], raw_ingredients)
        return CompositionResult(
            article_nr=article_nr,
            product_name=product_name,
            flat_ingredients=flat_list,
            total_input_weight=total_input,
            final_product_weight=final_weight,
            recipe_hash=recipe_hash,
            tree_depth=1,
        )

    def _calculate_from_compound_ingredient(
        self,
        article_nr: str,
        final_weight: float = None,
    ) -> Optional[CompositionResult]:
        """Fallback-расчет для составного ингредиента по его суб-ингредиентам."""
        base = self.db.get_ingredient_by_code(article_nr)
        if not base or not base.is_compound:
            return None

        subs = self.db.get_sub_ingredients(base.ingredient_id)
        if not subs:
            return None

        raw_ingredients: Dict[int, FlatIngredient] = {}
        total_input = 0.0
        product_name = base.name.de or article_nr

        for sub in subs:
            weight = float(sub.weight_grams or 0.0)
            if weight <= 0:
                continue
            total_input += weight
            self._accumulate_flat_ingredient(
                raw_ingredients=raw_ingredients,
                ingredient=sub.ingredient,
                net_weight=weight,
                highlight_quid=bool(sub.highlight_quid),
                path=[product_name],
            )

        if not raw_ingredients:
            return None

        if final_weight is None:
            if getattr(base, 'compound_total_grams', None):
                try:
                    final_weight = float(base.compound_total_grams)
                except Exception:
                    final_weight = total_input
            else:
                final_weight = total_input

        self._process_water(raw_ingredients, total_input, final_weight)

        flat_list = list(raw_ingredients.values())
        for fi in flat_list:
            fi.percentage = (fi.absolute_weight / final_weight * 100) if final_weight > 0 else 0
        flat_list.sort(key=lambda x: -x.absolute_weight)

        recipe_hash = self._compute_hash(article_nr, [], raw_ingredients)
        return CompositionResult(
            article_nr=article_nr,
            product_name=product_name,
            flat_ingredients=flat_list,
            total_input_weight=total_input,
            final_product_weight=final_weight,
            recipe_hash=recipe_hash,
            tree_depth=1,
        )

    def _flatten_tree(
        self,
        article_nr: str,
        tree_nodes: List[RecipeTreeNode],
        scale_factor: float,
        depth: int,
        visited: Set[str],
        raw_ingredients: Dict[int, FlatIngredient],
        max_depth: List[int],
        path: List[str],
    ) -> float:
        """
        Рекурсивно развертывает дерево рецепта до сырьевых ингредиентов.

        Args:
            article_nr: Текущий артикул рецепта
            tree_nodes: Узлы дерева для текущего рецепта
            scale_factor: Масштабирующий коэффициент (доля от родителя)
            depth: Текущая глубина рекурсии
            visited: Множество посещенных артикулов (защита от циклов)
            raw_ingredients: Аккумулятор сырьевых ингредиентов {ingredient_id: FlatIngredient}
            max_depth: Максимальная достигнутая глубина [mutable]
            path: Путь от корня ["Торт", "Бисквит", ...]

        Returns:
            Суммарный входной вес этого уровня (масштабированный)
        """
        if depth > MAX_RECURSION_DEPTH:
            logger.warning(f"Max recursion depth reached for {article_nr}")
            return 0.0

        max_depth[0] = max(max_depth[0], depth)
        total_input = 0.0

        for node in tree_nodes:
            scaled_weight = node.weight_grams * scale_factor
            total_input += scaled_weight

            if node.child_type == 'ingredient':
                # Листовой узел: сырьевой ингредиент
                ingredient = self.db.get_ingredient_by_id(node.child_ingredient_id)
                if not ingredient:
                    logger.warning(f"Ingredient {node.child_ingredient_id} not found, skipping")
                    continue

                # Нетто-вес после потерь обработки этого конкретного узла
                net_weight = scaled_weight * (1.0 - node.loss_percent / 100.0)

                self._accumulate_flat_ingredient(
                    raw_ingredients=raw_ingredients,
                    ingredient=ingredient,
                    net_weight=net_weight,
                    highlight_quid=node.highlight_quid,
                    path=path,
                )

            elif node.child_type == 'recipe':
                # Промежуточный узел: вложенный рецепт (полуфабрикат)
                child_article = node.child_article_nr
                if child_article in visited:
                    logger.warning(f"Circular reference detected: {child_article} in {visited}")
                    continue

                # Загружаем дерево вложенного рецепта
                child_tree = self.db.get_recipe_tree(child_article)
                if not child_tree:
                    logger.warning(f"Sub-recipe {child_article} has no tree nodes, skipping")
                    continue

                child_name = self.db.get_recipe_name(child_article) or child_article

                # Рассчитываем масштаб: сколько от полного рецепта мы используем
                # output_weight_grams = вес готового полуфабриката из полного замеса
                # weight_grams (scaled) = сколько этого полуфабриката мы берем в родительский рецепт
                child_total_input = sum(n.weight_grams for n in child_tree)

                if node.output_weight_grams and node.output_weight_grams > 0:
                    # Выход готового полуфабриката задан явно
                    child_output = node.output_weight_grams
                else:
                    # Считаем выход с учетом потерь
                    child_output = child_total_input * (1.0 - node.loss_percent / 100.0)

                if child_output <= 0:
                    continue

                # Масштаб: берем scaled_weight из child_output
                child_scale = scaled_weight / child_output

                visited.add(child_article)
                self._flatten_tree(
                    article_nr=child_article,
                    tree_nodes=child_tree,
                    scale_factor=child_scale,
                    depth=depth + 1,
                    visited=visited,
                    raw_ingredients=raw_ingredients,
                    max_depth=max_depth,
                    path=path + [child_name],
                )
                visited.discard(child_article)

        return total_input

    def _accumulate_flat_ingredient(
        self,
        raw_ingredients: Dict[int, FlatIngredient],
        ingredient: IngredientMaster,
        net_weight: float,
        highlight_quid: bool,
        path: List[str],
        depth: int = 0,
    ) -> None:
        """Добавить ингредиент в плоский список с поддержкой разворачивания составных."""
        if not ingredient or net_weight <= 0:
            return
        if depth > 8:
            return

        if ingredient.is_compound and not ingredient.sub_ingredients:
            ingredient.sub_ingredients = self.db.get_sub_ingredients(ingredient.ingredient_id)

        if ingredient.is_compound and ingredient.sub_ingredients:
            # Keep compound ingredient as a top-level label item by default.
            # Expand only if explicitly configured or legal filter forbids parent designation.
            parent_name = str(ingredient.name.de or ingredient.ingredient_code or "")
            must_expand = bool(getattr(ingredient, "expand_sub_ingredients_only", False))
            # Deklarationsname acts as an explicit alias — never expand, regardless of
            # expand_sub_ingredients_only flag or forbidden-name detection.
            has_declaration_name = bool(
                getattr(ingredient, 'declaration_name', None)
                and ingredient.declaration_name
                and ingredient.declaration_name.de
            )
            if has_declaration_name:
                must_expand = False
            elif self._contains_forbidden_designation(parent_name):
                # Если есть canonical-alias — НЕ разворачиваем, оставляем как compound.
                # "Margarine Baker's" → остаётся как compound, позже переименуется в "Margarine".
                if not FORBIDDEN_NAME_ALIASES.get(parent_name.strip().lower()):
                    must_expand = True

            if must_expand:
                total_sub_weight = sum(max(0.0, float(s.weight_grams or 0.0)) for s in ingredient.sub_ingredients)
                if total_sub_weight > 0:
                    for sub in ingredient.sub_ingredients:
                        sub_weight = max(0.0, float(sub.weight_grams or 0.0))
                        if sub_weight <= 0:
                            continue
                        share = sub_weight / total_sub_weight
                        self._accumulate_flat_ingredient(
                            raw_ingredients=raw_ingredients,
                            ingredient=sub.ingredient,
                            net_weight=net_weight * share,
                            highlight_quid=highlight_quid,
                            path=path + [ingredient.name.de],
                            depth=depth + 1,
                        )
                    return

        ing_id = ingredient.ingredient_id
        if ing_id in raw_ingredients:
            raw_ingredients[ing_id].absolute_weight += net_weight
            new_path = path + [ingredient.name.de]
            path_str = ' > '.join(new_path)
            if path_str not in raw_ingredients[ing_id].source_path:
                raw_ingredients[ing_id].source_path.append(path_str)
        else:
            raw_ingredients[ing_id] = FlatIngredient(
                ingredient=ingredient,
                absolute_weight=net_weight,
                highlight_quid=highlight_quid,
                source_path=[' > '.join(path + [ingredient.name.de])],
            )

    def _calculate_final_weight(self, tree_nodes: List[RecipeTreeNode], total_input: float) -> float:
        """
        Рассчитывает вес готового продукта на основе потерь.

        Для каждого прямого узла дерева учитываем loss_percent.
        Если у узла задан output_weight_grams — используем его приоритетно
        (согласовано с _flatten_tree()).
        """
        total_output = 0.0
        for node in tree_nodes:
            if node.output_weight_grams and node.output_weight_grams > 0:
                net = float(node.output_weight_grams)
            else:
                net = node.weight_grams * (1.0 - node.loss_percent / 100.0)
            total_output += net

        return total_output if total_output > 0 else total_input * 0.9

    def _process_water(
        self,
        raw_ingredients: Dict[int, FlatIngredient],
        total_input: float,
        final_weight: float,
    ):
        """
        Обработка воды по правилам LMIV (Annex VII Part A).

        Вода указывается только если > 5% готового продукта.
        Учитывает испарение при выпечке.
        """
        # Находим все ингредиенты-воду
        water_ids = [
            ing_id for ing_id, fi in raw_ingredients.items()
            if fi.ingredient.is_added_water
        ]

        if not water_ids:
            return

        # Суммарная вода на входе
        total_water_input = sum(raw_ingredients[wid].absolute_weight for wid in water_ids)

        # Влагопотеря при обработке
        moisture_loss = total_input - final_weight
        if moisture_loss < 0:
            moisture_loss = 0

        # Остаточная вода
        water_remaining = total_water_input - moisture_loss
        if water_remaining <= 0:
            # Вся вода испарилась — удаляем из списка
            for wid in water_ids:
                del raw_ingredients[wid]
            return

        # Процент воды в готовом продукте
        water_percent = (water_remaining / final_weight * 100) if final_weight > 0 else 0

        if water_percent < WATER_THRESHOLD_PERCENT:
            # Менее 5% — не указываем
            for wid in water_ids:
                del raw_ingredients[wid]
            return

        # Обновляем вес воды (остаточный)
        # Если несколько записей воды, оставляем одну с суммарным весом
        first_water_id = water_ids[0]
        raw_ingredients[first_water_id].absolute_weight = water_remaining
        for wid in water_ids[1:]:
            del raw_ingredients[wid]

    def _compute_hash(
        self,
        article_nr: str,
        tree_nodes: List[RecipeTreeNode],
        raw_ingredients: Dict[int, FlatIngredient],
    ) -> str:
        """
        Вычисляет хеш рецепта для детекции изменений.

        Включает структуру дерева и веса ингредиентов.
        """
        hash_data = {
            'article_nr': article_nr,
            'tree': [
                {
                    'child_type': n.child_type,
                    'child_article_nr': n.child_article_nr,
                    'child_ingredient_id': n.child_ingredient_id,
                    'weight_grams': n.weight_grams,
                    'loss_percent': n.loss_percent,
                }
                for n in tree_nodes
            ],
            'ingredients': sorted([
                {
                    'id': ing_id,
                    'weight': round(fi.absolute_weight, 2),
                }
                for ing_id, fi in raw_ingredients.items()
            ], key=lambda x: x['id']),
        }
        hash_str = json.dumps(hash_data, sort_keys=True)
        return hashlib.md5(hash_str.encode()).hexdigest()

    @staticmethod
    def _normalize_spaces(text: str) -> str:
        return re.sub(r"\s{2,}", " ", str(text or "")).strip()

    @staticmethod
    def _apply_text_corrections(name: str) -> str:
        """Исправляет известные опечатки и проблемы кодировки в именах ингредиентов."""
        for wrong, correct in TEXT_CORRECTIONS:
            name = re.sub(re.escape(wrong), correct, name, flags=re.IGNORECASE)
        return name

    @staticmethod
    def _normalize_e_number(raw_value: str) -> str:
        value = str(raw_value or "").strip().upper()
        if not value:
            return ""
        m = re.search(r"E\s*[- ]?\s*(\d{3,4}[A-Z]?)", value)
        if m:
            return f"E{m.group(1)}"
        # If already numeric-like additive number without E prefix.
        m2 = re.fullmatch(r"(\d{3,4}[A-Z]?)", value)
        if m2:
            return f"E{m2.group(1)}"
        return value

    def _contains_forbidden_designation(self, name: str) -> bool:
        text = self._normalize_spaces(name).lower()
        if not text:
            return False
        if text in FORBIDDEN_LABEL_PHRASES:
            return True

        compact = re.sub(r"[^a-z0-9]+", "", text)
        for phrase in FORBIDDEN_LABEL_PHRASES:
            if phrase and re.sub(r"[^a-z0-9]+", "", phrase) == compact:
                return True

        words = [w for w in re.split(r"[^a-z0-9]+", text) if w]
        for token in words:
            if token in FORBIDDEN_LABEL_TOKENS:
                return True
        return False

    @staticmethod
    def _looks_like_internal_code(name: str) -> bool:
        text = str(name or "").strip()
        if not text:
            return False
        # Typical code-like names: mostly uppercase/digits/separators and include digits.
        if re.fullmatch(r"[A-Z0-9][A-Z0-9 _./'-]{4,}", text) and re.search(r"\d", text):
            return True
        return False

    def _format_base_name(self, ing: IngredientMaster, lang) -> tuple[str, bool]:
        """Return (display_name, additive_format_ok)."""
        from .translations import (
            get_additive_class_name,
            get_hydrogenation_text,
        )

        # Deklarationsname overrides all other formatting:
        # bypasses forbidden-token checks, oil/fat formatting, and additive prefix logic.
        if getattr(ing, 'declaration_name', None) and ing.declaration_name:
            decl = self._normalize_spaces(ing.declaration_name.get(lang))
            if decl:
                return decl, True

        base_name = self._normalize_spaces(ing.name.get(lang))
        additive_format_ok = True

        if ing.additive_class_code:
            class_name = get_additive_class_name(ing.additive_class_code, lang)
            e_number = self._normalize_e_number(ing.e_number)
            if e_number:
                base_name = f"{class_name}: {e_number}"
            else:
                # Keep legal class prefix even when E-number missing, but flag as non-conform.
                base_name = f"{class_name}: {base_name}"
                additive_format_ok = False

        if ing.is_oil_fat and ing.botanical_origin:
            origin = self._normalize_spaces(ing.botanical_origin.get(lang))
            if ing.hydrogenation and ing.hydrogenation.value != 'NONE':
                hydro_text = get_hydrogenation_text(ing.hydrogenation.value, lang)
                base_name = f"{origin} ({hydro_text})"
            else:
                base_name = origin

        if ing.is_nano:
            base_name += " (nano)"

        base_name = self._apply_text_corrections(base_name)
        canonical = NAME_NORMALIZATIONS.get(base_name.strip().lower())
        if canonical is not None:
            base_name = canonical

        return self._normalize_spaces(base_name), additive_format_ok

    def _quid_needed(self, ing: IngredientMaster, result: CompositionResult, manual_flag: bool) -> bool:
        if manual_flag:
            return True
        # Auto-QUID: ingredient mentioned in product name.
        product_name = str(result.product_name or "").lower()
        ing_name = str(ing.name.de or "").lower()
        if not product_name or not ing_name:
            return False
        # Match by significant tokens only.
        tokens = [t for t in re.split(r"[^a-z0-9äöüß]+", ing_name) if len(t) >= 4]
        return any(tok in product_name for tok in tokens)

    def _merge_label_items(self, items: List[dict]) -> List[dict]:
        merged: Dict[str, dict] = {}
        for item in items:
            # Мёрдж по canonical-имени: "Weißzucker" и "Zucker" → один "Zucker"
            raw_name = str(item.get("name") or "")
            canonical = NAME_NORMALIZATIONS.get(raw_name.strip().lower(), raw_name)
            item["name"] = canonical
            key = canonical.casefold()
            if key in merged:
                merged[key]["weight"] += float(item.get("weight", 0.0) or 0.0)
                merged[key]["highlight_quid"] = bool(merged[key].get("highlight_quid")) or bool(item.get("highlight_quid"))
                merged[key]["allergen"] = bool(merged[key].get("allergen")) or bool(item.get("allergen"))
                merged[key]["sub_items"].extend(item.get("sub_items") or [])
                merged[key]["validation_errors"].extend(item.get("validation_errors") or [])
            else:
                merged[key] = {
                    **item,
                    "weight": float(item.get("weight", 0.0) or 0.0),
                    "sub_items": list(item.get("sub_items") or []),
                    "validation_errors": list(item.get("validation_errors") or []),
                }
        out = list(merged.values())
        for item in out:
            if item.get("sub_items"):
                item["sub_items"] = self._merge_label_items(item["sub_items"])
                item["sub_items"].sort(key=lambda s: -float(s.get("weight", 0.0) or 0.0))
        return out

    def _build_label_items_for_ingredient(
        self,
        ing: IngredientMaster,
        weight: float,
        highlight_quid: bool,
        result: CompositionResult,
        lang,
        depth: int = 0,
        path_ids: Optional[Set[int]] = None,
    ) -> List[dict]:
        if weight <= 0:
            return []
        if depth > 10:
            return [{
                "key": f"depth-limit:{ing.ingredient_id}",
                "name": self._normalize_spaces(ing.name.get(lang)),
                "weight": float(weight),
                "highlight_quid": False,
                "allergen": bool(ing.allergen_code),
                "sub_items": [],
                "validation_errors": ["max_compound_depth_exceeded"],
            }]

        if path_ids is None:
            path_ids = set()
        if ing.ingredient_id in path_ids:
            return [{
                "key": f"cycle:{ing.ingredient_id}",
                "name": self._normalize_spaces(ing.name.get(lang)),
                "weight": float(weight),
                "highlight_quid": False,
                "allergen": bool(ing.allergen_code),
                "sub_items": [],
                "validation_errors": ["compound_cycle_detected"],
            }]

        name, additive_ok = self._format_base_name(ing, lang)
        item_errors: List[str] = []
        if not additive_ok and ing.additive_class_code:
            item_errors.append("additive_missing_e_number")

        has_forbidden = self._contains_forbidden_designation(name)
        code_like = self._looks_like_internal_code(name)

        # Если запрещённое/торговое имя имеет canonical-alias — переименовываем,
        # не разворачиваем. Составной: показывается как "Margarine (sub-items)".
        # Простой: показывается с каноническим именем без ошибки.
        if has_forbidden or code_like:
            alias = FORBIDDEN_NAME_ALIASES.get(name.strip().lower())
            if alias is not None:
                name = alias
                has_forbidden = False
                code_like = False

        if ing.is_compound and not ing.sub_ingredients:
            if hasattr(self, 'db') and self.db is not None:
                ing.sub_ingredients = self.db.get_sub_ingredients(ing.ingredient_id)
            else:
                item_errors.append("compound_without_sub_ingredients")

        # Deklarationsname prevents expansion — acts as an explicit alias.
        has_declaration_name = bool(
            getattr(ing, 'declaration_name', None)
            and ing.declaration_name
            and ing.declaration_name.get(lang)
        )

        # Expand forbidden compound names to base ingredients.
        if ing.is_compound and ing.sub_ingredients and not has_declaration_name and (has_forbidden or code_like or bool(getattr(ing, "expand_sub_ingredients_only", False))):
            total_sub = sum(max(0.0, float(s.weight_grams or 0.0)) for s in ing.sub_ingredients)
            if total_sub <= 0:
                return [{
                    "key": f"invalid-compound:{ing.ingredient_id}",
                    "name": name,
                    "weight": float(weight),
                    "highlight_quid": False,
                    "allergen": bool(ing.allergen_code),
                    "sub_items": [],
                    "validation_errors": ["compound_without_valid_sub_weights"],
                }]
            expanded: List[dict] = []
            next_path = set(path_ids)
            next_path.add(ing.ingredient_id)
            for sub in ing.sub_ingredients:
                sw = max(0.0, float(sub.weight_grams or 0.0))
                if sw <= 0:
                    continue
                share = sw / total_sub
                expanded.extend(self._build_label_items_for_ingredient(
                    ing=sub.ingredient,
                    weight=weight * share,
                    highlight_quid=bool(sub.highlight_quid),
                    result=result,
                    lang=lang,
                    depth=depth + 1,
                    path_ids=next_path,
                ))
            return expanded

        if (has_forbidden or code_like) and not ing.is_compound:
            item_errors.append("forbidden_or_code_like_name_not_expandable")

        # Annex VII Part E: правило 2% для составных ингредиентов.
        # Если составной ингредиент < 2% готового продукта — состав не раскрывается,
        # кроме аллергенов и функциональных добавок (обязательно по Art. 21).
        final_wt = float(result.final_product_weight or 0.0)
        compound_pct = (weight / final_wt * 100.0) if final_wt > 0 else 100.0
        apply_2pct_rule = ing.is_compound and compound_pct < COMPOUND_THRESHOLD_PERCENT

        sub_items: List[dict] = []
        if ing.is_compound:
            if not ing.sub_ingredients:
                item_errors.append("compound_without_sub_ingredients")
            else:
                total_sub = sum(max(0.0, float(s.weight_grams or 0.0)) for s in ing.sub_ingredients)
                if total_sub <= 0:
                    item_errors.append("compound_without_valid_sub_weights")
                else:
                    next_path = set(path_ids)
                    next_path.add(ing.ingredient_id)
                    for sub in sorted(ing.sub_ingredients, key=lambda s: -float(s.weight_grams or 0.0)):
                        sw = max(0.0, float(sub.weight_grams or 0.0))
                        if sw <= 0:
                            continue
                        # 2% rule: пропускаем суб-ингредиенты без аллергенов и добавок
                        if apply_2pct_rule:
                            sub_ing = sub.ingredient
                            if not (sub_ing.allergen_code or sub_ing.additive_class_code):
                                continue
                        share = sw / total_sub
                        sub_items.extend(self._build_label_items_for_ingredient(
                            ing=sub.ingredient,
                            weight=weight * share,
                            highlight_quid=bool(sub.highlight_quid),
                            result=result,
                            lang=lang,
                            depth=depth + 1,
                            path_ids=next_path,
                        ))

        # Additive metadata for grouping same-class additives in compound ingredient brackets.
        additive_class_code = ing.additive_class_code or None
        additive_class_display = None
        additive_value = None
        if additive_class_code:
            from .translations import get_additive_class_name
            additive_class_display = get_additive_class_name(additive_class_code, lang)
            e_norm = self._normalize_e_number(ing.e_number) if ing.e_number else None
            additive_value = e_norm if e_norm else self._normalize_spaces(ing.name.get(lang))

        return [{
            "key": f"ing:{ing.ingredient_id}:{name.casefold()}",
            "name": name,
            "weight": float(weight),
            "highlight_quid": self._quid_needed(ing, result, highlight_quid),
            "allergen": bool(ing.allergen_code),
            "sub_items": self._merge_label_items(sub_items),
            "validation_errors": item_errors,
            "compound_pct_in_final": round(compound_pct, 2) if ing.is_compound else None,
            "two_pct_rule_applied": apply_2pct_rule,
            "additive_class_code": additive_class_code,
            "additive_class_display": additive_class_display,
            "additive_value": additive_value,
        }]

    def _collect_compliance_errors(self, items: List[dict]) -> List[str]:
        errors: List[str] = []

        prev_weight = None
        for item in items:
            w = float(item.get("weight", 0.0) or 0.0)
            if prev_weight is not None and w > prev_weight + 1e-9:
                errors.append("sorting_not_descending")
            prev_weight = w
            errors.extend(item.get("validation_errors") or [])
            if self._contains_forbidden_designation(item.get("name", "")):
                errors.append("forbidden_designation_in_final_output")
            if self._looks_like_internal_code(item.get("name", "")):
                errors.append("internal_code_in_final_output")
            errors.extend(self._collect_compliance_errors(item.get("sub_items") or []))

        # Deduplicate while preserving order.
        seen = set()
        out = []
        for e in errors:
            if e not in seen:
                seen.add(e)
                out.append(e)
        return out

    def _format_label_item_text(self, item: dict, final_weight: float) -> str:
        name = str(item.get("name") or "")
        if item.get("allergen"):
            name = name.upper()

        if item.get("highlight_quid") and final_weight > 0:
            pct = (float(item.get("weight", 0.0) or 0.0) / final_weight) * 100.0
            if pct > 0:
                name += f" ({pct:.0f}%)"

        sub_items = item.get("sub_items") or []
        if sub_items:
            sub_text = self._format_sub_items_grouped(sub_items, final_weight)
            name += f" ({sub_text})"
        return name

    def _format_sub_items_grouped(self, sub_items: list, final_weight: float) -> str:
        """
        Format sub-items of a compound ingredient, grouping same-class additives.

        Example: two EMULSIFIER sub-items (E471 and Lecithine) are rendered as
        "Emulgator: E471, Lecithine" instead of two separate entries.

        Regular (non-additive) sub-items keep their normal formatted string.
        Separator between all parts is "," unless any part itself contains ","
        (e.g. a grouped additive entry), in which case ";" is used as outer separator.
        """
        # Collect regular items and group additives by functional class.
        additive_groups: Dict[str, dict] = {}   # class_code → {display: str, values: [str]}
        regular_parts: List[str] = []

        for sub in sub_items:
            cls = sub.get("additive_class_code")
            if cls:
                cls_display = sub.get("additive_class_display") or cls
                val = sub.get("additive_value") or str(sub.get("name", ""))
                if cls not in additive_groups:
                    additive_groups[cls] = {"display": cls_display, "values": []}
                if val and val not in additive_groups[cls]["values"]:
                    additive_groups[cls]["values"].append(val)
            else:
                regular_parts.append(self._format_label_item_text(sub, final_weight))

        # Build "ClassName: val1, val2" strings for each additive group.
        additive_parts = [
            f"{g['display']}: {', '.join(g['values'])}"
            for g in additive_groups.values()
            if g["values"]
        ]

        all_parts = regular_parts + additive_parts

        # Use ";" as separator when any part itself contains "," (avoids ambiguity).
        sep = "; " if any(", " in p for p in all_parts) else ", "
        return sep.join(all_parts)

    def _aggregate_label_items(self, result: CompositionResult, lang) -> List[dict]:
        """
        Build final label items with LMIV constraints.
        """
        all_items: List[dict] = []
        for fi in result.flat_ingredients:
            all_items.extend(self._build_label_items_for_ingredient(
                ing=fi.ingredient,
                weight=float(fi.absolute_weight or 0.0),
                highlight_quid=bool(fi.highlight_quid),
                result=result,
                lang=lang,
            ))

        merged = self._merge_label_items(all_items)
        final_weight = float(result.final_product_weight or 0.0) or 0.0
        items = sorted(merged, key=lambda x: -float(x.get("weight", 0.0) or 0.0))
        for item in items:
            w = float(item.get("weight", 0.0) or 0.0)
            item["percentage"] = (w / final_weight * 100.0) if final_weight > 0 else 0.0
        return items

    def get_label_debug_items(self, result: CompositionResult, language: str = 'de') -> List[dict]:
        """Debug-данные для UI: позиция -> масса(г) -> % после итоговой агрегации."""
        from .enums import Language
        try:
            lang = Language(language)
        except ValueError:
            lang = Language.DE
        return self._aggregate_label_items(result, lang)

    def get_label_compliance_issues(self, result: CompositionResult, language: str = 'de') -> List[str]:
        """Return LMIV compliance issues for generated label items."""
        from .enums import Language
        try:
            lang = Language(language)
        except ValueError:
            lang = Language.DE
        items = self._aggregate_label_items(result, lang)
        return self._collect_compliance_errors(items)

    def _collect_compliance_errors_detailed(self, items: List[dict]) -> List[dict]:
        """
        Как _collect_compliance_errors, но возвращает список словарей
        {"code": str, "ingredient": str} — с именем ингредиента для каждой ошибки.
        """
        details: List[dict] = []
        prev_weight = None
        for item in items:
            name = str(item.get("name") or "?")
            w = float(item.get("weight", 0.0) or 0.0)
            if prev_weight is not None and w > prev_weight + 1e-9:
                details.append({"code": "sorting_not_descending", "ingredient": name})
            prev_weight = w
            for err in (item.get("validation_errors") or []):
                details.append({"code": err, "ingredient": name})
            if self._contains_forbidden_designation(name):
                details.append({"code": "forbidden_designation_in_final_output", "ingredient": name})
            if self._looks_like_internal_code(name):
                details.append({"code": "internal_code_in_final_output", "ingredient": name})
            details.extend(self._collect_compliance_errors_detailed(item.get("sub_items") or []))

        # Убираем дубли по паре (code, ingredient)
        seen: set = set()
        out: List[dict] = []
        for e in details:
            key = (e["code"], e["ingredient"])
            if key not in seen:
                seen.add(key)
                out.append(e)
        return out

    def get_label_compliance_issues_detailed(
        self, result: CompositionResult, language: str = 'de'
    ) -> List[dict]:
        """
        Детальные ошибки LMIV: [{code, ingredient}, ...].
        Используется для отображения в UI с указанием конкретного ингредиента.
        """
        from .enums import Language
        try:
            lang = Language(language)
        except ValueError:
            lang = Language.DE
        items = self._aggregate_label_items(result, lang)
        return self._collect_compliance_errors_detailed(items)

    @staticmethod
    def _compact_additive_names(text: str) -> str:
        """
        Сокращает текст этикетки: заменяет 'КлассДобавки: E###' → 'E###'.

        По LMIV допускается указывать добавки только по E-номеру без класса.
        Применяется когда текст этикетки превышает допустимый лимит символов.
        """
        import re
        # Паттерн: «любой текст без запятых и скобок» + «: E###» → «E###»
        return re.sub(r'[^,()\[\]]+:\s*(E\d{3,4}[a-zA-Z]?)', r'\1', text)

    def generate_label_text_compact(
        self,
        result: CompositionResult,
        language: str = 'de',
        max_chars: int = 920,
    ) -> dict:
        """
        Генерирует полный и сокращённый вариант текста этикетки.

        Если полный текст превышает max_chars:
          - additive class prefix перед E-номером убирается ('Emulgator: E471' → 'E471')
          - возвращается сокращённый вариант для печати

        Returns:
            {
                "full":           str   — полный текст,
                "compact":        str|None — сокращённый (None если не нужен),
                "was_shortened":  bool,
                "chars_full":     int,
                "chars_compact":  int|None,
            }
        """
        full_text = self.generate_label_text(result, language)
        chars_full = len(full_text)

        if chars_full <= max_chars:
            return {
                "full": full_text,
                "compact": None,
                "was_shortened": False,
                "chars_full": chars_full,
                "chars_compact": None,
            }

        compact_text = self._compact_additive_names(full_text)
        return {
            "full": full_text,
            "compact": compact_text,
            "was_shortened": True,
            "chars_full": chars_full,
            "chars_compact": len(compact_text),
        }

    def generate_label_text(
        self,
        result: CompositionResult,
        language: str = 'de',
    ) -> str:
        """
        Генерирует строку состава (Zutatenliste) из результата расчета.

        Args:
            result: CompositionResult от calculate()
            language: Код языка ('de', 'nl', 'fr')

        Returns:
            Строка состава для этикетки
        """
        from .enums import Language
        from .translations import (
            get_label_header,
        )

        try:
            lang = Language(language)
        except ValueError:
            lang = Language.DE

        header = get_label_header(lang)
        items = self._aggregate_label_items(result, lang)
        errors = self._collect_compliance_errors(items)
        if errors:
            blocking = [e for e in errors if e in BLOCKING_LABEL_ERRORS]
            if blocking:
                logger.warning(
                    "Label for %s has BLOCKING issues: %s",
                    result.article_nr, ", ".join(blocking)
                )
                return f"{header} nicht etikettenkonform."
            logger.warning(
                "Label for %s has non-blocking issues (label generated anyway): %s",
                result.article_nr, ", ".join(errors)
            )

        final_weight = float(result.final_product_weight or 0.0)
        parts = [self._format_label_item_text(item, final_weight) for item in items]
        return f"{header} {', '.join(parts)}."
