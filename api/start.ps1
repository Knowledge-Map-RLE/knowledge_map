# Run API microservice locally (without Docker)
# Run from ./api/ directory

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 1) Install dependencies via Poetry
Write-Host "Updating lock file..."
poetry lock --no-interaction
Write-Host "Installing dependencies..."
poetry install --only=main --no-root --no-interaction

# 2) Generate proto files
Write-Host "Generating proto files..."
New-Item -ItemType Directory -Force -Path "utils/generated" | Out-Null

python -m grpc_tools.protoc `
    -I./utils/proto `
    -I../nlp/proto `
    --python_out=./utils/generated `
    --grpc_python_out=./utils/generated `
    ./utils/proto/layout.proto `
    ./utils/proto/auth.proto `
    ../nlp/proto/nlp.proto

# 3) Create __init__.py for generated
$initFile = "utils/generated/__init__.py"
if (-not (Test-Path $initFile)) {
    New-Item -ItemType File -Path $initFile | Out-Null
}

# 4) Fix imports in generated grpc files
Write-Host "Fixing imports in grpc files..."
# nlp_pb2_grpc.py is excluded: nlp_grpc_client.py imports it via sys.path (absolute import)
$grpcFiles = @(
    "utils/generated/layout_pb2_grpc.py",
    "utils/generated/auth_pb2_grpc.py"
)
# Regex-замены: используем (?m) для многострочного режима,
# заменяем только строки где import X НЕ предшествует "from ."
$replacements = @{
    "(?m)^import layout_pb2 as layout__pb2" = "from . import layout_pb2 as layout__pb2"
    "(?m)^import auth_pb2 as auth__pb2"     = "from . import auth_pb2 as auth__pb2"
}
foreach ($file in $grpcFiles) {
    if (Test-Path $file) {
        $content = Get-Content $file -Raw
        foreach ($pattern in $replacements.Keys) {
            $content = [regex]::Replace($content, $pattern, $replacements[$pattern])
        }
        Set-Content $file $content
    }
}

# 5) Start server
Write-Host "Starting uvicorn on port 8000..."
poetry run python -m uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
