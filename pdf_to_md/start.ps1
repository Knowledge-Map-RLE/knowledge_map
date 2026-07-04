Set-Location $PSScriptRoot

# ── Kill any zombie process on port 5002 ──────────────────────────
$oldPid = (netstat -ano | Select-String ":5002\s").ForEach({ 
    $m = $_ | Select-String "LISTENING\s+(\d+)$"; if ($m) { $m.Matches.Groups[1].Value } 
}) | Select-Object -First 1
if ($oldPid) {
    Write-Host "Killing existing process on port 5002 (PID $oldPid)..."
    taskkill /F /PID $oldPid 2>$null
    Start-Sleep -Seconds 1
}

# ── Start OpenDataLoader hybrid backend ──────────────────────────
Write-Host "Starting OpenDataLoader hybrid backend on port 5002..."
Start-Process -NoNewWindow -FilePath "poetry" `
    -ArgumentList "run", "python", "hybrid_wrapper.py", "--port", "5002"

# Wait until hybrid backend HTTP /health returns {"status":"ok"} (up to 180 seconds)
Write-Host "Waiting for hybrid backend to be ready on port 5002 (this may take ~60s on first run)..."
$maxWait = 180
$waited = 0
$ready = $false
do {
    Start-Sleep -Seconds 3
    $waited += 3
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:5002/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
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

# ── Verify hybrid backend is still alive ─────────────────────────
# Double-check: if it died right after startup (EADDRINUSE), restart once
if (-not $ready) {
    $stillAlive = $false
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:5002/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        $stillAlive = $resp.StatusCode -eq 200
    } catch { }
    if (-not $stillAlive) {
        Write-Host "Hybrid backend is dead. Retrying once..."
        $oldPid2 = (netstat -ano | Select-String ":5002\s").ForEach({ 
            $m = $_ | Select-String "LISTENING\s+(\d+)$"; if ($m) { $m.Matches.Groups[1].Value } 
        }) | Select-Object -First 1
        if ($oldPid2) { taskkill /F /PID $oldPid2 2>$null; Start-Sleep -Seconds 1 }
        Start-Process -NoNewWindow -FilePath "poetry" `
            -ArgumentList "run", "python", "hybrid_wrapper.py", "--port", "5002"

        $retryWaited = 0
        $retryReady = $false
        do {
            Start-Sleep -Seconds 3
            $retryWaited += 3
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:5002/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($resp.StatusCode -eq 200 -and $resp.Content -match '"status"\s*:\s*"ok"') { $retryReady = $true }
            } catch { }
            if (-not $retryReady -and ($retryWaited % 30 -eq 0)) { Write-Host "  Retry still waiting... ${retryWaited}s elapsed" }
        } while (-not $retryReady -and $retryWaited -lt 60)

        if ($retryReady) { Write-Host "Hybrid backend ready after retry (${retryWaited}s)." }
        else { Write-Host "Warning: hybrid backend failed to start after retry." }
    }
}

# Start gRPC server as independent process (not tied to REST lifecycle)
Write-Host "Starting gRPC server on port 50053..."
Start-Process -NoNewWindow -FilePath "poetry" `
    -ArgumentList "run", "python", "-m", "src.grpc_server"

# Start REST server with reload (gRPC runs independently)
Write-Host "Starting REST server on port 8002..."
poetry run python -m uvicorn src.app:app --host 0.0.0.0 --port 8002 --reload
