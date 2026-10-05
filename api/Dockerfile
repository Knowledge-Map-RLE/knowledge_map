FROM python:3.12-slim

# чтобы APT не задавал вопросов
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 1) Установка системных зависимостей с retry логикой
RUN for i in 1 2 3; do \
        apt-get update --fix-missing && \
        apt-get install -y --no-install-recommends --fix-missing \
            curl \
            && rm -rf /var/lib/apt/lists/* \
            && apt-get clean \
        && break || sleep 10; \
    done

# 2) Копируем shared-пакет observability (нужен для path-зависимости poetry)
COPY --from=shared ./observability ../shared/observability
COPY --from=shared ./knowledge ../shared/knowledge
COPY --from=shared ./model_registry ../shared/model_registry
COPY --from=core ./pipeline ../knowledge_map_core/pipeline
COPY --from=config ./config/models.toml ./config/models.toml
ENV ARTICLE_PIPELINE_GOLD_DIR=/data/article_pipeline_gold
ENV REFERENCE_PILOT_DIR=/data/reference_pilots/pmc10000452

# 3) Копируем pyproject и lock-файл
COPY pyproject.toml poetry.lock* ./

# 3) Устанавливаем Poetry
RUN pip install --no-cache-dir poetry

# 4) Отключаем виртуальные окружения в Poetry
RUN poetry config virtualenvs.create false

# 5) Обновляем lock-файл (если pyproject изменился) и устанавливаем только production-зависимости
RUN for i in 1 2 3; do \
        poetry lock --no-interaction --no-ansi && \
        poetry install --only=main --no-root --no-interaction --no-ansi \
        && break || sleep 5; \
    done

# 6) Копируем исходный код
COPY . .
COPY --from=config ./eval/article_pipeline_gold /data/article_pipeline_gold

# 8) Генерируем proto файлы
# Создаем utils/generated если не существует
RUN mkdir -p utils/generated

# Генерируем proto файлы для всех сервисов
RUN python -m grpc_tools.protoc \
    -I./utils/proto \
    --python_out=./utils/generated \
    --grpc_python_out=./utils/generated \
    ./utils/proto/layout.proto \
    ./utils/proto/auth.proto \
    ./utils/proto/nlp.proto

# Создаем __init__.py для generated папки
RUN echo "" > utils/generated/__init__.py

# Исправляем импорты в сгенерированных grpc-файлах (делаем их относительными)
RUN sed -i "s/^import layout_pb2 as layout__pb2$/from . import layout_pb2 as layout__pb2/g" utils/generated/layout_pb2_grpc.py \
    && sed -i "s/^import auth_pb2 as auth__pb2$/from . import auth_pb2 as auth__pb2/g" utils/generated/auth_pb2_grpc.py \
    && sed -i "s/^import nlp_pb2 as nlp__pb2$/from . import nlp_pb2 as nlp__pb2/g" utils/generated/nlp_pb2_grpc.py

# 9) Открываем порт
EXPOSE 8000
ENV PYTHONPATH=/shared/model_registry

# 10) Команда запуска
CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
