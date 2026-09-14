# Деплой Knowledge Map: cloud.ru Kubernetes + GitHub Actions

## Архитектура

```
GitHub (исходный код)
  ↓ git tag v1.0.0
GitHub Actions
  ├── Сборка 9 Docker образов (для всех сервисов, используют additional_contexts shared)
  ├── Push в cloud.ru Artifact Registry     <name>.cr.cloud.ru/km/<service>:<tag>
  ├── Рендер манифестов (kubectl kustomize deploy/k8s/overlays/prod)
  └── kubectl apply в cloud.ru Managed Kubernetes
```

Внешние сервисы:
- **neo4j, qdrant, minio (dev)** — внутри кластера (StatefulSet + PVC)
- **Object Storage** (`s3.cloud.ru`, бакет `km-storage`) — вместо MinIO в production
- **cloud.ru Foundation Models, ЮKassa, OpenAlex, OpenCitations, Crossref, DataCite, NCBI/PubMed** — внешние API

**Деплой запускается только при создании git тега** `v*` (например `v1.0.0`).

---

## Структура манифестов

```
deploy/k8s/
  base/                      # Базовые манифесты (Namespace, ConfigMaps, Secrets, StatefulSet/Deployment/Service)
  overlays/
    dev/                     # Локальная разработка на k3d (MinIO, мягкие лимиты)
    prod/                    # cloud.ru production (Object Storage, replicas: 2, жёсткие лимиты)
  optional/
    observability/           # (не входит в prod по умолчанию) Loki/Prometheus/Alloy/Grafana
```

- `base/secret-template.yaml` — шаблон с заглушками `REPLACE_ME`, не деплоится напрямую
- `overlays/prod/secrets.env` — генерируется в CI из GitHub Secrets (в git не хранится!)

### Порты сервисов внутри кластера

| Сервис | Порт / протокол | Service name |
|--------|-----------------|--------------|
| neo4j | 7687 bolt / 7474 http | `neo4j` |
| qdrant | 6333 http / 6334 gRPC | `qdrant` |
| api | 8000 http | `api` |
| auth | 50057 gRPC | `auth` |
| billing | 50058 gRPC | `billing` |
| ai | 50059 http | `ai` |
| nlp | 50055 gRPC | `nlp` |
| layout | 50051 gRPC | `layout` |
| knowledge_map_core | 50056 gRPC | `knowledge-map-core` |
| pdf_to_md | 8002 http / 50053 gRPC | `pdf-to-md` |
| client | 80 http (LoadBalancer) | `client` |

---

## GitHub Secrets

Все секреты в: **Settings → Secrets and variables → Actions**.

| Секрет | Описание |
|--------|----------|
| `NEO4J_PASSWORD` | Пароль Neo4j |
| `SECRET_KEY` | JWT-секрет auth-сервиса |
| `INTERNAL_TOKEN` | Токен межсервисных вызовов api → billing |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Ключи Object Storage cloud.ru |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | ЮKassa |
| `CLOUDRU_API_KEY` | cloud.ru Foundation Models API ключ |
| `OPENALEX_API_KEY` | OpenAlex |
| `OPENCITATIONS_ACCESS_TOKEN` | OpenCitations |
| `NCBI_API_KEY` | NCBI/PubMed |
| `HUGGING_FACE_TOKEN` | HuggingFace Hub (скачивание моделей) |
| `CLOUDRU_REGISTRY_NAME` | Имя реестра cloud.ru (без домена; пусто → fallback на ghcr.io) |
| `CLOUDRU_KEY_ID` / `CLOUDRU_SECRET_ID` | Статические ключи доступа cloud.ru для Artifact Registry |
| `CLOUDRU_KUBECONFIG_B64` | kubeconfig кластера Managed Kubernetes (base64) |
| `DRY_RUN` | `true` — манифесты рендерятся, деплой не выполняется |

---

## Первичная настройка production (однократно)

