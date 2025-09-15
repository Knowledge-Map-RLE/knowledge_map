FROM python:3.12-slim

# Устанавливаем только curl
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Устанавливаем pip зависимости напрямую
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn==0.24.0 \
    pydantic==2.11.7 \
    pydantic-settings==2.9.1 \
    neomodel==5.3.1 \
    strawberry-graphql[fastapi]==0.219.0 \
    grpcio==1.74.0 \
    grpcio-tools==1.74.0 \
    protobuf==6.31.1 \
    networkx==3.5 \
    aioboto3==13.4.0 \
    aiofiles==24.1.0 \
    requests==2.32.4 \
    aiohttp==3.12.13 \
    python-multipart==0.0.6 \
    python-dotenv==1.1.0 \
    uuid6==2025.0.0 \
    psutil==6.0.0 \
    "pillow<11.0.0" \
    marker-pdf==1.9.3

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем исходный код
COPY . .

# Генерируем proto файлы
RUN python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./generated \
    --grpc_python_out=./generated \
    ./proto/layout.proto ./proto/auth.proto

# Создаем __init__.py для generated папки
RUN echo "" > generated/__init__.py

# Открываем порт
EXPOSE 8000

# Команда запуска
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
