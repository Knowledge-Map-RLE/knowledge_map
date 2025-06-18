FROM python:3.11-slim

# Устанавливаем системные зависимости с retry
RUN apt-get update --fix-missing && \
    for i in 1 2 3; do \
        apt-get install -y gcc g++ && break || \
        (echo "Retry $i failed, waiting..." && sleep 5); \
    done && \
    rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Устанавливаем Poetry
RUN pip install poetry

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock* ./

# Настраиваем Poetry и устанавливаем зависимости
RUN poetry config virtualenvs.create false \
    && poetry install --only=main --no-root --no-interaction --no-ansi

# Копируем исходный код
COPY . .

# Генерируем protobuf файлы
RUN mkdir -p src/generated \
    && python -m grpc_tools.protoc \
        -I./proto \
        --python_out=./src/generated \
        --grpc_python_out=./src/generated \
        ./proto/layout.proto \
    && touch src/generated/__init__.py

# Открываем порт
EXPOSE 50051

# Команда запуска
CMD ["python", "src/main.py"]