# Deploy Knowledge Map

Развёртывание системы на Kubernetes (cloud.ru Managed Kubernetes — production, k3d — локальная проверка).

## Структура

```
deploy/
  k8s/
    base/                  # Базовые манифесты: namespace, ConfigMaps, Secrets, все 11 сервисов
    overlays/
      dev/                 # k3d: MinIO вместо Object Storage, мягкие лимиты, dev-секреты
      prod/                # cloud.ru: Object Storage, replicas=2, sectets.env (не в git)
  scripts/
    prepare-secrets.sh     # Генерация prod/secrets.env из переменных окружения (CI)
    apply-prod.sh          # kustomize render + kubectl apply в production
    k3d-up.sh              # Поднятие локального кластера k3d и деплой dev-overlay
    k3d-down.sh            # Удаление локального кластера
```

## Сборка / рендер манифестов

Любой overlay можно отрендерить без кластера:

```powershell
kubectl kustomize deploy/k8s/overlays/prod > prod-manifests.yaml
kubectl kustomize deploy/k8s/overlays/dev  > dev-manifests.yaml
```

## Локальная проверка (k3d)

```bash
./deploy/scripts/k3d-up.sh     # создать кластер, собрать образы, применить dev-overlay
./deploy/scripts/k3d-down.sh   # удалить кластер
```

После `k3d-up.sh` клиент доступен на `http://localhost:30080`.

## Production (cloud.ru)

1. Заполнить GitHub Secrets (см. `docs/deployment.md`).
2. Создать тег: `git tag v1.0.0 && git push origin v1.0.0`.
3. Workflow собирает образы, пушет в `*.cr.cloud.ru/km/<service>` и применяет манифесты.

Пока не настроен кластер — установить `DRY_RUN=true`: манифесты рендерятся, деплой не выполняется.

Вручную без CI:

```bash
# 1. Заполнить deploy/k8s/overlays/prod/secrets.env реальными значениями
# 2. Применить
./deploy/scripts/apply-prod.sh
```

## Секреты

- `deploy/k8s/base/secret-template.yaml` — шаблон с заглушками `REPLACE_ME`, **не деплоится**.
- `deploy/k8s/overlays/dev/secret-app-secrets.yaml` — dev-секреты, значения безопасны для локальной разработки.
- `deploy/k8s/overlays/prod/secrets.env` — реальные секреты; генерируется в CI из GitHub Secrets, **в git не хранится** (см. `.gitignore`).