### 1. Artifact Registry
Создать реестр на cloud.ru, получить имя типа `km-images`. В CI укажется
`CLOUDRU_REGISTRY_NAME=km-images`, образы будут в `km-images.cr.cloud.ru/km/<service>`. Логин: `CLOUDRU_KEY_ID`/`CLOUDRU_SECRET_ID` (static access keys).

### 2. Managed Kubernetes
Создать кластер с нод-группой **минимум 16 vCPU / 32 GB RAM** (одна нода `s2.medium`-типа —
Neo4j один занимает 8 GB heap + pagecache; маленькие ноды 2vCPU/4GB бесполезны).

```bash
# Скачать kubeconfig из консоли cloud.ru, затем:
$kubeconfig = Get-Content kubeconfig.yaml -Raw
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($kubeconfig)) | clip
```
Вставить результат в `CLOUDRU_KUBECONFIG_B64`.

### 3. Object Storage
Создать бакет `km-storage` в Object Storage cloud.ru. Выдать пользователю статический ключ
(`S3_ACCESS_KEY`/`S3_SECRET_KEY`). Регион и endpoint уже заданы в `overlays/prod/config-common-patch.yaml`.

### 4. GitHub Secrets
Заполнить все значения из таблицы выше. Пока не всё готово — установить `DRY_RUN=true`.

---

## Как сделать деплой

```bash
git tag v1.0.0
git push origin v1.0.0
```

1. **build** — параллельная сборка 9 образов (`api`, `auth`, `ai`, `nlp`, `billing`, `laying`,
   `knowledge_map_core`, `pdf_to_md`, `client`), push в реестр с тегами `<tag>` и `latest`,
   Docker layer cache через GitHub Actions Cache (scope на сервис).
2. **deploy** — подтягивает секреты в `secrets.env` (`prepare-secrets.sh`), рендерит
   `kubectl kustomize overlays/prod`, проверяет `rollout status`.

### DRY_RUN (этап внедрения)

Пока `DRY_RUN=true` или `CLOUDRU_KUBECONFIG_B64` пуст — workflow рендерит манифесты,
но в кластер ничего не применяет. Это позволяет проверить сборку и рендер до реального деплоя.

---

## Локальная проверка перед деплоем (k3d)

```bash
deploy/scripts/k3d-up.sh     # создаёт кластер, собирает образы, деплоит dev-overlay
# Доступ: http://localhost:30080 (client), nginx → api → Neo4j/MinIO внутри
deploy/scripts/k3d-down.sh   # удалить кластер
```

Независимо от k3d/cloud.ru, дневная разработка остаётся на `docker compose up`.

---

## Применение вручную (без CI)

```bash
# Заполнить deploy/k8s/overlays/prod/secrets.env реальными значениями
deploy/scripts/apply-prod.sh
```

---

## Основные изменённые решения vs Railway

| Было (Railway) | Стало (cloud.ru Kubernetes) |
|----------------|------------------------------|
| ghcr.io + Railway Services | Artifact Registry + Managed Kubernetes |
| AuraDB Free | Neo4j StatefulSet с PVC (100 GB) |
| Railway Buckets | Object Storage cloud.ru (`s3.cloud.ru`, бакет `km-storage`) |
| Сборка только api/client/pdf_to_md | Сборка всех 9 сервисов |
| Hostname магия Railway | Стабильные Service names внутри кластера |

---

## Стоимость (оценка)

| Ресурс | Стоимость |
|--------|-----------|
| Managed Kubernetes, нода 16vCPU/32GB | ~23.77 ₽/час ≈ **17 350 ₽/мес** |
| Object Storage (бакет km-storage) | по тарифу на ~GB |
| GitHub Actions / Artifact Registry | в пределах бесплатных лимитов публичного репозитория |

> ⚠️ Экономить на размере ноды нельзя: Neo4j (heap 3G + pagecache 3G + накладные)
> физически не помещается в ноды 2-4 GB. Минимальная нода — **16 vCPU / 32 GB RAM**.

---

## Стоимость загрузки данных из data_download

Раздел описывает разовые и ежемесячные расходы на загрузку **всех данных** из
страниц `/api/data_download` и `/api/citation_graph`. Тарифы — Evolution, цены с НДС 22%
(актуальны на июнь 2026). Все источники дампов (NCBI, OpenAlex, DataCite, Figshare)
отдают данные бесплатно.

