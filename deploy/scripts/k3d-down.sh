#!/usr/bin/env bash
# Останавливает и удаляет локальный кластер k3d.
set -euo pipefail

CLUSTER="knowledge-map-dev"

if k3d cluster list 2>/dev/null | grep -q "^$CLUSTER[[:space:]]"; then
  k3d cluster delete "$CLUSTER"
  echo ">> Кластер $CLUSTER удалён"
else
  echo ">> Кластер $CLUSTER не существует — нечего удалять"
fi