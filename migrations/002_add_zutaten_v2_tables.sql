-- ================================================
-- МИГРАЦИЯ: Система управления ингредиентами (Zutaten v2)
-- Дата: 2026-02-03
-- Описание: Мультиязычное управление ингредиентами по LMIV (EU 1169/2011)
-- Языки: DE (немецкий), NL (нидерландский), FR (французский)
-- ================================================

-- 1. Справочник 14 аллергенов ЕС (Art. 21 LMIV)
CREATE TABLE IF NOT EXISTS allergens_reference (
    allergen_id INTEGER PRIMARY KEY AUTOINCREMENT,
    allergen_code TEXT UNIQUE NOT NULL,           -- "GLUTEN", "MILK", "EGGS"
    name_de TEXT NOT NULL,                        -- Немецкий
    name_nl TEXT NOT NULL,                        -- Нидерландский
    name_fr TEXT NOT NULL,                        -- Французский
    description_de TEXT,                          -- Описание DE
    sort_order INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 2. Справочник функциональных классов добавок (Annex VII Part C)
CREATE TABLE IF NOT EXISTS additive_classes (
    class_id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_code TEXT UNIQUE NOT NULL,              -- "PRESERVATIVE", "EMULSIFIER"
    name_de TEXT NOT NULL,                        -- "Konservierungsstoff"
    name_nl TEXT NOT NULL,                        -- "Conserveringsmiddel"
    name_fr TEXT NOT NULL,                        -- "Conservateur"
    example_e_numbers TEXT,                       -- "E 200-E 299"
    sort_order INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

-- 3. Мастер-таблица ингредиентов
CREATE TABLE IF NOT EXISTS ingredients_master (
    ingredient_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_code TEXT UNIQUE NOT NULL,         -- "FLOUR_WHEAT_T550", "SUGAR_WHITE"

    -- Мультиязычные названия
    name_de TEXT NOT NULL,                        -- Немецкий (обязательный)
    name_nl TEXT,                                 -- Нидерландский
    name_fr TEXT,                                 -- Французский

    -- Классификация
    category TEXT,                                -- "flour", "sugar", "dairy", "fruit", "nut", "additive"
    is_compound INTEGER DEFAULT 0,                -- Составной ингредиент (1/0)

    -- Аллерген (Art. 21)
    allergen_id INTEGER,                          -- FK to allergens_reference

    -- Добавки (Annex VII Part C)
    additive_class_id INTEGER,                    -- FK to additive_classes
    e_number TEXT,                                -- "E 202", "E 330"

    -- Нано-материалы (Art. 18, Abs. 3)
    is_nano INTEGER DEFAULT 0,                    -- Если 1, добавить "(nano)" к названию

    -- Масла/жиры (Annex VII Part A)
    is_oil_fat INTEGER DEFAULT 0,
    botanical_origin_de TEXT,                     -- "Palm", "Raps", "Sonnenblume"
    botanical_origin_nl TEXT,                     -- "Palm", "Koolzaad", "Zonnebloem"
    botanical_origin_fr TEXT,                     -- "Palme", "Colza", "Tournesol"
    hydrogenation TEXT DEFAULT 'NONE',            -- "NONE", "PARTLY", "FULLY"

    -- Вода (Anhang VII, Teil A)
    is_added_water INTEGER DEFAULT 0,
    loss_factor REAL DEFAULT 0.0,                 -- Коэф. потерь при обработке (0.0-1.0)

    -- Нутриенты (опционально для расчёта БЖУ)
    kcal_per_100g REAL,
    fat_per_100g REAL,
    carbs_per_100g REAL,
    protein_per_100g REAL,
    salt_per_100g REAL,

    -- Метаданные
    notes TEXT,
    active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (allergen_id) REFERENCES allergens_reference(allergen_id) ON DELETE SET NULL,
    FOREIGN KEY (additive_class_id) REFERENCES additive_classes(class_id) ON DELETE SET NULL
);

-- 4. Суб-ингредиенты для составных ингредиентов (Annex VII Part E)
CREATE TABLE IF NOT EXISTS ingredient_sub_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_ingredient_id INTEGER NOT NULL,        -- FK: составной ингредиент
    child_ingredient_id INTEGER NOT NULL,         -- FK: суб-ингредиент
    weight_percentage REAL NOT NULL,              -- Процент от веса родителя (0.0-100.0)
    sort_order INTEGER DEFAULT 0,                 -- Порядок сортировки (если отличается от веса)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (parent_ingredient_id) REFERENCES ingredients_master(ingredient_id) ON DELETE CASCADE,
    FOREIGN KEY (child_ingredient_id) REFERENCES ingredients_master(ingredient_id) ON DELETE RESTRICT,
    UNIQUE(parent_ingredient_id, child_ingredient_id)
);

-- 5. Связь рецептов с ингредиентами
CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_nr TEXT NOT NULL,                     -- FK to recipes.article_nr
    ingredient_id INTEGER NOT NULL,               -- FK to ingredients_master
    weight_grams REAL NOT NULL,                   -- Вес в рецепте (граммы)
    highlight_quid INTEGER DEFAULT 0,             -- Показывать % (Art. 22 QUID)
    sort_override INTEGER,                        -- Ручная сортировка (NULL = авто по весу)
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (article_nr) REFERENCES recipes(article_nr) ON DELETE CASCADE,
    FOREIGN KEY (ingredient_id) REFERENCES ingredients_master(ingredient_id) ON DELETE RESTRICT,
    UNIQUE(article_nr, ingredient_id)
);

