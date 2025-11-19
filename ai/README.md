# AI Model Service для Карты Знаний

AI Model Service - это gRPC микросервис для работы с Hugging Face моделями. Сервис предоставляет доступ к различным AI моделям для выполнения задач обработки естественного языка, которые ещё не имеют rule-based алгоритмов.

## Возможности

- 🤖 **Extensible Model Registry** - легко добавляйте новые модели через реестр
- 🚀 **GPU Support** - автоматическое использование CUDA, если доступно, с fallback на CPU
- 📦 **Automatic Chunking** - обработка больших текстов с автоматическим разбиением
- 🔌 **gRPC API** - высокопроизводительное взаимодействие с другими сервисами
- 🐳 **Docker Ready** - готов к запуску через Docker с поддержкой NVIDIA GPU

## Текущие модели

- **Qwen/Qwen2.5-0.5B-Instruct** (по умолчанию)
  - Instruction-tuned модель от Alibaba
  - Контекст: 32k токенов (используется 18k для чанков во избежание OOM)
  - Размер: 0.5B параметров - быстрая и легковесная
  - Задачи: генерация текста, форматирование документов, извлечение информации

- **meta-llama/Llama-3.2-1B-Instruct**
  - Instruction-tuned модель от Meta
  - Контекст: 128k токенов
  - Размер: 1B параметров
  - Задачи: генерация текста, форматирование документов, извлечение информации

## Архитектура

```
ai/
├── proto/
│   └── ai_model.proto          # gRPC определения
├── src/
│   ├── config.py               # Конфигурация сервиса
│   ├── grpc_server.py          # gRPC сервер
│   ├── models/
│   │   └── instruct_model.py   # Универсальная реализация для instruction-tuned моделей
│   ├── services/
│   │   ├── model_registry.py  # Реестр моделей
│   │   └── model_service.py   # Сервис управления моделями
│   └── utils/
│       └── chunking.py         # Утилиты для chunking
├── Dockerfile                  # Multi-stage build с CUDA
├── pyproject.toml              # Зависимости Poetry
└── README.md
```

## Установка и запуск

### Локальный запуск

#### Способ 1: Через start_local_dev.ps1 (рекомендуется)

```powershell
# Запустить все сервисы
.\start_local_dev.ps1

# Перезапустить только host сервисы (включая AI)
.\start_local_dev.ps1 -HostOnly

# Посмотреть логи AI сервиса
.\start_local_dev.ps1 -Logs -Service ai

# Статус всех сервисов
.\start_local_dev.ps1 -Status
```

#### Способ 2: Прямой запуск

```powershell
cd ai

# Установить зависимости
poetry install

# Сгенерировать proto файлы
poetry run python -m grpc_tools.protoc -I./proto --python_out=./src --grpc_python_out=./src ./proto/ai_model.proto

# Запустить gRPC сервер
poetry run python src/grpc_server.py
```

Сервис запустится на `localhost:50054`

### Запуск через Docker

#### Только AI сервис

```bash
# Build
docker build -t knowledge-map-ai ./ai

# Run с GPU
docker run --gpus all -p 50054:50054 \
  -v D:/Data/Data_Knowledge_Map/ai_models:/app/models \
  -e MODEL_DEVICE=auto \
  knowledge-map-ai

# Run без GPU (CPU only)
docker run -p 50054:50054 \
  -v D:/Data/Data_Knowledge_Map/ai_models:/app/models \
  -e MODEL_DEVICE=cpu \
  knowledge-map-ai
```

#### Вся система через docker-compose

```bash
# Запустить все сервисы
docker-compose up -d

# Только AI сервис
docker-compose up -d ai

# Логи AI сервиса
docker-compose logs -f ai
```

## Использование

### Через API сервис (REST)

AI сервис доступен через API сервис по адресу:

```
POST http://localhost:8000/api/ai/{model_id}/
```

Пример запроса:

```bash
curl -X POST "http://localhost:8000/api/ai/Qwen/Qwen2.5-0.5B-Instruct/" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain quantum computing in simple terms.",
    "max_tokens": 512,
    "temperature": 0.7,
    "top_p": 0.9
  }'
```

Ответ:

```json
{
  "success": true,
  "generated_text": "Quantum computing is...",
  "message": "Text generated successfully",
  "model_used": "Qwen/Qwen2.5-0.5B-Instruct",
  "input_tokens": 128,
  "output_tokens": 256,
  "chunked": false,
  "num_chunks": 0
}
```

### Прямое использование gRPC

```python
import grpc
from utils.generated import ai_model_pb2, ai_model_pb2_grpc

# Подключение
channel = grpc.insecure_channel('localhost:50054')
stub = ai_model_pb2_grpc.AIModelServiceStub(channel)

# Генерация текста
request = ai_model_pb2.GenerateTextRequest(
    model_id="Qwen/Qwen2.5-0.5B-Instruct",
    prompt="Your prompt here",
    max_tokens=512,
    temperature=0.7
)

response = stub.GenerateText(request)
print(response.generated_text)
```

## Пример использования: Форматирование Markdown

Одна из основных задач - форматирование Markdown файлов от Dockling:

