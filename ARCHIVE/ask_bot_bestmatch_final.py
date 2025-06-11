import os
import docx2txt
import tiktoken
from langchain.chat_models import ChatOpenAI
from tqdm import tqdm
import httpx
import asyncio

DOCS_FOLDER = "docs"
MAX_TOKENS_PER_BLOCK = 2000
encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
docs = []

# Словарь синонимов и терминов
synonyms_from_db = {
    "атз": ["атз", "администратор торгового зала", "ресепшн", "ресепшионист", "порше хост", "хост"],
    "отчет": ["отчет", "отчетность", "отчёт", "отчетный", "декларация", "сдача отчетов", "баланс"],
    "налог": ["налог", "налоговая", "налоговый", "налоговая отчетность", "декларация"],
    "главбух": ["главный бухгалтер", "гл. бухгалтер", "бухгалтер", "финансовый руководитель"],
    "заменять": ["замещает", "исполняет обязанности", "выполняет обязанности", "подменяет", "заменяет"],
}
async def fetch_synonyms_from_backend():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("http://localhost:8000/synonyms_from_db")
            response.raise_for_status()
            data = response.json()
            synonyms_map = {}
            for item in data:
                keyword = item["keyword"].lower()
                syn = item["synonym"].lower()
                synonyms_map.setdefault(keyword, []).append(syn)
            return synonyms_map
    except Exception as e:
        print(f"⚠️ Не удалось загрузить синонимы: {e}")
        return {}
# Токенизация
def num_tokens(text):
    return len(encoding.encode(text))

# Загрузка документов
def load_docs():
    docs = []
    for filename in os.listdir(DOCS_FOLDER):
        if filename.endswith(".docx"):
            try:
                text = docx2txt.process(os.path.join(DOCS_FOLDER, filename))
                docs.append((filename, text))
            except Exception as e:
                print(f"⚠️ Ошибка в {filename}: {e}")
    return docs

# Разбиение по абзацам
def split_into_blocks(text):
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 0]
    blocks = []
    current = ""
    for p in paragraphs:
        if num_tokens(current + "\n\n" + p) < MAX_TOKENS_PER_BLOCK:
            current += "\n\n" + p
        else:
            blocks.append(current.strip())
            current = p
    if current:
        blocks.append(current.strip())
    return blocks

# Расширение запроса синонимами
def extract_keywords_from_question(question, synonyms_from_db):
    result = set()
    for word in question.lower().split():
        for key, values in synonyms.items():
            if word == key or word in values:
                result.update(values)
    return result

# Фильтрация блоков по ключевым словам
def is_relevant_block(block, question, synonyms_from_db):
    keywords = extract_keywords_from_question(question, synonyms_from_db)
    return any(k in block.lower() for k in keywords)

# Запрос к GPT по одному блоку
def ask_gpt(block, question):
    prompt = f"""
Ты помощник по регламентам. Ответь на вопрос, используя только этот текст.
Если нет ответа — напиши: "ответа нет".

Текст:
{block}

Вопрос: {question}
Ответ:
"""
    llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.2, max_tokens=1000)
    return llm.invoke(prompt).content.strip()

# Выбор лучшего ответа из списка
def gpt_choose_best(question, answers):
    formatted = "\n\n".join(f"- {a}" for a in answers)
    prompt = f"""
Вот список возможных ответов на вопрос: "{question}".

{formatted}

Выбери наиболее точный, полный и релевантный. Напиши только финальный ответ, без пояснений.
"""
    llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.2)
    return llm.invoke(prompt).content.strip()

# Запуск
def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ Установи переменную окружения OPENAI_API_KEY")
        return

    global docs
    docs = load_docs()
    global synonyms_from_db
    synonyms_from_db = asyncio.run(fetch_synonyms_from_backend())
    print(f"📥 Синонимы загружены: {len(synonyms_from_db)} групп")
    while True:
        question = input("\n❓ Введите вопрос (или 'exit'): ")
        if question.strip().lower() == "exit":
            print("👋 До встречи!")
            break

        answers = []
        relevant_blocks = []

        for filename, text in tqdm(docs, desc="📄 Обработка документов"):
            blocks = split_into_blocks(text)
            for block in blocks:
                if not is_relevant_block(block, question, synonyms_from_db):
                    continue
                    print(f"🧩 Чанк:\n{block[:200]}...\n")

                answer = ask_gpt(block, question)
                if "ответа нет" not in answer.lower():
                    answers.append((answer, block))

        if not answers:
            print("⚠️ Ничего не найдено по фильтрации — пробуем весь документ...")
            for filename, text in docs:
                short_text = text[:12000]
                answer = ask_gpt(short_text, question)
                if "ответа нет" not in answer.lower():
                    print(f"\n✅ Ответ из всего текста ({filename}):\n{answer}")
                    break
            else:
                print("❌ Ничего не найдено даже при полном просмотре.")
            continue

        # Выбор лучшего ответа
        raw_answers = [a for a, _ in answers]
        best = gpt_choose_best(question, raw_answers)
        print("\n✅ Лучший ответ:\n", best)

        # Найдём использованный блок
        for ans, block in answers:
            if best.strip() in ans:
                print("\n📄 Фрагмент, использованный GPT:\n")
                print(block[:1000], "...\n")
                break

if __name__ == "__main__":
    main()
