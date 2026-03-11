#!/bin/sh
set -e

# Запуск gRPC сервера в фоне
/app/.venv/bin/python src/grpc_server.py &
GRPC_PID=$!

# Запуск REST сервера на переднем плане
# Railway устанавливает $PORT автоматически
/app/.venv/bin/python -m uvicorn src.app:app --host 0.0.0.0 --port "${PORT:-8002}"

# Остановить gRPC при завершении REST
kill "$GRPC_PID" 2>/dev/null || true