```python
import requests

# Raw markdown от Dockling
raw_markdown = """
# Scientific Paper Title
This is a poorly formatted document...
"""

# Промпт для форматирования
prompt = f"""You are a scientific document formatter. Transform raw Markdown into clean, canonical format.

Requirements:
1. Add YAML frontmatter (title, authors, date, keywords, abstract)
2. Fix heading hierarchy
3. Fix broken paragraphs
4. Convert tables to HTML with <caption>
5. Convert images to HTML <figure> with <figcaption>
6. Format references as numbered [1]

Raw markdown:
{raw_markdown}

Output ONLY formatted Markdown."""

# Отправка запроса
response = requests.post(
    "http://localhost:8000/api/ai/Qwen/Qwen2.5-0.5B-Instruct/",
    json={
        "prompt": prompt,
        "max_tokens": 4096,
        "temperature": 0.3,
        "enable_chunking": True
    }
)

formatted_md = response.json()["generated_text"]
```

## Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `GRPC_HOST` | Host для gRPC сервера | `0.0.0.0` |
| `GRPC_PORT` | Порт для gRPC сервера | `50054` |
| `MODEL_CACHE_DIR` | Директория для кэша моделей | `./models` |
| `DEFAULT_MODEL` | Модель по умолчанию | `Qwen/Qwen2.5-0.5B-Instruct` |
| `MODEL_DEVICE` | Устройство (auto/cpu/cuda) | `auto` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |
| `DEFAULT_MAX_TOKENS` | Max токенов по умолчанию | `2048` |
| `DEFAULT_TEMPERATURE` | Temperature по умолчанию | `0.7` |
| `MAX_CONTEXT_LENGTH` | Макс. контекст перед chunking | `18000` |
| `CHUNK_OVERLAP` | Overlap между чанками | `200` |

## Добавление новых моделей

1. Зарегистрируйте модель в `src/services/model_registry.py`:

```python
self.register_model(
    ModelConfig(
        model_id="new-model/model-name",
        name="Model Name",
        description="Model description",
        max_context_length=128000,
        model_class="instruct_model.InstructModel",  # или новый класс
        default_params={
            "max_tokens": 2048,
            "temperature": 0.7,
        }
    )
)
```

2. Если нужна специальная реализация, создайте новый файл в `src/models/`:

```python
# src/models/custom_model.py
class CustomModel:
    def __init__(self, model_id: str, device: str = "auto"):
        # Инициализация модели
        pass

    def generate(self, prompt: str, **kwargs) -> dict:
        # Генерация текста
        return {
            "generated_text": "...",
            "input_tokens": 0,
            "output_tokens": 0,
        }
```

3. Обновите `model_class` в конфигурации на `"custom_model.CustomModel"`

## Health Check

```bash
# gRPC health check
grpcurl -plaintext localhost:50054 ai_model.AIModelService/HealthCheck

# Через API
curl http://localhost:8000/api/ai/health
```

## Производительность

### Qwen 2.5 0.5B (модель по умолчанию)
- **GPU (CUDA)**: ~100-200 токенов/сек
- **CPU**: ~20-40 токенов/сек
- **Память**:
  - Модель: ~2GB VRAM/RAM
  - Инференс (18k контекст): ~4-6GB VRAM/RAM
  - Рекомендуется: минимум 8GB VRAM (GTX 1070/1080 или лучше)

### Llama 3.2 1B
- **GPU (CUDA)**: ~50-100 токенов/сек
- **CPU**: ~10-20 токенов/сек
- **Память**: 4-8GB RAM (зависит от batch size)

## Troubleshooting

### Модель не загружается

Убедитесь что:
1. Есть доступ к интернету для скачивания модели
2. Достаточно места на диске (модели ~5-10GB)
3. Достаточно RAM (минимум 4GB свободно)

### Медленная генерация

Проверьте:
1. Используется ли GPU: смотрите логи при запуске
2. CPU ограничения: увеличьте `cpus` в docker-compose
3. Размер промпта: большие промпты медленнее

### Out of Memory

Сервис уже оптимизирован для работы на GTX 1070 (8GB VRAM):
- `max_memory` ограничивает использование до 7GB GPU + 8GB RAM
- `low_cpu_mem_usage=True` снижает пиковое потребление RAM
- `use_cache=True` использует KV-кэш для эффективности
- `max_length=18000` жестко ограничивает размер входа

Если всё равно возникает OOM:
1. Уменьшите `MAX_CONTEXT_LENGTH` до 12000-14000
2. Уменьшите `ai_max_generation_tokens` до 2048
3. Закройте другие GPU-приложения
4. Используйте CPU режим: `MODEL_DEVICE=cpu`

## Логи

```bash
# Локально
.\start_local_dev.ps1 -Logs -Service ai

# Docker
docker-compose logs -f ai

# Файл логов (локально)
tail -f ai/logs/ai_model.log
tail -f ai/logs/ai_model_error.log
```

## API Documentation

После запуска API сервиса, документация доступна по адресу:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

Раздел AI Models содержит все endpoints для работы с AI моделями.

## Лицензия

Part of Knowledge Map project
