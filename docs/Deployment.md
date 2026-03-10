# Деплой Knowledge Map: Railway + GitHub Actions

## Архитектура

```
GitHub (исходный код)
  ↓ git tag v1.0.0
GitHub Actions
  ├── Сборка Docker образов → ghcr.io (GitHub Container Registry)
  └── Деплой через Railway GraphQL API
        ├── api     → Railway Service (FastAPI)
        └── client  → Railway Service (React + Nginx)

Внешние сервисы:
  ├── Neo4j AuraDB Free  (база данных)
  └── Railway Buckets    (S3-совместимое хранилище файлов)
```

**Деплой запускается только при создании git тега** вида `v*` (например `v1.0.0`), не при каждом пуше.

---

## GitHub Secrets

Все секреты хранятся в GitHub репозитории: **Settings → Secrets and variables → Actions**.

| Секрет | Описание | Где взять |
|--------|----------|-----------|
| `RAILWAY_API_TOKEN` | Токен аккаунта Railway | Railway → аватар (левый низ) → Account Settings → Tokens → Create Token |
| `RAILWAY_PROJECT_ID` | ID проекта Railway | Railway → проект → Settings → Project ID |
| `RAILWAY_ENVIRONMENT_ID` | ID окружения (production) | Railway → проект → окружение → Settings → Environment ID |
| `RAILWAY_API_SERVICE_ID` | ID сервиса `api` | Railway → сервис api → Settings → Service ID |
| `RAILWAY_CLIENT_SERVICE_ID` | ID сервиса `client` | Railway → сервис client → Settings → Service ID |

`GITHUB_TOKEN` создаётся автоматически — его создавать не нужно.

---

## Railway: структура проекта

Проект на Railway содержит:
- **Storage Bucket** — Railway Buckets (S3-совместимый, на базе Tigris). Credentials автоматически доступны через reference variables.
- **Service `api`** — FastAPI, Docker Image из ghcr.io
- **Service `client`** — React + Nginx, Docker Image из ghcr.io

### Переменные сервиса `api`

| Переменная | Значение |
|------------|----------|
| `NEO4J_URI` | `neo4j+s://xxxx.databases.neo4j.io` (из AuraDB) |
| `NEO4J_USER` | `neo4j` |
| `NEO4J_PASSWORD` | (из AuraDB) |
| `S3_ENDPOINT_URL` | `${{bucket.BUCKET_ENDPOINT}}` |
| `S3_ACCESS_KEY` | `${{bucket.BUCKET_ACCESS_KEY_ID}}` |
| `S3_SECRET_KEY` | `${{bucket.BUCKET_SECRET_ACCESS_KEY}}` |
| `S3_BUCKET_NAME` | `${{bucket.BUCKET_NAME}}` |
| `DEBUG` | `false` |
| `ALLOWED_ORIGINS` | URL клиента на Railway (например `https://client.up.railway.app`) |
| `IMAGE_TAG` | `latest` (обновляется автоматически при деплое) |

### Переменные сервиса `client`

| Переменная | Значение |
|------------|----------|
| `API_HOST` | `api.railway.internal` (внутренний hostname сервиса api) |

---

## Neo4j AuraDB Free

1. Создать аккаунт на https://console.neo4j.io
2. **New Instance → AuraDB Free** → выбрать регион US East 1
3. После создания появится окно с credentials — скачать `.txt` файл **немедленно** (показывается один раз)
4. Из файла взять:
   - `NEO4J_URI` → в Railway переменные сервиса `api` как `NEO4J_URI`
   - `NEO4J_USERNAME` → как `NEO4J_USER`
   - `NEO4J_PASSWORD` → как `NEO4J_PASSWORD`

> ⚠️ AuraDB Free паузируется через 72 часа без активности.
> Если пароль потерян — сбросить через кнопку **Reset Password** на странице инстанса.

---

## Как сделать деплой

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions запустится автоматически. Прогресс виден во вкладке **Actions** репозитория.

---

## Правки в коде для совместимости с продакшном

### 1. `api/services/config.py` — поддержка AuraDB URI

