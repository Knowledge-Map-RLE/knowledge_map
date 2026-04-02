# Worker: Article to Knowledge Map

Пакетный воркер для автоматической обработки статей из PubMed Central.

## Запуск

Из папки воркера
```powershell
.\start.ps1
```

## Что делает

1. Ищет статьи в PMC по запросу (по умолчанию **"aging"**) через NCBI eSearch API
2. Для каждой статьи последовательно:
   - Загружает статью и конвертирует XML → Markdown
   - Запускает автоматическое аннотирование текста
   - Извлекает действия и причинно-следственные связи
   - Автоматически подтверждает/отклоняет связи по биомедицинским правилам
3. Сохраняет прогресс в Neo4j — при перезапуске продолжает с места остановки
4. Поднимает API статуса на порту **8004** — фронтенд показывает прогресс в реальном времени

По завершении все статьи доступны в интерфейсе в разделе «Загруженные документы», для каждой можно открыть вкладку «Карта статьи» с графом действий.

---

## Требования

- Python ≥ 3.12
- [Poetry](https://python-poetry.org/docs/#installation)
- Запущенные сервисы Knowledge Map:
  - Основной API (`api/`) на порту **8000**
  - NLP-сервис (`nlp/`) на порту **50055**
  - xml_to_md (`xml_to_md/`) на порту **50054**
  - Neo4j на порту **7687**

---

## Быстрый старт


Скрипт сам установит зависимости и запустит воркер.

После запуска:
- Прогресс виден в UI Knowledge Map (левая колонка → «Пакетная загрузка»)
- API статуса: http://localhost:8004/status

---

## Настройка через переменные окружения

Установите переменные **до** запуска `start.ps1`:

```powershell
$env:WORKER_QUERY          = "aging"      # поисковый запрос
$env:WORKER_TARGET_COUNT   = "1000"       # сколько статей обработать
$env:WORKER_BATCH_SIZE     = "3"          # сколько статей параллельно
$env:WORKER_API_URL        = "http://localhost:8000/api/data_extraction"
$env:NCBI_API_KEY          = ""           # ключ NCBI для повышенного лимита (10 req/s вместо 3)
$env:NEO4J_URI             = "bolt://127.0.0.1:7687"
$env:NEO4J_USER            = "neo4j"
$env:NEO4J_PASSWORD        = "password"
.\start.ps1
```

| Переменная | По умолчанию | Описание |
|---|---|---|
| `WORKER_QUERY` | `aging` | Поисковый запрос в PMC |
| `WORKER_TARGET_COUNT` | `1000` | Максимум статей за один запуск |
| `WORKER_BATCH_SIZE` | `3` | Параллельных статей (≥ 5 может перегрузить NLP-сервис) |
| `WORKER_API_URL` | `http://localhost:8000/api/data_extraction` | Адрес основного API |
| `WORKER_STATUS_PORT` | `8004` | Порт API статуса |
| `NCBI_API_KEY` | _(пусто)_ | [Ключ NCBI](https://www.ncbi.nlm.nih.gov/account/) для лимита 10 req/s |
| `WORKER_ANNOTATE_WAIT` | `30` | Секунд ожидания после запуска аннотирования |
| `WORKER_POLL_TIMEOUT` | `300` | Максимум секунд ожидания конвертации Markdown |
| `WORKER_MAX_RETRIES` | `3` | Попыток на статью при ошибках |
| `NEO4J_URI` | `bolt://127.0.0.1:7687` | Адрес Neo4j |
| `NEO4J_USER` | `neo4j` | Пользователь Neo4j |
| `NEO4J_PASSWORD` | `password` | Пароль Neo4j |

---

## API статуса (порт 8004)

Пока воркер работает, доступны эндпоинты:

```
GET /status           — сводная статистика (total, done, failed, percent, ...)
GET /status/details   — список всех статей с их текущим состоянием
GET /status/logs      — последние 100 строк лога воркера
GET /health           — проверка доступности
```

Пример ответа `/status`:

```json
{
  "run_id": "uuid...",
  "total": 1000,
  "done": 342,
  "failed": 5,
  "in_progress": 3,
  "pending": 650,
  "percent": 34.2,
  "status": "running",
  "started_at": "2026-03-30T10:00:00+00:00"
}
```

---

## Состояния обработки статьи

```
PENDING → INGESTING → AWAITING_MARKDOWN → ANNOTATING → EXTRACTING → REVIEWING → DONE
                                                                                   ↓
                                                                                FAILED
```

| Состояние | Описание |
|---|---|
| `pending` | В очереди, ещё не начато |
| `ingesting` | Загрузка из PMC, конвертация XML → Markdown |
| `awaiting_markdown` | Ожидание фоновой конвертации (если статья в PDF-формате) |
| `annotating` | Автоматическое аннотирование текста NLP-моделью |
| `extracting` | Извлечение глагольных действий и причинно-следственных связей |
| `reviewing` | Авто-подтверждение связей по биомедицинским правилам |
| `done` | Готово, карта знаний доступна |
| `failed` | Исчерпаны все попытки (см. `error_msg` в `/status/details`) |

---

## Возобновление после остановки

Состояние хранится в Neo4j. При повторном запуске воркер:
1. Ищет незавершённую сессию с тем же запросом
2. Пропускает статьи в состоянии `done`
3. Продолжает обработку остальных

Принудительно начать заново (игнорируя предыдущую сессию) — удалите узлы в Neo4j:

```cypher
MATCH (r:WorkerRun {query: "aging"}) DETACH DELETE r
MATCH (p:WorkerArticleProgress) DELETE p
```

---

## Лог-файл

Помимо вывода в консоль, воркер пишет лог в файл:

```
worker_article_to_knowledge_map/worker.log
```
