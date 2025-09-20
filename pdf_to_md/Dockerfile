# Многоэтапная сборка для оптимизации размера образа
FROM python:3.11-slim AS builder

# Установка системных зависимостей с retry логикой
RUN for i in 1 2 3; do \
        apt-get update --fix-missing && \
        apt-get install -y --no-install-recommends --fix-missing \
            build-essential \
            gcc \
            g++ \
            libffi-dev \
            libssl-dev \
            && rm -rf /var/lib/apt/lists/* \
            && apt-get clean \
        && break || sleep 10; \
    done

# Установка Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Настройка Poetry для оптимизации
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Рабочая директория
WORKDIR /app

# Копирование только файлов зависимостей для лучшего кэширования
COPY pyproject.toml poetry.lock* ./

# Установка только основных зависимостей без dev зависимостей
RUN poetry install --no-dev --no-interaction --no-ansi --no-root && \
    poetry env info && \
    ls -la /tmp/poetry_cache/virtualenvs/ && \
    mkdir -p /app/.venv && \
    cp -r /tmp/poetry_cache/virtualenvs/pdf-to-md-service-*/* /app/.venv/ && \
    ls -la /app/.venv/ && \
    ls -la /app/.venv/bin/ && \
    /app/.venv/bin/python -c "import grpc; print('grpc installed successfully')" && \
    rm -rf $POETRY_CACHE_DIR

# Финальный образ
FROM python:3.11-slim AS runtime

# Установка runtime зависимостей с retry логикой
RUN for i in 1 2 3; do \
        apt-get update --fix-missing && \
        apt-get install -y --no-install-recommends --fix-missing \
            libgomp1 \
            libgcc-s1 \
            libstdc++6 \
            && rm -rf /var/lib/apt/lists/* \
            && apt-get clean \
        && break || sleep 10; \
    done

# Копирование виртуального окружения из builder
COPY --from=builder /app/.venv /app/.venv

# Проверяем что виртуальное окружение скопировалось правильно
RUN ls -la /app/.venv/ && \
    ls -la /app/.venv/bin/ && \
    ls -la /app/.venv/lib/python3.11/site-packages/ | head -10

# Добавление venv в PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:/app/marker_models:/app/.venv/lib/python3.11/site-packages" \
    PYTHONUNBUFFERED=1

# Рабочая директория
WORKDIR /app

# Копирование исходного кода
COPY src/ ./src/
COPY proto/ ./proto/

# Копирование моделей (критически важно для работы)
COPY marker_models/ ./marker_models/

# Генерация proto файлов
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=src \
    --grpc_python_out=src \
    proto/pdf_to_md.proto || echo "Proto generation failed, continuing..."

# Создание пользователя для безопасности
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

# Экспорт портов
EXPOSE 8002 50051

# Команда по умолчанию
CMD ["/app/.venv/bin/python", "src/grpc_server.py"]
