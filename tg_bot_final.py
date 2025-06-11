import os
import json
import subprocess
import re
import logging
import docx2txt
import tiktoken
import httpx
import unicodedata
import threading
import asyncio
import time
import functools
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional, Set
import pickle
import hashlib
from pymorphy2 import MorphAnalyzer

global synonyms_from_db

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
from langchain_community.chat_models import ChatOpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from tqdm import tqdm
from telegram.ext import CommandHandler
from telegram.ext import CallbackQueryHandler
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
morph = MorphAnalyzer()

def normalize(text: str) -> List[str]:
    """Нормализует слова до начальной формы"""
    return [morph.parse(word)[0].normal_form for word in re.findall(r'\b\w+\b', text.lower())]
# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("❌ ОШИБКА: Переменная TELEGRAM_TOKEN не установлена.")
    exit(1)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("❌ ОШИБКА: Переменная окружения OPENAI_API_KEY не установлена.")
    print("Установите её командой: set OPENAI_API_KEY=ваш_ключ (Windows) или")
    print("export OPENAI_API_KEY=ваш_ключ (Linux/Mac)")
    exit(1)  # Выходим с ошибкой, если ключ не найден
with open("law_keywords.json", "r", encoding="utf-8") as f:
    LAW_KEYWORDS = json.load(f)
# Установка ключа для langchain
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

ADMIN_IDS = [339948299]
allowed_users = {}  # user_id -> role
DOCS_FOLDER = "docs"
MAX_TOKENS_PER_BLOCK = 2000
docs = []
CP_FOLDER = r"\\srv-2\обмен\Отдел продаж\Наличие 2023_производство 2024"
CRM_KEYWORDS = {"срм", "crm", "автодилер", "срмка"}
CRM_DOCUMENTS = {
    unicodedata.normalize('NFKD', "Porsche Инструкция по работе системой Автодилер администратор.docx").lower().strip(),
    unicodedata.normalize('NFKD', "Porsche Инструкция по работе системой Автодилер роп.docx").lower().strip(),
    unicodedata.normalize('NFKD', "Porsche Инструкция по работе системой Автодилер менеджер отдела продаж.docx").lower().strip()
}

with open('law_keywords.json', 'r', encoding='utf-8') as f:
    LAW_KEYWORDS = json.load(f)
# === КЭШИРОВАНИЕ И КАТАЛОГИ ===
CACHE_DIR = "cache"
CACHE_LIFETIME = 3600  # время жизни кэша в секундах (1 час)

# Проверка и создание необходимых каталогов
for directory in [CACHE_DIR, DOCS_FOLDER]:
    os.makedirs(directory, exist_ok=True)
    print(f"✅ Каталог {directory} готов")

# === ОГРАНИЧЕНИЕ ЗАПРОСОВ ===
# Максимальное число запросов в минуту для каждого пользователя
MAX_REQUESTS_PER_MINUTE = 5
user_request_counts = defaultdict(list)  # user_id -> [timestamp1, timestamp2, ...]

# === СИСТЕМА ОЧЕРЕДЕЙ ===
MAX_CONCURRENT_REQUESTS = 3  # максимальное количество одновременных запросов к API
api_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
# Очередь задач на обработку
processing_queue = asyncio.Queue()
# Флаг для управления работой воркеров
worker_running = True

# === НАСТРОЙКА ЛОГГЕРА ===
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("tg_bot")
logger.setLevel(logging.INFO)

# === КОДОВАЯ БАЗА ===
encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
synonyms_from_db = {}
priorities_from_db = {}


# === ФУНКЦИЯ ПОВТОРНЫХ ПОПЫТОК ===
async def retry_async(func, max_retries=3, base_delay=1, max_delay=10):
    """Декоратор для повторных попыток асинхронных функций с экспоненциальной задержкой"""
    retries = 0
    while True:
        try:
            return await func()
        except Exception as e:
            retries += 1
            if retries > max_retries:
                logger.error(f"Превышено максимальное количество попыток: {e}")
                raise

            delay = min(base_delay * (2 ** (retries - 1)), max_delay)
            logger.warning(f"Попытка {retries} не удалась: {e}. Повторная попытка через {delay} сек.")
            await asyncio.sleep(0.1)


# === КЭШИРОВАНИЕ ===
def get_cache_key(func_name: str, *args, **kwargs) -> str:
    """Генерирует уникальный ключ кэша на основе имени функции и её аргументов"""
    key_parts = [func_name]
    for arg in args:
        key_parts.append(str(arg))
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")

    key_string = "_".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def save_cache(key: str, data: Any) -> None:
    """Сохраняет данные в кэш"""
    cache_path = os.path.join(CACHE_DIR, f"{key}.pkl")
    with open(cache_path, 'wb') as f:
        pickle.dump((datetime.now(), data), f)


def load_cache(key: str) -> Optional[Any]:
    """Загружает данные из кэша если они ещё валидны"""
    cache_path = os.path.join(CACHE_DIR, f"{key}.pkl")
    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, 'rb') as f:
            timestamp, data = pickle.load(f)
            if datetime.now() - timestamp < timedelta(seconds=CACHE_LIFETIME):
                return data
    except Exception as e:
        logger.warning(f"Ошибка чтения кэша: {e}")
    return None


async def cached(func, *args, **kwargs):
    """Обертка для кэширования результатов функции"""
    func_name = func.__name__
    cache_key = get_cache_key(func_name, *args, **kwargs)

    # Проверяем кэш
    cached_result = load_cache(cache_key)
    if cached_result is not None:
        logger.info(f"Данные получены из кэша: {func_name}")
        return cached_result

    # Выполняем функцию
    result = await func(*args, **kwargs)

    # Сохраняем результат в кэш
    save_cache(cache_key, result)
    return result