-- ================================================
-- ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ
-- ================================================

CREATE INDEX IF NOT EXISTS idx_ingredients_allergen ON ingredients_master(allergen_id);
CREATE INDEX IF NOT EXISTS idx_ingredients_additive ON ingredients_master(additive_class_id);
CREATE INDEX IF NOT EXISTS idx_ingredients_category ON ingredients_master(category);
CREATE INDEX IF NOT EXISTS idx_ingredients_code ON ingredients_master(ingredient_code);
CREATE INDEX IF NOT EXISTS idx_ingredients_active ON ingredients_master(active);

CREATE INDEX IF NOT EXISTS idx_sub_ingredients_parent ON ingredient_sub_ingredients(parent_ingredient_id);
CREATE INDEX IF NOT EXISTS idx_sub_ingredients_child ON ingredient_sub_ingredients(child_ingredient_id);

CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_article ON recipe_ingredients(article_nr);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_ingredient ON recipe_ingredients(ingredient_id);

-- ================================================
-- ЗАПОЛНЕНИЕ НАЧАЛЬНЫМИ ДАННЫМИ: 14 АЛЛЕРГЕНОВ ЕС
-- ================================================

INSERT OR IGNORE INTO allergens_reference
(allergen_code, name_de, name_nl, name_fr, description_de, sort_order, active, created_at)
VALUES
    ('GLUTEN', 'Gluten', 'Gluten', 'Gluten',
     'Glutenhaltiges Getreide: Weizen, Roggen, Gerste, Hafer, Dinkel, Kamut', 1, 1, datetime('now')),

    ('CRUSTACEANS', 'Krebstiere', 'Schaaldieren', 'Crustacés',
     'Krebstiere und daraus gewonnene Erzeugnisse', 2, 1, datetime('now')),

    ('EGGS', 'Eier', 'Eieren', 'Œufs',
     'Eier und daraus gewonnene Erzeugnisse', 3, 1, datetime('now')),

    ('FISH', 'Fisch', 'Vis', 'Poisson',
     'Fisch und daraus gewonnene Erzeugnisse', 4, 1, datetime('now')),

    ('PEANUTS', 'Erdnüsse', 'Pinda''s', 'Arachides',
     'Erdnüsse und daraus gewonnene Erzeugnisse', 5, 1, datetime('now')),

    ('SOYBEANS', 'Soja', 'Soja', 'Soja',
     'Sojabohnen und daraus gewonnene Erzeugnisse', 6, 1, datetime('now')),

    ('MILK', 'Milch', 'Melk', 'Lait',
     'Milch und daraus gewonnene Erzeugnisse (einschließlich Laktose)', 7, 1, datetime('now')),

    ('NUTS', 'Schalenfrüchte', 'Noten', 'Fruits à coque',
     'Schalenfrüchte: Mandeln, Haselnüsse, Walnüsse, Cashewnüsse, Pecannüsse, Paranüsse, Pistazien, Macadamia', 8, 1, datetime('now')),

    ('CELERY', 'Sellerie', 'Selderij', 'Céleri',
     'Sellerie und daraus gewonnene Erzeugnisse', 9, 1, datetime('now')),

    ('MUSTARD', 'Senf', 'Mosterd', 'Moutarde',
     'Senf und daraus gewonnene Erzeugnisse', 10, 1, datetime('now')),

    ('SESAME', 'Sesam', 'Sesamzaad', 'Sésame',
     'Sesamsamen und daraus gewonnene Erzeugnisse', 11, 1, datetime('now')),

    ('SULPHITES', 'Schwefeldioxid und Sulphite', 'Zwaveldioxide en sulfieten', 'Anhydride sulfureux et sulfites',
     'Schwefeldioxid und Sulphite in Konzentrationen von mehr als 10 mg/kg oder 10 mg/l', 12, 1, datetime('now')),

    ('LUPIN', 'Lupinen', 'Lupine', 'Lupin',
     'Lupinen und daraus gewonnene Erzeugnisse', 13, 1, datetime('now')),

    ('MOLLUSCS', 'Weichtiere', 'Weekdieren', 'Mollusques',
     'Weichtiere und daraus gewonnene Erzeugnisse', 14, 1, datetime('now'));

