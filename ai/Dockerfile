FROM python:3.12-slim

# Устанавливаем только curl
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Устанавливаем минимальные зависимости
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    requests \
    python-multipart

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем исходный код
COPY src/ ./src/

# Создаем пользователя для безопасности
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Открываем порт
EXPOSE 8001

# Команда запуска
CMD ["python", "-m", "src.main_simple"]
