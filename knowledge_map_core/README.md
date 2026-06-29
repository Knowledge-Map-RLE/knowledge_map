# Knowledge Language Parser

Детерминированный Rule-based движок извлечения знаний из научных текстов на английском языке. Является частью микросервиса `knowledge_map_core`.

## Архитектура

```
Text → NLP gRPC (spaCy) → DependencyTree → RuleEngine → Statement[] → Neo4j
                                   ↑                        ↓
                               LLM (ai gRPC) ←──── MetaBuilder
```

### Компоненты

| Модуль | Назначение |
|--------|-----------|
| `parser/` | gRPC клиент к сервису nlp (spaCy dependency trees) |
| `extractor/` | Rule engine с набором правил извлечения |
| `normalizer/` | Приведение концептов к каноническому виду |
| `meta/` | Построение мета-утверждений (связи между фактами) |
| `llm/` | gRPC клиент к сервису ai для LLM-достройки |
| `validator/` | Проверка корректности графа |
| `serializer/` | Statement → ProtoBuf / JSON |
| `neo4j/` | Запись графа в Neo4j |

## Формат "Языка Знаний"

Утверждение (Statement) — атомарная единица знания:

```
Concept → Predicate → Concept | Statement | Literal
```

Типы утверждений:
- **FACT (F)** — атомарный факт: `дофамин → является → нейромедиатором`
- **META (M)** — мета-утверждение (связь между фактами)

Идентификаторы: UUIDv7 (время-упорядоченный) с раздельным полем `type: FACT | META`.

## Правила извлечения

Каждое правило — отдельный класс с единым интерфейсом `BaseRule`:

| Правило | Языковая конструкция | UD-паттерн |
|---------|---------------------|------------|
| `CopularRule` | X is Y | `cop` + `nsubj` |
| `PassiveVoiceRule` | X was discovered by Y | `nsubj:pass` + `aux:pass` |
| `ActiveVoiceRule` | X influences Y | `nsubj` + `obj` |
| `CoordinationRule` | X and Y | `conj` + `cc` |
| `NegationRule` | X is not Y | `neg` |
| `CausalRule` | X causes Y | causal verbs + `advcl` |
| `TemporalRule` | X before Y | temporal markers |
| `RelativeClauseRule` | X, which is Y | `relcl` |

## Добавление нового правила

1. Создать класс в `src/extractor/rules/`, унаследовать от `BaseRule`
2. Реализовать `name`, `matches()`, `extract()`
3. Зарегистрировать в `src/extractor/rules/__init__.py`
4. Написать unit test

```python
from src.extractor.rules.base import BaseRule

class MyRule(BaseRule):
    @property
    def name(self) -> str:
        return "my_rule"

    def matches(self, tree: DependencyTree) -> bool:
        return len(tree.find_by_dep("my_dep")) > 0

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        ...
```

## Пайплайн обработки

1. Текст → **NLP gRPC** → `UnifiedDocument` (sentences, tokens, dependencies)
2. Каждое предложение → `DependencyTree`
3. **RuleEngine** → все подходящие правила → `Statement[]`
4. **Normalizer** → лемматизация концептов
5. **MetaBuilder** → M-утверждения между фактами
6. **(optional) LLM** → достройка неоднозначных мета-связей
7. **Validator** → проверка графа
8. **Neo4jWriter** → запись в Neo4j

## Тестовые данные

Используются реальные научные статьи из `data/articles/`:
- "Hallmarks of cancer and hallmarks of aging"
- "The hallmarks of Parkinson's disease"

## Запуск

```powershell
.\start.ps1  # gRPC сервер на порту 50056
```

## gRPC API

```protobuf
service KnowledgeLanguageService {
    rpc ProcessText(ProcessTextRequest) returns (KnowledgeGraphResponse);
    rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}
```
