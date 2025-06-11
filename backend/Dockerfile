FROM python:3.11-slim

WORKDIR /app

# Скопировать requirements.txt отдельно — для кэширования pip install
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