# === ЗАГРУЗКА ДИНАМИЧЕСКИХ ДАННЫХ ===
async def load_dynamic_data():
    global synonyms_from_db, priorities_from_db
    logger.info("🔄 Начата загрузка динамических данных")
    #logger.info(f"🧪 Получены приоритеты из API: {prio.text}") #временно

    async def _load_data():
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info("📥 Запрос синонимов из API")
            syns = await client.get(f"{BACKEND_URL}/synonyms_from_db")
            syns.raise_for_status()
            logger.info(f"✅ Получен ответ о синонимах, статус: {syns.status_code}")

            synonyms = {}
            for item in syns.json():
                key = item["keyword"]
                val = item["synonym"]
                logger.info(f"🔄 Синоним добавлен: {key} → {val}")

                synonyms.setdefault(key, []).append(val)
            logger.info(f"📊 Загружено синонимов: {len(synonyms)} ключевых слов")

            logger.info("📥 Запрос приоритетов из API")
            prio = await client.get(f"{BACKEND_URL}/priorities")
            prio.raise_for_status()
            logger.info(f"✅ Получен ответ о приоритетах, статус: {prio.status_code}")

            # Загружаем приоритеты из базы данных
            priorities = {p["keyword"]: p["document_name"] for p in prio.json()}
            logger.info(f"📊 Загружено приоритетов: {len(priorities)} ключевых слов")

            # 🚀 ДОБАВЛЯЕМ ЖЁСТКИЕ ПРИОРИТЕТЫ для CRM
            for word in CRM_KEYWORDS:
                priorities[word] = CRM_DOCUMENTS

            logger.info(f"📌 Обновлённые приоритеты для CRM: {CRM_DOCUMENTS}")
            logger.info(f"📊 Загружено приоритетов: {len(priorities)} ключевых слов")
            return synonyms, priorities

    try:
        synonyms, priorities = await cached(_load_data)
        synonyms_from_db = synonyms
        priorities_from_db = priorities

        logger.info(f"📊 Загружено приоритетов: {len(priorities_from_db)}") #временное логирование
        for keyword, doc_name in priorities_from_db.items(): #временное логирование
            logger.info(f"🔑 Приоритет: '{keyword}' → '{doc_name}'") #временное логирование
    except Exception as e:
        import traceback
        logger.error(f"⚠️ Ошибка загрузки синонимов и приоритетов: {e}")
        traceback.print_exc()

        # Используем резервные данные если API недоступен
        priorities_from_db = {
            "одежда": "Кодекс Деловой Этики Orbis Auto.docx",
            "дресс-код": "Кодекс Деловой Этики Orbis Auto.docx",
            "отпуск": "Трудовой договор.docx",
            "отпускной": "Трудовой договор.docx",
            "налог": "ДИ-01-07 Гл. бухгалтер новый.docx"
        }

        synonyms_from_db = {
            "атз": ["атз", "администратор торгового зала", "ресепшн", "ресепшионист", "порше хост", "хост"],
            "отчет": ["отчет", "отчетность", "отчёт", "отчетный", "декларация", "сдача отчетов", "баланс"],
            "налог": ["налог", "налоговая", "налоговый", "налоговая отчетность", "декларация"],
            "главбух": ["главный бухгалтер", "гл. бухгалтер", "бухгалтер", "финансовый руководитель"],
            "заменять": ["замещает", "исполняет обязанности", "выполняет обязанности", "подменяет", "заменяет"],
            "одежда": ["одежда", "дресс-код", "внешний вид", "джинсы", "шорты", "майка", "футболка", "форма"],
        }


async def load_allowed_users():
    global allowed_users

    async def _load_users():
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{BACKEND_URL}/roles")
            response.raise_for_status()
            users = response.json()
            if isinstance(users, list):
                return {int(u["user_id"]): u["role"] for u in users}
            else:
                logger.warning(f"⚠️ Неверный формат ответа: {users}")
                return {}

    try:
        users = await retry_async(lambda: _load_users())
        allowed_users = users
        logger.info(f"✅ Загружены пользователи: {list(allowed_users.keys())}")
    except Exception as e:
        logger.error(f"⚠️ Ошибка при загрузке пользователей: {e}")
        # Оставляем предыдущие значения

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_role(user_id, "директор"):
        await update.message.reply_text("🚫 У вас нет доступа к этой команде.")
        return

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BACKEND_URL}/roles")
        data = r.json()

    if not data:
        await update.message.reply_text("Пользователей пока нет.")
        return

    msg = "👥 Список пользователей:\n" + "\n".join([f"{r['user_id']} — {r['role']}" for r in data])
    await update.message.reply_text(msg)

import time

last_update_time = 0  # глобальная переменная для анти-флуда

class DocsChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        global last_update_time
        if event.src_path.endswith(".docx"):
            now = time.time()
            if now - last_update_time > 10:  # Прошло больше 10 секунд с последнего обновления
                logger.info(f"📄 Обнаружено изменение: {event.src_path}, обновляем...")
                cache_key = get_cache_key("load_docs")
                cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                threading.Thread(target=lambda: asyncio.run(update_docs()), daemon=True).start()
                last_update_time = now
            else:
                pass


async def update_docs():
    """Обновление документов с использованием кеширования"""
    global docs
    # Используем синхронную версию загрузки документов
    docs = await cached(lambda: asyncio.to_thread(load_docs))


def start_watchdog():
    """Запуск наблюдателя за документами"""
    print("📄 Начало инициализации наблюдателя...")
    try:
        # Сначала загружаем документы без watchdog
        print("   Загрузка документов...")
        global docs
        docs = load_docs()  # Сканируем один раз
        print(f"   ✅ Загружено {len(docs)} документов")

        # Затем настраиваем наблюдателя
        print("   Настройка наблюдателя...")
        handler = DocsChangeHandler()
        observer = Observer()
        observer.schedule(handler, DOCS_FOLDER, recursive=False)

        # Запускаем в отдельном потоке
        print("   Запуск наблюдателя в отдельном потоке...")
        observer_thread = threading.Thread(target=observer.start, daemon=True)
        observer_thread.start()
        print("   ✅ Поток наблюдателя запущен")

        return True
    except Exception as e:
        print(f"   ❌ Ошибка в start_watchdog: {e}")
        # Выводим подробный стек-трейс для отладки
        import traceback
        traceback.print_exc()
        return False


def load_docs():
    """Загружает и разбивает документы на чанки через parse_documents.py"""
    print("📄 Загрузка и разбиение документов...")
    try:
        from parse_documents import parse_and_return_chunks
        chunks = parse_and_return_chunks()
        print(f"✅ Загружено {len(chunks)} чанков")
        return chunks
    except Exception as e:
        print(f"❌ Ошибка при загрузке документов: {e}")
        return []



# === ОГРАНИЧЕНИЕ ЧАСТОТЫ ЗАПРОСОВ ===
async def check_rate_limit(user_id: int) -> bool:
    """Проверяет, не превышен ли лимит запросов для пользователя"""
    now = time.time()
    # Удаляем устаревшие записи (старше 1 минуты)
    user_request_counts[user_id] = [t for t in user_request_counts[user_id] if now - t < 60]

    # Проверяем количество запросов за последнюю минуту
    if len(user_request_counts[user_id]) >= MAX_REQUESTS_PER_MINUTE:
        return False

    # Добавляем текущий запрос
    user_request_counts[user_id].append(now)
    return True


# === СИСТЕМА ОЧЕРЕДЕЙ ===
async def worker():
    """Обработчик очереди задач"""
    global worker_running
    while worker_running:
        try:
            # Получаем задачу из очереди
            task_data = await asyncio.wait_for(processing_queue.get(), timeout=1.0)
            if task_data is None:
                continue

            update, context, question, user_id, username = task_data

            # Выполняем задачу в ограниченном количестве
            async with api_semaphore:
                await process_question(update, context, question, user_id, username)

            # Отмечаем задачу как выполненную
            processing_queue.task_done()
        except asyncio.TimeoutError:
            # Таймаут ожидания - нормальная ситуация, продолжаем
            pass
        except Exception as e:
            logger.error(f"Ошибка в воркере: {e}")
            # Даже при ошибке, пытаемся пометить задачу как выполненную
            try:
                processing_queue.task_done()
            except:
                pass


