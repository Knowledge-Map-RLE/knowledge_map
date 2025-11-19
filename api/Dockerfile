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

# 2) Копируем pyproject и lock-файл
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
