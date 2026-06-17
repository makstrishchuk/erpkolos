"""
Zutaten V2 - Мультиязычная система управления ингредиентами
Соответствует EU Regulation 1169/2011 (LMIV)

Языки: DE (немецкий), NL (нидерландский), FR (французский)

V2.1: Рекурсивное дерево рецептов, CompositionCalculator,
      подтверждение состава с детекцией изменений.
"""

from .enums import Language, AllergenCode, HydrogenationStatus, AdditiveClassCode
from .models import (
    TranslatedText,
    IngredientMaster,
    RecipeIngredient,
    RecipeForLabel,
    AllergenReference,
    AdditiveClass,
    # V2.1
    RecipeTreeNode,
    FlatIngredient,
    CompositionResult,
    ConfirmedComposition,
)
from .generator import MultilingualLabelGenerator
from .database import ZutatenDatabase
from .calculator import CompositionCalculator

__all__ = [
    # Enums
    'Language',
    'AllergenCode',
    'HydrogenationStatus',
    'AdditiveClassCode',
    # Models
    'TranslatedText',
    'IngredientMaster',
    'RecipeIngredient',
    'RecipeForLabel',
    'AllergenReference',
    'AdditiveClass',
    # V2.1 Models
    'RecipeTreeNode',
    'FlatIngredient',
    'CompositionResult',
    'ConfirmedComposition',
    # Core
    'MultilingualLabelGenerator',
    'ZutatenDatabase',
    'CompositionCalculator',
]

__version__ = '2.1.0'