async def start_workers():
    """Запускает воркеры обработки очереди"""
    workers = []
    for _ in range(3):  # 3 воркера
        workers.append(asyncio.create_task(worker()))
    return workers


import requests

import requests
import io

async def handle_cp_request(update: Update, context: ContextTypes.DEFAULT_TYPE, cp_code: str):
    user_id = update.message.from_user.id
    role = allowed_users.get(user_id)
    logger.info("🧪 ВЕРСИЯ 2: Вызов handle_cp_request через HTTP")

    if role not in ("продавец", "роп", "директор"):
        await update.message.reply_text("🚫 У вас нет доступа к коммерческим предложениям.")
        return

    url = f"http://10.102.71.75:8090/get_cp?code={cp_code}"
    logger.info(f"🔍 Запрос КП по адресу: {url}")

    try:
        response = requests.get(url)
        response.raise_for_status()

        # Имя файла из заголовка или по умолчанию
        filename = cp_code + ".pdf"
        content = io.BytesIO(response.content)

        await update.message.reply_document(
            document=content,
            filename=filename
        )
        logger.info(f"✅ КП {cp_code} успешно отправлен")

    except requests.exceptions.HTTPError as e:
        if response.status_code == 404:
            await update.message.reply_text(f"❌ КП {cp_code} не найден.")
        else:
            await update.message.reply_text("⚠️ Ошибка при получении файла.")
        logger.error(f"⚠️ HTTP ошибка: {e}")

    except Exception as e:
        await update.message.reply_text("⚠️ Общая ошибка при получении файла.")
        logger.error(f"❌ Ошибка: {e}")






async def check_override(question: str):
    async def _get_overrides():
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{BACKEND_URL}/overrides")
            response.raise_for_status()
            return response.json()

    try:
        # Загружаем синонимы, если они еще не загружены
        if not synonyms_from_db:
            await load_dynamic_data()

        logger.info(f"🔄 Загруженные синонимы: {synonyms_from_db}")

        # Приводим к нижнему регистру и убираем лишние знаки
        question_lower = question.lower().replace('-', ' ').replace('?', '').replace('!', '').strip()
        question_words = question_lower.split()

        # Создаем обратную карту синонимов для более быстрого поиска
        reverse_synonyms = {}
        for key, values in synonyms_from_db.items():
            for value in values:
                if value not in reverse_synonyms:
                    reverse_synonyms[value] = []
                reverse_synonyms[value].append(key)

        # Логируем для отладки
        logger.info(f"🔄 Обратная карта синонимов: {reverse_synonyms}")

        # Получаем ручные ответы
        overrides = await retry_async(lambda: _get_overrides())

        for item in overrides:
            # Подготовка эталонного вопроса
            item_question = item["question"].lower().replace('-', ' ').replace('?', '').replace('!', '').strip()
            item_words = item_question.split()

            # 1. Проверка на точное совпадение
            if question_lower == item_question:
                logger.info(f"✅ Найдено точное совпадение вопроса: {question}")
                return item["answer"]

            # 2. Проверка с учетом синонимов
            # Расширенный список стоп-слов
            stop_words = {"если", "что", "как", "ли", "можно", "нужно", "и", "а", "но", "то", "по", "на", "в", "из",
                          "при", "за", "кто", "где", "когда", "почему", "зачем", "должен", "должны", "должна", "мне",
                          "вам"}

            # Строим семантические множества для обоих вопросов
            semantic_set_question = set()
            semantic_set_item = set()

            # Обрабатываем слова из вопроса пользователя
            for word in question_words:
                if word in stop_words:
                    continue

                # Добавляем само слово
                semantic_set_question.add(word)

                # Добавляем ключевые слова, если это синоним
                if word in reverse_synonyms:
                    for key in reverse_synonyms[word]:
                        semantic_set_question.add(key)

                # Добавляем синонимы, если это ключевое слово
                if word in synonyms_from_db:
                    for synonym in synonyms_from_db[word]:
                        semantic_set_question.add(synonym)

            # Обрабатываем слова из эталонного вопроса
            for word in item_words:
                if word in stop_words:
                    continue

                # Добавляем само слово
                semantic_set_item.add(word)

                # Добавляем ключевые слова, если это синоним
                if word in reverse_synonyms:
                    for key in reverse_synonyms[word]:
                        semantic_set_item.add(key)

                # Добавляем синонимы, если это ключевое слово
                if word in synonyms_from_db:
                    for synonym in synonyms_from_db[word]:
                        semantic_set_item.add(synonym)

            # Находим общие семантические элементы
            common_semantic = semantic_set_question.intersection(semantic_set_item)

            # Считаем процент совпадения
            all_semantic = semantic_set_question.union(semantic_set_item)
            if all_semantic:
                match_percent = len(common_semantic) / len(all_semantic)
            else:
                match_percent = 0

            # Логируем для отладки
            #logger.info(f"Вопрос пользователя: {question_lower}")
            #logger.info(f"Семантический набор пользователя: {semantic_set_question}")
            #logger.info(f"Вопрос в базе: {item_question}")
            #logger.info(f"Семантический набор базы: {semantic_set_item}")
            #logger.info(f"Общие семантические элементы: {common_semantic}")
            #logger.info(f"Процент совпадения: {match_percent:.2f}")

            # Требуем минимум 2 общих элемента и 50% совпадение
            if len(common_semantic) >= 2 and match_percent >= 0.5:
                logger.info(f"✅ Найдено хорошее семантическое совпадение: {common_semantic}")
                return item["answer"]

            # Особый случай для очень коротких вопросов (2-3 слова)
            # Если большинство слов из вопроса пользователя содержатся в эталонном вопросе
            significant_question_words = [w for w in question_words if w not in stop_words]
            if len(significant_question_words) <= 3 and len(common_semantic) >= len(significant_question_words) * 0.67:
                logger.info(f"✅ Найдено совпадение для короткого вопроса: {common_semantic}")
                return item["answer"]

    except Exception as e:
        logger.error(f"⚠️ Ошибка при запросе overrides: {e}")
        import traceback
        traceback.print_exc()

    return None


