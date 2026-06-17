"""
Перечисления для модуля Zutaten V2
"""

from enum import Enum


class Language(Enum):
    """Поддерживаемые языки для этикеток"""
    DE = "de"  # Немецкий (по умолчанию, обязательный)
    NL = "nl"  # Нидерландский
    FR = "fr"  # Французский


class AllergenCode(Enum):
    """14 основных аллергенов ЕС согласно Приложению II LMIV"""
    GLUTEN = "GLUTEN"           # Глютен (пшеница, рожь, ячмень, овес, полба, камут)
    CRUSTACEANS = "CRUSTACEANS" # Ракообразные
    EGGS = "EGGS"               # Яйца
    FISH = "FISH"               # Рыба
    PEANUTS = "PEANUTS"         # Арахис
    SOYBEANS = "SOYBEANS"       # Соя
    MILK = "MILK"               # Молоко (включая лактозу)
    NUTS = "NUTS"               # Орехи (миндаль, фундук, грецкие и др.)
    CELERY = "CELERY"           # Сельдерей
    MUSTARD = "MUSTARD"         # Горчица
    SESAME = "SESAME"           # Кунжут
    SULPHITES = "SULPHITES"     # Диоксид серы и сульфиты (>10 мг/кг)
    LUPIN = "LUPIN"             # Люпин
    MOLLUSCS = "MOLLUSCS"       # Моллюски


class HydrogenationStatus(Enum):
    """Статус гидрогенизации для масел и жиров (Annex VII Part A)"""
    NONE = "NONE"       # Не гидрогенизировано
    PARTLY = "PARTLY"   # Частично гидрогенизировано (teilweise gehärtet)
    FULLY = "FULLY"     # Полностью гидрогенизировано (ganz gehärtet)


class AdditiveClassCode(Enum):
    """Функциональные классы пищевых добавок (Annex VII Part C)"""
    PRESERVATIVE = "PRESERVATIVE"         # Консервант
    ANTIOXIDANT = "ANTIOXIDANT"           # Антиоксидант
    EMULSIFIER = "EMULSIFIER"             # Эмульгатор
    STABILIZER = "STABILIZER"             # Стабилизатор
    THICKENER = "THICKENER"               # Загуститель
    GELLING_AGENT = "GELLING_AGENT"       # Желирующий агент
    COLORANT = "COLORANT"                 # Краситель
    SWEETENER = "SWEETENER"               # Подсластитель
    ACIDIFIER = "ACIDIFIER"               # Регулятор кислотности
    RAISING_AGENT = "RAISING_AGENT"       # Разрыхлитель
    FLAVOR_ENHANCER = "FLAVOR_ENHANCER"   # Усилитель вкуса
    HUMECTANT = "HUMECTANT"               # Влагоудерживающий агент
    ANTI_CAKING = "ANTI_CAKING"           # Антислеживающий агент
    GLAZING_AGENT = "GLAZING_AGENT"       # Глазирователь
    MODIFIED_STARCH = "MODIFIED_STARCH"   # Модифицированный крахмал


class IngredientCategory(Enum):
    """Категории ингредиентов для фильтрации"""
    FLOUR = "flour"           # Мука
    SUGAR = "sugar"           # Сахар и подсластители
    DAIRY = "dairy"           # Молочные продукты
    EGG = "egg"               # Яйца
    FAT = "fat"               # Жиры и масла
    NUT = "nut"               # Орехи
    FRUIT = "fruit"           # Фрукты и ягоды
    CHOCOLATE = "chocolate"   # Шоколад и какао
    FLAVORING = "flavoring"   # Ароматизаторы
    ADDITIVE = "additive"     # Пищевые добавки
    OTHER = "other"           # Прочее
