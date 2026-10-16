# PDF to Markdown Service

Микросервис для преобразования PDF документов в Markdown формат с использованием современных ML моделей.

## Особенности

- 🚀 **Высокая производительность** - Асинхронная обработка с поддержкой множественных конверсий
- 🔧 **Модульная архитектура** - Четкое разделение ответственности между слоями
- 🛡️ **Безопасность** - Валидация входных данных, rate limiting, безопасная работа с файлами
- 📊 **Мониторинг** - Детальное логирование и отслеживание прогресса
- 🔄 **Единый OCR-конвейер** - Indra обрабатывает все страницы в режиме OCR, включая формулы
- 📄 **Сохранение структуры** - LaTeX-формулы, HTML-таблицы и рисунки с подписями остаются в Markdown
- 🌐 **Двойной API** - REST API (FastAPI) и gRPC для максимальной совместимости
- 🧪 **Тестирование** - Полное покрытие тестами с поддержкой unit и integration тестов

## Архитектура

```
pdf_to_md/
├── src/
│   ├── api/              # API слой (FastAPI + gRPC)
│   ├── core/             # Бизнес-логика и конфигурация
│   ├── services/         # Сервисы (конвертация, модели, файлы)
│   └── grpc_services/    # gRPC сервисы
├── tests/                # Тесты
├── docs/                 # Документация
└── scripts/              # Скрипты для разработки
```

## Установка

### Требования

- Python 3.11+
- Poetry
- Docker (опционально)

### Локальная установка

```bash
# Клонирование репозитория
git clone <repository-url>
cd pdf_to_md

# Установка зависимостей
poetry install

# Активация виртуального окружения
poetry shell

# Установка pre-commit hooks
pre-commit install
```

### Docker установка

```bash
# Сборка образа
docker build -t pdf-to-md-service .

# Запуск контейнера
docker run -p 8002:8002 -p 50053:50053 pdf-to-md-service
```

## Использование

### REST API

#### Запуск серверов на фиксированных портах

```powershell
# PowerShell запускает REST на 8002 и gRPC на 50053.
# Повторный запуск сначала останавливает оставшийся экземпляр pdf_to_md.
.\start.ps1
```

Нажмите `Ctrl+C` в окне `start.ps1` для штатной остановки обоих серверов. Если окно
было закрыто принудительно, выполните `.\stop.ps1`: скрипт очистит сохранённые PID
и оставшиеся Python-процессы на портах `8002` и `50053`. Для предварительной проверки
можно выполнить `.\stop.ps1 -WhatIf`.

#### API Endpoints

- `GET /` - Информация о сервисе
- `GET /health` - Проверка здоровья
- `GET /api/v1/status` - Статус сервиса
- `POST /api/v1/convert` - Конвертация PDF в Markdown
- `GET /api/v1/models` - Список доступных моделей
- `POST /api/v1/models/{model_id}/set-default` - Установка модели по умолчанию
- `POST /api/v1/models/{model_id}/enable` - Включение/отключение модели

#### Пример использования

```bash
# Конвертация PDF файла
curl -X POST "http://localhost:8002/api/v1/convert" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf" \
  -F "model_id=default"

# Получение списка моделей
curl "http://localhost:8002/api/v1/models"
```

### gRPC API

#### Запуск gRPC сервера

```bash
poetry run python -m src.grpc_app
```

#### Пример клиента

```python
import grpc
from src import pdf_to_md_pb2, pdf_to_md_pb2_grpc

# Подключение к серверу
channel = grpc.insecure_channel('localhost:50053')
stub = pdf_to_md_pb2_grpc.PDFToMarkdownServiceStub(channel)

# Чтение PDF файла
with open('document.pdf', 'rb') as f:
    pdf_content = f.read()

# Запрос на конвертацию
request = pdf_to_md_pb2.ConvertPDFRequest(
    pdf_content=pdf_content,
    doc_id="test_doc",
    model_id="default"
)

# Выполнение конвертации
response = stub.ConvertPDF(request)

if response.success:
    print("Конвертация успешна!")
    print(f"Markdown: {response.markdown_content[:100]}...")
else:
    print(f"Ошибка: {response.message}")
```