async def handle_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    callback_data = update.callback_query.data
    logger.info(f"Получены callback данные: {callback_data}")

    _, log_id = callback_data.split(":")
    logger.info(f"Извлеченный log_id: {log_id}")

    await update.callback_query.answer("Жалоба принята ✅")
    await update.callback_query.edit_message_reply_markup(reply_markup=None)

    # Добавляем проверку на валидность log_id
    if log_id is None or log_id == "error" or not log_id.isdigit():
        logger.error(f"⚠️ Некорректный log_id: {log_id}")
        await update.effective_chat.send_message("К сожалению, не удалось обработать жалобу. Попробуйте позже.")
        return
    await update.effective_chat.send_message("Ваша жалоба принята и будет рассмотрена администратором.")
    logger.info(f"🚨 Жалоба на лог #{log_id} - пользователю сообщено")


    async def _send_complaint():
        logger.info(f"Отправка жалобы для log_id: {log_id}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "log_id": int(log_id),
                "complaint": "Жалоба из Telegram"
            }
            logger.info(f"Отправляемые данные: {params}")

            response = await client.post(
                f"{BACKEND_URL}/complaints",
                params=params,
            )

            status_code = response.status_code
            logger.info(f"Статус ответа: {status_code}")

            response.raise_for_status()

            # Получаем текст ответа для отладки
            response_text = response.text
            logger.info(f"Текст ответа: {response_text}")

            try:
                data = response.json()
                logger.info(f"JSON ответа: {data}")
                return data
            except Exception as json_error:
                logger.error(f"Ошибка при парсинге JSON: {str(json_error)}")
                return {}

    try:
        result = await retry_async(lambda: _send_complaint())
        logger.info(f"🚨 Жалоба на лог #{log_id} отправлена успешно. Результат: {result}")
    except Exception as e:
        logger.error(f"⚠️ Ошибка при отправке жалобы: {e}")
        await update.effective_chat.send_message("К сожалению, не удалось обработать жалобу. Попробуйте позже.")


async def log_interaction(user_id: int, username: str, question: str, answer: str):
    try:
        logger.info(f"Отправка лога: user_id={user_id}, username={username}")
        logger.info(f"Вопрос: {question[:50]}...")  # Выводим только начало для краткости

        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "user_id": user_id,
                "username": username,
                "question": question,
                "answer": answer
            }
            logger.info(f"Отправляемые данные: {payload}")

            response = await client.post(
                f"{BACKEND_URL}/logs",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            status_code = response.status_code
            logger.info(f"Статус ответа: {status_code}")

            response.raise_for_status()

            # Получаем текст ответа для отладки
            response_text = response.text
            logger.info(f"Текст ответа: {response_text}")

            try:
                data = response.json()
                logger.info(f"JSON ответа: {data}")

                if "error" in data:
                    logger.error(f"Ошибка при логировании: {data['error']}")
                    return "error"
                if "id" not in data:
                    logger.error(f"ID не найден в ответе: {data}")
                    return "error"

                log_id = data.get("id")
                logger.info(f"Получен log_id: {log_id}")
                return log_id
            except Exception as json_error:
                logger.error(f"Ошибка при парсинге JSON: {str(json_error)}")
                return "error"

    except Exception as e:
        logger.error(f"Ошибка при логировании: {str(e)}")
        return "error"


async def send_answer(update, context, answer, block, log_id, filename=None):
    kb = [[InlineKeyboardButton("🚫 Пожаловаться", callback_data=f"complain:{log_id}")]]
    user_id = update.message.from_user.id

    # ДОБАВЛЕНО: Определение максимальной длины сообщения
    MAX_MESSAGE_LENGTH = 1000

    # ДОБАВЛЕНО: Подготовка информации об источнике
    if user_id in ADMIN_IDS:
        source_info = f"📂 {filename}\n\n"
    else:
        source_info = ""

    # ДОБАВЛЕНО: Проверка длины ответа и разбиение на части
    if len(answer) > MAX_MESSAGE_LENGTH:
        # ДОБАВЛЕНО: Разбиение на абзацы для лучшей читабельности
        paragraphs = answer.split('\n')
        current_message = ""
        messages = []

        for p in paragraphs:
            # Если добавление абзаца не превысит лимит
            if len(current_message + p + "\n") <= MAX_MESSAGE_LENGTH:
                current_message += p + "\n"
            else:
                # Если текущее сообщение не пустое, добавляем его в список
                if current_message.strip():
                    messages.append(current_message.strip())
                # Начинаем новое сообщение с текущего абзаца
                current_message = p + "\n"

        # Добавляем последнее сообщение, если оно не пустое
        if current_message.strip():
            messages.append(current_message.strip())

        # ДОБАВЛЕНО: Если нет абзацев или получилось одно сообщение, разбиваем по символам
        if not messages or len(messages) == 1:
            messages = [answer[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(answer), MAX_MESSAGE_LENGTH)]

        total_parts = len(messages)
        logger.info(f"Ответ разбит на {total_parts} частей")

        # ДОБАВЛЕНО: Отправляем первую часть
        first_message = f"{source_info}✅ Ответ (1/{total_parts}):\n{messages[0]}"
        await update.message.reply_text(first_message)

        # ДОБАВЛЕНО: Отправляем промежуточные части
        for i in range(1, total_parts - 1):
            # Небольшая задержка для избежания ограничений API
            await asyncio.sleep(0.3)
            middle_message = f"✅ Продолжение ({i + 1}/{total_parts}):\n{messages[i]}"
            await update.message.reply_text(middle_message)

        # ДОБАВЛЕНО: Отправляем последнюю часть с кнопкой жалобы
        if total_parts > 1:
            await asyncio.sleep(0.3)
            last_message = f"✅ Завершение ({total_parts}/{total_parts}):\n{messages[total_parts - 1]}"

            # Информацию о блоке добавляем только для админов и только к последнему сообщению
            if user_id in ADMIN_IDS:
                last_message += f"\n\n📄 Источник:\n{block[:300]}..."

            await update.message.reply_text(last_message, reply_markup=InlineKeyboardMarkup(kb))
        else:
            # Если отправлена только одна часть, добавляем источник и кнопку к ней
            if user_id in ADMIN_IDS:
                admin_addition = f"\n\n📄 Источник:\n{block[:300]}..."
                await update.message.edit_text(first_message + admin_addition, reply_markup=InlineKeyboardMarkup(kb))
            else:
                # Добавляем только кнопку к первому сообщению
                await update.message.edit_text(first_message, reply_markup=InlineKeyboardMarkup(kb))
    else:
        # ИЗМЕНЕНО: Для коротких ответов оставляем как есть, но с обновленным форматированием
        if user_id in ADMIN_IDS:
            msg = f"{source_info}✅ Ответ:\n{answer}\n\n📄 Источник:\n{block[:300]}..."
        else:
            msg = f"{source_info}✅ Ответ:\n{answer}"

        # НЕИЗМЕНЕНО: Отправка сообщения с кнопкой жалобы
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

    # ДОБАВЛЕНО: Логирование успешной отправки
    logger.info(f"✅ Ответ успешно отправлен пользователю {user_id}")


async def check_role(user_id: int, role: str) -> bool:
    async def _check_role_api():
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{BACKEND_URL}/roles")
            r.raise_for_status()
            return r.json()

    try:
        roles = await retry_async(lambda: _check_role_api())
        for r in roles:
            if r["user_id"] == user_id and r["role"] == role:
                return True
    except Exception as e:
        logger.error(f"⚠️ Ошибка при проверке роли: {e}")
    return False


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_role(user_id, "директор"):
        await update.message.reply_text("🚫 У вас нет доступа к этой команде.")
        return

    async def _get_stats():
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{BACKEND_URL}/stats")
            r.raise_for_status()
            return r.json()

    try:
        data = await retry_async(lambda: _get_stats())
        msg = (
            f"📊 Статистика:\n"
            f"— Вопросов: {data['total_logs']}\n"
            f"— Жалоб: {data['total_complaints']}\n"
            f"— Ручных ответов: {data['total_overrides']}\n"
        )
        if data['top_user']:
            msg += f"— Активный: @{data['top_user']} ({data['top_count']} вопросов)"
        await update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"⚠️ Ошибка при получении статистики: {e}")
        await update.message.reply_text("⚠️ Не удалось получить статистику. Попробуйте позже.")


