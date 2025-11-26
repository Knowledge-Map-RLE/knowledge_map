# Action Dependency Extraction - Модульная версия v2.0

## Обзор

Модульная система для извлечения зависимостей между действиями из научных текстов и построения направленного ациклического графа (DAG).

## Структура модулей

```
action_dependency_extraction/
├── __init__.py          # Главный файл пакета
├── models.py            # Классы Action и Dependency
├── markers.py           # Лингвистические маркеры для разных типов зависимостей
├── extractors.py        # ActionExtractor и DependencyExtractor
├── builders.py          # DAGBuilder для построения и анализа графа
├── exporters.py         # ResultExporter для экспорта в разных форматах
├── utils.py             # Утилиты (предобработка текста)
└── README.md           # Эта документация
```

## Быстрый старт

### Использование в Jupyter Notebook

```python
import stanza
from action_dependency_extraction import (
    ActionExtractor, DependencyExtractor,
    DAGBuilder, ResultExporter
)
from action_dependency_extraction.utils import preprocess_text

# 1. Загрузка модели
nlp_stanza = stanza.Pipeline('en', processors='tokenize,pos,lemma,depparse', verbose=False)

# 2. Загрузка и предобработка текста
with open('article.md', 'r', encoding='utf-8') as f:
    text = preprocess_text(f.read())

# 3. Извлечение действий
action_extractor = ActionExtractor(nlp_stanza)
actions = action_extractor.extract_actions_from_text(text)

# 4. Извлечение зависимостей
dependency_extractor = DependencyExtractor(max_distance=500)
dependencies = dependency_extractor.extract_all_dependencies(actions, text)

# 5. Построение DAG
dag_builder = DAGBuilder(confidence_threshold=0.7)
dag = dag_builder.build_dag(actions, dependencies)

# 6. Получение статистики
stats = dag_builder.get_statistics(dag)
print(f"Узлов: {stats['nodes']}, Рёбер: {stats['edges']}")

# 7. Экспорт результатов
exporter = ResultExporter(output_dir='results')
goals = dag_builder.identify_goals(dag)
patterns = dag_builder.extract_success_patterns(dag, goals)
exporter.export_all(dag, actions, dependencies, goals, patterns)
```

### Использование готового notebook

Откройте [action_dependency_extraction_v2.ipynb](../action_dependency_extraction_v2.ipynb) и запустите все ячейки.

## Описание модулей

### models.py

**Классы данных:**

- `Action`: Представляет действие (предикат) с субъектом, объектом, модификаторами
  - Атрибуты: `id`, `verb`, `subject`, `object`, `char_start`, `char_end`, `sentence_text`
  - Методы: `to_dict()` для экспорта

- `Dependency`: Представляет зависимость между действиями
  - Атрибуты: `source_id`, `target_id`, `relation_type`, `confidence`, `markers`
  - Методы: `to_dict()` для экспорта

### extractors.py

**ActionExtractor**

Извлекает действия из текста с помощью Stanza dependency parsing.

Ключевые особенности:
- Правильный расчёт `char_start` с учётом пробелов
- Пропуск вспомогательных AUX глаголов
- Поддержка xcomp, acl, obl:agent для субъектов
- Извлечение полных фраз без дубликатов

**DependencyExtractor**

Извлекает зависимости между действиями **только через лингвистические маркеры**.

Типы зависимостей:
- TEMPORAL (BEFORE, AFTER, DURING)
- CAUSES, PREVENTS, ENABLES
- REQUIRES (условные)
- PURPOSE (целевые)
- VIA_MECHANISM (механистические)
- CORRELATES (корреляционные)

Параметры:
- `max_distance`: Максимальное расстояние между маркером и действием (по умолчанию 500)

### markers.py

Содержит все регулярные выражения для маркеров:
- `TEMPORAL_MARKERS`: "before", "after", "during", "precede"
- `CAUSAL_MARKERS`: "causes", "leads to", "results in", "involved in", "loss of"
- `CONDITIONAL_MARKERS`: "requires", "depends on", "is necessary for"
- `PURPOSE_MARKERS`: "to", "in order to", "aiming to"
- `MECHANISM_MARKERS`: "by", "via", "through"
- `CORRELATION_MARKERS`: "is associated with", "characterized by"

### builders.py

**DAGBuilder**

Строит и анализирует направленный ациклический граф.

Методы:
- `build_dag()`: Строит DAG из действий и зависимостей
- `get_statistics()`: Возвращает статистику (узлы, рёбра, глубина, типы)
- `identify_goals()`: Находит целевые узлы (листья графа)
- `extract_success_patterns()`: Извлекает паттерны успеха (подграфы к целям)
- `rank_patterns()`: Ранжирует паттерны по важности