## Конфигурация

### Переменные окружения

```bash
# Основные настройки
SERVICE_NAME=pdf-to-md-service
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8002
GRPC_PORT=50053
DEFAULT_MODEL=default
HF_HOME=../tmp/indra_models
INDRA_THREADS=1
INDRA_DPI=200
# В production установить true только после проверки лицензии весов.
INDRA_LICENSE_REVIEWED=false

# Обработка файлов
MAX_FILE_SIZE_MB=100
MAX_CONCURRENT_CONVERSIONS=5
CONVERSION_TIMEOUT_SECONDS=1800

# Безопасность
ENABLE_RATE_LIMITING=true
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=3600

# Логирование
LOG_LEVEL=INFO
```

### Файл конфигурации

Создайте файл `.env` в корне проекта:

```env
DEBUG=true
LOG_LEVEL=DEBUG
MAX_FILE_SIZE_MB=50
```

## Разработка

### Запуск тестов

```bash
# Все тесты
poetry run pytest

# Только unit тесты
poetry run pytest -m "not integration"

# С покрытием кода
poetry run pytest --cov=src --cov-report=html

# Конкретный тест
poetry run pytest tests/test_core/test_config.py::test_default_settings
```

### Форматирование кода

```bash
# Форматирование с black
poetry run black src tests

# Сортировка импортов
poetry run isort src tests

# Проверка стиля
poetry run flake8 src tests

# Проверка типов
poetry run mypy src
```

### Pre-commit hooks

```bash
# Установка hooks
poetry run pre-commit install

# Запуск на всех файлах
poetry run pre-commit run --all-files
```

## Модель преобразования

- **Внешний ID**: `default`
- **Внутренний движок**: Indra OCR (`engine=indra-ocr`)
- **Режим**: `mode=ocr` для всех страниц и `math=True`
- **Формулы**: LaTeX
- **Таблицы**: HTML, без преобразования в Markdown-сетки
- **Рисунки**: извлечение из PDF, загрузка в S3 и вставка `<figure>` с `<figcaption>`
- **Лицензия**: код Indra — Apache 2.0, веса — изменённая OpenRAIL-M. Владелец модели указывает ограничения по выручке/финансированию свыше $20 млн и использованию в конкурирующих с ним продуктах; лицензия также содержит условия распространения и атрибуции. Перед production-развёртыванием требуется отдельная юридическая проверка [текста лицензии весов](https://huggingface.co/datalab-to/indra-ocr/blob/main/LICENSE). Сервис откажется запускаться в production без `INDRA_LICENSE_REVIEWED=true`.

## Мониторинг и логирование

### Логи

Логи записываются в:
- Консоль (stdout)
- Файлы в папке `logs/` (если настроено)

### Метрики

- Количество активных конверсий
- Время обработки
- Статус моделей
- Ошибки конвертации

## Безопасность

- ✅ Валидация входных данных
- ✅ Ограничение размера файлов
- ✅ Rate limiting
- ✅ Безопасная работа с временными файлами
- ✅ Санитизация путей
- ✅ Логирование безопасности

## Производительность

- Асинхронная обработка
- Пул потоков для CPU-интенсивных задач
- Кэширование моделей
- Оптимизированная работа с памятью
- Таймауты для предотвращения зависания

## Troubleshooting

### Частые проблемы

1. **Недостаточно памяти**
   - Уменьшите `MAX_CONCURRENT_CONVERSIONS`
   - Увеличьте `CONVERSION_TIMEOUT_SECONDS`

2. **Медленная конвертация**
   - Проверьте размер PDF файла
   - Проверьте `INDRA_THREADS` и `INDRA_DPI` с учётом доступных ресурсов
   - Увеличьте таймаут

### Логи отладки

```bash
# Включение debug режима
export DEBUG=true
export LOG_LEVEL=DEBUG

# Запуск REST и gRPC с подробными логами на фиксированных портах
.\start.ps1
```

## Лицензия

MIT License

## Поддержка

Для вопросов и поддержки создайте issue в репозитории.
