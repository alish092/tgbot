FROM python:3.10-slim

# Установка только необходимых системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# НЕ УСТАНАВЛИВАЕМ Ollama - он в отдельном контейнере!

# Установка Python-зависимостей
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаем директории
RUN mkdir -p docs cache

# НЕ ЗАГРУЖАЕМ модель здесь - она уже в контейнере ollama!

# Запускаем Python бота
CMD ["python", "tg_bot_final.py"]