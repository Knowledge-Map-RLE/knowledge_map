# PDF to Text Service (gRPC)

Микросервис для преобразования PDF в текст с векторизацией и сохранением в Qdrant через gRPC API.

## Особенности

- 📄 **Извлечение текста из PDF** - Использует Docling для высококачественного извлечения текста
- 🔤 **Векторизация текста** - Автоматическое разбиение на чанки и генерация embeddings
- 🗄️ **Хранение в Qdrant** - Сохранение векторизованного текста в векторной базе данных
- 🔍 **Семантический поиск** - Поиск по смыслу через векторные представления
- 🚀 **gRPC API** - Высокопроизводительный gRPC интерфейс
- 📦 **Простая архитектура** - Монолитный сервис без сложных зависимостей

## Архитектура

**Workflow:**
```
PDF → Docling (текст) → Chunking → Embeddings → Qdrant (векторы)
```

```
pdf_to_text/
├── proto/                 # Protobuf схемы
│   └── pdf_to_text.proto
├── src/
│   ├── core/              # Основные модули
│   ├── services/          # Бизнес-логика
│   │   ├── docling_service.py      # PDF → Text
│   │   ├── embedding_service.py    # Text → Vectors
│   │   ├── qdrant_service.py       # Qdrant client
│   │   └── conversion_service.py   # Главный сервис
│   ├── generated/         # Сгенерированные protobuf файлы
│   ├── grpc_server.py     # gRPC сервер
│   └── main.py            # Точка входа
├── scripts/
│   └── generate_proto.bat # Скрипт генерации proto
└── ...
```

## Технологический стек

- **Python 3.11+** - Язык программирования
- **gRPC** - RPC framework
- **Protobuf** - Сериализация данных
- **Docling** - Извлечение текста из PDF
- **Sentence-Transformers** - Векторизация текста
- **Qdrant** - Векторная база данных
- **Poetry** - Управление зависимостями

## Установка

### Локальная установка

```bash
# Установка зависимостей
poetry install

# Генерация protobuf файлов
poetry run python -m grpc_tools.protoc -I proto --python_out=src/generated --grpc_python_out=src/generated proto/pdf_to_text.proto

# Или используйте скрипт (Windows)
scripts\generate_proto.bat
```

### Docker установка

```bash
# Сборка образа
docker build -t pdf-to-text-service .

# Запуск контейнера
docker run -p 8003:8003 pdf-to-text-service
```

## Конфигурация

Создайте файл `.env` в корне проекта:

```env
# Service
SERVICE_NAME=pdf-to-text-service
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8003

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=documents

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
CHUNK_SIZE=512
CHUNK_OVERLAP=50

# Processing
MAX_FILE_SIZE_MB=100

# Logging
LOG_LEVEL=INFO
```

## Использование

### Запуск сервиса

```bash
# Через Poetry
poetry run python -m src.main

# Или напрямую
python -m src.main
```

### gRPC API

#### Protobuf схема

```protobuf
service PDFToTextService {
    rpc ConvertPDF(ConvertPDFRequest) returns (ConvertPDFResponse);
    rpc SearchDocuments(SearchRequest) returns (SearchResponse);
    rpc DeleteDocument(DeleteDocumentRequest) returns (DeleteDocumentResponse);
    rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}
```

#### Python клиент

```python
import grpc
from src.generated import pdf_to_text_pb2, pdf_to_text_pb2_grpc

# Подключение к серверу
channel = grpc.insecure_channel('localhost:8003')
stub = pdf_to_text_pb2_grpc.PDFToTextServiceStub(channel)

# 1. Конвертация PDF
with open('document.pdf', 'rb') as f:
    pdf_content = f.read()

request = pdf_to_text_pb2.ConvertPDFRequest(
    pdf_content=pdf_content,
    filename='document.pdf'
)

response = stub.ConvertPDF(request)
print(f"Success: {response.success}")
print(f"Doc ID: {response.doc_id}")
print(f"Text length: {response.text_length}")
print(f"Chunks: {response.chunks_count}")
print(f"Points uploaded: {response.points_uploaded}")

# 2. Поиск документов
search_request = pdf_to_text_pb2.SearchRequest(
    query="machine learning algorithms",
    limit=10,
    score_threshold=0.7
)

search_response = stub.SearchDocuments(search_request)
for result in search_response.results:
    print(f"Score: {result.score}, Text: {result.text[:100]}")

# 3. Удаление документа
delete_request = pdf_to_text_pb2.DeleteDocumentRequest(
    doc_id=response.doc_id
)

delete_response = stub.DeleteDocument(delete_request)
print(f"Deleted: {delete_response.success}")

# 4. Health check
health_request = pdf_to_text_pb2.HealthCheckRequest()
health_response = stub.HealthCheck(health_request)
print(f"Status: {health_response.status}")
print(f"Qdrant available: {health_response.qdrant_available}")
```

