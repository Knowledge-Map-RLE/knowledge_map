# PDF to Markdown Service

Микросервис для преобразования PDF документов в Markdown формат с поддержкой различных моделей обработки.

## Возможности

- Преобразование PDF в Markdown с использованием различных моделей
- Поддержка Marker AI моделей (Proper, Legacy)
- gRPC API для интеграции с другими сервисами
- REST API для прямого использования
- Отслеживание прогресса конвертации
- Обработка изображений из PDF

## Архитектура

Сервис построен на FastAPI с поддержкой gRPC для межсервисного взаимодействия. Поддерживает несколько моделей конвертации через реестр моделей.

## Запуск

### Предварительная загрузка моделей (рекомендуется)
```bash
# Загрузка моделей Marker перед сборкой Docker образа
python download_marker_models.py
```

### Локальная разработка
```bash
# Установка зависимостей
poetry install

# Запуск сервиса
poetry run python -m uvicorn src.main:app --host 0.0.0.0 --port 8002

# Запуск gRPC сервера
poetry run python -m src.grpc_server
```

### Docker
```bash
# Сборка образа (с предзагруженными моделями)
docker build -t pdf-to-md-service .

# Запуск контейнера
docker run -p 8000:8000 -p 50051:50051 pdf-to-md-service
```

## API

### REST API

- `POST /api/convert` - Конвертация PDF в Markdown
- `GET /api/models` - Список доступных моделей
- `POST /api/models/{model_id}/set-default` - Установка модели по умолчанию

### gRPC API

- `ConvertPdf` - Конвертация PDF в Markdown
- `GetModels` - Получение списка моделей
- `SetDefaultModel` - Установка модели по умолчанию

## Модели

- **marker_proper** - Улучшенная модель Marker (по умолчанию)
- **marker_legacy** - Оригинальная модель Marker
