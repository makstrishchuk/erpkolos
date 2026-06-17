"""
Модели данных для модуля Zutaten V2
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

from .enums import Language, HydrogenationStatus, AllergenCode, AdditiveClassCode


@dataclass
class TranslatedText:
    """Контейнер для мультиязычного текста"""
    de: str                          # Немецкий (обязательный)
    nl: Optional[str] = None         # Нидерландский
    fr: Optional[str] = None         # Французский

    def get(self, lang: Language) -> str:
        """Получить текст на указанном языке с fallback на немецкий"""
        if lang == Language.NL and self.nl:
            return self.nl
        if lang == Language.FR and self.fr:
            return self.fr
        return self.de

    def to_dict(self) -> dict:
        """Конвертация в словарь для JSON"""
        return {
            'de': self.de,
            'nl': self.nl,
            'fr': self.fr
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TranslatedText':
        """Создание из словаря"""
        return cls(
            de=data.get('de', ''),
            nl=data.get('nl'),
            fr=data.get('fr')
        )


@dataclass
class AllergenReference:
    """Справочник аллергенов"""
    allergen_id: int
    allergen_code: str
    name: TranslatedText
    description_de: Optional[str] = None
    sort_order: int = 0
    active: bool = True


@dataclass
class AdditiveClass:
    """Справочник классов добавок"""
    class_id: int
    class_code: str
    name: TranslatedText
    example_e_numbers: Optional[str] = None
    sort_order: int = 0
    active: bool = True


@dataclass
class IngredientMaster:
    """Мастер-данные ингредиента"""
    ingredient_id: int
    ingredient_code: str
    name: TranslatedText
    category: Optional[str] = None
    is_compound: bool = False
    expand_sub_ingredients_only: bool = False
    compound_total_grams: Optional[float] = None
    declaration_name: Optional['TranslatedText'] = None  # Deklarationsname — overrides name_de for label output

    # Аллерген (Art. 21)
    allergen_id: Optional[int] = None
    allergen_ids: List[int] = field(default_factory=list)
    allergen_code: Optional[str] = None      # Для удобства (GLUTEN, MILK и т.д.)
    allergen_name: Optional[TranslatedText] = None  # Название аллергена

    # Добавки (Annex VII Part C)
    additive_class_id: Optional[int] = None
    additive_class_code: Optional[str] = None
    additive_class_name: Optional[TranslatedText] = None
    e_number: Optional[str] = None           # E 202, E 330 и т.д.

    # Нано-материалы (Art. 18, Abs. 3)
    is_nano: bool = False

    # Масла/жиры (Annex VII Part A)
    is_oil_fat: bool = False
    botanical_origin: Optional[TranslatedText] = None  # Palm, Raps, Sonnenblume
    hydrogenation: HydrogenationStatus = HydrogenationStatus.NONE

    # Вода
    is_added_water: bool = False
    loss_factor: float = 0.0                 # Коэф. потерь (0.0-1.0)

    # Нутриенты (опционально)
    kcal_per_100g: Optional[float] = None
    kj_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    saturated_fat_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    sugar_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    salt_per_100g: Optional[float] = None

    # Метаданные
    notes: Optional[str] = None
    active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Суб-ингредиенты (загружаются по запросу)
    sub_ingredients: List['RecipeIngredient'] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Конвертация в словарь для JSON/API"""
        return {
            'ingredient_id': self.ingredient_id,
            'ingredient_code': self.ingredient_code,
            'name_de': self.name.de,
            'name_nl': self.name.nl,
            'name_fr': self.name.fr,
            'category': self.category,
            'is_compound': self.is_compound,
            'expand_sub_ingredients_only': self.expand_sub_ingredients_only,
            'compound_total_grams': self.compound_total_grams,
            'declaration_name_de': self.declaration_name.de if self.declaration_name else None,
            'declaration_name_nl': self.declaration_name.nl if self.declaration_name else None,
            'declaration_name_fr': self.declaration_name.fr if self.declaration_name else None,
            'allergen_id': self.allergen_id,
            'allergen_ids': self.allergen_ids,
            'allergen_code': self.allergen_code,
            'additive_class_id': self.additive_class_id,
            'additive_class_code': self.additive_class_code,
            'e_number': self.e_number,
            'is_nano': self.is_nano,
            'is_oil_fat': self.is_oil_fat,
            'botanical_origin_de': self.botanical_origin.de if self.botanical_origin else None,
            'botanical_origin_nl': self.botanical_origin.nl if self.botanical_origin else None,
            'botanical_origin_fr': self.botanical_origin.fr if self.botanical_origin else None,
            'hydrogenation': self.hydrogenation.value,
            'is_added_water': self.is_added_water,
            'loss_factor': self.loss_factor,
            'kcal_per_100g': self.kcal_per_100g,
            'kj_per_100g': self.kj_per_100g,
            'fat_per_100g': self.fat_per_100g,
            'saturated_fat_per_100g': self.saturated_fat_per_100g,
            'carbs_per_100g': self.carbs_per_100g,
            'sugar_per_100g': self.sugar_per_100g,
            'protein_per_100g': self.protein_per_100g,
            'salt_per_100g': self.salt_per_100g,
            'notes': self.notes,
            'active': self.active,
        }


