"""
Мультиязычный генератор этикеток согласно LMIV (EU 1169/2011)

Реализованные правила:
- Art. 18: Сортировка по весу в порядке убывания
- Art. 21: Выделение аллергенов
- Art. 22: QUID проценты для выделенных ингредиентов
- Annex VII Part A: Расчет воды (порог 5%)
- Annex VII Part C: Формат добавок "[Класс] [Название/E-код]"
- Annex VII Part E: Составные ингредиенты (правило 2%)
"""

import logging
from typing import List, Optional, Set

from .enums import Language, HydrogenationStatus
from .models import (
    TranslatedText,
    IngredientMaster,
    RecipeIngredient,
    RecipeForLabel,
    GeneratedLabel
)
from .translations import (
    get_label_header,
    get_hydrogenation_text,
    get_additive_class_name,
    get_water_name,
    get_contains_text,
    ALLERGEN_NAMES
)

logger = logging.getLogger(__name__)


class MultilingualLabelGenerator:
    """
    Генератор списка ингредиентов по LMIV.

    Ключевые правила LMIV:
    - Art. 18: Сортировка по весу в порядке убывания
    - Art. 21: Выделение аллергенов (bold/caps)
    - Art. 22: QUID проценты для выделенных ингредиентов
    - Annex VII Part A: Расчет воды (порог 5%)
    - Annex VII Part C: Формат добавок
    - Annex VII Part E: Составные ингредиенты (правило 2%)
    """

    # Порог для воды (5% от готового продукта)
    WATER_THRESHOLD_PERCENT = 5.0

    # Порог для составных ингредиентов (2% от готового продукта)
    COMPOUND_THRESHOLD_PERCENT = 2.0

    def __init__(self, recipe: RecipeForLabel, language: Language = Language.DE):
        """
        Инициализация генератора.

        Args:
            recipe: Рецепт с ингредиентами
            language: Язык генерации (DE, NL, FR)
        """
        self.recipe = recipe
        self.language = language
        self.total_input_weight = recipe.total_input_weight
        self.final_weight = recipe.final_product_weight
        self._allergens_found: Set[str] = set()

    def generate(self) -> GeneratedLabel:
        """
        Основной метод генерации этикетки.

        Returns:
            GeneratedLabel с текстом этикетки и списком аллергенов
        """
        # Разделяем воду и остальные ингредиенты
        water_ingredients = []
        other_ingredients = []

        for ing in self.recipe.ingredients:
            if ing.ingredient.is_added_water:
                water_ingredients.append(ing)
            else:
                other_ingredients.append(ing)

        # Рассчитываем декларируемую воду
        water_weight = self._calculate_declarable_water(water_ingredients)

        # Добавляем воду как виртуальный ингредиент если > 5%
        if water_weight > 0:
            water_ingredient = self._create_water_ingredient(water_weight)
            other_ingredients.append(water_ingredient)

        # Разворачиваем составные ингредиенты, отмеченные как "только суб-ингредиенты"
        other_ingredients = self._expand_compound_ingredients(other_ingredients)

        # Сортируем по весу (Art. 18)
        sorted_ingredients = sorted(
            other_ingredients,
            key=lambda x: (x.sort_override if x.sort_override is not None else 999999, -x.weight_grams)
        )

        # Форматируем каждый ингредиент
        formatted_parts = []
        for ing in sorted_ingredients:
            formatted = self._format_ingredient(ing, is_sub=False)
            if formatted:
                formatted_parts.append(formatted)

        # Собираем финальную строку
        header = get_label_header(self.language)
        label_text = f"{header} {', '.join(formatted_parts)}."

        return GeneratedLabel(
            article_nr=self.recipe.article_nr,
            language=self.language,
            label_text=label_text,
            allergens_present=list(self._allergens_found)
        )

    def _expand_compound_ingredients(self, ingredients: List[RecipeIngredient], depth: int = 0) -> List[RecipeIngredient]:
        """Развернуть составные ингредиенты без вывода родительского названия."""
        if depth > 5:
            return ingredients

        expanded: List[RecipeIngredient] = []
        for rec_ing in ingredients:
            ing = rec_ing.ingredient
            if (
                ing.is_compound
                and getattr(ing, 'expand_sub_ingredients_only', False)
                and ing.sub_ingredients
            ):
                total_sub_weight = sum(max(0.0, float(s.weight_grams or 0.0)) for s in ing.sub_ingredients)
                if total_sub_weight > 0:
                    sub_scaled = []
                    for sub in ing.sub_ingredients:
                        sub_w = max(0.0, float(sub.weight_grams or 0.0))
                        if sub_w <= 0:
                            continue
                        share = sub_w / total_sub_weight
                        sub_scaled.append(RecipeIngredient(
                            ingredient=sub.ingredient,
                            weight_grams=rec_ing.weight_grams * share,
                            highlight_quid=bool(sub.highlight_quid),
                            sort_override=sub.sort_override,
                        ))
                    expanded.extend(self._expand_compound_ingredients(sub_scaled, depth + 1))
                    continue
            expanded.append(rec_ing)
        return expanded

    def _calculate_declarable_water(self, water_ingredients: List[RecipeIngredient]) -> float:
        """
        Рассчитывает количество воды для декларации (Annex VII Part A).

        Правило: Вода указывается только если она составляет > 5% готового продукта.

        Formula: Added_Water = Total_Water_Input - (Total_Input_Weight - Final_Product_Weight)
        """
        if not water_ingredients:
            return 0.0

        total_water_input = sum(w.weight_grams for w in water_ingredients)

        # Влагопотеря при обработке
        moisture_loss = self.total_input_weight - self.final_weight

        # Остаточная вода
        water_remaining = total_water_input - moisture_loss

        if water_remaining <= 0:
            return 0.0

        # Процент воды в готовом продукте
        water_percent = (water_remaining / self.final_weight) * 100

        # Порог 5%
        if water_percent < self.WATER_THRESHOLD_PERCENT:
            return 0.0

        return water_remaining

    def _create_water_ingredient(self, weight: float) -> RecipeIngredient:
        """Создает виртуальный ингредиент для воды"""
        water_name = get_water_name(self.language)

        water_master = IngredientMaster(
            ingredient_id=0,
            ingredient_code="WATER",
            name=TranslatedText(
                de="Wasser",
                nl="Water",
                fr="Eau"
            ),
            is_added_water=True
        )

        return RecipeIngredient(
            ingredient=water_master,
            weight_grams=weight,
            highlight_quid=False
        )

    def _format_ingredient(self, rec_ing: RecipeIngredient, is_sub: bool = False) -> str:
        """
        Форматирует один ингредиент в строку.

        Args:
            rec_ing: Ингредиент рецепта
            is_sub: Является ли суб-ингредиентом
        """
        ing = rec_ing.ingredient
        display_name = ing.name.get(self.language)

        # 1. Добавки: "[Функциональный класс] [Название или E-номер]"
        if ing.additive_class_code:
            class_name = get_additive_class_name(ing.additive_class_code, self.language)
            if ing.e_number:
                display_name = f"{class_name} {ing.e_number}"
            else:
                display_name = f"{class_name} {display_name}"

        # 2. Масла/жиры с ботаническим происхождением
        if ing.is_oil_fat and ing.botanical_origin:
            origin = ing.botanical_origin.get(self.language)
            if ing.hydrogenation != HydrogenationStatus.NONE:
                hydro_text = get_hydrogenation_text(ing.hydrogenation.value, self.language)
                display_name = f"{origin} ({hydro_text})"
            else:
                display_name = origin

        # 3. Нано-материалы (Art. 18, Abs. 3)
        if ing.is_nano:
            display_name += " (nano)"

        # 4. Аллергены - выделение (Art. 21)
        if ing.allergen_code:
            self._allergens_found.add(ing.allergen_code)
            display_name = self._format_allergen(display_name)

        # 5. QUID проценты (Art. 22) - только для основных ингредиентов
        if rec_ing.highlight_quid and not is_sub:
            quid_text = self._format_quid(rec_ing)
            display_name += quid_text

        # 6. Составные ингредиенты (Annex VII Part E)
        if ing.is_compound and ing.sub_ingredients:
            sub_text = self._format_compound_ingredient(rec_ing)
            if sub_text:
                display_name += sub_text

        return display_name

    def _format_allergen(self, text: str) -> str:
        """
        Применяет выделение для аллергенов (Art. 21).

        Используем **bold** markdown формат.
        """
        return f"**{text}**"

    def _format_quid(self, rec_ing: RecipeIngredient) -> str:
        """
        Рассчитывает процент QUID (Art. 22).

        Процент рассчитывается от веса на момент смешивания (input weight).
        """
        percent = (rec_ing.weight_grams / self.total_input_weight) * 100
        return f" {percent:.1f}%"

    def _format_compound_ingredient(self, rec_ing: RecipeIngredient) -> str:
        """
        Обрабатывает составные ингредиенты (Annex VII Part E).

        Правило 2%: Если составной ингредиент < 2% готового продукта,
        его состав можно не расписывать, КРОМЕ:
        - Аллергенов (обязательно по Art. 21)
        - Добавок с технологической функцией
        """
        ing = rec_ing.ingredient

        if not ing.sub_ingredients:
            return ""

        # Annex VII Part E: проверка 2% порога
        compound_pct = (rec_ing.weight_grams / self.final_weight * 100.0) if self.final_weight > 0 else 100.0
        apply_2pct_rule = compound_pct < self.COMPOUND_THRESHOLD_PERCENT

        # Сортируем суб-ингредиенты по весу
        sorted_subs = sorted(
            ing.sub_ingredients,
            key=lambda x: -x.weight_grams
        )

        formatted_subs = []
        for sub in sorted_subs:
            if apply_2pct_rule:
                # Правило 2%: только аллергены и добавки обязательны
                sub_ing = sub.ingredient
                if not (sub_ing.allergen_code or sub_ing.additive_class_code):
                    continue
            sub_formatted = self._format_ingredient(sub, is_sub=True)
            if sub_formatted:
                formatted_subs.append(sub_formatted)

        if not formatted_subs:
            return ""

        return f" ({', '.join(formatted_subs)})"

    def get_allergens_summary(self) -> str:
        """
        Получить строку с перечислением аллергенов для отдельного блока.

        Returns:
            Строка вида "Enthält: Gluten, Milch, Eier" или пустая строка
        """
        if not self._allergens_found:
            return ""

        contains = get_contains_text(self.language)

        allergen_names = []
        for code in sorted(self._allergens_found):
            if code in ALLERGEN_NAMES:
                name = ALLERGEN_NAMES[code].get(self.language, code)
                allergen_names.append(name)

        if not allergen_names:
            return ""

        return f"{contains.capitalize()}: {', '.join(allergen_names)}"


