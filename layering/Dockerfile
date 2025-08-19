FROM python:3.12-slim

# чтобы APT не задавал вопросов
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 1) Установка системных зависимостей (gcc, g++) с retry и --fix-missing
RUN set -eux; \
    for i in 1 2 3; do \
      apt-get update -o Acquire::Retries=3 --fix-missing && \
      apt-get install -y --no-install-recommends gcc g++ -o Acquire::Retries=3 --fix-missing && \
      break || (echo "APT install failed, retry #${i}" && sleep 5); \
    done; \
    rm -rf /var/lib/apt/lists/*

# 2) Копируем pyproject и lock-файл
COPY pyproject.toml poetry.lock* ./

# 3) Устанавливаем Poetry
RUN pip install --no-cache-dir poetry

# 4) Отключаем виртуальные окружения в Poetry
RUN poetry config virtualenvs.create false

# 5) Устанавливаем только production-зависимости
RUN poetry install --only=main --no-root --no-interaction --no-ansi

# 6) Копируем исходники
COPY . .

# 7) Генерируем gRPC-клиент/сервер из .proto
RUN python -m grpc_tools.protoc \
    -I proto \
    --python_out=src/generated \
    --grpc_python_out=src/generated \
    proto/layout.proto

# 8) Открываем порт gRPC
EXPOSE 50051

# 9) Запуск
CMD ["poetry", "run", "python", "-m", "src.main"]