@dataclass
class RecipeIngredient:
    """Ингредиент в составе рецепта"""
    ingredient: IngredientMaster
    weight_grams: float
    highlight_quid: bool = False            # Показывать % (Art. 22)
    sort_override: Optional[int] = None     # Ручная сортировка

    def to_dict(self) -> dict:
        """Конвертация в словарь (nested ingredient для клиента)"""
        return {
            'ingredient_id': self.ingredient.ingredient_id,
            'weight_grams': self.weight_grams,
            'highlight_quid': self.highlight_quid,
            'sort_override': self.sort_override,
            'ingredient': {
                'ingredient_id': self.ingredient.ingredient_id,
                'ingredient_code': self.ingredient.ingredient_code,
                'name_de': self.ingredient.name.de,
                'name_nl': self.ingredient.name.nl,
                'name_fr': self.ingredient.name.fr,
                'allergen_code': self.ingredient.allergen_code,
                'is_compound': self.ingredient.is_compound,
                'allergen_id': self.ingredient.allergen_id,
                'additive_class_id': self.ingredient.additive_class_id,
                'e_number': self.ingredient.e_number,
            },
        }


@dataclass
class RecipeForLabel:
    """Рецепт с ингредиентами для генерации этикетки"""
    article_nr: str
    name: str
    ingredients: List[RecipeIngredient]
    final_product_weight: float             # Вес готового продукта (граммы)

    @property
    def total_input_weight(self) -> float:
        """Суммарный вес всех ингредиентов на входе"""
        return sum(i.weight_grams for i in self.ingredients)

    def to_dict(self) -> dict:
        """Конвертация в словарь"""
        return {
            'article_nr': self.article_nr,
            'name': self.name,
            'final_product_weight': self.final_product_weight,
            'total_input_weight': self.total_input_weight,
            'ingredients': [i.to_dict() for i in self.ingredients],
        }


