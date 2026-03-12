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
RUN poetry install --only=main --no-interaction --no-ansi --no-root && \
    mkdir -p /app/.venv && \
    cp -r /tmp/poetry_cache/virtualenvs/pdf-to-md-service-*/* /app/.venv/ && \
    /app/.venv/bin/python -c "import grpc; print('grpc OK')" && \
    rm -rf $POETRY_CACHE_DIR

# Предзагрузка моделей Docling в слой образа (исключает загрузку при старте)
ENV DOCLING_ARTIFACTS_PATH=/app/docling_models \
    HF_HOME=/app/docling_models/hf_cache \
    TORCH_HOME=/app/docling_models/torch_cache \
    HOME=/tmp
RUN mkdir -p /app/docling_models/ds4sd--docling-layout-heron && \
    /app/.venv/bin/python -c "\
from pathlib import Path; \
from huggingface_hub import snapshot_download; \
layout_dir = Path('/app/docling_models/ds4sd--docling-layout-heron'); \
print('Downloading ds4sd/docling-layout-heron...'); \
result = snapshot_download(repo_id='ds4sd/docling-layout-heron', local_dir=str(layout_dir)); \
print(f'Downloaded to: {result}'); \
files = list(layout_dir.iterdir()); \
print(f'Files: {[f.name for f in files]}'); \
" && echo "Models downloaded OK"

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
COPY --from=builder /app/docling_models /app/docling_models

RUN /app/.venv/bin/python -c "import docling; print('docling OK')"

# Добавление venv в PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:/app/marker_models:/app/.venv/lib/python3.11/site-packages" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/docling_models/hf_cache \
    TORCH_HOME=/app/docling_models/torch_cache \
    OMP_NUM_THREADS=4

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
    proto/pdf_to_md.proto || echo "Proto generation failed, continuing..."

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
