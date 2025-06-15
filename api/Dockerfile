FROM python:3.12-slim

# Устанавливаем только необходимые системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Настраиваем Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    POETRY_VIRTUALENVS_CREATE=false

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы Poetry
COPY pyproject.toml poetry.lock* ./

# Устанавливаем зависимости
RUN poetry install --only=main --no-root && rm -rf $POETRY_CACHE_DIR

# Копируем исходный код
COPY . .

# Открываем порт
EXPOSE 8000

# Команда запуска
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]