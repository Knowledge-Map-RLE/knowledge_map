Set-Location $PSScriptRoot

# Start gRPC server as independent process (not tied to REST lifecycle)
Write-Host "Starting gRPC server on port 50053..."
Start-Process -NoNewWindow -FilePath "poetry" `
    -ArgumentList "run", "python", "-m", "src.grpc_server"

# Start REST server with reload (gRPC runs independently)
Write-Host "Starting REST server on port 8002..."
poetry run python -m uvicorn src.app:app --host 0.0.0.0 --port 8002 --reload
