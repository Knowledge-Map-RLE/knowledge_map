Set-Location $PSScriptRoot

Write-Host "Starting NLP gRPC server on port 50055..."
poetry run python src/main.py
