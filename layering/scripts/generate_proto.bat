@echo off

REM Скрипт для генерации Python кода из protobuf файлов на Windows

echo Генерация gRPC кода из protobuf...

REM Активируем виртуальное окружение Poetry
poetry install

REM Создаем папку для сгенерированных файлов если её нет
if not exist "src\generated" mkdir "src\generated"

REM Генерируем Python код
poetry run python -m grpc_tools.protoc ^
    -I proto ^
    --python_out=src/generated ^
    --grpc_python_out=src/generated ^
    proto/layout.proto

REM Создаем __init__.py файл для Python пакета
echo. > src\generated\__init__.py

REM Исправляем импорты в сгенерированных файлах
powershell -Command "(Get-Content src\generated\layout_pb2_grpc.py) -replace 'import layout_pb2 as', 'from . import layout_pb2 as' | Set-Content src\generated\layout_pb2_grpc.py"

echo Генерация завершена! Файлы созданы в src/generated/
pause 