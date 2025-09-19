FROM python:3.12-slim

# чтобы APT не задавал вопросов
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 1) Установка системных зависимостей (curl) с очисткой
RUN set -eux; \
    apt-get update -o Acquire::Retries=3 --fix-missing; \
    apt-get install -y --no-install-recommends curl; \
    rm -rf /var/lib/apt/lists/*

# 2) Копируем pyproject и lock-файл
COPY pyproject.toml poetry.lock* ./

# 3) Устанавливаем Poetry
RUN pip install --no-cache-dir poetry

# 4) Отключаем виртуальные окружения в Poetry
RUN poetry config virtualenvs.create false

# 5) Обновляем lock-файл (если pyproject изменился) и устанавливаем только production-зависимости
RUN poetry lock --no-interaction --no-ansi \
    && poetry install --only=main --no-root --no-interaction --no-ansi

# 6) Копируем исходный код
COPY . .

# 7) Копируем предзагруженные модели Marker (если есть)
# COPY marker_models/ ./marker_models/

# 8) Генерируем proto файлы
RUN python -m grpc_tools.protoc \
    -I./utils/proto \
    --python_out=./utils/generated \
    --grpc_python_out=./utils/generated \
    ./utils/proto/layout.proto ./utils/proto/auth.proto

# Создаем __init__.py для generated папки
RUN echo "" > utils/generated/__init__.py

# Исправляем импорты в сгенерированных grpc-файлах (делаем их относительными)
RUN sed -i "s/import layout_pb2 as layout__pb2/from \. import layout_pb2 as layout__pb2/g" utils/generated/layout_pb2_grpc.py \
    && sed -i "s/import auth_pb2 as auth__pb2/from \. import auth_pb2 as auth__pb2/g" utils/generated/auth_pb2_grpc.py

# 9) Открываем порт
EXPOSE 8000

# 10) Команда запуска
CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
