Set-Location $PSScriptRoot

Write-Host "Starting Knowledge Language gRPC server on port 50056..."
poetry run python -m src.main
