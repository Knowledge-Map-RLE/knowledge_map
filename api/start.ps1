# Run API microservice locally (without Docker)
# Run from ./api/ directory

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$registryPythonPath = (Resolve-Path "..\shared\model_registry").Path
$existingPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH")
if ([string]::IsNullOrWhiteSpace($existingPythonPath)) {
    $env:PYTHONPATH = $registryPythonPath
} else {
    $env:PYTHONPATH = $registryPythonPath + ";" + $existingPythonPath
}

# Observability (local dev): OTLP → Alloy localhost:4317
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4317"
$env:OTEL_SERVICE_NAME = "api"
$env:OTEL_SERVICE_VERSION = "0.1.0"
$env:OTEL_METRIC_EXPORT_INTERVAL = "30000"
$env:LOG_FORMAT = "logfmt"

# The API has one fixed port shared by its clients. Fail before running setup if
# another process already owns it; do not switch ports or terminate that process.
$selectedPort = 8000
$listeners = @(Get-NetTCPConnection -LocalPort $selectedPort -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $owners = ($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "Configured API port $selectedPort is already in use by PID(s): $owners"
}

# 1) Install exactly the dependency versions recorded in poetry.lock.
# Resolving/updating the lock file on every service start adds latency and makes
# startup depend on the current package index state.
Write-Host "Checking dependencies from poetry.lock..."
poetry install --only=main --no-root --no-interaction
if ($LASTEXITCODE -ne 0) {
    throw "Poetry dependency installation failed with exit code $LASTEXITCODE"
}

# 2) Generate proto files only when an input changed or an output is missing.
New-Item -ItemType Directory -Force -Path "utils/generated" | Out-Null

$protoSources = @(
    "utils/proto/layout.proto",
    "utils/proto/auth.proto",
    "../nlp/proto/nlp.proto"
)
$generatedFiles = @(
    "utils/generated/layout_pb2.py",
    "utils/generated/layout_pb2_grpc.py",
    "utils/generated/auth_pb2.py",
    "utils/generated/auth_pb2_grpc.py",
    "utils/generated/nlp_pb2.py",
    "utils/generated/nlp_pb2_grpc.py"
)

$missingProtoFiles = @($protoSources + $generatedFiles | Where-Object { -not (Test-Path $_) })
if ($missingProtoFiles.Count -gt 0) {
    $generateProtos = $true
} else {
    $latestProtoChange = ($protoSources | Get-Item | Measure-Object -Property LastWriteTimeUtc -Maximum).Maximum
    $earliestGenerated = ($generatedFiles | Get-Item | Measure-Object -Property LastWriteTimeUtc -Minimum).Minimum
    $generateProtos = $latestProtoChange -gt $earliestGenerated
}

if ($generateProtos) {
    Write-Host "Generating changed proto files..."
    poetry run python -m grpc_tools.protoc `
        -I../nlp/proto `
        -I./utils/proto `
        --python_out=./utils/generated `
        --grpc_python_out=./utils/generated `
        ./utils/proto/layout.proto `
        ./utils/proto/auth.proto `
        ../nlp/proto/nlp.proto
    if ($LASTEXITCODE -ne 0) {
        throw "Protobuf generation failed with exit code $LASTEXITCODE"
    }
} else {
    Write-Host "Proto files are up to date."
}

# 3) Create __init__.py for generated
$initFile = "utils/generated/__init__.py"
if (-not (Test-Path $initFile)) {
    New-Item -ItemType File -Path $initFile | Out-Null
}

# 4) Fix imports only when generated content needs a change.
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
        $updatedContent = $content
        foreach ($pattern in $replacements.Keys) {
            $updatedContent = [regex]::Replace($updatedContent, $pattern, $replacements[$pattern])
        }
        if ($updatedContent -cne $content) {
            $utf8NoBom = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
            [System.IO.File]::WriteAllText((Resolve-Path $file).Path, $updatedContent, $utf8NoBom)
        }
    }
}

# 5) Start the app once in the serving process; avoid a second full import just
# to warm Python's module cache.
Write-Host "Starting uvicorn on port $selectedPort..."
poetry run python -m uvicorn web.app:app --host 0.0.0.0 --port $selectedPort --timeout-keep-alive 120 --no-access-log
