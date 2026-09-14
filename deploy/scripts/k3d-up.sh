#!/usr/bin/env bash
# Поднимает локальный кластер k3d и деплоит dev-overlay для проверки перед тегом.
# Требуется: k3d, kubectl, docker. Образы берутся локальными (docker build).
set -euo pipefail

CLUSTER="knowledge-map-dev"

if k3d cluster list 2>/dev/null | grep -q "^$CLUSTER[[:space:]]"; then
  echo ">> Кластер $CLUSTER уже существует"
else
  echo ">> Создание кластера $CLUSTER..."
  k3d cluster create "$CLUSTER" \
    --agents 1 \
    --registry-create km-registry \
    --port 30080:80@loadbalancer
fi

echo ">> Сборка образов сервисов (dev)..."
docker build -t auth:latest -f auth/Dockerfile --build-context shared=./shared auth &
docker build -t api:latest -f api/Dockerfile --build-context shared=./shared api &
docker build -t billing:latest -f billing/Dockerfile --build-context shared=./shared billing &
docker build -t ai:latest -f ai/Dockerfile --build-context shared=./shared ai &
docker build -t nlp:latest -f nlp/Dockerfile --build-context shared=./shared nlp &wait

docker build -t laying:latest -f laying/Dockerfile laying &
docker build -t knowledge_map_core:latest -f knowledge_map_core/Dockerfile knowledge_map_core &
docker build -t pdf_to_md:latest -f pdf_to_md/Dockerfile pdf_to_md &
docker build -t client:latest -f client/Dockerfile client &
wait

echo ">> Импорт образов в k3d..."
k3d image import -c "$CLUSTER" \
  auth:latest api:latest billing:latest ai:latest nlp:latest \
  laying:latest knowledge_map_core:latest pdf_to_md:latest client:latest

echo ">> Деплой dev-overlay..."
kubectl apply -f <(kubectl kustomize deploy/k8s/overlays/dev)

echo ">> Ожидание rollout..."
kubectl -n knowledge-map rollout status deploy --timeout=600s
kubectl -n knowledge-map rollout status sts --timeout=900s

echo ">> Доступ: http://localhost:30080 (client)"
kubectl -n knowledge-map get pods -o wide