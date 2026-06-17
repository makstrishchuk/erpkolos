-- ================================================
-- МИГРАЦИЯ 003: Поле Deklarationsname для ингредиентов
-- Дата: 2026-02-24
-- Описание: Добавляет поле "declaration_name" (Deklarationsname) к ингредиентам.
--
-- Назначение:
--   Позволяет задать официальное декларационное название ингредиента на этикетке,
--   отличное от внутреннего названия. Например:
--     name_de = "Backmargarine RSPOsg Typ A"  (внутреннее)
--     declaration_name_de = "Margarine"       (на этикетке)
--
--   Если declaration_name заполнен:
--   1. Он используется как отображаемое имя на этикетке (вместо name_de).
--   2. Составной ингредиент НЕ разворачивается в суб-ингредиенты,
--      даже если expand_sub_ingredients_only=1 или имя содержит запрещённые токены.
--   3. Несколько ингредиентов с одинаковым declaration_name_de ("Margarine")
--      автоматически объединяются в одну запись с суммарным весом и
--      объединёнными суб-ингредиентами.
-- ================================================

ALTER TABLE ingredients_master ADD COLUMN declaration_name_de TEXT;
ALTER TABLE ingredients_master ADD COLUMN declaration_name_nl TEXT;
ALTER TABLE ingredients_master ADD COLUMN declaration_name_fr TEXT;
