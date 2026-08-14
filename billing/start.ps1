# Run Billing microservice locally (without Docker)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$port = 50058

Write-Host "Starting Billing microservice on port $port..."

# 1) Install dependencies via Poetry
Write-Host "Installing dependencies..."
poetry install --only=main --no-root --no-interaction

# 2) Generate proto files (auth.proto -> utils/generated)
Write-Host "Generating proto files..."
New-Item -ItemType Directory -Force -Path "utils/generated" | Out-Null
python -m grpc_tools.protoc `
    -I./proto `
    --python_out=./utils/generated `
    --grpc_python_out=./utils/generated `
    ./proto/auth.proto

$initFile = "utils/generated/__init__.py"
if (-not (Test-Path $initFile)) {
    New-Item -ItemType File -Path $initFile | Out-Null
}

# Fix imports in generated grpc file
$grpcFile = "utils/generated/auth_pb2_grpc.py"
if (Test-Path $grpcFile) {
    $content = Get-Content $grpcFile -Raw
    $content = [regex]::Replace($content, "(?m)^import auth_pb2 as auth__pb2", "from . import auth_pb2 as auth__pb2")
    Set-Content $grpcFile $content
}

# 3) Kill any stale process holding the port
$listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    foreach ($listener in $listeners) {
        $pidToKill = $listener.OwningProcess
        Write-Host "Port $port is in use by PID $pidToKill. Stopping it..."
        Stop-Process -Id $pidToKill -Force -ErrorAction Stop
    }
    Start-Sleep -Milliseconds 500
}

# 4) Remove stale bytecode caches
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 5) Start server (fixed port 50058)
poetry run python src/main.py