-- ================================================
-- ЗАПОЛНЕНИЕ НАЧАЛЬНЫМИ ДАННЫМИ: КЛАССЫ ДОБАВОК
-- ================================================

INSERT OR IGNORE INTO additive_classes
(class_code, name_de, name_nl, name_fr, example_e_numbers, sort_order, active, created_at)
VALUES
    ('PRESERVATIVE', 'Konservierungsstoff', 'Conserveringsmiddel', 'Conservateur',
     'E 200-E 299', 1, 1, datetime('now')),

    ('ANTIOXIDANT', 'Antioxidationsmittel', 'Antioxidant', 'Antioxydant',
     'E 300-E 399', 2, 1, datetime('now')),

    ('EMULSIFIER', 'Emulgator', 'Emulgator', 'Émulsifiant',
     'E 322, E 471-E 495', 3, 1, datetime('now')),

    ('STABILIZER', 'Stabilisator', 'Stabilisator', 'Stabilisant',
     'E 400-E 499', 4, 1, datetime('now')),

    ('THICKENER', 'Verdickungsmittel', 'Verdikkingsmiddel', 'Épaississant',
     'E 400-E 499', 5, 1, datetime('now')),

    ('GELLING_AGENT', 'Geliermittel', 'Geleermiddel', 'Gélifiant',
     'E 400-E 499', 6, 1, datetime('now')),

    ('COLORANT', 'Farbstoff', 'Kleurstof', 'Colorant',
     'E 100-E 199', 7, 1, datetime('now')),

    ('SWEETENER', 'Süßungsmittel', 'Zoetstof', 'Édulcorant',
     'E 950-E 969', 8, 1, datetime('now')),

    ('ACIDIFIER', 'Säuerungsmittel', 'Zuurteregelaar', 'Acidifiant',
     'E 260, E 270, E 330', 9, 1, datetime('now')),

    ('RAISING_AGENT', 'Backtriebmittel', 'Rijsmiddel', 'Poudre à lever',
     'E 500, E 503', 10, 1, datetime('now')),

    ('FLAVOR_ENHANCER', 'Geschmacksverstärker', 'Smaakversterker', 'Exhausteur de goût',
     'E 620-E 640', 11, 1, datetime('now')),

    ('HUMECTANT', 'Feuchthaltemittel', 'Bevochtigingsmiddel', 'Humectant',
     'E 420, E 422', 12, 1, datetime('now')),

    ('ANTI_CAKING', 'Trennmittel', 'Antiklontermiddel', 'Antiagglomérant',
     'E 535, E 551, E 552', 13, 1, datetime('now')),

    ('GLAZING_AGENT', 'Überzugsmittel', 'Glansmiddel', 'Agent d''enrobage',
     'E 901-E 904', 14, 1, datetime('now')),

    ('MODIFIED_STARCH', 'Modifizierte Stärke', 'Gemodificeerd zetmeel', 'Amidon modifié',
     'E 1404-E 1450', 15, 1, datetime('now'));

-- ================================================
-- ЗАПОЛНЕНИЕ НАЧАЛЬНЫМИ ДАННЫМИ: БАЗОВЫЕ ИНГРЕДИЕНТЫ ДЛЯ КОНДИТЕРСКОЙ
-- ================================================

