# План тестирования алгоритма преобразования онтологий в карты знаний

## 1. Общее описание

Тестирование алгоритма преобразования RDF онтологий в направленные ациклические графы (DAG) - карты знаний с блоками действий.

## 2. Тестовые сценарии

### 2.1 Основной тест преобразования

#### 2.1.1 Входные данные
- 4 эталонные онтологии из `nlp/src/ontology/reference/ontologies.py`
- Текстовые предложения из теста `test_text_to_ontology.py`

#### 2.1.2 Процесс тестирования
1. Загрузка эталонных онтологий
2. Преобразование каждой онтологии в карту знаний
3. Валидация структуры карты знаний
4. Сравнение с ожидаемыми результатами
5. Расчет метрик качества

#### 2.1.3 Ожидаемые результаты
- Все 4 онтологии успешно преобразованы
- Полученные карты знаний проходят валидацию
- Метрики качества >= 70%

### 2.2 Тест валидации DAG

#### 2.2.1 Проверка ацикличности
```python
def test_dag_validation():
    """Проверяет что карта знаний является DAG"""
    # Создаем тестовый граф с циклом
    graph_with_cycle = create_cyclic_graph()
    
    # Проверяем что валидация выдает ошибку
    with pytest.raises(CycleError):
        validate_dag(graph_with_cycle)
    
    # Проверяем что корректный граф проходит валидацию
    valid_graph = create_valid_dag()
    assert validate_dag(valid_graph)
```

#### 2.2.2 Проверка уникальности связей
```python
def test_unique_edges():
    """Проверяет уникальность связей"""
    # Создаем граф с дублирующимися ребрами
    graph_with_duplicates = create_graph_with_duplicate_edges()
    
    # Проверяем что валидация выдает ошибку
    with pytest.raises(DuplicateEdgeError):
        validate_unique_edges(graph_with_duplicates)
```

### 2.3 Тест валидации глаголов

#### 2.3.1 Проверка количества глаголов
```python
def test_verb_count_validation():
    """Проверяет количество глаголов в блоках"""
    # Создаем блок с неправильным количеством глаголов
    block_with_wrong_verbs = create_block_with_wrong_verb_count()
    
    # Проверяем что валидация выдает ошибку
    with pytest.raises(InvalidVerbCountError):
        validate_verb_count([block_with_wrong_verbs])
```

#### 2.3.2 Проверка формы глаголов
```python
def test_verb_form_validation():
    """Проверяет форму глаголов"""
    # Создаем блок с глаголами несовершенного вида
    block_with_imperfect_verbs = create_block_with_imperfect_verbs()
    
    # Проверяем что валидация выдает ошибку
    with pytest.raises(InvalidVerbFormError):
        validate_verb_forms([block_with_imperfect_verbs])
```

### 2.4 Тест метрик качества

#### 2.4.1 Precision и Recall
```python
def test_precision_recall():
    """Проверяет метрики Precision и Recall"""
    expected_graph = create_expected_graph()
    actual_graph = create_actual_graph()
    
    comparison = compare_graphs(expected_graph, actual_graph)
    
    assert 0 <= comparison['metrics']['precision'] <= 1
    assert 0 <= comparison['metrics']['recall'] <= 1
```

#### 2.4.2 F1-Score
```python
def test_f1_score():
    """Проверяет метрику F1-Score"""
    expected_graph = create_expected_graph()
    actual_graph = create_actual_graph()
    
    comparison = compare_graphs(expected_graph, actual_graph)
    f1_score = comparison['metrics']['f1_score']
    
    assert 0 <= f1_score <= 1
```

## 3. Формат выходных файлов теста

### 3.1 Графы в формате GML
```
data/knowledge_map/
├── sentence1_knowledge_map.gml
├── sentence2_knowledge_map.gml
├── sentence3_knowledge_map.gml
├── sentence4_knowledge_map.gml
└── combined_knowledge_map.gml
```

### 3.2 Изображения графов
```
data/knowledge_map/
├── sentence1_knowledge_map.png
├── sentence2_knowledge_map.png
├── sentence3_knowledge_map.png
├── sentence4_knowledge_map.png
└── combined_knowledge_map.png
```

### 3.3 Отчеты по метрикам
```
data/knowledge_map/
├── sentence1_metrics.txt
├── sentence2_metrics.txt
├── sentence3_metrics.txt
├── sentence4_metrics.txt
└── combined_metrics.txt
```

## 4. Интеграционные тесты

### 4.1 Тест с существующими компонентами
```python
def test_integration_with_existing_components():
    """Тест интеграции с существующими компонентами"""
    # Используем существующие утилиты
    from src.ontology.comparison.graph_comparison import compare_graphs
    from src.ontology.visualization.graph_viz import visualize_graph
    
    # Преобразуем онтологию
    knowledge_map = builder.ontology_to_knowledge_map(ontology)
    
    # Сравниваем с ожидаемым результатом
    comparison = compare_graphs(expected_map, knowledge_map)
    
    # Визуализируем результат
    visualize_graph(knowledge_map, "knowledge_map")
```

### 4.2 Тест производительности
```python
def test_performance():
    """Тест производительности"""
    import time
    
    start_time = time.time()
    
    # Преобразуем все 4 онтологии
    for ontology in test_ontologies:
        knowledge_map = builder.ontology_to_knowledge_map(ontology)
    
    end_time = time.time()
    
    # Проверяем что время выполнения приемлемо
    assert (end_time - start_time) < 30  # менее 30 секунд
```

## 5. Стратегия тестирования

### 5.1 Unit тестирование
- Тестирование отдельных функций
- Тестирование классов преобразования
- Тестирование валидаторов

### 5.2 Интеграционное тестирование
- Тестирование взаимодействия с RDF графами
- Тестирование взаимодействия с NetworkX
- Тестирование взаимодействия с утилитами сравнения

### 5.3 Системное тестирование
- Тестирование полного процесса преобразования
- Тестирование сохранения результатов
- Тестирование визуализации

## 6. Критерии успеха

### 6.1 Функциональные критерии
- Все 4 онтологии успешно преобразованы
- Все карты знаний проходят валидацию
- Метрики качества >= 70%

### 6.2 Нефункциональные критерии
- Время выполнения < 30 секунд
- Память < 500 MB
- 100% покрытие кода тестами

### 6.3 Критерии качества
- Читаемость кода
- Документированность
- Соблюдение стандартов кодирования

## 7. План реализации тестов

### 7.1 Этап 1: Базовые тесты
1. Создание тестового файла `test_ontology_to_knowledge_map.py`
2. Реализация основного теста преобразования
3. Реализация тестов валидации

### 7.2 Этап 2: Метрики и сравнение
1. Интеграция с существующими утилитами сравнения
2. Реализация расчета метрик
3. Реализация тестов метрик

### 7.3 Этап 3: Интеграционные тесты
1. Тестирование с реальными онтологиями
2. Тестирование сохранения файлов
3. Тестирование визуализации

### 7.4 Этап 4: Оптимизация и финальное тестирование
1. Оптимизация производительности
2. Финальное тестирование всех сценариев
3. Подготовка отчетов по тестированию