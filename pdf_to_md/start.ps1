Set-Location $PSScriptRoot

# Start OpenDataLoader hybrid backend (required for hybrid=docling-fast mode)
Write-Host "Starting OpenDataLoader hybrid backend on port 5002..."
Start-Process -NoNewWindow -FilePath "poetry" `
    -ArgumentList "run", "opendataloader-pdf-hybrid", "--port", "5002"

# Wait until hybrid backend HTTP /health returns {"status":"ok"} (up to 180 seconds)
Write-Host "Waiting for hybrid backend to be ready on port 5002 (this may take ~60s on first run)..."
$maxWait = 180
$waited = 0
$ready = $false
do {
    Start-Sleep -Seconds 3
    $waited += 3
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:5002/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($resp.StatusCode -eq 200 -and $resp.Content -match '"status"\s*:\s*"ok"') {
            $ready = $true
        }
    } catch {
        $ready = $false
    }
    if (-not $ready -and ($waited % 15 -eq 0)) {
        Write-Host "  Still waiting... ${waited}s elapsed"
    }
} while (-not $ready -and $waited -lt $maxWait)

if ($ready) {
    Write-Host "Hybrid backend ready after ${waited}s."
} else {
    Write-Host "Warning: hybrid backend did not respond in ${maxWait}s, continuing anyway."
}

# Start gRPC server as independent process (not tied to REST lifecycle)
Write-Host "Starting gRPC server on port 50053..."
Start-Process -NoNewWindow -FilePath "poetry" `
    -ArgumentList "run", "python", "-m", "src.grpc_server"

# Start REST server with reload (gRPC runs independently)
Write-Host "Starting REST server on port 8002..."
poetry run python -m uvicorn src.app:app --host 0.0.0.0 --port 8002 --reload