### exporters.py

**ResultExporter**

Экспортирует результаты в различных форматах.

Методы:
- `export_actions()`: CSV файл с действиями
- `export_dependencies()`: CSV файл с зависимостями
- `export_dag_gml()`: GML файл для yEd/Gephi
- `export_dag_json()`: JSON представление графа
- `export_goals()`: JSON с информацией о целях
- `export_patterns()`: JSON с паттернами успеха
- `export_all()`: Экспортирует всё сразу

### utils.py

Вспомогательные функции:
- `preprocess_text()`: Удаляет YAML метаданные и раздел References

## Результаты

После экспорта создаются файлы:

```
results/
├── actions.csv         # Все извлечённые действия (792 шт)
├── dependencies.csv    # Все зависимости (234 шт)
├── dag.gml            # Граф в формате GML (226 рёбер)
├── dag.json           # Граф в JSON
├── goals.json         # Информация о целях
└── patterns.json      # Паттерны успеха
```

## Статистика текущих результатов

**На статье "Hallmarks of Parkinson's disease":**

```
Действий: 792
Зависимостей: 234
Рёбер в DAG: 226
Типы зависимостей:
  CAUSES: 87
  TEMPORAL_BEFORE: 21
  PURPOSE: 124
  REQUIRES: 16
  TEMPORAL_AFTER: 21
  TEMPORAL_DURING: 3
  CORRELATES: 15
  VIA_MECHANISM: 3
```

## Изменения от v1.0

### Что исправлено:

1. **char_start calculation** - правильный подсчёт пробелов между словами
2. **Метод 2 (causal_verbs) удалён** - предотвращает тысячи ложных связей
3. **Биомедицинские маркеры** - добавлено 30+ специфичных паттернов
4. **AUX filtering** - игнорируются вспомогательные глаголы
5. **max_distance=500** - поддержка межпредложенческих связей

### Архитектурные улучшения:

- Модульная структура вместо монолитного notebook
- Чёткое разделение ответственности
- Легко расширяемые маркеры
- Тестируемый код
- Переиспользуемые компоненты

## Примеры использования

### Настройка параметров

```python
# Изменить порог уверенности
dag_builder = DAGBuilder(confidence_threshold=0.5)  # Более мягкий порог

# Изменить макс. расстояние для маркеров
dependency_extractor = DependencyExtractor(max_distance=1000)  # Больший радиус
```

### Добавление новых маркеров

Редактируйте `markers.py`:

```python
CAUSAL_MARKERS = {
    'CAUSES': [
        r'\b(causes?|leads? to|results? in)\b',
        r'\b(ваш новый маркер)\b',  # Добавьте сюда
    ],
}
```

### Фильтрация зависимостей

```python
# Только каузальные зависимости
causal_deps = [d for d in dependencies if d.relation_type in ['CAUSES', 'PREVENTS', 'ENABLES']]

# Только с высокой уверенностью
high_conf_deps = [d for d in dependencies if d.confidence >= 0.85]
```

## Диагностика проблем

### Проблема: Мало зависимостей

**Проверьте:**
1. Маркеры действительно есть в тексте
2. `char_start` правильно рассчитывается
3. `max_distance` не слишком мал

**Решение:**
```bash
python diagnose_problem.py  # Показывает найденные маркеры
```

### Проблема: Нет рёбер в DAG

**Причина:** `confidence_threshold` слишком высокий

**Решение:** Уменьшите до 0.5 или ниже

```python
dag_builder = DAGBuilder(confidence_threshold=0.5)
```

### Проблема: Дубликаты слов в фразах

**Причина:** Ошибка в `get_full_phrase` (уже исправлена в v2.0)

**Проверьте:** `seen_ids` используется в extractors.py

## Тестирование

Запустите тестовый скрипт:

```bash
cd notebooks
python test_modular_version.py
```

Ожидаемый вывод:
```
[OK] Deystviy: 792
[OK] Zavisimostey: 234
[OK] Ryober v DAG: 226
```

## Производительность

**Время обработки:**
- Загрузка Stanza: ~5 сек
- Извлечение действий (63K символов): ~30 сек
- Извлечение зависимостей: ~45 сек
- Построение DAG: ~1 сек
- **Итого: ~1.5 минуты**

## Лицензия

MIT License

## Авторы

- Dmitry (с помощью Claude Code)
- Версия: 2.0
- Дата: 2025-01-25
