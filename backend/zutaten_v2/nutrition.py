"""
Калькулятор пищевой ценности для печати этикеток.
Рассчитывает нутриенты на 100г готового продукта из данных ингредиентов рецепта.
"""

from dataclasses import dataclass
from typing import List, Optional
from .models import RecipeIngredient


@dataclass
class NutritionPer100g:
    """Пищевая ценность на 100г готового продукта"""
    energy_kj: float
    energy_kcal: float
    fat: float
    saturated_fat: float
    carbs: float
    sugar: float
    protein: float
    salt: float


def calculate_nutrition(ingredients: List[RecipeIngredient],
                        final_product_weight: float) -> Optional[NutritionPer100g]:
    """
    Рассчитать пищевую ценность на 100г готового продукта.

    Алгоритм:
    1. Для каждого ингредиента: абс_значение = (вес_г / 100) * нутриент_на_100г
    2. Сумма по всем ингредиентам
    3. Пересчет на 100г готового продукта: (сумма / вес_готового) * 100
    """
    if not ingredients or final_product_weight <= 0:
        return None

    total_kcal = 0.0
    total_kj = 0.0
    total_fat = 0.0
    total_sat_fat = 0.0
    total_carbs = 0.0
    total_sugar = 0.0
    total_protein = 0.0
    total_salt = 0.0
    has_data = False

    for ri in ingredients:
        ing = ri.ingredient
        w = ri.weight_grams

        if ing.kcal_per_100g is not None:
            has_data = True
            total_kcal += (w / 100.0) * (ing.kcal_per_100g or 0)

            # kJ: из поля kj_per_100g, иначе пересчет из kcal
            kj = ing.kj_per_100g
            if kj is not None:
                total_kj += (w / 100.0) * kj
            else:
                total_kj += (w / 100.0) * (ing.kcal_per_100g or 0) * 4.184

        total_fat += (w / 100.0) * (ing.fat_per_100g or 0)
        total_sat_fat += (w / 100.0) * (ing.saturated_fat_per_100g or 0)
        total_carbs += (w / 100.0) * (ing.carbs_per_100g or 0)
        total_sugar += (w / 100.0) * (ing.sugar_per_100g or 0)
        total_protein += (w / 100.0) * (ing.protein_per_100g or 0)
        total_salt += (w / 100.0) * (ing.salt_per_100g or 0)

    if not has_data:
        return None

    # Пересчет на 100г готового продукта
    factor = 100.0 / final_product_weight

    return NutritionPer100g(
        energy_kj=round(total_kj * factor),
        energy_kcal=round(total_kcal * factor),
        fat=round(total_fat * factor, 1),
        saturated_fat=round(total_sat_fat * factor, 1),
        carbs=round(total_carbs * factor, 1),
        sugar=round(total_sugar * factor, 1),
        protein=round(total_protein * factor, 1),
        salt=round(total_salt * factor, 1),
    )


def format_nutrition_for_label(n: NutritionPer100g) -> dict:
    """
    Форматирование для CSV файла GoLabel.

    Формат:
      ENERGIE: "1682_kJ/402Kcal"
      FETT: "20,6_g"
    """
    def fmt(val):
        """Немецкий десятичный формат с _g"""
        return f"{val:.1f}_g".replace('.', ',')

    return {
        'ENERGIE': f"{int(n.energy_kj)}_kJ/{int(n.energy_kcal)}Kcal",
        'FETT': fmt(n.fat),
        'DAVON_FETT': fmt(n.saturated_fat),
        'KOHLENHYDRATE': fmt(n.carbs),
        'DAVON_ZUCKER': fmt(n.sugar),
        'EIWIESS': fmt(n.protein),
        'SALZ': fmt(n.salt),
    }
