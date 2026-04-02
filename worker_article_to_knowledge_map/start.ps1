# Worker: PMC Article to Knowledge Map
# Searches PMC for "aging" articles and processes them through the full pipeline.
#
# Configuration via environment variables:
#   WORKER_QUERY          - search query (default: "aging")
#   WORKER_TARGET_COUNT   - number of articles to process (default: 1000)
#   WORKER_BATCH_SIZE     - concurrent articles (default: 3)
#   WORKER_API_URL        - main API base URL (default: http://localhost:8000/api/data_extraction)
#   NCBI_API_KEY          - NCBI API key for higher rate limits (optional)
#   NEO4J_URI             - Neo4j URI (default: bolt://127.0.0.1:7687)
#   NEO4J_USER            - Neo4j user (default: neo4j)
#   NEO4J_PASSWORD        - Neo4j password (default: password)
#
# Status API available at http://localhost:8004/status while worker is running.

Set-Location $PSScriptRoot
$ErrorActionPreference = "Stop"

Write-Host "=== Knowledge Map: Article Batch Worker ===" -ForegroundColor Cyan
Write-Host "Query:       $(if ($env:WORKER_QUERY) { $env:WORKER_QUERY } else { 'aging' })"
Write-Host "Target:      $(if ($env:WORKER_TARGET_COUNT) { $env:WORKER_TARGET_COUNT } else { '1000' }) articles"
Write-Host "Batch size:  $(if ($env:WORKER_BATCH_SIZE) { $env:WORKER_BATCH_SIZE } else { '3' }) concurrent"
Write-Host "API URL:     $(if ($env:WORKER_API_URL) { $env:WORKER_API_URL } else { 'http://localhost:8000/api/data_extraction' })"
Write-Host "Status API:  http://localhost:$(if ($env:WORKER_STATUS_PORT) { $env:WORKER_STATUS_PORT } else { '8004' })/status"
Write-Host ""

# Check if poetry is available
if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    Write-Error "poetry is not installed or not in PATH. Please install it from https://python-poetry.org"
    exit 1
}

Write-Host "Installing dependencies..." -ForegroundColor Yellow
poetry install --no-root --no-interaction

Write-Host "Starting worker..." -ForegroundColor Green
poetry run python main.py