INSERT OR IGNORE INTO ingredients_master
(ingredient_code, name_de, name_nl, name_fr, category, allergen_id, active, created_at, updated_at)
VALUES
    -- Мука (с глютеном)
    ('FLOUR_WHEAT', 'Weizenmehl', 'Tarwemeel', 'Farine de blé', 'flour',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'GLUTEN'), 1, datetime('now'), datetime('now')),

    ('FLOUR_RYE', 'Roggenmehl', 'Roggemeel', 'Farine de seigle', 'flour',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'GLUTEN'), 1, datetime('now'), datetime('now')),

    ('FLOUR_SPELT', 'Dinkelmehl', 'Speltmeel', 'Farine d''épeautre', 'flour',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'GLUTEN'), 1, datetime('now'), datetime('now')),

    -- Сахар
    ('SUGAR_WHITE', 'Zucker', 'Suiker', 'Sucre', 'sugar', NULL, 1, datetime('now'), datetime('now')),
    ('SUGAR_BROWN', 'Brauner Zucker', 'Bruine suiker', 'Sucre brun', 'sugar', NULL, 1, datetime('now'), datetime('now')),
    ('SUGAR_POWDERED', 'Puderzucker', 'Poedersuiker', 'Sucre glace', 'sugar', NULL, 1, datetime('now'), datetime('now')),
    ('HONEY', 'Honig', 'Honing', 'Miel', 'sugar', NULL, 1, datetime('now'), datetime('now')),

    -- Яйца
    ('EGG_WHOLE', 'Vollei', 'Heel ei', 'Œuf entier', 'egg',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'EGGS'), 1, datetime('now'), datetime('now')),

    ('EGG_YOLK', 'Eigelb', 'Eigeel', 'Jaune d''œuf', 'egg',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'EGGS'), 1, datetime('now'), datetime('now')),

    ('EGG_WHITE', 'Eiweiß', 'Eiwit', 'Blanc d''œuf', 'egg',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'EGGS'), 1, datetime('now'), datetime('now')),

    -- Молочные продукты
    ('BUTTER', 'Butter', 'Boter', 'Beurre', 'dairy',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),

    ('CREAM', 'Sahne', 'Room', 'Crème', 'dairy',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),

    ('SOUR_CREAM', 'Sauerrahm', 'Zure room', 'Crème fraîche', 'dairy',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),

    ('MILK', 'Milch', 'Melk', 'Lait', 'dairy',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),

    ('MILK_CONDENSED', 'Kondensmilch', 'Gecondenseerde melk', 'Lait concentré', 'dairy',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),

    ('CREAM_CHEESE', 'Frischkäse', 'Roomkaas', 'Fromage frais', 'dairy',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),

    ('MASCARPONE', 'Mascarpone', 'Mascarpone', 'Mascarpone', 'dairy',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),

    -- Орехи
    ('ALMOND', 'Mandeln', 'Amandelen', 'Amandes', 'nut',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'NUTS'), 1, datetime('now'), datetime('now')),

    ('HAZELNUT', 'Haselnüsse', 'Hazelnoten', 'Noisettes', 'nut',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'NUTS'), 1, datetime('now'), datetime('now')),

    ('WALNUT', 'Walnüsse', 'Walnoten', 'Noix', 'nut',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'NUTS'), 1, datetime('now'), datetime('now')),

    ('PISTACHIO', 'Pistazien', 'Pistachenoten', 'Pistaches', 'nut',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'NUTS'), 1, datetime('now'), datetime('now')),

    ('PEANUT', 'Erdnüsse', 'Pinda''s', 'Cacahuètes', 'nut',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'PEANUTS'), 1, datetime('now'), datetime('now')),

    -- Шоколад и какао
    ('COCOA_POWDER', 'Kakaopulver', 'Cacaopoeder', 'Poudre de cacao', 'chocolate', NULL, 1, datetime('now'), datetime('now')),
    ('COCOA_BUTTER', 'Kakaobutter', 'Cacaoboter', 'Beurre de cacao', 'chocolate', NULL, 1, datetime('now'), datetime('now')),
    ('CHOCOLATE_DARK', 'Zartbitterschokolade', 'Pure chocolade', 'Chocolat noir', 'chocolate', NULL, 1, datetime('now'), datetime('now')),
    ('CHOCOLATE_MILK', 'Vollmilchschokolade', 'Melkchocolade', 'Chocolat au lait', 'chocolate',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),
    ('CHOCOLATE_WHITE', 'Weiße Schokolade', 'Witte chocolade', 'Chocolat blanc', 'chocolate',
     (SELECT allergen_id FROM allergens_reference WHERE allergen_code = 'MILK'), 1, datetime('now'), datetime('now')),

    -- Фрукты и ягоды
    ('STRAWBERRY', 'Erdbeeren', 'Aardbeien', 'Fraises', 'fruit', NULL, 1, datetime('now'), datetime('now')),
    ('RASPBERRY', 'Himbeeren', 'Frambozen', 'Framboises', 'fruit', NULL, 1, datetime('now'), datetime('now')),
    ('BLUEBERRY', 'Heidelbeeren', 'Bosbessen', 'Myrtilles', 'fruit', NULL, 1, datetime('now'), datetime('now')),
    ('CHERRY', 'Kirschen', 'Kersen', 'Cerises', 'fruit', NULL, 1, datetime('now'), datetime('now')),
    ('APPLE', 'Äpfel', 'Appels', 'Pommes', 'fruit', NULL, 1, datetime('now'), datetime('now')),
    ('LEMON', 'Zitrone', 'Citroen', 'Citron', 'fruit', NULL, 1, datetime('now'), datetime('now')),
    ('ORANGE', 'Orange', 'Sinaasappel', 'Orange', 'fruit', NULL, 1, datetime('now'), datetime('now')),
    ('BANANA', 'Bananen', 'Bananen', 'Bananes', 'fruit', NULL, 1, datetime('now'), datetime('now')),

    -- Ваниль и ароматизаторы
    ('VANILLA_EXTRACT', 'Vanilleextrakt', 'Vanille-extract', 'Extrait de vanille', 'flavoring', NULL, 1, datetime('now'), datetime('now')),
    ('VANILLA_SUGAR', 'Vanillezucker', 'Vanillesuiker', 'Sucre vanillé', 'flavoring', NULL, 1, datetime('now'), datetime('now')),

    -- Прочее
    ('SALT', 'Salz', 'Zout', 'Sel', 'other', NULL, 1, datetime('now'), datetime('now')),
    ('WATER', 'Wasser', 'Water', 'Eau', 'other', NULL, 1, datetime('now'), datetime('now')),
    ('GELATIN', 'Gelatine', 'Gelatine', 'Gélatine', 'other', NULL, 1, datetime('now'), datetime('now')),
    ('STARCH_CORN', 'Maisstärke', 'Maïszetmeel', 'Fécule de maïs', 'other', NULL, 1, datetime('now'), datetime('now')),
    ('STARCH_POTATO', 'Kartoffelstärke', 'Aardappelzetmeel', 'Fécule de pomme de terre', 'other', NULL, 1, datetime('now'), datetime('now'));

