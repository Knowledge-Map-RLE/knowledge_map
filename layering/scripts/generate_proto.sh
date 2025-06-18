#!/bin/bash

# Скрипт для генерации Python кода из protobuf файлов

echo "Генерация gRPC кода из protobuf..."

# Создаем папку для сгенерированных файлов если её нет
mkdir -p src/generated

# Генерируем Python код из .proto файла
python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src/generated \
    --grpc_python_out=./src/generated \
    ./proto/layout.proto

# Создаем __init__.py файл для Python пакета
touch src/generated/__init__.py

echo "Генерация завершена! Файлы созданы в src/generated/" 