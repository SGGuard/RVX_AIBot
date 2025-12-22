FROM python:3.12-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements.txt
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всех файлов приложения
COPY . .

# Создание директории для данных
RUN mkdir -p /data /app/backups

# Сделать стартовый скрипт исполняемым
RUN chmod +x /app/start.py

# Запустить оба сервиса одновременно
CMD ["python", "start.py"]
