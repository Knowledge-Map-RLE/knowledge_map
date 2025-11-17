# Тестирование Knowledge Map API

Комплексная система тестирования с использованием размеченных датасетов для консистентной проверки функциональности NLP, аннотаций, связей и цепочек действий.

## Быстрый старт

### 1. Установка зависимостей

```bash
cd api
poetry install
```

### 2. Запуск тестов

```bash
# Все тесты
poetry run pytest tests/

# Только unit тесты (быстрые)
poetry run pytest tests/ -m unit

# Только тесты с датасетами
poetry run pytest tests/ -m dataset

# Конкретный файл
poetry run pytest tests/test_routers/test_nlp.py -v
```

### 3. Создание датасета

Если у вас есть размеченный документ в Neo4j:

```bash
# Экспортируем в датасет
poetry run python tools/dataset_builder/export_dataset.py \
  --doc-id <your_doc_id> \
  --output sample_001 \
  --include-pdf

# Валидируем
poetry run python tools/dataset_builder/validate_dataset.py --sample sample_001
```

### 4. Использование датасета в тестах

```python
import pytest

@pytest.mark.dataset
async def test_my_feature(load_document_dataset):
    # Загружаем датасет
    doc_data = load_document_dataset("sample_001")

    # Используем в тесте
    assert doc_data["markdown"] is not None
```

## Структура

```
tests/
├── conftest.py                 # Общие фикстуры для всех тестов
├── fixtures/                   # Дополнительные фикстуры
│   └── __init__.py
├── datasets/                   # Размеченные тестовые данные
│   ├── README.md              # Подробная документация по датасетам
│   ├── schema.json            # JSON Schema для валидации
│   ├── documents/             # Исходные документы (PDF, MD, metadata)
│   ├── annotations/           # Размеченные аннотации и связи
│   └── expected/              # Ожидаемые результаты анализа
├── test_routers/              # Тесты эндпоинтов API
│   ├── test_nlp.py
│   ├── test_annotations.py
│   ├── test_relations.py
│   └── test_action_chains.py
├── test_services/             # Тесты сервисов
│   └── test_data_extraction_service.py
└── test_integration/          # Интеграционные тесты
    └── test_pdf_processing_integration.py
```

## Маркеры pytest

Используйте маркеры для организации тестов:

```bash
# Unit тесты (быстрые, изолированные)
pytest -m unit

# Integration тесты (требуют внешних сервисов)
pytest -m integration

# NLP тесты
pytest -m nlp

# Тесты с датасетами
pytest -m dataset

# Медленные тесты (пропустить)
pytest -m "not slow"

# Комбинации
pytest -m "dataset and nlp and not slow"
```

## Доступные фикстуры

### Загрузка датасетов

- `dataset_loader(sample_id, resource_path)` - универсальный загрузчик
- `load_document_dataset(sample_id)` - загрузка документа
- `load_annotations_dataset(sample_id)` - загрузка аннотаций
- `load_expected_results(sample_id)` - загрузка ожидаемых результатов

### Mock фикстуры

- `mock_s3_client` - мок S3 клиента
- `mock_neo4j_connection` - мок Neo4j соединения

### Тестовые данные

- `sample_markdown_text` - пример markdown текста
- `sample_annotations` - пример аннотаций
- `sample_relations` - пример связей

### Утилиты

- `assert_annotations_equal(actual, expected, threshold)` - сравнение аннотаций
- `assert_chains_equal(actual, expected, tolerance)` - сравнение цепочек

## Инструменты

### Export Dataset

Экспорт размеченного документа из Neo4j в датасет:

```bash
poetry run python tools/dataset_builder/export_dataset.py \
  --doc-id <doc_id> \
  --output sample_001 \
  --include-pdf
```

### Import Dataset

Импорт датасета в Neo4j для тестирования:

```bash
poetry run python tools/dataset_builder/import_dataset.py \
  --sample sample_001 \
  --clean
```

### Validate Dataset

Валидация структуры и консистентности датасета:

```bash
# Один датасет
poetry run python tools/dataset_builder/validate_dataset.py --sample sample_001

# Все датасеты
poetry run python tools/dataset_builder/validate_dataset.py --all
```

## Написание тестов

### Простой тест с датасетом

```python
import pytest

@pytest.mark.dataset
async def test_nlp_analysis(load_document_dataset):
    # Загружаем датасет
    doc_data = load_document_dataset("sample_001")

    # Запускаем анализ
    from services.nlp_service import NLPService
    nlp_service = NLPService()
    result = nlp_service.analyze_text(doc_data["markdown"])

    # Проверяем результат
    assert "tokens" in result
    assert len(result["tokens"]) > 0
```

### Тест с ожидаемыми результатами

```python
@pytest.mark.dataset
async def test_with_expected_results(
    load_document_dataset,
    load_expected_results
):
    doc_data = load_document_dataset("sample_001")
    expected = load_expected_results("sample_001")

    # Запускаем анализ
    result = await analyze_document(doc_data["markdown"])

    # Сравниваем с ожидаемым
    assert result["sentence_count"] == expected["nlp_analysis"]["sentence_count"]
```

### Тест с моками

```python
@pytest.mark.asyncio
async def test_with_mocks(mock_s3_client, mock_neo4j_connection):
    # Настраиваем моки
    mock_s3_client.download_text.return_value = "test markdown"

    # Тестируем с моками
    from services.data_extraction_service import DataExtractionService
    service = DataExtractionService()
    # ...
```

## Workflow разработки

### 1. Создание нового датасета

1. Разметьте документ через веб-интерфейс
2. Экспортируйте: `poetry run python tools/dataset_builder/export_dataset.py --doc-id <id> --output sample_new`
3. Валидируйте: `poetry run python tools/dataset_builder/validate_dataset.py --sample sample_new`
4. Добавьте в git: `git add tests/datasets/`

### 2. Написание теста

1. Создайте тестовый файл в `tests/test_routers/`
2. Используйте фикстуры для загрузки датасета
3. Добавьте подходящие pytest маркеры
4. Запустите тест: `poetry run pytest tests/test_routers/test_your_feature.py -v`

### 3. Проверка перед коммитом

```bash
# Валидация всех датасетов
poetry run python tools/dataset_builder/validate_dataset.py --all

# Запуск быстрых тестов
poetry run pytest tests/ -m "not slow" --tb=short

# Запуск всех тестов
poetry run pytest tests/ -v
```

## Troubleshooting

### "Dataset not found"

Убедитесь что датасет существует:
```bash
ls tests/datasets/documents/sample_001/
```

### "Invalid JSON"

Проверьте JSON файлы:
```bash
python -m json.tool tests/datasets/annotations/sample_001/linguistic.json
```

### "Offset exceeds markdown length"

Валидируйте датасет:
```bash
poetry run python tools/dataset_builder/validate_dataset.py --sample sample_001
```

## Дополнительная документация

- [Datasets README](./datasets/README.md) - Подробная документация по датасетам
- [pytest.ini](../pytest.ini) - Конфигурация pytest
- [conftest.py](./conftest.py) - Общие фикстуры

## Best Practices

1. **Всегда валидируйте датасеты** перед коммитом
2. **Используйте осмысленные имена** для датасетов (`sample_scientific_paper_001`)
3. **Документируйте специфику** каждого датасета
4. **Не изменяйте существующие датасеты** без крайней необходимости
5. **Создавайте маленькие датасеты** для unit тестов, большие для integration
6. **Покрывайте edge cases** отдельными датасетами