def num_tokens(text):
    return len(encoding.encode(text))


def split_into_blocks(text):
    # print("🚀 Начинаем разбиение текста на блоки...")

    # Ищем заголовки и разделы
    section_patterns = [
        r'\*\*([^*]+)\*\*',  # **Заголовок**
        r'\n\d+\.\s',  # 1. Нумерованный список
        r'\n•\s',  # • Маркированный список
    ]

    # Сначала попробуем разбить по заголовкам, сохраняя заголовки в блоках
    sections = []
    current_section = ""
    lines = text.split('\n')

    for line in lines:
        if any(re.search(pattern, line) for pattern in section_patterns[:1]):  # Только заголовки
            if current_section:
                sections.append(current_section.strip())
            current_section = line
        else:
            current_section += "\n" + line

    if current_section:
        sections.append(current_section.strip())

    # Если получилось мало секций, используем более мелкое разбиение
    if len(sections) < 3:
        paragraphs = [p.strip() for p in re.split(r'\n\n|\n\d+\.\s|\n•\s', text) if len(p.strip()) > 0]

        # Объединяем пронумерованные списки для сохранения контекста
        blocks = []
        current_block = ""
        for p in paragraphs:
            if re.match(r'\d+\.\s', p) or len(current_block) == 0:
                if current_block:
                    blocks.append(current_block.strip())
                current_block = p
            elif num_tokens(current_block + "\n\n" + p) < MAX_TOKENS_PER_BLOCK:
                current_block += "\n\n" + p
            else:
                blocks.append(current_block.strip())
                current_block = p

        if current_block:
            blocks.append(current_block.strip())

        return blocks
    else:
        # Проверка размера блоков и разбиение слишком больших
        blocks = []
        for section in sections:
            if num_tokens(section) > MAX_TOKENS_PER_BLOCK:
                # Разбиваем большую секцию
                sub_parts = [p.strip() for p in re.split(r'\n\n|\n\d+\.\s', section) if len(p.strip()) > 0]
                current_sub = ""
                for part in sub_parts:
                    if num_tokens(current_sub + "\n\n" + part) < MAX_TOKENS_PER_BLOCK:
                        current_sub += "\n\n" + part
                    else:
                        blocks.append(current_sub.strip())
                        current_sub = part
                if current_sub:
                    blocks.append(current_sub.strip())
            else:
                blocks.append(section)

        return blocks


def extract_keywords_from_question(question, synonyms_from_db):
    result = set()
    for word in question.lower().split():
        for key, values in synonyms_from_db.items():
            if word == key or word in values:
                result.update(values)
    return result


def is_relevant_block(block, question, synonyms_from_db):
    keywords = extract_keywords_from_question(question, synonyms_from_db)
    return any(k in block.lower() for k in keywords)


async def ask_gpt(block, question, username):
    """Асинхронная версия запроса к GPT с повторными попытками"""
    tone = get_tone_by_username(username)

    # Определяем, связан ли вопрос с инструкцией
    instruction_keywords = ["как", "инструкция", "шаги", "порядок действий", "процедура", "механизм", "алгоритм"]
    is_instruction_question = any(keyword in question.lower() for keyword in instruction_keywords)

    if is_instruction_question:
        prompt = f"""
            {tone}

            Ты эксперт по CRM системе Автодилер и внутренним инструкциям. 

            При ответе на вопрос СТРОГО соблюдай следующие правила:
            1. Используй ТОЛЬКО факты из предоставленного текста.
            2. Если в тексте есть пронумерованный список или шаги инструкции - ОБЯЗАТЕЛЬНО сохрани все пункты с их оригинальной нумерацией.
            3. Перечисли ВСЕ шаги процесса полностью, не пропуская ни одного пункта.
            4. Не добавляй информацию, которой нет в тексте.
            5. Не обобщай и не сокращай шаги - приведи полное описание каждого шага.
            6. Если в вопросе упоминается конкретная роль (менеджер, администратор), найди соответствующий раздел в тексте.

            Текст:
            {block}

            Вопрос: {question}
            Подробный ответ (сохраняя ВСЕ шаги):
            """
    else:
        prompt = f"""
            {tone}

            Ответь на вопрос, используя ТОЛЬКО информацию из этого текста.
            Если в тексте есть списки или шаги - приведи их полностью.
            Если нет ответа — напиши: "ответа нет".

            Текст:
            {block}

            Вопрос: {question}
            Ответ:
            """

    try:
        # Используем семафор для ограничения параллельных запросов к API
        async with api_semaphore:
            async def _call_gpt():
                llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.2, max_tokens=1000, max_retries=3)
                #logger.info("📡 Отправка запроса к GPT...")
                response = await llm.ainvoke(prompt)
                #logger.info("📥 Получен ответ от GPT")
                return response.content.strip()

            # Запускаем с повторными попытками
            return await retry_async(_call_gpt)
    except Exception as e:
        logger.error(f"⚠️ Ошибка при запросе к GPT: {e}")
        return "ответа нет"

def get_tone_by_username(username: str) -> str:
    if username in {"msattarov", "Madi Sattarov	"}:  # можно любые username
        return "Отвечай грубо, дерзко, с переходами на личности. Можешь использовать сарказм, пренебрежение, высокомерие и унижение."
    return "Ты помощник по регламентам. Говори вежливо, по делу, остроумно и добавь комплимент."


def is_relevant_for_role(block, question):
    """Определяет, соответствует ли блок роли, упомянутой в вопросе"""
    role_keywords = {
        "администратор": ["администратор", "атз", "ресепшионист", "ресепшн"],
        "менеджер": ["менеджер", "продавец", "менеджер отдела продаж", "мене", "мсп"],
        "руководитель": ["руководитель", "роп", "руководитель отдела", "директор"]
    }

    question_lower = question.lower()

    # Проверяем, упоминается ли роль в вопросе
    for role, keywords in role_keywords.items():
        if any(keyword in question_lower for keyword in keywords):
            # Проверяем наличие заголовка с ролью в блоке
            role_pattern = fr'\*\*\s*{role}.*?\*\*|\*\*.*?{role}.*?\*\*'
            return bool(re.search(role_pattern, block, re.IGNORECASE))

    return False

