# Dockerfile для worker_distributed_layering с Poetry и Neo4j процедурами
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости с retry механизмом
RUN set -eux; \
    for i in 1 2 3; do \
      apt-get update -o Acquire::Retries=3 --fix-missing && \
      apt-get install -y --no-install-recommends curl -o Acquire::Retries=3 --fix-missing && \
      break || (echo "APT install failed, retry #${i}" && sleep 5); \
    done; \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock* ./

# Настраиваем Poetry и устанавливаем зависимости
RUN poetry config virtualenvs.create false && \
    poetry install --only=main --no-interaction --no-ansi

# Копируем исходный код
COPY . .

# Создаём пользователя для безопасности
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Настройки для работы
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV NUMBA_DISABLE_JIT=1
ENV NUMBA_NUM_THREADS=4
ENV OMP_NUM_THREADS=4

# Экспортируем порты
EXPOSE 8000 9100

# Команда по умолчанию
CMD ["python", "main.py", "standalone"]