> **Ключевой факт:** в cloud.ru входящий и исходящий трафик виртуальных машин
> **сейчас не тарифицируется** (официальный FAQ «Как тарифицируется входящий и исходящий
> трафик на платформе Evolution», включая sNAT-шлюз). Само скачивание стоит ≈ 0 ₽.
> Основные расходы — хранение данных и вычислительное время.

### Объёмы дампов по источникам

| Источник | Объём загрузки | Куда сохраняется |
|----------|----------------|------------------|
| PubMed Baseline + Update (FTP NCBI) | ~45–50 ГБ (XML.gz) | диск ноды, затем S3/Neo4j |
| PubMed Central OA (`s3://pmc-oa-opendata`) | ~700 ГБ – 1 ТБ (XML + изображения) | диск ноды, затем S3/Neo4j |
| OpenAlex (`s3://openalex/data/jsonl/works`) | ~666 ГБ (2 446 файлов .gz) | диск ноды |
| Crossref annual dump | ~208 ГБ (tar) | диск ноды |
| DataCite public dump | ~33 ГБ (JSONL.gz) | диск ноды |
| OpenCitations COCI (Figshare) | ~40 ГБ (CSV.gz) | диск ноды |
| **Итого к скачиванию** | **~1,7–2 ТБ** | |

> **Crossref:** облачный снимок `api-snapshots-reqpays-crossref` — бакет
> *Requester Pays* (оплачивается Amazon AWS, из cloud.ru напрямую не качается).
> В коде предусмотрен торрент (DOI `10.13003/nggf-vt1j`) — он бесплатный.

### Статьи расходов

**1. Трафик на скачивание** — **0 ₽** (не тарифицируется, включая sNAT-шлюз).

**2. Хранение дампов на диске** — временное, удаляется после обработки:

| Диск | Тариф | 2 ТБ за 10 дней | 2 ТБ за месяц |
|------|-------|-----------------|---------------|
| SSD NVMe | 0,01586 ₽/ГБ·час | ≈ 7 600 ₽ | ≈ 22 800 ₽ |
| HDD | 0,00427 ₽/ГБ·час | ≈ 2 000 ₽ | ≈ 6 100 ₽ |

При параллельной обработке и немедленном удалении дампов вы укладываетесь в нижнюю
границу (~2–8 тыс. ₽ за период загрузки).

**3. Object Storage для результата** (markdown-документы + изображения, п. 4.8
архитектуры): стандартный класс, однозонный — ≈ 1,13 ₽/ГБ·мес.

| Компонент | Оценка объёма |
|-----------|---------------|
| PubMed/PMC markdown + изображения | ~800 ГБ – 1,3 ТБ |
| **Итого** | **≈ 900 – 1 500 ₽/мес** |

Бесплатно каждый месяц: первые 15 ГБ хранения и первые 10 ТБ исходящего трафика.

**4. Neo4j цитатный граф** (2,5+ млрд рёбер OpenAlex/OpenCitations и др.) — не в S3,
а в StatefulSet кластера. Текущий PVC 100 ГБ нужно нарастить до ~500–700 ГБ →
дополнительные SSD-диски ≈ **5–8 тыс. ₽/мес**.

### Итог по загрузке

Без учёта уже рассчитанной ноды кластера (17 350 ₽/мес, её достаточно для загрузки):

| Статья | Стоимость |
|--------|-----------|
| Трафик на скачивание | **≈ 0 ₽** |
| Разовый период загрузки (диски под дампы, ~2 недели) | ≈ 4 000 – 8 000 ₽ |
| Постоянное хранение результата (OBS + диск Neo4j) | ≈ 6 000 – 9 500 ₽/мес |

> 💡 Оптимизация: после обработки переводить результат в **Cold/Warm** класс OBS
> (архив ~0,6 ₽/ГБ·мес) и удалять исходные дампы — ежемесячные расходы снижаются
> в разы.