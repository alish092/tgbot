import os
import logging
import docx2txt
import tiktoken
from langchain.chat_models import ChatOpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from tqdm import tqdm

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = "7634065162:AAFuAJnaRIX73PdMfjyDsYtYlpRcSNUf7a0"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DOCS_FOLDER = "docs"
MAX_TOKENS_PER_BLOCK = 2000

# === НАСТРОЙКА ЛОГГЕРА ===
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# === КОДОВАЯ БАЗА ===
encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
SYNONYMS = {
    "атз": ["атз", "администратор торгового зала", "ресепшн", "ресепшионист", "порше хост", "хост"],
    "отчет": ["отчет", "отчетность", "отчёт", "отчетный", "декларация", "сдача отчетов", "баланс"],
    "налог": ["налог", "налоговая", "налоговый", "налоговая отчетность", "декларация"],
    "главбух": ["главный бухгалтер", "гл. бухгалтер", "бухгалтер", "финансовый руководитель"],
    "заменять": ["замещает", "исполняет обязанности", "выполняет обязанности", "подменяет", "заменяет"],
}

def num_tokens(text): return len(encoding.encode(text))

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

def split_into_blocks(text):
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 0]
    blocks, current = [], ""
    for p in paragraphs:
        if num_tokens(current + "\n\n" + p) < MAX_TOKENS_PER_BLOCK:
            current += "\n\n" + p
        else:
            blocks.append(current.strip())
            current = p
    if current: blocks.append(current.strip())
    return blocks

def extract_keywords_from_question(question, synonyms):
    result = set()
    for word in question.lower().split():
        for key, values in synonyms.items():
            if word == key or word in values:
                result.update(values)
    return result

def is_relevant_block(block, question, synonyms):
    keywords = extract_keywords_from_question(question, synonyms)
    return any(k in block.lower() for k in keywords)

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

def gpt_choose_best(question, answers):
    formatted = "\n\n".join(f"- {a}" for a in answers)
    prompt = f"""
Вот список возможных ответов на вопрос: "{question}".

{formatted}

Выбери наиболее точный, полный и релевантный. Напиши только финальный ответ, без пояснений.
"""
    llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.2)
    return llm.invoke(prompt).content.strip()

# === ОБРАБОТЧИК ===
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args)
    if not question:
        await update.message.reply_text("❗ Используй: /ask [вопрос]")
        return

    await update.message.reply_text("⏳ Думаю...")

    docs = load_docs()
    answers = []

    for filename, text in tqdm(docs, desc="📄 Обработка"):
        blocks = split_into_blocks(text)
        for block in blocks:
            if not is_relevant_block(block, question, SYNONYMS):
                continue
            answer = ask_gpt(block, question)
            if "ответа нет" not in answer.lower():
                answers.append((answer, block))

    if not answers:
        for filename, text in docs:
            short_text = text[:12000]
            answer = ask_gpt(short_text, question)
            if "ответа нет" not in answer.lower():
                await update.message.reply_text(f"📂 {filename}\n\n✅ Ответ:\n{answer}")
                return
        await update.message.reply_text("❌ Ничего не найдено.")
        return

    raw_answers = [a for a, _ in answers]
    best = gpt_choose_best(question, raw_answers)

    for ans, block in answers:
        if best.strip() in ans:
            await update.message.reply_text(f"✅ Ответ:\n{best}\n\n📄 Источник:\n{block[:1000]}...")
            return

# === ЗАПУСК ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("ask", ask))
    print("🤖 Telegram-бот запущен. Жду вопросы по /ask")
    app.run_polling()
