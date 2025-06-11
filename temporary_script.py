import os
import unicodedata

docs_folder = "docs"  # папка, где лежат документы
required_files = {
    "Porsche Инструкция по работе системой Автодилер администратор.docx",
    "Porsche Инструкция по работе системой Автодилер роп.docx",
    "Porsche Инструкция по работе системой Автодилер менеджер отдела продаж.docx"
}

# Приводим к нормализованной форме
normalized_required_files = {unicodedata.normalize('NFKD', f) for f in required_files}
existing_files = {unicodedata.normalize('NFKD', f) for f in os.listdir(docs_folder)}

# Приводим к нижнему регистру и обрезаем пробелы
normalized_required_files = {f.lower().strip() for f in normalized_required_files}
existing_files = {f.lower().strip() for f in existing_files}

# Проверяем
missing_files = normalized_required_files - existing_files

if missing_files:
    print(f"❌ Эти файлы не найдены в папке docs: {missing_files}")
else:
    print(f"✅ Все нужные файлы на месте.")
