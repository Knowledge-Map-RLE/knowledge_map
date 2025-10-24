FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Настройка Poetry
RUN poetry config virtualenvs.create false

WORKDIR /app

# Копирование файлов зависимостей
COPY pyproject.toml ./

# Установка зависимостей
RUN poetry install --no-interaction --no-ansi --no-root --only main

# Копирование proto файлов и генерация
COPY proto/ ./proto/
RUN poetry run python -m grpc_tools.protoc \
    -I proto \
    --python_out=src/generated \
    --grpc_python_out=src/generated \
    proto/pdf_to_text.proto

# Копирование кода приложения
COPY . .

# Создание директорий для логов
RUN mkdir -p /app/logs

# Открытие портов (gRPC)
EXPOSE 8003

# Запуск gRPC сервера
CMD ["python", "-m", "src.main"]

