# Run data_to_db worker locally
# Run from ./data_to_db/ directory

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Create logs directory if not exists
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Force -Path "logs" | Out-Null
}

# Install dependencies via Poetry if needed
if (Test-Path "pyproject.toml") {
    Write-Host "Installing dependencies..."
    poetry install --only=main --no-root --no-interaction
}

# Check if xml_to_md service is running
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:50054" -Method GET -TimeoutSec 2 -ErrorAction SilentlyContinue
    Write-Host "xml_to_md service is running"
} catch {
    Write-Host "WARNING: xml_to_md service not running on port 50054"
    Write-Host "Start it with: poetry run python -m xml_to_md.service"
}

# Start worker
Write-Host "Starting data_to_db worker..."
poetry run python worker.py