AuraDB использует схему `neo4j+s://` вместо `bolt://`. Метод `get_database_url()` исправлен для поддержки всех схем:

```python
def get_database_url(self) -> str:
    uri = self.NEO4J_URI
    for scheme in ("bolt+s", "neo4j+s", "neo4j", "bolt"):
        prefix = f"{scheme}://"
        if uri.startswith(prefix):
            hostport = uri[len(prefix):]
            return f"{scheme}://{self.NEO4J_USER}:{self.NEO4J_PASSWORD}@{hostport}"
    return uri
```

### 2. `api/src/app.py` — TLS только для локального Neo4j

AuraDB требует TLS — `ENCRYPTED = False` нельзя применять глобально:

```python
if not settings.NEO4J_URI.startswith(("bolt+s://", "neo4j+s://")):
    neomodel_config.ENCRYPTED = False
```

### 3. `api/src/middleware.py` — CORS origins из env

Добавлена поддержка `ALLOWED_ORIGINS` через переменную окружения:

```python
_extra_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
ORIGINS = _extra_origins + ["http://localhost:5173", ...]
```

### 4. `client/nginx.conf` — API hostname через env

```nginx
location /api/ {
    proxy_pass http://${API_HOST}:8000/;
    ...
}
```

### 5. `client/Dockerfile` — envsubst для nginx

Файл `nginx.conf` помещён в `/etc/nginx/templates/` — nginx автоматически применяет `envsubst` при старте:

```dockerfile
COPY nginx.conf /etc/nginx/templates/default.conf.template
```

### 6. `api/Dockerfile` — nlp.proto в контексте сборки

Docker не имеет доступа к файлам вне своего build context. `nlp.proto` скопирован в `api/utils/proto/`:

```dockerfile
# Было: -I../nlp/proto  и  ../nlp/proto/nlp.proto  — не работает вне контекста
# Стало:
RUN python -m grpc_tools.protoc \
    -I./utils/proto \
    --python_out=./utils/generated \
    --grpc_python_out=./utils/generated \
    ./utils/proto/layout.proto \
    ./utils/proto/auth.proto \
    ./utils/proto/nlp.proto
```

---

## Как работает GitHub Actions workflow

Файл: `.github/workflows/deploy.yml`

### Job 1: `build-and-push`

1. Извлекает тег из `GITHUB_REF` и приводит имя репозитория к lowercase (Docker требует lowercase)
2. Логинится в ghcr.io через `GITHUB_TOKEN`
3. Собирает образы `api` и `client` с Docker layer cache (через GitHub Actions Cache)
4. Пушит образы с двумя тегами: версионным (`v1.0.0`) и `latest`

### Job 2: `deploy`

Использует Railway GraphQL API напрямую через `curl` — надёжнее CLI (см. ниже историю проблем).

Для каждого сервиса:
1. Устанавливает переменную `IMAGE_TAG` через `variableUpsert` mutation
2. Перезапускает сервис через `serviceInstanceRedeploy` mutation

```bash
curl --request POST \
  --url https://backboard.railway.com/graphql/v2 \
  --header "Authorization: Bearer $RAILWAY_API_TOKEN" \
  --header "Content-Type: application/json" \
  --data '{"query":"mutation { variableUpsert(input: { ... }) }"}'
```

---

## История проблем с Railway CLI (для справки)

В процессе настройки Railway CLI (`@railway/cli`) давал несовместимые ошибки из-за частых изменений API CLI:

| Команда | Ошибка |
|---------|--------|
| `railway variables --project ID --service api set KEY=VAL` | `unexpected argument '--project'` |
| `railway variable set KEY=VAL --project-id ID --service api` | `unexpected argument '--project-id'` |
| `railway variable set KEY=VAL --yes` | `unexpected argument '--yes'` |
| `railway variable set KEY=VAL` с `RAILWAY_PROJECT_ID` в env | `No linked project found` |
| С правильным `RAILWAY_API_TOKEN` вместо `RAILWAY_TOKEN` | Работает, но проект не линкован |

