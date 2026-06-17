-- ================================================
-- МИГРАЦИЯ: Система управления производственными ресурсами
-- Дата: 2025-12-23
-- Описание: Добавление таблиц для управления мощностями цехов
-- ================================================

-- 1. Таблица ресурсов (печи, рабочие места, оборудование)
CREATE TABLE IF NOT EXISTS factory_resources (
    resource_id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_name TEXT NOT NULL UNIQUE,           -- "Печь", "Стол сборки", "Линия машинки"
    resource_type TEXT NOT NULL,                  -- "equipment", "workstation", "manual"
    category TEXT,                                -- Связь с категорией (Biskuit, Medowik, etc.)
    quantity INTEGER NOT NULL DEFAULT 1,          -- Количество единиц оборудования/мест
    shifts_count INTEGER NOT NULL DEFAULT 1,      -- Количество рабочих смен (1, 2, 3)
    shift_duration_min INTEGER NOT NULL DEFAULT 480, -- Длительность смены в минутах (480 = 8 часов)
    efficiency REAL NOT NULL DEFAULT 1.0,         -- Коэффициент эффективности (0.0-1.0)
    description TEXT,                             -- Описание ресурса
    active INTEGER DEFAULT 1,                     -- Активен (1/0)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Таблица потребления ресурсов артикулами
CREATE TABLE IF NOT EXISTS product_resource_consumption (
    consumption_id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_nr TEXT NOT NULL,                     -- Артикул (05501)
    resource_id INTEGER NOT NULL,                 -- ID ресурса
    time_needed_min REAL NOT NULL,                -- Минут на единицу продукции
    batch_multiplier REAL DEFAULT 1.0,            -- Множитель для замесов
    setup_time_min REAL DEFAULT 0,                -- Время на подготовку (разогрев печи, настройка)
    comments TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (resource_id) REFERENCES factory_resources(resource_id) ON DELETE CASCADE,
    UNIQUE(article_nr, resource_id)
);

-- 3. Таблица загрузки ресурсов (real-time данные)
CREATE TABLE IF NOT EXISTS resource_load_history (
    load_id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    date TEXT NOT NULL,                           -- Дата производства (YYYY-MM-DD)
    planned_load_min REAL NOT NULL DEFAULT 0,     -- Запланированная загрузка (минут)
    actual_load_min REAL DEFAULT 0,               -- Фактическая загрузка (минут)
    available_capacity_min REAL NOT NULL,         -- Доступная мощность (минут)
    utilization_percent REAL NOT NULL,            -- Процент использования
    status TEXT DEFAULT 'normal',                 -- normal, warning, critical, overload
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (resource_id) REFERENCES factory_resources(resource_id) ON DELETE CASCADE,
    UNIQUE(resource_id, date)
);

-- 4. Таблица рекомендаций системы
CREATE TABLE IF NOT EXISTS production_recommendations (
    recommendation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                           -- Дата производства
    resource_id INTEGER,                          -- ID ресурса (если специфично)
    recommendation_type TEXT NOT NULL,            -- "add_shift", "move_to_prev_day", "increase_capacity"
    severity TEXT DEFAULT 'info',                 -- info, warning, critical
    message TEXT NOT NULL,                        -- Текст рекомендации
    details TEXT,                                 -- JSON с деталями
    acknowledged INTEGER DEFAULT 0,               -- Пользователь увидел (1/0)
    acknowledged_at TEXT,
    acknowledged_by TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (resource_id) REFERENCES factory_resources(resource_id) ON DELETE SET NULL
);

-- 5. Создание индексов для производительности
CREATE INDEX IF NOT EXISTS idx_product_consumption_article ON product_resource_consumption(article_nr);
CREATE INDEX IF NOT EXISTS idx_product_consumption_resource ON product_resource_consumption(resource_id);
CREATE INDEX IF NOT EXISTS idx_resource_load_date ON resource_load_history(date);
CREATE INDEX IF NOT EXISTS idx_resource_load_resource ON resource_load_history(resource_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_date ON production_recommendations(date);
CREATE INDEX IF NOT EXISTS idx_recommendations_acknowledged ON production_recommendations(acknowledged);

-- ================================================
-- ЗАПОЛНЕНИЕ НАЧАЛЬНЫМИ ДАННЫМИ
-- ================================================

-- Ресурсы по умолчанию (5 цехов)
INSERT OR IGNORE INTO factory_resources
(resource_name, resource_type, category, quantity, shifts_count, shift_duration_min, efficiency, description, active, created_at, updated_at)
VALUES
    -- Цех 1: Печь (Выпечка)
    ('Печь', 'equipment', NULL, 2, 1, 480, 0.90, 'Производственные печи для выпечки тортов и хлебобулочных изделий. Эффективность 90% (учет разогрева и чистки)', 1, datetime('now'), datetime('now')),

    -- Цех 2: Крем (Приготовление кремов)
    ('Крем - Рабочие места', 'workstation', NULL, 3, 1, 480, 1.0, 'Рабочие места для приготовления кремов и начинок', 1, datetime('now'), datetime('now')),

    -- Цех 3: Грунтовка (Грунтовка тортов)
    ('Грунтовка - Рабочие места', 'workstation', NULL, 4, 1, 480, 1.0, 'Рабочие места для грунтовки и выравнивания тортов', 1, datetime('now'), datetime('now')),

    -- Цех 4: Декор (Украшение)
    ('Декор - Рабочие места', 'workstation', NULL, 5, 1, 480, 1.0, 'Рабочие места для финального украшения тортов', 1, datetime('now'), datetime('now')),

    -- Цех 5: Машинка (Упаковка)
    ('Машинка - Линия упаковки', 'equipment', NULL, 1, 1, 480, 0.95, 'Автоматическая линия упаковки. Эффективность 95% (техническое обслуживание)', 1, datetime('now'), datetime('now'));

-- ================================================
-- ПРИМЕРЫ ПОТРЕБЛЕНИЯ РЕСУРСОВ (ШАБЛОНЫ)
-- ================================================
-- Эти данные будут заполняться автоматически на основе рецептов
-- Здесь приведены примеры для понимания структуры

INSERT OR IGNORE INTO product_resource_consumption
(article_nr, resource_id, time_needed_min, batch_multiplier, setup_time_min, comments, created_at, updated_at)
VALUES
    -- Пример: Торт Медовик
    ('05501', 1, 45.0, 1.0, 15.0, 'Выпечка коржей: 45 мин на замес + 15 мин разогрев печи', datetime('now'), datetime('now')),
    ('05501', 2, 30.0, 1.0, 0, 'Приготовление медового крема: 30 мин', datetime('now'), datetime('now')),
    ('05501', 3, 20.0, 1.0, 0, 'Грунтовка: 20 мин на торт', datetime('now'), datetime('now')),
    ('05501', 4, 40.0, 1.0, 0, 'Украшение: 40 мин на торт', datetime('now'), datetime('now')),
    ('05501', 5, 5.0, 1.0, 0, 'Упаковка: 5 мин на торт', datetime('now'), datetime('now'));

-- ================================================
-- ПРЕДСТАВЛЕНИЯ (VIEWS) ДЛЯ УДОБСТВА ЗАПРОСОВ
-- ================================================

-- View: Сводка по доступной мощности ресурсов
CREATE VIEW IF NOT EXISTS v_resource_capacity AS
SELECT
    r.resource_id,
    r.resource_name,
    r.resource_type,
    r.quantity,
    r.shifts_count,
    r.shift_duration_min,
    r.efficiency,
    (r.quantity * r.shifts_count * r.shift_duration_min * r.efficiency) AS total_capacity_min,
    r.active
FROM factory_resources r
WHERE r.active = 1;

-- View: Загрузка ресурсов с цветовым статусом
CREATE VIEW IF NOT EXISTS v_resource_load_status AS
SELECT
    rlh.load_id,
    rlh.resource_id,
    r.resource_name,
    rlh.date,
    rlh.planned_load_min,
    rlh.available_capacity_min,
    rlh.utilization_percent,
    rlh.status,
    CASE
        WHEN rlh.utilization_percent < 70 THEN '🟢 Норма'
        WHEN rlh.utilization_percent < 85 THEN '🟡 Предупреждение'
        WHEN rlh.utilization_percent < 100 THEN '🟠 Высокая загрузка'
        ELSE '🔴 Перегрузка'
    END AS status_label,
    rlh.updated_at
FROM resource_load_history rlh
JOIN factory_resources r ON rlh.resource_id = r.resource_id;

-- View: Потребление ресурсов с названиями артикулов
CREATE VIEW IF NOT EXISTS v_product_resource_details AS
SELECT
    prc.consumption_id,
    prc.article_nr,
    rec.name AS article_name,
    rec.category,
    prc.resource_id,
    fr.resource_name,
    prc.time_needed_min,
    prc.batch_multiplier,
    prc.setup_time_min,
    prc.comments
FROM product_resource_consumption prc
JOIN factory_resources fr ON prc.resource_id = fr.resource_id
LEFT JOIN recipes rec ON prc.article_nr = rec.article_nr;

-- ================================================
-- КОНЕЦ МИГРАЦИИ
-- ================================================
