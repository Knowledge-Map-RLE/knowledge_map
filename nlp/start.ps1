Set-Location $PSScriptRoot

# Observability (local dev): OTLP → Alloy localhost:4317
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4317"
$env:OTEL_SERVICE_NAME = "nlp"
$env:OTEL_SERVICE_VERSION = "0.1.0"
$env:OTEL_METRIC_EXPORT_INTERVAL = "30000"
$env:LOG_FORMAT = "logfmt"

Write-Host "Starting NLP gRPC server on port 50055..."
$env:CUDA_VISIBLE_DEVICES = "0"
poetry run python src/main.py
