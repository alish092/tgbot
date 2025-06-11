import os
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import sqlite3


DOCS_FOLDER = "docs"

FILTER_PHRASES = [
    "Визировать документы", "Лист ознакомления", "Ф.И.О.",
    "Согласовано", "Утверждено", "подпись", "ознакомлен", "ознакомлена"
]

def is_garbage(text):
    if len(text.strip()) < 30:
        return True
    if any(p.lower() in text.lower() for p in FILTER_PHRASES):
        return True
    if sum(c in ".,:-–_ \n" for c in text) / len(text) > 0.8:
        return True
    return False


def load_documents(folder):
    documents = []
    for filename in os.listdir(folder):
        filepath = os.path.join(folder, filename)
        try:
            if filename.endswith(".pdf"):
                loader = PyPDFLoader(filepath)
            elif filename.endswith(".docx"):
                # Проверка файла перед загрузкой
                import zipfile
                if not zipfile.is_zipfile(filepath):
                    print(f"❌ ОШИБКА: Файл {filename} поврежден или не является DOCX файлом!")
                    continue
                loader = Docx2txtLoader(filepath)
            else:
                continue

            #print(f"📄 Обработка файла: {filename}")
            loaded_docs = loader.load()

            for doc in loaded_docs:
                doc.metadata["source"] = filename
                documents.append(doc)

            #print(f"✅ Файл {filename} успешно загружен")

        except Exception as e:
            print(f"❌ ОШИБКА при загрузке файла {filename}: {str(e)}")
            # Продолжаем с другими файлами
            continue

    return documents

def split_and_filter_documents(documents):
    # Список приоритетных документов (в нижнем регистре)
    PRIORITY_FILES = {"rules.docx"}

    final_chunks = []
    for doc in documents:
        filename = doc.metadata.get("source", "").lower()
        is_priority = filename in PRIORITY_FILES

        if is_priority:
            # ДЛЯ ПРИОРИТЕТНЫХ ФАЙЛОВ - БОЛЕЕ КРУПНЫЕ ЧАНКИ
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=3000,  # Увеличили в 2 раза
                chunk_overlap=500,  # Больше перекрытие
                separators=["\n\n**", "\n\n", "\n", ".", " "]  # Разбиваем по заголовкам
            )
        else:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=300,
                chunk_overlap=100,
                separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
            )

        chunks = splitter.split_documents([doc])

        if is_priority:
            # НЕ ФИЛЬТРУЕМ приоритетные документы
            final_chunks.extend(chunks)
            print(f"🎯 ПРИОРИТЕТНЫЙ: {filename} разбит на {len(chunks)} чанков")
        else:
            filtered = [chunk for chunk in chunks if not is_garbage(chunk.page_content)]
            final_chunks.extend(filtered)

    return final_chunks



def main():
    documents = load_documents(DOCS_FOLDER)
    chunks = split_and_filter_documents(documents)
    print(f"✅ Загружено {len(documents)} документов.")
    print(f"✅ После фильтрации: {len(chunks)} чанков.")

    # Подготовим данные для записи в базу
    results = [(chunk.metadata.get("source", "неизвестно"), chunk.page_content.strip()) for chunk in chunks]

    # Запишем в базу
    save_chunks_to_db(results)

    return results


def parse_and_return_chunks():
    documents = load_documents(DOCS_FOLDER)
    chunks = split_and_filter_documents(documents)
    results = [(chunk.metadata.get("source", "неизвестно"), chunk.page_content.strip()) for chunk in chunks]
    return results

def save_chunks_to_db(chunks):
    conn = sqlite3.connect("bot_data.db")
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_name TEXT,
        chunk TEXT
    )
    """)
    cur.execute("DELETE FROM chunks")  # очищаем старое
    for docname, text in chunks:
        cur.execute("INSERT INTO chunks (document_name, chunk) VALUES (?, ?)", (docname, text))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
