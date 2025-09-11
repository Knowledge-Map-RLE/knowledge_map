# Тестирование топологической сортировки

Этот каталог содержит комплексные тесты для алгоритма топологической сортировки и валидации топологического порядка.

## Структура тестов

### Основные файлы тестов

- **`test_topological_sort.py`** - Основные тесты алгоритма топологической сортировки
- **`test_topological_validation.py`** - Тесты валидации топологического порядка
- **`test_neo4j_client.py`** - Тесты клиента Neo4j
- **`test_distributed_layout.py`** - Тесты распределенной укладки
- **`test_tasks.py`** - Тесты задач Celery

### Типы тестов

#### Unit тесты (`@pytest.mark.unit`)
- Тестируют отдельные функции и методы
- Используют моки для изоляции компонентов
- Быстро выполняются

#### Интеграционные тесты (`@pytest.mark.integration`)
- Тестируют взаимодействие между компонентами
- Могут использовать реальные данные
- Требуют больше времени на выполнение

#### Тесты производительности (`@pytest.mark.performance`)
- Тестируют производительность алгоритмов
- Проверяют масштабируемость
- Могут выполняться дольше

## Запуск тестов

### Через Poetry (рекомендуется)

```bash
# Все тесты
poetry run pytest

# Только тесты топологической сортировки
poetry run pytest tests/test_topological_sort.py

# Только тесты валидации
poetry run pytest tests/test_topological_validation.py

# С покрытием кода
poetry run pytest --cov=src --cov-report=html

# Параллельно
poetry run pytest -n auto

# По маркерам
poetry run pytest -m unit
poetry run pytest -m integration
poetry run pytest -m performance
```

### Через Makefile

```bash
# Все тесты
make test

# Тесты топологической сортировки
make test-topological

# Тесты валидации
make test-validation

# С покрытием кода
make test-coverage

# В режиме наблюдения
make test-watch

# Параллельно
make test-parallel
```

### Через скрипт

```bash
# Все тесты
python scripts/run_tests.py

# Конкретный набор тестов
python scripts/run_tests.py --suite topological

# В режиме наблюдения
python scripts/run_tests.py --watch

# Тесты производительности
python scripts/run_tests.py --performance

# С параллельным выполнением
python scripts/run_tests.py --parallel --workers 8
```

## Автоматический запуск тестов

### Pre-commit хуки

Настройте автоматический запуск тестов при коммитах:

```bash
# Установка pre-commit хуков
make setup-hooks

# Или вручную
poetry run pre-commit install
```

Теперь при каждом коммите будут автоматически запускаться:
- Форматирование кода (Black, isort)
- Проверка стиля (flake8)
- Проверка типов (mypy)
- Тесты для измененных файлов

### Режим наблюдения

Для разработки используйте режим наблюдения за изменениями:

```bash
# Через Makefile
make test-watch

# Через скрипт
python scripts/run_tests.py --watch

# Через pytest-watch
poetry run ptw --runner "pytest -v"
```

## Покрытие кода

### Генерация отчета

```bash
# HTML отчет
make test-coverage

# Или через pytest
poetry run pytest --cov=src --cov-report=html:htmlcov --cov-report=xml:coverage.xml
```

### Просмотр отчета

После генерации отчета откройте файл `htmlcov/index.html` в браузере.

## Структура тестов топологической сортировки

### TestTopologicalSorter
- `test_compute_toposort_order_db_success()` - Успешное выполнение
- `test_compute_toposort_order_db_with_cycles()` - Обработка циклов
- `test_compute_toposort_order_db_large_graph()` - Большой граф
- `test_compute_toposort_order_db_database_error()` - Обработка ошибок

### TestTopologicalOrderValidation
- `test_validate_monotonic_sequence_valid()` - Корректная последовательность
- `test_validate_monotonic_sequence_invalid()` - Некорректная последовательность
- `test_validate_sequence_gaps()` - Проверка пропусков
- `test_validate_sequence_bounds()` - Проверка границ