#### grpcurl примеры

```bash
# Health check
grpcurl -plaintext localhost:8003 pdf_to_text.PDFToTextService/HealthCheck

# Конвертация PDF
grpcurl -plaintext -d @ localhost:8003 pdf_to_text.PDFToTextService/ConvertPDF <<EOF
{
  "pdf_content": "$(base64 < document.pdf)",
  "filename": "document.pdf"
}
EOF

# Поиск
grpcurl -plaintext -d '{"query": "machine learning", "limit": 5}' \
  localhost:8003 pdf_to_text.PDFToTextService/SearchDocuments
```

## Workflow

```mermaid
graph LR
    A[PDF Bytes] --> B[gRPC Server]
    B --> C[Docling Service]
    C --> D[Text Extraction]
    D --> E[Embedding Service]
    E --> F[Text Chunking]
    F --> G[Vector Generation]
    G --> H[Qdrant Service]
    H --> I[Vector Storage]
    I --> J[Search Available]
```

### Этапы обработки

1. **PDF → Text**: Docling извлекает текст из PDF
2. **Text → Chunks**: Текст разбивается на чанки (512 символов с перекрытием 50)
3. **Chunks → Vectors**: Каждый чанк векторизуется через sentence-transformers
4. **Vectors → Qdrant**: Векторы сохраняются в Qdrant с метаданными

## Метаданные в Qdrant

Каждый чанк сохраняется с следующими метаданными:

```json
{
  "doc_id": "abc123",
  "chunk_index": 0,
  "text": "Текст чанка...",
  "full_text": "Полный текст документа (только в первом чанке)",
  "chunk_count": 32,
  "filename": "document.pdf",
  "created_at": "2025-10-06T10:00:00"
}
```

## Docker Compose

```yaml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  pdf-to-text:
    build: ./pdf_to_text
    ports:
      - "8003:8003"  # gRPC port
    environment:
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
    depends_on:
      - qdrant

volumes:
  qdrant_data:
```

Запуск:
```bash
docker-compose up -d
```

## Генерация protobuf файлов

### Windows (PowerShell/CMD)
```bash
scripts\generate_proto.bat
```

### Linux/Mac
```bash
poetry run python -m grpc_tools.protoc \
    -I proto \
    --python_out=src/generated \
    --grpc_python_out=src/generated \
    proto/pdf_to_text.proto
```

## Производительность

- **Скорость конвертации**: ~3-10 секунд на документ (зависит от размера)
- **Размер чанка**: 512 символов (настраивается)
- **Векторное пространство**: 384 измерения (all-MiniLM-L6-v2)
- **Максимальный размер файла**: 100MB (настраивается)
- **gRPC**: Бинарная сериализация для высокой производительности

## Преимущества gRPC

- ⚡ **Высокая производительность** - Бинарная сериализация (Protobuf)
- 🔄 **Streaming** - Поддержка потоковой передачи данных
- 🌐 **Кроссплатформенность** - Клиенты на любых языках
- 📜 **Строгая типизация** - Автоматическая генерация кода из proto
- 🔌 **HTTP/2** - Мультиплексирование запросов

## Интеграция с другими проектами

Для интеграции:

1. Скопируйте `proto/pdf_to_text.proto` в ваш проект
2. Сгенерируйте клиент для вашего языка
3. Подключитесь к gRPC серверу на порту 8003

### Пример для Go
```bash
protoc --go_out=. --go-grpc_out=. proto/pdf_to_text.proto
```

### Пример для Node.js
```bash
npm install @grpc/grpc-js @grpc/proto-loader
```

## Troubleshooting

### Protobuf файлы не генерируются
```bash
poetry add grpcio-tools
poetry run python -m grpc_tools.protoc --version
```

### Qdrant недоступен
```bash
docker run -p 6333:6333 qdrant/qdrant
```

### Модель векторизации не загружается
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

### gRPC ошибки подключения
```bash
# Проверить что сервер запущен
netstat -an | grep 8003

# Проверить логи
tail -f logs/pdf-to-text-service.log
```

## Лицензия

MIT License

## Автор

Knowledge Map Team