-- Устанавливаем флаг is_added_water для воды
UPDATE ingredients_master SET is_added_water = 1 WHERE ingredient_code = 'WATER';

-- ================================================
-- ПРИМЕРЫ ДОБАВОК С E-НОМЕРАМИ
-- ================================================

INSERT OR IGNORE INTO ingredients_master
(ingredient_code, name_de, name_nl, name_fr, category, additive_class_id, e_number, active, created_at, updated_at)
VALUES
    ('E_500', 'Natriumcarbonat', 'Natriumcarbonaat', 'Carbonate de sodium', 'additive',
     (SELECT class_id FROM additive_classes WHERE class_code = 'RAISING_AGENT'), 'E 500', 1, datetime('now'), datetime('now')),

    ('E_503', 'Ammoniumcarbonat', 'Ammoniumcarbonaat', 'Carbonate d''ammonium', 'additive',
     (SELECT class_id FROM additive_classes WHERE class_code = 'RAISING_AGENT'), 'E 503', 1, datetime('now'), datetime('now')),

    ('E_322', 'Lecithin', 'Lecithine', 'Lécithine', 'additive',
     (SELECT class_id FROM additive_classes WHERE class_code = 'EMULSIFIER'), 'E 322', 1, datetime('now'), datetime('now')),

    ('E_330', 'Citronensäure', 'Citroenzuur', 'Acide citrique', 'additive',
     (SELECT class_id FROM additive_classes WHERE class_code = 'ACIDIFIER'), 'E 330', 1, datetime('now'), datetime('now')),

    ('E_300', 'Ascorbinsäure', 'Ascorbinezuur', 'Acide ascorbique', 'additive',
     (SELECT class_id FROM additive_classes WHERE class_code = 'ANTIOXIDANT'), 'E 300', 1, datetime('now'), datetime('now')),

    ('E_202', 'Kaliumsorbat', 'Kaliumsorbaat', 'Sorbate de potassium', 'additive',
     (SELECT class_id FROM additive_classes WHERE class_code = 'PRESERVATIVE'), 'E 202', 1, datetime('now'), datetime('now')),

    ('E_440', 'Pektin', 'Pectine', 'Pectine', 'additive',
     (SELECT class_id FROM additive_classes WHERE class_code = 'GELLING_AGENT'), 'E 440', 1, datetime('now'), datetime('now')),

    ('E_415', 'Xanthan', 'Xanthaangom', 'Gomme xanthane', 'additive',
     (SELECT class_id FROM additive_classes WHERE class_code = 'THICKENER'), 'E 415', 1, datetime('now'), datetime('now'));

-- ================================================
-- КОНЕЦ МИГРАЦИИ
-- ================================================
