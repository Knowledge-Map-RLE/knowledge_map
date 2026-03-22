Set-Location $PSScriptRoot

# Start gRPC server as independent process
Write-Host "Starting xml_to_md gRPC server on port 50054..."
Start-Process -NoNewWindow -FilePath "poetry" `
    -ArgumentList "run", "python", "-m", "src.main"

# Start REST server with reload
Write-Host "Starting xml_to_md REST server on port 8003..."
poetry run python -m uvicorn src.app:app --host 0.0.0.0 --port 8003 --reload
