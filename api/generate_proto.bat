@echo off

REM Скрипт для генерации Python кода из protobuf файлов в API

echo Генерация gRPC кода из protobuf для API...

REM Создаем папку для сгенерированных файлов если её нет
if not exist "generated" mkdir "generated"

REM Генерируем Python код из .proto файла
python -m grpc_tools.protoc -I./proto --python_out=./generated --grpc_python_out=./generated ./proto/layout.proto

REM Создаем __init__.py файл для Python пакета
echo. > generated\__init__.py

echo Генерация завершена! Файлы созданы в generated/
pause 