**Итог:** Railway CLI плохо подходит для CI/CD без интерактивного `railway link`. Прямые вызовы GraphQL API через `curl` — единственный надёжный способ.

### Разница между токенами Railway

| Переменная | Тип токена | Где создаётся |
|------------|-----------|---------------|
| `RAILWAY_TOKEN` | Project token | В настройках конкретного проекта |
| `RAILWAY_API_TOKEN` | Account token | Account Settings → Tokens |

Для CI/CD нужен `RAILWAY_API_TOKEN` (account token).

---

## Стоимость

| Ресурс | Стоимость |
|--------|-----------|
| Railway Hobby план | $5/мес (включает $5 кредитов) |
| api + client (малая нагрузка) | ~$1-3/мес (в пределах кредитов) |
| Railway Buckets | $0.015/GB-мес, API операции бесплатны |
| Neo4j AuraDB Free | $0 |
| GitHub Actions (публичный репо) | $0 |
| ghcr.io (публичный репо) | $0 |
| **Итого** | **~$5/мес** |


**Финальные образы:**
- `ghcr.io/knowledge-map-rle/knowledge_map/api:latest`
- `ghcr.io/knowledge-map-rle/knowledge_map/client:latest`

---

## Проблемы, возникшие при первом деплое, и их решения

### 1. Строчные буквы в имени Docker образа

**Ошибка:** `invalid tag: repository name must be lowercase`

**Причина:** `github.repository` возвращает `Knowledge-Map-RLE/knowledge_map` с заглавными буквами, Docker требует lowercase.

**Решение** в `.github/workflows/deploy.yml`:
```yaml
- name: Extract tag name and repo
  id: tag
  run: |
    echo "tag=${GITHUB_REF#refs/tags/}" >> $GITHUB_OUTPUT
    echo "repo=${GITHUB_REPOSITORY,,}" >> $GITHUB_OUTPUT  # ,, = lowercase
```

### 2. Dockerfile: nlp.proto вне build context

**Ошибка:** `failed to solve: process grpc_tools.protoc ... exit code: 1`

**Причина:** Dockerfile API пытался скомпилировать `../nlp/proto/nlp.proto` — файл за пределами Docker build context (`./api`).

**Решение:** скопировать `nlp.proto` внутрь контекста и исправить Dockerfile:
```bash
cp nlp/proto/nlp.proto api/utils/proto/nlp.proto
```
```dockerfile
# Было: -I../nlp/proto  и  ../nlp/proto/nlp.proto
# Стало:
RUN python -m grpc_tools.protoc \
    -I./utils/proto \
    --python_out=./utils/generated \
    --grpc_python_out=./utils/generated \
    ./utils/proto/layout.proto \
    ./utils/proto/auth.proto \
    ./utils/proto/nlp.proto
```

### 3. Railway CLI — несовместимый синтаксис

**Проблема:** Railway CLI (`@railway/cli`) менял API между версиями. Последовательно не работали варианты:
- `railway variables --project ID --service api set KEY=VAL` → `unexpected argument '--project'`
- `railway variable set KEY=VAL --project-id ID` → `unexpected argument '--project-id'`
- `railway variable set KEY=VAL --yes` → `unexpected argument '--yes'`
- `railway variable set KEY=VAL` с `RAILWAY_PROJECT_ID` в env → `No linked project found`

**Решение:** отказаться от CLI, использовать Railway GraphQL API напрямую через `curl` (см. раздел "Как работает GitHub Actions workflow").

### 4. Токен Railway: RAILWAY_TOKEN vs RAILWAY_API_TOKEN

**Проблема:** `Invalid RAILWAY_TOKEN`

**Причина:** Railway различает два типа токенов:
- `RAILWAY_TOKEN` — Project token (ограничен одним проектом, создаётся внутри проекта)
- `RAILWAY_API_TOKEN` — Account token (создаётся в Account Settings → Tokens)

Для CI/CD нужен `RAILWAY_API_TOKEN`.

### 5. Пакеты ghcr.io приватные по умолчанию

**Ошибка Railway:** `We were unable to connect to the registry for this image`

