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

ghcr.io/knowledge-map-rle/knowledge_map/api:latest
ghcr.io/knowledge-map-rle/knowledge_map/client:latest