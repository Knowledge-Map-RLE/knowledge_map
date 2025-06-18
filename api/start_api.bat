@echo off
echo Starting Knowledge Map API server...

REM Активируем виртуальное окружение Poetry
poetry install

REM Генерируем proto файлы
call generate_proto.bat

REM Запускаем сервер
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000 