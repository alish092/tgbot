-- db-init/init.sql

-- Создаём таблицу синонимов
CREATE TABLE IF NOT EXISTS synonym (
    id SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL,
    synonym TEXT NOT NULL
);

-- Создаём таблицу приоритетов
CREATE TABLE IF NOT EXISTS priority (
    id SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL,
    document_name TEXT NOT NULL
);