def generate_label(recipe: RecipeForLabel, language: Language = Language.DE) -> GeneratedLabel:
    """
    Удобная функция для генерации этикетки.

    Args:
        recipe: Рецепт с ингредиентами
        language: Язык (DE, NL, FR)

    Returns:
        GeneratedLabel
    """
    generator = MultilingualLabelGenerator(recipe, language)
    return generator.generate()


def generate_all_languages(recipe: RecipeForLabel) -> dict:
    """
    Генерация этикеток на всех поддерживаемых языках.

    Args:
        recipe: Рецепт с ингредиентами

    Returns:
        Словарь {language_code: GeneratedLabel}
    """
    results = {}

    for lang in [Language.DE, Language.NL, Language.FR]:
        generator = MultilingualLabelGenerator(recipe, lang)
        results[lang.value] = generator.generate()

    return results


# ============================================
# Генерация из CompositionResult (рекурсивный калькулятор)
# ============================================

def generate_label_from_composition(
    composition,
    language: Language = Language.DE,
    db=None,
) -> GeneratedLabel:
    """
    Генерирует этикетку из CompositionResult (от CompositionCalculator).

    Используется вместо MultilingualLabelGenerator, когда состав
    уже рассчитан рекурсивным калькулятором.

    Args:
        composition: CompositionResult
        language: Язык
        db: ZutatenDatabase (опционально). Нужен если составные ингредиенты
            в flat_ingredients не имеют предзагруженных sub_ingredients.

    Returns:
        GeneratedLabel
    """
    from .calculator import CompositionCalculator

    # Создаём калькулятор с db (может быть None — тогда sub_ingredients
    # должны быть уже загружены в FlatIngredient.ingredient.sub_ingredients).
    calc = CompositionCalculator.__new__(CompositionCalculator)
    calc.db = db
    calc._cache = {}
    calc._cache_ttl = 300
    label_text = calc.generate_label_text(composition, language.value)

    return GeneratedLabel(
        article_nr=composition.article_nr,
        language=language,
        label_text=label_text,
        allergens_present=composition.allergens_present,
    )


def generate_all_languages_from_composition(composition, db=None) -> dict:
    """
    Генерация этикеток на всех языках из CompositionResult.

    Args:
        composition: CompositionResult
        db: ZutatenDatabase (опционально)

    Returns:
        Словарь {language_code: GeneratedLabel}
    """
    results = {}
    for lang in [Language.DE, Language.NL, Language.FR]:
        results[lang.value] = generate_label_from_composition(composition, lang, db=db)
    return results
