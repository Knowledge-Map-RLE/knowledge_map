# Обработка естественного языка. NLP

Микросервис для многоуровневого лингвистического анализа текста через gRPC. Извлекает из текста графовую лингвистическую структуру и представляет сущности, действия и смыслы, содержащиеся в нём.

## Возможности

- **Многоуровневый анализ**: Токенизация, морфология, синтаксис, семантика, дискурс
- **Voting система**: Согласование результатов между разными NLP процессорами (spaCy, NLTK, Stanza, UDPipe)
- **Универсальный формат**: Стандартизация на Universal Dependencies
- **gRPC API**: Высокопроизводительное взаимодействие с API сервисом

## Архитектура

```
nlp/
├── proto/
│   └── nlp.proto                  # gRPC определения
├── src/
│   ├── grpc_server.py            # gRPC сервер
│   ├── config.py                 # Конфигурация
│   ├── base.py                   # Базовые классы
│   ├── nlp_manager.py            # Менеджер NLP процессоров
│   ├── multilevel_analyzer.py    # Многоуровневый анализатор
│   ├── unified_types.py          # Унифицированные типы данных
│   ├── adapters/                 # Адаптеры для NLP библиотек
│   │   ├── spacy_adapter.py
│   │   ├── nltk_adapter.py
│   │   ├── stanza_adapter.py
│   │   └── udpipe_adapter.py
│   ├── processors/               # Процессоры для разных уровней
│   │   ├── level1_tokenization_processor.py
│   │   ├── level2_morphology_processor.py
│   │   └── level3_syntax_processor.py
│   ├── voting/                   # Система голосования
│   │   ├── voting_engine.py
│   │   ├── agreement_calculator.py
│   │   └── confidence_aggregator.py
│   ├── mappers/                  # Маппинг данных
│   ├── morphemic/                # Морфемный анализ (отдельная функциональность)
│   └── legacy/                   # Старая функциональность (S3, deprecated)
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

## gRPC API

Сервис предоставляет следующие методы через gRPC (порт 50055):

### ProcessText
Обработка текста с аннотациями и отношениями.

**Запрос:**
```protobuf
message ProcessTextRequest {
    string text = 1;
    repeated string processor_names = 2;  // Если пусто - использовать все
    bool merge_results = 3;
}
```

**Ответ:**
```protobuf
message ProcessTextResponse {
    bool success = 1;
    repeated ProcessingResult results = 2;
    ProcessingResult merged_result = 3;
    string message = 4;
}
```

### ProcessSelection
Обработка выделенного фрагмента текста.

**Запрос:**
```protobuf
message ProcessSelectionRequest {
    string text = 1;
    string selection = 2;
    int32 start_offset = 3;
    int32 end_offset = 4;
    repeated string processor_names = 5;
    bool merge_results = 6;
}
```

### AnalyzeText
Многоуровневый лингвистический анализ.

**Запрос:**
```protobuf
message AnalyzeTextRequest {
    string text = 1;
    repeated LinguisticLevel levels = 2;  // Если пусто - все уровни
    bool enable_voting = 3;
    int32 min_agreement = 4;  // Минимум процессоров для согласия (default: 2)
}
```

**Ответ:**
```protobuf
message AnalyzeTextResponse {
    bool success = 1;
    UnifiedDocument document = 2;
    string message = 3;
    float processing_time = 4;
}
```

### GetSupportedTypes
Получение списка поддерживаемых типов процессоров.

**Ответ:**
```protobuf
message GetSupportedTypesResponse {
    repeated ProcessorInfo processors = 1;
    repeated string annotation_types = 2;
    repeated string relation_types = 3;
}
```

## Лингвистические уровни

1. **TOKENIZATION**: Токенизация и сегментация на предложения
2. **MORPHOLOGY**: Морфологический анализ и POS теггинг
3. **SYNTAX**: Синтаксический анализ и зависимости
4. **SEMANTIC_ROLES**: Семантические роли (TODO)
5. **LEXICAL_SEMANTICS**: Лексическая семантика (TODO)
6. **DISCOURSE**: Дискурс и отношения (TODO)

## Voting система

Для повышения точности анализа используется voting между процессорами:
- Минимум 2 процессора должны согласиться для принятия результата
- Каждый результат имеет confidence score и список источников (sources)
- Поддерживаемые процессоры: spaCy, NLTK, Stanza, UDPipe

## Конфигурация

Переменные окружения (префикс `NLP_`):

```bash
# Сервер
NLP_HOST=0.0.0.0
NLP_PORT=50055
NLP_MAX_WORKERS=10

# Процессоры
NLP_ENABLE_SPACY=true
NLP_ENABLE_NLTK=true
NLP_ENABLE_STANZA=true
NLP_ENABLE_UDPIPE=true

# Voting
NLP_MIN_AGREEMENT=2
NLP_ENABLE_VOTING=true

# Модели
NLP_SPACY_MODEL=ru_core_news_sm
NLP_STANZA_LANG=ru

# Производительность
NLP_MAX_TEXT_LENGTH=1000000
NLP_BATCH_SIZE=32
```

## Запуск

### Локальный запуск

1. Установите зависимости:
```bash
cd nlp
poetry install
```

2. Загрузите языковые модели:
```bash
# spaCy
python -m spacy download ru_core_news_sm

# Stanza
python -c "import stanza; stanza.download('ru')"

# NLTK
python -m nltk.downloader punkt averaged_perceptron_tagger
```

3. Запустите сервер:
```bash
poetry run python src/grpc_server.py
```

Сервер будет доступен на `localhost:50055`

### Docker

```bash
docker build -t nlp-service .
docker run -p 50055:50055 nlp-service
```

## Использование из API

```python
from services.nlp_grpc_client import get_nlp_grpc_client

# Получить клиент
client = get_nlp_grpc_client()

# Обработка текста
result = await client.process_text(
    text="Кот сидит на столе.",
    processor_names=["spacy", "nltk"],
    merge_results=True
)

# Многоуровневый анализ
analysis = await client.analyze_text(
    text="Кот сидит на столе.",
    levels=["tokenization", "morphology", "syntax"],
    enable_voting=True,
    min_agreement=2
)

# Получить поддерживаемые типы
types = await client.get_supported_types()
```

## Тестирование

```bash
# Unit тесты
poetry run pytest tests/unit/

# Integration тесты
poetry run pytest tests/integration/

# E2E тесты
poetry run pytest tests/e2e/
```

## Разработка

### Генерация proto файлов

```bash
python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src \
    --grpc_python_out=./src \
    ./proto/nlp.proto
```

### Добавление нового процессора

1. Создайте адаптер в `src/adapters/`
2. Реализуйте `BaseNLPAdapter` интерфейс
3. Зарегистрируйте в `NLPManager`

## Зависимости

- **gRPC**: grpcio, grpcio-tools, protobuf
- **NLP библиотеки**: spacy, nltk, stanza, pymorphy2
- **Утилиты**: networkx, pydantic, pydantic-settings

## Лицензия

MIT
