"""
Статические переводы для модуля Zutaten V2
Языки: DE (немецкий), NL (нидерландский), FR (французский)
"""

from .enums import Language

# ============================================
# ЗАГОЛОВКИ ЭТИКЕТОК
# ============================================

LABEL_HEADERS = {
    Language.DE: "Zutaten:",
    Language.NL: "Ingrediënten:",
    Language.FR: "Ingrédients:",
}

# ============================================
# СТАТУС ГИДРОГЕНИЗАЦИИ (для масел/жиров)
# ============================================

HYDROGENATION_TRANSLATIONS = {
    "PARTLY": {
        Language.DE: "teilweise gehärtet",
        Language.NL: "gedeeltelijk gehard",
        Language.FR: "partiellement hydrogéné",
    },
    "FULLY": {
        Language.DE: "ganz gehärtet",
        Language.NL: "volledig gehard",
        Language.FR: "totalement hydrogéné",
    },
}

# ============================================
# НАЗВАНИЯ АЛЛЕРГЕНОВ
# ============================================

ALLERGEN_NAMES = {
    "GLUTEN": {
        Language.DE: "Gluten",
        Language.NL: "Gluten",
        Language.FR: "Gluten",
    },
    "CRUSTACEANS": {
        Language.DE: "Krebstiere",
        Language.NL: "Schaaldieren",
        Language.FR: "Crustacés",
    },
    "EGGS": {
        Language.DE: "Eier",
        Language.NL: "Eieren",
        Language.FR: "Œufs",
    },
    "FISH": {
        Language.DE: "Fisch",
        Language.NL: "Vis",
        Language.FR: "Poisson",
    },
    "PEANUTS": {
        Language.DE: "Erdnüsse",
        Language.NL: "Pinda's",
        Language.FR: "Arachides",
    },
    "SOYBEANS": {
        Language.DE: "Soja",
        Language.NL: "Soja",
        Language.FR: "Soja",
    },
    "MILK": {
        Language.DE: "Milch",
        Language.NL: "Melk",
        Language.FR: "Lait",
    },
    "NUTS": {
        Language.DE: "Schalenfrüchte",
        Language.NL: "Noten",
        Language.FR: "Fruits à coque",
    },
    "CELERY": {
        Language.DE: "Sellerie",
        Language.NL: "Selderij",
        Language.FR: "Céleri",
    },
    "MUSTARD": {
        Language.DE: "Senf",
        Language.NL: "Mosterd",
        Language.FR: "Moutarde",
    },
    "SESAME": {
        Language.DE: "Sesam",
        Language.NL: "Sesamzaad",
        Language.FR: "Sésame",
    },
    "SULPHITES": {
        Language.DE: "Schwefeldioxid und Sulphite",
        Language.NL: "Zwaveldioxide en sulfieten",
        Language.FR: "Anhydride sulfureux et sulfites",
    },
    "LUPIN": {
        Language.DE: "Lupinen",
        Language.NL: "Lupine",
        Language.FR: "Lupin",
    },
    "MOLLUSCS": {
        Language.DE: "Weichtiere",
        Language.NL: "Weekdieren",
        Language.FR: "Mollusques",
    },
}

# ============================================
# НАЗВАНИЯ КЛАССОВ ДОБАВОК
# ============================================