async def gpt_choose_best(question, answers):
    """Асинхронная версия выбора лучшего ответа"""
    formatted = "\n\n".join(f"- {a}" for a in answers)
    prompt = f"""
Вот список возможных ответов на вопрос: "{question}".

{formatted}

Выбери наиболее точный, полный и релевантный. Напиши только финальный ответ, без пояснений.
"""
    try:
        async def _call_gpt():
            llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.2, max_tokens=1000, max_retries=3)
            response = await llm.ainvoke(prompt)
            return response.content.strip()

        return await retry_async(_call_gpt)
    except Exception as e:
        logger.error(f"⚠️ Ошибка при выборе лучшего ответа: {e}")
        # В случае ошибки возвращаем первый ответ
        return answers[0] if answers else "Ответ не найден"

def contains_instructions(block):
    """Проверяет, содержит ли блок инструкции или пронумерованные шаги"""
    # Ищем нумерованные списки или пункты
    pattern = r'\d+\.\s|\d+\)\s|•\s'
    return bool(re.search(pattern, block))


async def process_question(update: Update, context, question, user_id, username):
    """Основная логика обработки вопроса"""
    logger.info(f"🔍 Обрабатываем вопрос: '{question}'")

    # 🔄 1) Загрузка документов и данных
    global docs
    await load_dynamic_data()
    docs = await cached(lambda: asyncio.to_thread(load_docs))
    logger.info(f"📂 Загружено документов: {len(docs)}")

    # 🔄 Приводим все загруженные файлы к нормализованной форме
    docs = [(unicodedata.normalize('NFKD', name).lower().strip(), content) for name, content in docs]

    # 🔍 3) Ручной override
    override = await check_override(question)
    if override:
        log_id = await log_interaction(user_id, username, question, override)
        if log_id and log_id != "error":
            kb = [[InlineKeyboardButton("🚫 Пожаловаться", callback_data=f"complain:{log_id}")]]
            await update.message.reply_text(
                text=f"✅ Ручной ответ:\n{override}",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await update.message.reply_text(
                text=f"✅ Ручной ответ:\n{override}\n\n⚠️ (жалоба на ответ недоступна)"
            )
        return

    # 🎯 ИСПРАВЛЕННАЯ проверка приоритетных документов
    priority_hits = []
    question_lower = question.lower()

    for keyword, prio_doc in priorities_from_db.items():
        if keyword in question_lower:
            if isinstance(prio_doc, str):
                normalized_doc = unicodedata.normalize('NFKD', prio_doc).lower().strip()
                priority_hits.append(normalized_doc)
                logger.info(f"📌 Добавлен приоритетный документ: {normalized_doc}")
            elif isinstance(prio_doc, (list, set)):
                for d in prio_doc:
                    normalized_doc = unicodedata.normalize('NFKD', d).lower().strip()
                    priority_hits.append(normalized_doc)

    # 🎯 НОВАЯ ЛОГИКА: Тщательный поиск в приоритетных документах
    if priority_hits:
        logger.info(f"🎯 Найдены приоритетные документы: {priority_hits}")
        priority_docs = [(name, content) for (name, content) in docs if name in priority_hits]

        if priority_docs:
            logger.info(f"🎯 Запуск тщательного поиска в {len(priority_docs)} приоритетных документах")

            # Тщательный поиск в приоритетных документах
            for filename, content in priority_docs:
                logger.info(f"🔍 Детальный поиск в: {filename}")

                # Ищем по крупным кускам (4000 символов)
                step = 4000
                for i in range(0, len(content), step):
                    part = content[i:i + step]

                    # Проверяем, есть ли в этом куске ключевые слова из вопроса
                    question_words = [w for w in question.lower().split() if len(w) > 2]
                    if any(word in part.lower() for word in question_words):

                        # Специальный промпт для приоритетных документов
                        prompt = f"""
                        Ты ищешь ответ в корпоративном документе компании.

                        ВНИМАТЕЛЬНО прочитай текст и найди информацию о скидках, льготах, поощрениях для сотрудников.

                        Если найдешь ответ - дай ПОЛНЫЙ и ТОЧНЫЙ ответ со всеми деталями и процентами.
                        Если информации нет - напиши "ответа нет".

                        Текст документа:
                        {part}

                        Вопрос: {question}

                        Ответ:
                        """

                        try:
                            async with api_semaphore:
                                llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.1, max_tokens=1000)
                                response = await llm.ainvoke(prompt)
                                answer = response.content.strip()

                            if "ответа нет" not in answer.lower() and len(answer.strip()) > 10:
                                logger.info(f"✅ НАЙДЕН ОТВЕТ в приоритетном документе!")
                                log_id = await log_interaction(user_id, username, question, answer)
                                await send_answer(update, context, answer, part, log_id, filename=filename)
                                return

                        except Exception as e:
                            logger.error(f"Ошибка GPT: {e}")
                            continue

    # 🔍 Проверяем, есть ли в вопросе ключевые слова из CRM
    if any(keyword in question.lower() for keyword in CRM_KEYWORDS):
        logger.info("🔎 Ключевое слово CRM найдено. Ищем только в 3 документах.")

        # Фильтруем только нужные файлы
        ordered_docs = [(name, content) for (name, content) in docs if name in CRM_DOCUMENTS]

        # Принудительная сортировка, чтобы менеджер был первым
        ordered_docs.sort(key=lambda x: (
            'менеджер отдела продаж' in x[0].lower(),
            'роп' in x[0].lower(),
            'администратор' in x[0].lower()
        ), reverse=True)

        if not ordered_docs:
            logger.error(f"❌ Документы CRM не найдены в базе: {CRM_DOCUMENTS}")
    else:
        # 🔄 Упорядочиваем документы по приоритету
        if priority_hits:
            logger.info(f"📌 Приоритетные документы по ключевым словам: {priority_hits}")
            priority_docs = [(name, content) for (name, content) in docs if name in priority_hits]
            other_docs = [(name, content) for (name, content) in docs if name not in priority_hits]
            ordered_docs = priority_docs + other_docs
        else:
            ordered_docs = docs.copy()

    # 🔍 Фильтрация документов по роли (только для CRM)
    if any(keyword in question.lower() for keyword in CRM_KEYWORDS):
        priority_order = []

        if "менеджер" in question.lower():
            priority_order = [
                "porsche инструкция по работе системой автодилер менеджер отдела продаж.docx",
                "porsche инструкция по работе системой автодилер роп.docx",
                "porsche инструкция по работе системой автодилер администратор.docx"
            ]
        elif "роп" in question.lower() or "руководитель" in question.lower():
            priority_order = [
                "porsche инструкция по работе системой автодилер роп.docx",
                "porsche инструкция по работе системой автодилер менеджер отдела продаж.docx",
                "porsche инструкция по работе системой автодилер администратор.docx"
            ]
        else:
            priority_order = [
                "porsche инструкция по работе системой автодилер администратор.docx",
                "porsche инструкция по работе системой автодилер роп.docx",
                "porsche инструкция по работе системой автодилер менеджер отдела продаж.docx"
            ]

        # 🔄 Перекладываем в нужном порядке
        ordered_docs = sorted(
            ordered_docs,
            key=lambda x: priority_order.index(x[0]) if x[0] in priority_order else 100
        )

    # 🔄 4) Прямой поиск по ключевым словам из вопроса
    answers = []

    def direct_search_relevant(block, question):
        # Проверка по роли
        if is_relevant_for_role(block, question):
            return True
        important_short_words = ["срм", "crm", "атз"]
        stop_words = {"и", "а", "в", "на", "по", "к", "с", "от", "из", "у", "о", "за", "для", "как", "что"}
        words = [w for w in re.findall(r'\b\w{4,}\b', question.lower()) if w not in stop_words]
        words += [w for w in question.lower().split() if w in important_short_words]
        return any(w in block.lower() for w in words)

    # 🔍 Поиск по документам
    for filename, text in ordered_docs[:10]:  # Ограничиваем количество документов
        blocks = split_into_blocks(text)

        for block in blocks[:5]:  # Ограничиваем количество блоков
            if direct_search_relevant(block, question):
                answer = await ask_gpt(block, question, username)
                if "ответа нет" not in answer.lower() and len(answer.strip()) > 10:
                    answers.append((answer, block, filename))
                    logger.info(f"✅ Найден ответ в {filename}: {answer[:50]}...")
                    if len(answers) >= 3:  # Максимум 3 ответа
                        break

        if len(answers) >= 3:
            break

    # 🔄 5) Если ищем инструкцию, даем приоритет блокам с инструкциями
    if not answers:
        question_lower = question.lower()
        if "как" in question_lower or "инструкция" in question_lower:
            for filename, text in ordered_docs[:10]:
                blocks = split_into_blocks(text)
                for block in blocks[:5]:
                    if direct_search_relevant(block, question) and contains_instructions(block):
                        answer = await ask_gpt(block, question, username)
                        if "ответа нет" not in answer.lower() and len(answer.strip()) > 10:
                            answers.append((answer, block, filename))
                            if len(answers) >= 3:
                                break
                if len(answers) >= 3:
                    break

    # 🔄 6) Второй проход — поиск с синонимами
    if not answers:
        logger.info("🔄 Ничего не найдено в прямом поиске, пробуем с синонимами...")
        for filename, text in ordered_docs[:10]:
            blocks = split_into_blocks(text)
            for block in blocks[:5]:
                if is_relevant_block(block, question, synonyms_from_db):
                    answer = await ask_gpt(block, question, username)
                    if "ответа нет" not in answer.lower() and len(answer.strip()) > 10:
                        answers.append((answer, block, filename))
                        if len(answers) >= 3:
                            break
            if len(answers) >= 3:
                break

    # 🔎 7) Выбор лучшего ответа
    if answers:
        if len(answers) == 1:
            best_answer, best_block, best_filename = answers[0]
        else:
            raw_answers = [a for a, _, _ in answers]
            best = await gpt_choose_best(question, raw_answers)
            best_answer, best_block, best_filename = answers[0]  # По умолчанию первый
            for ans, block, filename in answers:
                if best.strip() in ans or ans in best.strip():
                    best_answer, best_block, best_filename = ans, block, filename
                    break

        log_id = await log_interaction(user_id, username, question, best_answer)
        await send_answer(update, context, best_answer, best_block, log_id, filename=best_filename)
        return

    # Если ничего не найдено
    log_id = await log_interaction(user_id, username, question, "Ничего не найдено")
    kb = [[InlineKeyboardButton("🚫 Пожаловаться", callback_data=f"complain:{log_id}")]]
    await update.message.reply_text(
        "❌ Ничего не найдено.",
        reply_markup=InlineKeyboardMarkup(kb)
    )