### TestTopologicalSortIntegration
- `test_end_to_end_topological_sort()` - Полный интеграционный тест
- `test_topological_sort_performance()` - Тест производительности

### TestTopologicalSortEdgeCases
- `test_empty_graph()` - Пустой граф
- `test_single_node_graph()` - Граф с одной вершиной
- `test_disconnected_components()` - Несвязанные компоненты

## Параметризованные тесты

Используются для тестирования различных размеров графов:

```python
@pytest.mark.parametrize("graph_size,expected_calls", [
    (0, 4),    # Пустой граф
    (1, 7),    # Одна вершина
    (10, 10),  # Небольшой граф
    (100, 10), # Средний граф
    (1000, 10), # Большой граф
])
```

## Моки и фикстуры

### Фикстуры Neo4j
```python
@pytest.fixture
def mock_neo4j_responses():
    return {
        "total_articles": [{"total": 5}],
        "init_result": [{"batches": 1, "total": 5, "errorMessages": []}],
        # ...
    }
```

### Моки для тестирования
```python
with patch.object(neo4j_client, 'execute_query_with_retry') as mock_execute:
    mock_execute.side_effect = [
        mock_responses["total_articles"],
        mock_responses["init_result"],
        # ...
    ]
```

## Валидация топологического порядка

### Проверяемые свойства

1. **Монотонность** - последовательность должна быть неубывающей
2. **Отсутствие пропусков** - все числа от 0 до (n-1) должны присутствовать
3. **Правильные границы** - начинается с 0, заканчивается на (n-1)
4. **Целые числа** - все значения должны быть целыми
5. **Уникальность** - каждое значение должно встречаться только один раз

### Пример валидации

```python
validator = TopologicalOrderValidator()
topo_orders = [0, 1, 2, 3, 4, 5]
is_valid, errors = validator.validate_topological_order(topo_orders, 6)

assert is_valid is True
assert len(errors) == 0
```

## Отладка тестов

### Подробный вывод

```bash
# Максимально подробный вывод
poetry run pytest -vvv --tb=long --capture=no

# Только для тестов топологической сортировки
poetry run pytest tests/test_topological_sort.py -vvv --tb=long
```

### Отладка конкретного теста

```bash
# Запуск одного теста
poetry run pytest tests/test_topological_sort.py::TestTopologicalSorter::test_compute_toposort_order_db_success -vvv

# С остановкой на первой ошибке
poetry run pytest -x -vvv
```

## Непрерывная интеграция

### GitHub Actions

Создайте файл `.github/workflows/tests.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v3
      with:
        python-version: '3.11'
    - name: Install Poetry
      uses: snok/install-poetry@v1
    - name: Install dependencies
      run: poetry install
    - name: Run tests
      run: poetry run pytest --cov=src --cov-report=xml
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Лучшие практики

1. **Именование тестов** - используйте описательные имена
2. **Изоляция** - каждый тест должен быть независимым
3. **Моки** - используйте моки для внешних зависимостей
4. **Параметризация** - используйте `@pytest.mark.parametrize` для похожих тестов
5. **Фикстуры** - переиспользуйте общие данные через фикстуры
6. **Покрытие** - стремитесь к высокому покрытию кода
7. **Производительность** - тестируйте производительность критических алгоритмов

## Устранение неполадок

### Частые проблемы

1. **Ошибки импорта** - убедитесь, что PYTHONPATH настроен правильно
2. **Моки не работают** - проверьте правильность путей в `patch.object`
3. **Медленные тесты** - используйте моки вместо реальных вызовов БД
4. **Проблемы с async** - используйте `@pytest.mark.asyncio`

### Получение помощи

```bash
# Справка по pytest
poetry run pytest --help

# Справка по скрипту тестов
python scripts/run_tests.py --help

# Справка по Makefile
make help
```
