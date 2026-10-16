#!/bin/sh
set -eu

/app/.venv/bin/python -m src.grpc_server &
GRPC_PID=$!

cleanup() {
    kill "$GRPC_PID" 2>/dev/null || true
    wait "$GRPC_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

/app/.venv/bin/python -m uvicorn src.app:app --host 0.0.0.0 --port 8002
