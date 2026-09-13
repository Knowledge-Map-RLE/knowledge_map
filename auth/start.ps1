Set-Location $PSScriptRoot

# Observability (local dev): OTLP → Alloy localhost:4317
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4317"
$env:OTEL_SERVICE_NAME = "auth"
$env:OTEL_SERVICE_VERSION = "0.1.0"
$env:OTEL_METRIC_EXPORT_INTERVAL = "30000"
$env:LOG_FORMAT = "logfmt"

$port = 50057

Write-Host "Starting Auth gRPC server on port $port..." -ForegroundColor Cyan

# Pre-warm (создаёт .pyc кэш)
Write-Host "Pre-warming imports..."
poetry run python -c "
import src.config
import src.models
import src.schemas
import src.utils
print('Pre-warm OK')
" 2>&1 | Out-Null

# Запуск
poetry run python -m src.main
