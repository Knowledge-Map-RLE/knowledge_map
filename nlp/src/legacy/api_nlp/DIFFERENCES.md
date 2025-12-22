# Различия между версиями файлов из api/nlp и nlp/src

Этот документ описывает основные различия между версиями файлов, сохраненными из `api/nlp` и текущими версиями в `nlp/src`.

## Общие различия

### Импорты

**api/nlp версии** используют относительные импорты:
```python
from .base import ...
from .adapters import ...
```

**nlp/src версии** используют абсолютные импорты:
```python
from src.base import ...
from src.adapters import ...
```

Это связано с разной структурой пакетов:
- В `api/nlp` файлы находятся в пакете `nlp`, поэтому используются относительные импорты
- В `nlp/src` файлы находятся в пакете `src`, поэтому используются абсолютные импорты с префиксом `src.`

## Файлы с различиями (19 файлов)

### Основные модули
- `nlp_manager.py` - различия в импортах (`.base` vs `src.base`)
- `multilevel_analyzer.py` - различия в импортах

### Адаптеры (adapters/)
- `__init__.py` - различия в импортах
- `base_adapter.py` - различия в импортах
- `nltk_adapter.py` - различия в импортах
- `spacy_adapter.py` - различия в импортах
- `stanza_adapter.py` - различия в импортах
- `udpipe_adapter.py` - различия в импортах

### Мапперы (mappers/)
- `__init__.py` - различия в импортах
- `spacy_mapper.py` - различия в импортах

### Процессоры (processors/)
- `__init__.py` - различия в импортах
- `base.py` - различия в импортах
- `level1_tokenization_processor.py` - различия в импортах
- `level2_morphology_processor.py` - различия в импортах
- `level3_syntax_processor.py` - различия в импортах
- `spacy_processor.py` - различия в импортах
- `stanza_processors.py` - различия в импортах

### Voting (voting/)
- `__init__.py` - различия в импортах
- `voting_engine.py` - различия в импортах

## Идентичные файлы (6 файлов)

Эти файлы полностью идентичны и были удалены из `api/nlp`:
- `__init__.py`
- `base.py`
- `unified_types.py`
- `adapters/universal_dependencies_mapper.py`
- `voting/agreement_calculator.py`
- `voting/confidence_aggregator.py`

## Уникальные файлы

### Только в nlp/src (8 файлов)
Эти файлы существуют только в `nlp/src` и не имеют аналогов в `api/nlp`:
- `config.py` - конфигурация NLP сервиса
- `grpc_server.py` - gRPC сервер
- `main.py` - точка входа
- `morphemic/__init__.py` - морфологический анализ
- `morphemic/tihonov_dictorinary_parser.py` - парсер словаря Тихонова
- `morphological_analysis.py` - морфологический анализ
- `nlp_pb2.py` - сгенерированные proto файлы
- `nlp_pb2_grpc.py` - сгенерированные proto файлы

### Только в api/nlp (0 файлов)
Нет уникальных файлов в `api/nlp`.

## Примечания

Все различия связаны с разной структурой пакетов и импортов. Функциональность файлов идентична, различается только способ импорта модулей.

Версия из `nlp/src` является основной и используется в микросервисе. Версии из `api/nlp` сохранены здесь для справки и возможного восстановления, если потребуется.