**Причина:** Пакеты GitHub Container Registry для организаций по умолчанию приватные. Опция сделать их публичными была отключена администратором организации.

**Решение:** Разрешить публикацию публичных пакетов в настройках организации:
- GitHub → Organization Settings → Packages → Package Creation → разрешить Public
- Затем для каждого пакета: Package Settings → Change visibility → Public

### 6. ImportError: attempted relative import with no known parent package

**Ошибка:** `from . import nlp_pb2 as nlp__pb2 — ImportError: attempted relative import with no known parent package`

**Причина:** В `services/nlp_grpc_client.py` использовался `sys.path.append` для добавления `utils/generated` в путь поиска модулей, затем `import nlp_pb2_grpc` напрямую. При таком способе Python загружает файл вне пакета, и относительный импорт `from . import` внутри него падает.

**Решение:** заменить `sys.path` хак на пакетный импорт во всех gRPC клиентах:
```python
# Было:
sys.path.append(str(Path(__file__).parent.parent / "utils" / "generated"))
import nlp_pb2
import nlp_pb2_grpc

# Стало:
from utils.generated import nlp_pb2, nlp_pb2_grpc
```

Исправлено в: `services/nlp_grpc_client.py`, `services/pdf_to_md_grpc_client.py`, `services/annotation_service.py`.

### 7. Отсутствующая зависимость PyYAML

**Ошибка:** `ModuleNotFoundError: No module named 'yaml'`

**Причина:** `pyyaml` использовался в `src/routers/data_extraction/csv_export.py` но не был указан в `pyproject.toml`.

**Решение:** добавить в `api/pyproject.toml`:
```toml
pyyaml = "^6.0"
```

### 8. Private Networking не был включён

**Симптом:** `504 Gateway Timeout` при запросах через nginx.

**Причина:** Railway Private Networking (внутренняя сеть между сервисами) не включён по умолчанию. Без него `api.railway.internal` не резолвится.

**Решение:** Сервис `api` → Settings → Networking → нажать **Enable Private Networking**.

После этого в Variables сервиса `client` указать:
```
API_HOST=api
```
(Railway рекомендует короткое имя сервиса, а не `api.railway.internal`)

### 9. nginx proxy_pass обрезал /api/ префикс

**Симптом:** `404 Not Found` на всех `/api/...` запросах.

**Причина:** В nginx, если `proxy_pass` содержит URI с `/` в конце (`http://host:8000/`), nginx заменяет `location` prefix на этот URI. Запрос `/api/data_extraction/documents` превращался в `/data_extraction/documents`, но API ожидал полный путь `/api/data_extraction/documents`.

**Решение:** убрать `/` в конце `proxy_pass`:
```nginx
# Было (обрезало /api/):
proxy_pass http://${API_HOST}:8000/;

# Стало (передаёт путь как есть):
proxy_pass http://${API_HOST}:8000;
```

---

## Итоговые переменные окружения сервиса `api` на Railway

| Переменная | Значение |
|-----------|---------|
| `NEO4J_URI` | `neo4j+s://xxxx.databases.neo4j.io` |
| `NEO4J_USER` | `neo4j` |
| `NEO4J_PASSWORD` | (из AuraDB) |
| `S3_ENDPOINT_URL` | `${{S3.BUCKET_ENDPOINT}}` |
| `S3_ACCESS_KEY` | `${{S3.BUCKET_ACCESS_KEY_ID}}` |
| `S3_SECRET_KEY` | `${{S3.BUCKET_SECRET_ACCESS_KEY}}` |
| `S3_BUCKET_NAME` | `${{S3.BUCKET_NAME}}` |
| `DEBUG` | `false` |
| `ALLOWED_ORIGINS` | `https://client-production-xxx.up.railway.app` |
| `NCBI_EMAIL` | email для NCBI API |
| `NCBI_TOOL_NAME` | `KnowledgeMap` |
| `NCBI_API_KEY` | ключ NCBI (опционально) |

## Итоговые переменные окружения сервиса `client` на Railway

| Переменная | Значение |
|-----------|---------|
| `API_HOST` | `api` |
| `PORT` | `80` |