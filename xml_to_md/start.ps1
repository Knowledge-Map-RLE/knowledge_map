Set-Location $PSScriptRoot

# Observability (local dev): OTLP → Alloy localhost:4317
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4317"
$env:OTEL_SERVICE_NAME = "xml_to_md"
$env:OTEL_SERVICE_VERSION = "0.1.0"
$env:OTEL_METRIC_EXPORT_INTERVAL = "30000"
$env:LOG_FORMAT = "logfmt"

# Start gRPC server as independent process
Write-Host "Starting xml_to_md gRPC server on port 50054..."
Start-Process -NoNewWindow -FilePath "poetry" `
    -ArgumentList "run", "python", "-m", "src.main"

# Start REST server with reload
Write-Host "Starting xml_to_md REST server on port 8003..."
poetry run python -m uvicorn src.app:app --host 0.0.0.0 --port 8003 --reload
