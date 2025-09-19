FROM python:3.11-slim

# Установка системных зависимостей с retry логикой
RUN for i in 1 2 3; do \
        apt-get update && \
        apt-get install -y --fix-missing \
            build-essential \
            curl \
            git \
        && break || sleep 10; \
    done && \
    rm -rf /var/lib/apt/lists/*

# Установка Poetry
RUN pip install poetry

# Настройка Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Рабочая директория
WORKDIR /app

# Копирование файлов зависимостей
COPY pyproject.toml poetry.lock* ./

# Установка зависимостей
RUN poetry install --only=main && rm -rf $POETRY_CACHE_DIR

# Копирование исходного кода
COPY . .

# Генерация proto файлов
RUN poetry run python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=src \
    --grpc_python_out=src \
    proto/pdf_to_md.proto

# Создание пользователя для безопасности
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Экспорт портов
EXPOSE 8002 50051

# Команда по умолчанию
CMD ["poetry", "run", "python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
