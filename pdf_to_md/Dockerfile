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
RUN pip install --no-cache-dir poetry==2.4.1

# Настройка Poetry для оптимизации
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Рабочая директория
WORKDIR /app

# Копирование только файлов зависимостей для лучшего кэширования
COPY pyproject.toml poetry.lock* ./

# Установка только основных зависимостей без dev зависимостей
RUN poetry install --only=main --no-interaction --no-ansi --no-root && \
    /app/.venv/bin/python -c "import grpc; print('grpc OK')" && \
    rm -rf $POETRY_CACHE_DIR

# Предзагрузка моделей OCR и формул в слой образа.
ENV HF_HOME=/app/indra_models \
    HOME=/tmp
RUN mkdir -p /app/indra_models && \
    cd /app && poetry run python -c "\
import indra_ocr; \
converter = indra_ocr.load(threads=1, dpi=200, mode='ocr', math=True); \
print(f'Indra OCR models loaded: {type(converter).__name__}'); \
" && echo "Indra OCR and math models downloaded OK"

# Финальный образ
FROM python:3.11-slim AS runtime

# Установка runtime зависимостей с retry логикой
RUN for i in 1 2 3; do \
        apt-get update --fix-missing && \
        apt-get install -y --no-install-recommends --fix-missing \
            libgomp1 \
            libgcc-s1 \
            libstdc++6 \
            libxcb1 \
            libgl1 \
            libglib2.0-0 \
            && rm -rf /var/lib/apt/lists/* \
            && apt-get clean \
        && break || sleep 10; \
    done

# Копирование виртуального окружения и предзагруженных моделей из builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/indra_models /app/indra_models

RUN /app/.venv/bin/python -c "import indra_ocr; print('indra-ocr OK')"

# Добавление venv в PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:/app/.venv/lib/python3.11/site-packages" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/indra_models \
    OMP_NUM_THREADS=1

# Рабочая директория
WORKDIR /app

# Копирование исходного кода
COPY src/ ./src/
COPY proto/ ./proto/
COPY start.sh ./start.sh

# Генерация proto файлов
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=src \
    --grpc_python_out=src \
    proto/pdf_to_md.proto

# Создание пользователя для безопасности с домашней директорией
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser && \
    chmod +x /app/start.sh && \
    chown -R appuser:appuser /app && \
    chown -R appuser:appuser /home/appuser
USER appuser

# Экспорт портов
EXPOSE 8002 50053

# Команда по умолчанию — запуск обоих серверов
CMD ["/app/start.sh"]
