# syntax=docker/dockerfile:1
FROM python:3.12-slim

# не спрашивать APT ничего интерактивно
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 1) Установка компиляторов (с retry и --fix-missing)
RUN set -eux; \
    for i in 1 2 3; do \
      apt-get update \
        -o Acquire::Retries=3 \
        --fix-missing && \
      apt-get install -y --no-install-recommends gcc g++ \
        -o Acquire::Retries=3 \
        --fix-missing && \
      break || (echo "APT install failed, retry #${i}" && sleep 5); \
    done; \
    rm -rf /var/lib/apt/lists/*

# 2) Установка Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# 3) Копируем манифесты и устанавливаем зависимости
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only=main --no-interaction --no-ansi

# 4) Копируем исходники
COPY . .

# 5) Точка входа
CMD ["poetry", "run", "start-auth"]
