#!/usr/bin/env bash
# Локальный / ручной деплой всей стеки knowledge-map в cloud.ru Kubernetes.
# Требуется: kubectl с доступом к кластеру (kubeconfig), заполненный secrets.env.
set -euo pipefail

OVERLAY_DIR="deploy/k8s/overlays/prod"

echo ">> Рендер манифестов (kustomize)..."
kubectl kustomize "$OVERLAY_DIR" > /tmp/km-prod-manifests.yaml

echo ">> Применение манифестов..."
kubectl apply -f /tmp/km-prod-manifests.yaml

echo ">> Ожидание rollout всех Deployment/StatefulSet..."
kubectl -n knowledge-map rollout status deploy --timeout=600s
kubectl -n knowledge-map rollout status sts --timeout=900s

echo ">> Статус..."
kubectl -n knowledge-map get pods -o wide