def is_law_related_question(text: str) -> bool:
    """Определяет, связан ли вопрос с юридической тематикой"""
    # Оставляем существующий код
    logger.info(f"🔍 Проверка на юридический вопрос: {text}")

    normalized_words = normalize(text)

    # Оригинальная проверка
    if any(n in normalized_words for n in LAW_KEYWORDS):
        logger.info(f"✅ Найдено точное совпадение с юр. ключевым словом")
        return True

    # ДОБАВЛЯЕМ НОВЫЕ ПРОВЕРКИ:

    # 1. Проверка по корням слов
    text_lower = text.lower()
    words_in_question = re.findall(r'\b\w+\b', text_lower)

    # Проверка частей слов (первые 4 буквы)
    for word in words_in_question:
        if len(word) < 4:
            continue

        word_stem = word[:4]  # Берем первые 4 буквы

        for keyword in LAW_KEYWORDS:
            if len(keyword) < 4:
                continue

            keyword_stem = keyword[:4]

            if word_stem == keyword_stem:
                logger.info(f"✅ Совпадение по корню: {word} ~ {keyword}")
                return True

    # 2. Простая проверка на наиболее частые юридические корни
    common_stems = ["налог", "деклар", "закон", "прав"]
    for stem in common_stems:
        if stem in text_lower:
            logger.info(f"✅ Найден юридический корень: {stem}")
            return True

    # Если ничего не сработало, возвращаем False
    logger.info("❌ Юридических терминов не обнаружено")
    return False


def call_kazllm(question: str) -> str:
    """Вызов модели KazLLM через Ollama API"""
    logger.info(f"🤖 Вызов KazLLM: {question}")

    try:
        payload = {
            "model": "kazllm8b",
            "prompt": question,
            "stream": False,
            "options": {
                "temperature": 0.8,
                "top_p": 0.95
            }
        }

        # Используем curl для вызова API Ollama
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", "http://ollama:11434/api/generate",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600
        )

        stdout = result.stdout.decode("utf-8").strip()
        stderr = result.stderr.decode("utf-8").strip()

        logger.info(f"📥 Ответ от KazLLM, длина: {len(stdout)}")
        if stderr:
            logger.warning(f"⚠️ Ошибка stderr: {stderr}")

        if not stdout:
            logger.error("⚠️ KazLLM вернул пустой ответ.")
            return "⚠️ Модель не вернула ответ. Пожалуйста, попробуйте позже."

        try:
            response = json.loads(stdout)
            answer = response.get("response", "")
            logger.info(f"📝 Полный ответ от KazLLM:\n{answer}")

            if answer:
                logger.info(f"✅ Успешный ответ: {answer[:50]}...")
                return answer.strip()
            else:
                logger.error("⚠️ KazLLM вернул пустой или некорректный ответ.")
                return "⚠️ Пустой ответ от модели."
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка JSON: {e}")
            return f"⚠️ Ошибка при обработке ответа: {str(e)}"

    except subprocess.TimeoutExpired:
        logger.error("⏱️ Превышено время ожидания (600с)")
        return "⚠️ Превышено время ожидания ответа. Попробуйте упростить вопрос."

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        return f"❌ Ошибка при запросе: {str(e)}"