ADDITIVE_CLASS_NAMES = {
    "PRESERVATIVE": {
        Language.DE: "Konservierungsstoff",
        Language.NL: "Conserveringsmiddel",
        Language.FR: "Conservateur",
    },
    "ANTIOXIDANT": {
        Language.DE: "Antioxidationsmittel",
        Language.NL: "Antioxidant",
        Language.FR: "Antioxydant",
    },
    "EMULSIFIER": {
        Language.DE: "Emulgator",
        Language.NL: "Emulgator",
        Language.FR: "Émulsifiant",
    },
    "STABILIZER": {
        Language.DE: "Stabilisator",
        Language.NL: "Stabilisator",
        Language.FR: "Stabilisant",
    },
    "THICKENER": {
        Language.DE: "Verdickungsmittel",
        Language.NL: "Verdikkingsmiddel",
        Language.FR: "Épaississant",
    },
    "GELLING_AGENT": {
        Language.DE: "Geliermittel",
        Language.NL: "Geleermiddel",
        Language.FR: "Gélifiant",
    },
    "COLORANT": {
        Language.DE: "Farbstoff",
        Language.NL: "Kleurstof",
        Language.FR: "Colorant",
    },
    "SWEETENER": {
        Language.DE: "Süßungsmittel",
        Language.NL: "Zoetstof",
        Language.FR: "Édulcorant",
    },
    "ACIDIFIER": {
        Language.DE: "Säuerungsmittel",
        Language.NL: "Zuurteregelaar",
        Language.FR: "Acidifiant",
    },
    "RAISING_AGENT": {
        Language.DE: "Backtriebmittel",
        Language.NL: "Rijsmiddel",
        Language.FR: "Poudre à lever",
    },
    "FLAVOR_ENHANCER": {
        Language.DE: "Geschmacksverstärker",
        Language.NL: "Smaakversterker",
        Language.FR: "Exhausteur de goût",
    },
    "HUMECTANT": {
        Language.DE: "Feuchthaltemittel",
        Language.NL: "Bevochtigingsmiddel",
        Language.FR: "Humectant",
    },
    "ANTI_CAKING": {
        Language.DE: "Trennmittel",
        Language.NL: "Antiklontermiddel",
        Language.FR: "Antiagglomérant",
    },
    "GLAZING_AGENT": {
        Language.DE: "Überzugsmittel",
        Language.NL: "Glansmiddel",
        Language.FR: "Agent d'enrobage",
    },
    "MODIFIED_STARCH": {
        Language.DE: "Modifizierte Stärke",
        Language.NL: "Gemodificeerd zetmeel",
        Language.FR: "Amidon modifié",
    },
}

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ТЕКСТЫ
# ============================================

WATER_NAMES = {
    Language.DE: "Wasser",
    Language.NL: "Water",
    Language.FR: "Eau",
}

CONTAINS_TEXT = {
    Language.DE: "enthält",
    Language.NL: "bevat",
    Language.FR: "contient",
}

VARIABLE_PROPORTIONS = {
    Language.DE: "in veränderlichen Gewichtsanteilen",
    Language.NL: "in wisselende gewichtsverhoudingen",
    Language.FR: "en proportions variables",
}

VEGETABLE_OILS = {
    Language.DE: "pflanzliche Öle",
    Language.NL: "plantaardige oliën",
    Language.FR: "huiles végétales",
}

VEGETABLE_FATS = {
    Language.DE: "pflanzliche Fette",
    Language.NL: "plantaardige vetten",
    Language.FR: "graisses végétales",
}

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

def get_label_header(lang: Language) -> str:
    """Получить заголовок этикетки на указанном языке"""
    return LABEL_HEADERS.get(lang, LABEL_HEADERS[Language.DE])


def get_hydrogenation_text(status: str, lang: Language) -> str:
    """Получить текст статуса гидрогенизации"""
    if status not in HYDROGENATION_TRANSLATIONS:
        return ""
    return HYDROGENATION_TRANSLATIONS[status].get(lang, HYDROGENATION_TRANSLATIONS[status][Language.DE])


def get_allergen_name(code: str, lang: Language) -> str:
    """Получить название аллергена на указанном языке"""
    if code not in ALLERGEN_NAMES:
        return code
    return ALLERGEN_NAMES[code].get(lang, ALLERGEN_NAMES[code][Language.DE])


def get_additive_class_name(code: str, lang: Language) -> str:
    """Получить название класса добавки на указанном языке"""
    if code not in ADDITIVE_CLASS_NAMES:
        return code
    return ADDITIVE_CLASS_NAMES[code].get(lang, ADDITIVE_CLASS_NAMES[code][Language.DE])


def get_water_name(lang: Language) -> str:
    """Получить название воды на указанном языке"""
    return WATER_NAMES.get(lang, WATER_NAMES[Language.DE])


def get_contains_text(lang: Language) -> str:
    """Получить текст 'содержит' на указанном языке"""
    return CONTAINS_TEXT.get(lang, CONTAINS_TEXT[Language.DE])
