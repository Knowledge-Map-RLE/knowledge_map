Set-Location $PSScriptRoot

Write-Host "Starting AI gRPC server on port 50054..."
poetry run python src/grpc_server.py
