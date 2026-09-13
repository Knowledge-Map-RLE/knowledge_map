$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Observability (local dev): OTLP → Alloy localhost:4317
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4317"
$env:OTEL_SERVICE_NAME = "ai"
$env:OTEL_SERVICE_VERSION = "0.1.0"
$env:OTEL_METRIC_EXPORT_INTERVAL = "30000"
$env:LOG_FORMAT = "logfmt"

$port = 50059

Write-Host "Starting AI Agent microservice on port $port..."

# Kill any stale process holding the AI port before binding.
$listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    foreach ($listener in $listeners) {
        $pidToKill = $listener.OwningProcess
        Write-Host "Port $port is in use by PID $pidToKill. Stopping it..."
        try {
            Stop-Process -Id $pidToKill -Force -ErrorAction Stop
        } catch {
            Write-Warning "Could not stop PID $pidToKill : $_"
        }
    }
    Start-Sleep -Milliseconds 500
}

# Remove stale bytecode caches for a clean import.
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

poetry run python src/main.py
