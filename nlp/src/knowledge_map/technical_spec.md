# Техническая спецификация алгоритма преобразования онтологий в карты знаний

## 1. Общее описание

Алгоритм преобразует RDF онтологии в направленные ациклические графы (DAG) - карты знаний, где:
- Узлы представляют собой блоки действий
- Ребра представляют зависимости между действиями
- Каждый блок содержит 1-2 глагола в совершенном виде

## 2. Входные данные

### 2.1 Источники онтологий
- `nlp/src/ontology/reference/ontologies.py` - эталонные онтологии
- 4 тестовые онтологии для предложений:
  1. `data/nlp/sentence1_1_expected_graph`
  2. `data/nlp/sentence2_1_expected_graph`
  3. `data/nlp/sentence3_1_expected_graph`
  4. `data/nlp/sentence4_1_expected_graph`

### 2.2 Структура онтологии
Онтология представлена в формате RDF графа с:
- Концептами (узлами)
- Семантическими связями (ребрами)
- Синтаксическими связями
- Онтологическими отношениями

## 3. Выходные данные

### 3.1 Формат карты знаний
- NetworkX DiGraph
- Узлы: блоки действий
- Ребра: зависимости между действиями
- Все ребра одного типа

### 3.2 Файлы вывода
```
data/knowledge_map/
├── sentence1_knowledge_map.gml
├── sentence1_knowledge_map.png
├── sentence2_knowledge_map.gml
├── sentence2_knowledge_map.png
├── sentence3_knowledge_map.gml
├── sentence3_knowledge_map.png
├── sentence4_knowledge_map.gml
├── sentence4_knowledge_map.png
└── combined_knowledge_map.gml
```

## 4. Алгоритм преобразования

### 4.1 Этап 1: Извлечение глаголов совершенного вида

#### 4.1.1 Идентификация глаголов
```python
def extract_verbs(ontology_graph):
    """Извлекает все глаголы из онтологии"""
    verbs = []
    for s, p, o in ontology_graph:
        # Проверяем что это глагол в совершенном виде
        if is_perfect_verb(s) or is_perfect_verb(o):
            verbs.append((s, p, o))
    return verbs
```

#### 4.1.2 Проверка формы глагола
```python
def is_perfect_verb(verb):
    """Проверяет что глагол в совершенном виде"""
    perfect_verbs = {
        'revealed', 'generated', 'influenced', 'increased', 
        'explored', 'proposed', 'organized', 'encouraged', 
        'adopted', 'improved'
    }
    return str(verb).split('#')[-1] in perfect_verbs
```

### 4.2 Этап 2: Формирование блоков действий

#### 4.2.1 Группировка по субъектам
```python
def group_by_subject(verbs):
    """Группирует глаголы по субъектам"""
    groups = {}
    for s, p, o in verbs:
        if s not in groups:
            groups[s] = []
        groups[s].append((s, p, o))
    return groups
```

#### 4.2.2 Создание блоков
```python
def create_action_blocks(verb_groups):
    """Создает блоки действий"""
    blocks = []
    for subject, verbs in verb_groups.items():
        # Ограничиваем 1-2 глаголами на блок
        if len(verbs) <= 2:
            blocks.append({
                'id': f"block_{len(blocks)}",
                'subject': subject,
                'verbs': verbs,
                'objects': extract_objects(verbs)
            })
    return blocks
```

### 4.3 Этап 3: Построение зависимостей

#### 4.3.1 Анализ семантических связей
```python
def build_dependencies(blocks, ontology_graph):
    """Строит зависимости между блоками"""
    dependencies = []
    for block1 in blocks:
        for block2 in blocks:
            if block1 != block2:
                if has_dependency(block1, block2, ontology_graph):
                    dependencies.append((block1['id'], block2['id']))
    return dependencies
```

#### 4.3.2 Проверка зависимости
```python
def has_dependency(block1, block2, ontology_graph):
    """Проверяет наличие зависимости между блоками"""
    # Проверяем семантические связи между элементами блоков
    for verb1 in block1['verbs']:
        for verb2 in block2['verbs']:
            if check_semantic_link(verb1, verb2, ontology_graph):
                return True
    return False
```

### 4.4 Этап 4: Валидация

#### 4.4.1 Проверка DAG
```python
def validate_dag(graph):
    """Проверяет что граф является DAG"""
    try:
        nx.algorithms.dag.topological_sort(graph)
        return True
    except nx.NetworkXError:
        return False
```

#### 4.4.2 Проверка глаголов
```python
def validate_verbs(blocks):
    """Проверяет что каждый блок содержит 1-2 глагола"""
    for block in blocks:
        verb_count = len(block['verbs'])
        if verb_count < 1 or verb_count > 2:
            return False
    return True
```

## 5. Интеграция с существующими компонентами

### 5.1 Использование существующих утилит
- `nlp/src/ontology/comparison/graph_comparison.py` для метрик
- `nlp/src/ontology/visualization/graph_viz.py` для визуализации

### 5.2 Совместимость с RDF
- Преобразование из RDF графа в NetworkX граф
- Сохранение семантической информации

## 6. Тестирование

### 6.1 Тестовые сценарии
1. Преобразование 4 эталонных онтологий
2. Валидация структуры карты знаний
3. Проверка метрик качества
4. Визуализация результатов

### 6.2 Метрики качества
- Precision: отношение корректных ребер к общему числу ребер
- Recall: отношение найденных корректных ребер к общему числу ожидаемых ребер
- F1-Score: гармоническое среднее Precision и Recall
- Node coverage: покрытие узлов

### 6.3 Формат тестов
```python
def test_ontology_to_knowledge_map():
    """Тест преобразования онтологии в карту знаний"""
    # Загрузка эталонной онтологии
    ontology = get_first_sentence_ontology()
    
    # Преобразование в карту знаний
    knowledge_map = builder.ontology_to_knowledge_map(ontology)
    
    # Валидация
    assert validate_dag(knowledge_map)
    assert validate_verbs(extract_blocks(knowledge_map))
    
    # Метрики
    metrics = compare_with_expected(knowledge_map, expected_map)
    assert metrics['f1_score'] >= 0.70
```

## 7. Обработка ошибок

### 7.1 Типы ошибок
1. Несовершенные глаголы в блоках
2. Циклы в графе
3. Некорректное количество глаголов в блоке
4. Дублирование связей

### 7.2 Обработка ошибок
```python
class KnowledgeMapError(Exception):
    """Базовый класс ошибок карты знаний"""
    pass

class InvalidVerbError(KnowledgeMapError):
    """Ошибка некорректного глагола"""
    pass

class CycleError(KnowledgeMapError):
    """Ошибка цикла в графе"""
    pass
```

## 8. Производительность

### 8.1 Оптимизация
- Кэширование результатов извлечения глаголов
- Использование эффективных структур данных
- Минимизация операций с графами

### 8.2 Масштабируемость
- Поддержка больших онтологий
- Потенциальное распараллеливание
- Оптимизация памяти

## 9. Расширяемость

### 9.1 Параметры конфигурации
```python
config = {
    'max_verbs_per_block': 2,
    'min_verbs_per_block': 1,
    'validate_dag': True,
    'output_formats': ['gml', 'png']
}
```

### 9.2 Плагины для расширения
- Дополнительные правила валидации
- Новые типы зависимостей
- Расширенные метрики

## 10. Документация

### 10.1 API документация
- Документация всех методов класса
- Примеры использования
- Описание параметров

### 10.2 Руководство пользователя
- Описание процесса преобразования
- Примеры входных и выходных данных
- Рекомендации по настройке