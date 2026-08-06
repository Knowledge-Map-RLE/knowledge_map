$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$port = 50054

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