@dataclass
class GeneratedLabel:
    """Результат генерации этикетки"""
    article_nr: str
    language: Language
    label_text: str
    allergens_present: List[str]           # Коды присутствующих аллергенов
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Конвертация в словарь для API"""
        return {
            'article_nr': self.article_nr,
            'language': self.language.value,
            'label_text': self.label_text,
            'allergens_present': self.allergens_present,
            'generated_at': self.generated_at,
        }


# ============================================
# ZUTATEN V2 — Рекурсивное дерево рецептов
# ============================================

@dataclass
class RecipeTreeNode:
    """Узел дерева рецептов (связь parent -> child)"""
    id: Optional[int]
    parent_article_nr: str
    child_type: str                        # 'recipe' | 'ingredient'
    child_article_nr: Optional[str] = None
    child_ingredient_id: Optional[int] = None
    weight_grams: float = 0.0             # Брутто-вес компонента
    loss_percent: float = 0.0             # Потери при обработке (0-100)
    output_weight_grams: Optional[float] = None  # Выход готового (для sub-recipes)
    highlight_quid: bool = False
    sort_order: int = 0
    notes: Optional[str] = None

    @property
    def net_weight(self) -> float:
        """Нетто-вес после потерь"""
        return self.weight_grams * (1.0 - self.loss_percent / 100.0)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'parent_article_nr': self.parent_article_nr,
            'child_type': self.child_type,
            'child_article_nr': self.child_article_nr,
            'child_ingredient_id': self.child_ingredient_id,
            'weight_grams': self.weight_grams,
            'loss_percent': self.loss_percent,
            'output_weight_grams': self.output_weight_grams,
            'highlight_quid': self.highlight_quid,
            'sort_order': self.sort_order,
            'notes': self.notes,
        }


@dataclass
class FlatIngredient:
    """Развернутый ингредиент с абсолютным весом в конечном продукте.

    Результат рекурсивного развертывания дерева рецептов.
    """
    ingredient: IngredientMaster
    absolute_weight: float                 # Абсолютный вес в конечном продукте (г)
    percentage: float = 0.0               # Процент от конечного продукта
    highlight_quid: bool = False
    source_path: List[str] = field(default_factory=list)  # Путь: ["Торт", "Бисквит", "Мука"]

    def to_dict(self) -> dict:
        return {
            'ingredient_id': self.ingredient.ingredient_id,
            'ingredient_code': self.ingredient.ingredient_code,
            'name_de': self.ingredient.name.de,
            'name_nl': self.ingredient.name.nl,
            'name_fr': self.ingredient.name.fr,
            'absolute_weight': round(self.absolute_weight, 2),
            'percentage': round(self.percentage, 2),
            'highlight_quid': self.highlight_quid,
            'allergen_code': self.ingredient.allergen_code,
            'is_compound': self.ingredient.is_compound,
            'e_number': self.ingredient.e_number,
            'additive_class_code': self.ingredient.additive_class_code,
            'is_added_water': self.ingredient.is_added_water,
            'source_path': self.source_path,
        }


@dataclass
class CompositionResult:
    """Результат расчета состава продукта"""
    article_nr: str
    product_name: str
    flat_ingredients: List[FlatIngredient]  # Все ингредиенты, отсортированные по весу
    total_input_weight: float               # Суммарный входной вес
    final_product_weight: float             # Вес готового продукта
    recipe_hash: str = ''                   # Хеш для детекции изменений
    tree_depth: int = 0                     # Глубина дерева

    @property
    def allergens_present(self) -> List[str]:
        """Список кодов аллергенов"""
        allergens = set()
        for fi in self.flat_ingredients:
            if fi.ingredient.allergen_code:
                allergens.add(fi.ingredient.allergen_code)
            # Суб-ингредиенты составных
            if fi.ingredient.is_compound:
                for sub in fi.ingredient.sub_ingredients:
                    if sub.ingredient.allergen_code:
                        allergens.add(sub.ingredient.allergen_code)
        return sorted(allergens)

    def to_dict(self) -> dict:
        return {
            'article_nr': self.article_nr,
            'product_name': self.product_name,
            'total_input_weight': round(self.total_input_weight, 2),
            'final_product_weight': round(self.final_product_weight, 2),
            'tree_depth': self.tree_depth,
            'recipe_hash': self.recipe_hash,
            'allergens_present': self.allergens_present,
            'ingredients': [fi.to_dict() for fi in self.flat_ingredients],
        }


@dataclass
class ConfirmedComposition:
    """Подтвержденный состав для этикетки"""
    id: Optional[int]
    article_nr: str
    confirmed_text_de: Optional[str] = None
    confirmed_text_nl: Optional[str] = None
    confirmed_text_fr: Optional[str] = None
    auto_generated_text_de: Optional[str] = None
    recipe_hash: Optional[str] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[str] = None
    is_outdated: bool = False

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'article_nr': self.article_nr,
            'confirmed_text_de': self.confirmed_text_de,
            'confirmed_text_nl': self.confirmed_text_nl,
            'confirmed_text_fr': self.confirmed_text_fr,
            'auto_generated_text_de': self.auto_generated_text_de,
            'recipe_hash': self.recipe_hash,
            'confirmed_by': self.confirmed_by,
            'confirmed_at': self.confirmed_at,
            'is_outdated': self.is_outdated,
        }