# === ОБРАБОТЧИК ЛЮБОГО СООБЩЕНИЯ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"🔍 Получено сообщение: {update.message.text}")
    question = update.message.text.strip()
    if not question:
        await update.message.reply_text("❗ Вопрос пустой.")
        return

    user_id = update.message.from_user.id
    logger.info(f"🔍 Проверка пользователя {user_id}")

    if user_id not in allowed_users:
        logger.info(f"🚫 Пользователь {user_id} не имеет доступа")
        await update.message.reply_text("🚫 У вас нет доступа к боту.")
        return

    # Проверяем ограничение частоты
    logger.info(f"🔍 Проверка ограничения частоты для {user_id}")
    if not await check_rate_limit(user_id):
        logger.info(f"⚠️ Превышен лимит для {user_id}")
        await update.message.reply_text(
            f"⚠️ Превышен лимит запросов ({MAX_REQUESTS_PER_MINUTE} в минуту). Пожалуйста, подождите.")
        return

    username = update.message.from_user.username or update.message.from_user.full_name
    # 📌 Проверка на юридический вопрос
    if is_law_related_question(question):
        logger.info("⚖️ Вопрос определён как юридический. Запуск KazLLM...")

        # Сообщаем пользователю о начале обработки
        waiting_message = await update.message.reply_text(
            "⏳ Модель думает над ответом. Это может занять несколько минут...")

        # Вызываем KazLLM
        kazllm_answer = call_kazllm(question)

        # Логируем результат
        logger.info(f"⚖️ Получен ответ от KazLLM: {kazllm_answer[:100]}...")

        # Логируем взаимодействие
        log_id = await log_interaction(user_id, username, question, kazllm_answer)

        # Создаем кнопку для жалобы
        kb = [[InlineKeyboardButton("🚫 Пожаловаться", callback_data=f"complain:{log_id}")]]

        # Удаляем сообщение об ожидании
        try:
            await waiting_message.delete()
        except Exception as e:
            logger.error(f"⚠️ Не удалось удалить сообщение об ожидании: {e}")

        # Отправляем ответ пользователю
        await update.message.reply_text(
            f"⚖️ Ответ от KazLLM:\n{kazllm_answer}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return


    # КП обрабатываем сразу, минуя очередь
    if question.lower().startswith('кп'):
        logger.info(f"🔍 Запрос КП: {question}")
        cp_code = question[2:].strip()  # убираем 'кп' и пробелы
        await handle_cp_request(update, context, cp_code)
        return

    # Первичный ответ пользователю
    logger.info(f"🔍 Отправка первичного ответа пользователю {user_id}")
    await update.message.reply_text("⏳ Думаю...")

    # Добавляем задачу в очередь
    logger.info(f"🔍 Добавление задачи в очередь для {user_id}: {question}")
    await processing_queue.put((update, context, question, user_id, username))
    logger.info(f"✅ Задача добавлена в очередь, размер очереди: {processing_queue.qsize()}")


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_role(user_id, "директор"):
        await update.message.reply_text("🚫 У вас нет доступа к этой команде.")
        return

    try:
        uid = int(context.args[0])
        role = context.args[1]
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Используй: /adduser <id> <роль>")
        return

    async def _add_role():
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{BACKEND_URL}/roles", params={"user_id": uid, "role": role})
            response.raise_for_status()
            return response.json()

    try:
        await retry_async(lambda: _add_role())
        await update.message.reply_text(f"✅ Пользователь {uid} с ролью '{role}' добавлен.")
        # Обновляем список разрешенных пользователей
        await load_allowed_users()
    except Exception as e:
        logger.error(f"⚠️ Ошибка при добавлении пользователя: {e}")
        await update.message.reply_text(f"⚠️ Ошибка при добавлении пользователя.")


async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not await check_role(user_id, "директор"):
        await update.message.reply_text("🚫 У вас нет доступа к этой команде.")
        return

    try:
        uid = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Используй: /removeuser <id>")
        return

    async def _remove_role():
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(f"{BACKEND_URL}/roles/{uid}")
            response.raise_for_status()
            return response.json()


async def on_startup(app):
    """Функция, выполняемая при запуске бота"""
    logger.info("🚀 Запуск инициализации бота...")

    # Запускаем воркеры для обработки очереди
    logger.info("🔍 Запуск обработчиков очереди...")
    worker_tasks = await start_workers()
    app._worker_tasks = worker_tasks
    logger.info(f"✅ Запущено {len(worker_tasks)} обработчиков очереди")
    logger.info("🔍 Загрузка приоритетов и синонимов...")
    await load_dynamic_data()
    # Загружаем пользователей
    logger.info("🔍 Загрузка списка разрешенных пользователей...")
    for attempt in range(10):
        try:
            await load_allowed_users()
            if allowed_users:
                break
            logger.warning(f"Попытка {attempt + 1}: список пользователей пустой")
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1} не удалась: {e}")
        await asyncio.sleep(2)
    logger.info(f"✅ Пользователи загружены: {allowed_users}")

    logger.info("✅ Инициализация бота завершена!")
if __name__ == "__main__":
    from threading import Thread

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(on_startup).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("removeuser", remove_user))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(CallbackQueryHandler(handle_complaint))
    print("🤖 Бот запущен. Просто напишите сообщение...")
    Thread(target=start_watchdog, daemon=True).start()


    def start_watchdog():
        try:
            event_handler = DocsChangeHandler()
            observer = Observer()
            observer.schedule(event_handler, path="docs", recursive=False)
            observer.start()
            logger.info("✅ Watchdog инициализирован успешно")
            while True:
                time.sleep(1)
        except Exception as e:
            logger.error(f"❌ Ошибка в watchdog: {e}")


    logger.info("🔁 Watchdog запущен, следим за папкой docs/")
    docx_files = [f for f in os.listdir("docs") if f.endswith(".docx")]
    #logger.info(f"📂 В папке docs найдено {len(docx_files)} .docx-файлов: {docx_files}")
    from parse_documents import parse_and_return_chunks

    logger.info("📄 Форс-парсинг всех документов...")
    chunks = parse_and_return_chunks()
    logger.info(f"✅ Загружено {len(chunks)} чанков")

    app.run_polling()
