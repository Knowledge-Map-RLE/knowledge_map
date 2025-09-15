FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка Poetry
RUN pip install poetry

# Копирование файлов проекта
COPY pyproject.toml ./

# Установка зависимостей
RUN poetry config virtualenvs.create false \
    && poetry install --only=main --no-root

# Копирование исходного кода
COPY src/ ./src/

# Создание директории для загрузок
RUN mkdir -p /tmp/uploads

# Открытие порта
EXPOSE 8001

# Запуск приложения
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
