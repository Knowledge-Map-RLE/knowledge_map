# PowerShell script for starting Knowledge Map microservices on host
# Starts neo4j, redis, s3 via Docker, other services on host

param(
    [switch]$Stop,
    [switch]$Restart,
    [switch]$HostOnly,
    [switch]$Status,
    [switch]$Logs,
    [string]$Service = ""
)

# Get the root directory where the script is located
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Colors for output
$ErrorColor = "Red"
$SuccessColor = "Green"
$InfoColor = "Cyan"
$WarningColor = "Yellow"

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Test-Port {
    param(
        [int]$Port,
        [string]$ServiceName
    )
    
    try {
        $connection = New-Object System.Net.Sockets.TcpClient
        $connection.Connect("localhost", $Port)
        $connection.Close()
        return $true
    }
    catch {
        return $false
    }
}

function Wait-ForService {
    param(
        [int]$Port,
        [string]$ServiceName,
        [int]$TimeoutSeconds = 60
    )
    
    Write-ColorOutput "Waiting for $ServiceName to start on port $Port..." $InfoColor
    
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        if (Test-Port -Port $Port -ServiceName $ServiceName) {
            Write-ColorOutput "$ServiceName started on port $Port" $SuccessColor
            return $true
        }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    
    Write-ColorOutput "Timeout waiting for $ServiceName" $ErrorColor
    return $false
}

function Start-DockerServices {
    Write-ColorOutput "Starting Docker services (neo4j, redis, s3)..." $InfoColor
    
    # Start only required services
    docker-compose up -d neo4j redis s3
    
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput "Error starting Docker services" $ErrorColor
        exit 1
    }
    
    # Wait for services to start
    Wait-ForService -Port 7687 -ServiceName "Neo4j" -TimeoutSeconds 90
    Wait-ForService -Port 6379 -ServiceName "Redis" -TimeoutSeconds 30
    Wait-ForService -Port 9000 -ServiceName "MinIO S3" -TimeoutSeconds 30
}

function Stop-DockerServices {
    Write-ColorOutput "Stopping Docker services..." $InfoColor
    docker-compose stop neo4j redis s3
}

function Start-AuthService {
    Write-ColorOutput "Starting Auth service..." $InfoColor
    
    $authDir = Join-Path $ScriptRoot "auth"
    if (-not (Test-Path $authDir)) {
        Write-ColorOutput "Directory $authDir not found" $ErrorColor
        return $false
    }
    
    # Install dependencies via Poetry
    Write-ColorOutput "Installing dependencies for auth..." $InfoColor
    Push-Location $authDir
    try {
        # Install dependencies without installing the project as a package
        poetry install --no-root
    }
    finally {
        Pop-Location
    }
    
    # Generate proto files
    Write-ColorOutput "Generating proto files for auth..." $InfoColor
    Push-Location $authDir
    try {
        python -m grpc_tools.protoc -I proto --python_out=src --grpc_python_out=src proto/auth.proto
    }
    finally {
        Pop-Location
    }
    
    # Start service
    Write-ColorOutput "Starting auth service..." $InfoColor
    $env:NEO4J_URI = "bolt://127.0.0.1:7687"
    $env:NEO4J_ENCRYPTED = "false"
    $env:REDIS_URL = "redis://127.0.0.1:6379"
    $env:GRPC_HOST = "0.0.0.0"
    $env:GRPC_PORT = "50052"
    $env:SECRET_KEY = "your-secret-key-change-in-production"
    $env:ALGORITHM = "HS256"
    $env:ACCESS_TOKEN_EXPIRE_MINUTES = "30"
    $env:PASSWORD_MIN_LENGTH = "8"
    $env:RECOVERY_KEYS_COUNT = "10"
    $env:RECOVERY_KEY_LENGTH = "16"
    $env:LOGIN_ATTEMPTS_LIMIT = "5"
    $env:LOGIN_ATTEMPTS_WINDOW = "300"
    
    # Create logs directory
    $logsDir = Join-Path $authDir "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -Path $logsDir -ItemType Directory -Force
    }
    
    # Start service in background with logging
    $logFile = Join-Path $logsDir "auth.log"
    $errorFile = Join-Path $logsDir "auth_error.log"
    $process = Start-Process -FilePath "poetry" -ArgumentList "run", "python", "-m", "src.main" -WorkingDirectory $authDir -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errorFile -PassThru
    
    Start-Sleep -Seconds 5
    
    if (Test-Port -Port 50052 -ServiceName "Auth gRPC") {
        Write-ColorOutput "Auth service started on port 50052" $SuccessColor
        return $true
    } else {
        Write-ColorOutput "Auth service failed to start" $ErrorColor
        if ($process -and !$process.HasExited) {
            $process.Kill()
        }
        return $false
    }
}

function Start-AIService {
    Write-ColorOutput "Starting AI Model service..." $InfoColor

    $aiDir = Join-Path $ScriptRoot "ai"
    if (-not (Test-Path $aiDir)) {
        Write-ColorOutput "Directory $aiDir not found" $ErrorColor
        return $false
    }

    # Install dependencies via Poetry
    Write-ColorOutput "Installing dependencies for ai..." $InfoColor
    Push-Location $aiDir
    try {
        poetry install
    }
    catch {
        Write-ColorOutput "Failed to install dependencies for ai: $($_.Exception.Message)" $WarningColor
        Write-ColorOutput "Trying to run with existing dependencies..." $InfoColor
    }
    finally {
        Pop-Location
    }

    # Generate proto files
    Write-ColorOutput "Generating proto files for ai..." $InfoColor
    Push-Location $aiDir
    try {
        python -m grpc_tools.protoc -I./proto --python_out=./src --grpc_python_out=./src ./proto/ai_model.proto
    }
    finally {
        Pop-Location
    }

    # Start service
    Write-ColorOutput "Starting AI Model gRPC service..." $InfoColor
    $env:GRPC_HOST = "0.0.0.0"
    $env:GRPC_PORT = "50054"
    $env:MODEL_CACHE_DIR = "D:/Data/Data_Knowledge_Map/ai_models"
    $env:DEFAULT_MODEL = "meta-llama/Llama-3.2-1B-Instruct"
    $env:MODEL_DEVICE = "auto"
    $env:LOG_LEVEL = "INFO"

    # Load Hugging Face token from .env file
    $envFile = Join-Path $ScriptRoot ".env"
    if (Test-Path $envFile) {
        $envContent = Get-Content $envFile
        foreach ($line in $envContent) {
            if ($line -match "^HUGGING_FACE_TOKEN=(.+)$") {
                $env:HUGGING_FACE_TOKEN = $matches[1]
                Write-ColorOutput "Loaded Hugging Face token from .env" $InfoColor
                break
            }
        }
    }

    # Create logs directory
    $logsDir = Join-Path $aiDir "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -Path $logsDir -ItemType Directory -Force
    }

    # Create model cache directory
    $modelCacheDir = "D:/Data/Data_Knowledge_Map/ai_models"
    if (-not (Test-Path $modelCacheDir)) {
        New-Item -Path $modelCacheDir -ItemType Directory -Force
    }

    # Start gRPC service in background with logging
    $logFile = Join-Path $logsDir "ai_model.log"
    $errorFile = Join-Path $logsDir "ai_model_error.log"
    $grpcProcess = Start-Process -FilePath "poetry" -ArgumentList "run", "python", "src/grpc_server.py" -WorkingDirectory $aiDir -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errorFile -PassThru

    Start-Sleep -Seconds 10

    if (Test-Port -Port 50054 -ServiceName "AI Model gRPC") {
        Write-ColorOutput "AI Model gRPC service started on port 50054" $SuccessColor
        return $true
    } else {
        Write-ColorOutput "AI Model gRPC service failed to start" $ErrorColor
        if ($grpcProcess -and !$grpcProcess.HasExited) {
            $grpcProcess.Kill()
        }
        return $false
    }
}

function Start-PdfToMdService {
    Write-ColorOutput "Starting PDF to MD service..." $InfoColor
    
    $pdfToMdDir = Join-Path $ScriptRoot "pdf_to_md"
    if (-not (Test-Path $pdfToMdDir)) {
        Write-ColorOutput "Directory $pdfToMdDir not found" $ErrorColor
        return $false
    }
    
    # Install dependencies via Poetry
    Write-ColorOutput "Installing dependencies for pdf_to_md..." $InfoColor
    Push-Location $pdfToMdDir
    try {
        # Try to update lock file first
        Write-ColorOutput "Updating poetry lock file..." $InfoColor
        poetry lock 2>$null
        poetry install
    }
    catch {
        Write-ColorOutput "Failed to install dependencies for pdf_to_md: $($_.Exception.Message)" $WarningColor
        Write-ColorOutput "Trying to run with existing dependencies..." $InfoColor
    }
    finally {
        Pop-Location
    }
    
    # Generate proto files
    Write-ColorOutput "Generating proto files for pdf_to_md..." $InfoColor
    Push-Location $pdfToMdDir
    try {
        python -m grpc_tools.protoc --proto_path=proto --python_out=src --grpc_python_out=src proto/pdf_to_md.proto
    }
    finally {
        Pop-Location
    }
    
    # Start service
    Write-ColorOutput "Starting pdf_to_md service..." $InfoColor
    $env:PYTHONUNBUFFERED = "1"
    $env:OMP_NUM_THREADS = "2"
    $env:MKL_NUM_THREADS = "2"
    $env:OPENBLAS_NUM_THREADS = "2"
    $env:NUMEXPR_NUM_THREADS = "2"
    $env:VECLIB_MAXIMUM_THREADS = "2"
    $env:NUMBA_NUM_THREADS = "2"
    $env:PYTORCH_CUDA_ALLOC_CONF = "max_split_size_mb:512"
    $env:S3_ENDPOINT_URL = "http://127.0.0.1:9000"
    $env:S3_ACCESS_KEY = "minio"
    $env:S3_SECRET_KEY = "minio123456"
    $env:S3_REGION = "us-east-1"
    
    # Create logs directory
    $logsDir = Join-Path $pdfToMdDir "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -Path $logsDir -ItemType Directory -Force
    }
    
    # Start gRPC service in background with logging
    $logFile = Join-Path $logsDir "pdf_to_md.log"
    $errorFile = Join-Path $logsDir "pdf_to_md_error.log"
    $grpcProcess = Start-Process -FilePath "poetry" -ArgumentList "run", "python", "src/grpc_server.py" -WorkingDirectory $pdfToMdDir -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errorFile -PassThru
    
    # Also start HTTP API for images on port 8002
    $httpLogFile = Join-Path $logsDir "pdf_to_md_http.log"
    $httpErrorFile = Join-Path $logsDir "pdf_to_md_http_error.log"
    $env:API_BASE_URL = "http://localhost:8002"
    $httpProcess = Start-Process -FilePath "poetry" -ArgumentList "run", "python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8002" -WorkingDirectory $pdfToMdDir -WindowStyle Hidden -RedirectStandardOutput $httpLogFile -RedirectStandardError $httpErrorFile -PassThru
    
    Start-Sleep -Seconds 5
    
    $grpcOk = Test-Port -Port 50053 -ServiceName "PDF to MD gRPC"
    $httpOk = Test-Port -Port 8002 -ServiceName "PDF to MD HTTP API"
    
    if ($grpcOk) {
        Write-ColorOutput "PDF to MD gRPC service started on port 50053" $SuccessColor
    } else {
        Write-ColorOutput "PDF to MD gRPC service failed to start" $ErrorColor
        if ($grpcProcess -and !$grpcProcess.HasExited) {
            $grpcProcess.Kill()
        }
    }
    
    if ($httpOk) {
        Write-ColorOutput "PDF to MD HTTP API started on port 8002" $SuccessColor
    } else {
        Write-ColorOutput "PDF to MD HTTP API failed to start" $ErrorColor
        if ($httpProcess -and !$httpProcess.HasExited) {
            $httpProcess.Kill()
        }
    }
    
    return ($grpcOk -and $httpOk)
}


function Start-ApiService {
    Write-ColorOutput "Starting API service..." $InfoColor
    
    $apiDir = Join-Path $ScriptRoot "api"
    if (-not (Test-Path $apiDir)) {
        Write-ColorOutput "Directory $apiDir not found" $ErrorColor
        return $false
    }
    
    # Install dependencies via Poetry
    Write-ColorOutput "Installing dependencies for api..." $InfoColor
    Push-Location $apiDir
    try {
        poetry install

        # Download NLP models and data for multi-level NLP system
        Write-ColorOutput "Checking NLP models and data..." $InfoColor

        # Download NLTK data
        Write-ColorOutput "Downloading NLTK data (punkt, wordnet, stopwords)..." $InfoColor
        poetry run python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('averaged_perceptron_tagger', quiet=True); nltk.download('wordnet', quiet=True); nltk.download('omw-1.4', quiet=True); nltk.download('stopwords', quiet=True)" 2>&1 | Out-Null

        # Check if spaCy model exists, if not download it
        Write-ColorOutput "Checking spaCy model (en_core_web_sm)..." $InfoColor
        $spacyCheck = poetry run python -c "import spacy; spacy.load('en_core_web_sm')" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "Downloading spaCy model en_core_web_sm..." $InfoColor
            poetry run python -m spacy download en_core_web_sm
        } else {
            Write-ColorOutput "spaCy model already installed" $SuccessColor
        }

        # Download Stanza models for English
        Write-ColorOutput "Downloading Stanza models (en)..." $InfoColor
        poetry run python -c "import stanza; stanza.download('en', verbose=False)" 2>&1 | Out-Null
        Write-ColorOutput "Stanza models ready" $SuccessColor

        Write-ColorOutput "NLP models and data ready" $SuccessColor
    }
    catch {
        Write-ColorOutput "Failed to install dependencies for api: $($_.Exception.Message)" $WarningColor
        Write-ColorOutput "Trying to run with existing dependencies..." $InfoColor
    }
    finally {
        Pop-Location
    }
    
    # Generate proto files
    Write-ColorOutput "Generating proto files for api..." $InfoColor
    Push-Location $apiDir
    try {
        # Create utils/generated directory if it doesn't exist
        if (-not (Test-Path "utils/generated")) {
            New-Item -Path "utils/generated" -ItemType Directory -Force
        }

        # Resolve proto locations inside current monorepo
        $graphProto = Join-Path $ScriptRoot "worker_distributed_layering_rust\proto\graph_layout.proto"
        $authProto  = Join-Path $ScriptRoot "auth\proto\auth.proto"
        $pdfProto   = Join-Path $ScriptRoot "pdf_to_md\proto\pdf_to_md.proto"
        $aiProto    = Join-Path $ScriptRoot "ai\proto\ai_model.proto"

        # Build include dirs for protoc
        $incGraph = Split-Path $graphProto -Parent
        $incAuth  = Split-Path $authProto  -Parent
        $incPdf   = Split-Path $pdfProto   -Parent
        $incAI    = Split-Path $aiProto    -Parent

        # Validate proto paths
        if (-not (Test-Path $graphProto)) { Write-ColorOutput "Missing proto: $graphProto" $WarningColor }
        if (-not (Test-Path $authProto))  { Write-ColorOutput "Missing proto: $authProto"  $WarningColor }
        if (-not (Test-Path $pdfProto))   { Write-ColorOutput "Missing proto: $pdfProto"   $WarningColor }
        if (-not (Test-Path $aiProto))    { Write-ColorOutput "Missing proto: $aiProto"    $WarningColor }

        # Generate grpc stubs (any missing file will be ignored by protoc include search order)
        poetry run python -m grpc_tools.protoc `
            -I"$incGraph" -I"$incAuth" -I"$incPdf" -I"$incAI" `
            --python_out=./utils/generated `
            --grpc_python_out=./utils/generated `
            "$graphProto" "$authProto" "$pdfProto" "$aiProto"

        # Create __init__.py for generated folder
        if (-not (Test-Path "utils/generated/__init__.py")) {
            New-Item -Path "utils/generated/__init__.py" -ItemType File -Force | Out-Null
        }

        # Fix imports in generated grpc files (relative imports)
        $grpcFiles = @("utils/generated/graph_layout_pb2_grpc.py", "utils/generated/auth_pb2_grpc.py", "utils/generated/pdf_to_md_pb2_grpc.py", "utils/generated/ai_model_pb2_grpc.py")
        foreach ($file in $grpcFiles) {
            if (Test-Path $file) {
                (Get-Content $file) `
                    -replace "import graph_layout_pb2 as graph_layout__pb2", "from . import graph_layout_pb2 as graph_layout__pb2" `
                    -replace "import auth_pb2 as auth__pb2", "from . import auth_pb2 as auth__pb2" `
                    -replace "import pdf_to_md_pb2 as pdf_to_md__pb2", "from . import pdf_to_md_pb2 as pdf_to_md__pb2" `
                    -replace "import ai_model_pb2 as ai_model__pb2", "from . import ai_model_pb2 as ai_model__pb2" | Set-Content $file
            }
        }
    }
    finally {
        Pop-Location
    }
    
    # Start service
    Write-ColorOutput "Starting API service..." $InfoColor
    $env:NEO4J_URI = "bolt://127.0.0.1:7687"
    $env:NEO4J_ENCRYPTED = "false"
    $env:NEO4J_USER = "neo4j"
    $env:NEO4J_PASSWORD = "password"
    $env:LAYOUT_SERVICE_HOST = "127.0.0.1"
    $env:LAYOUT_SERVICE_PORT = "50051"  # Rust service port
    $env:AUTH_SERVICE_HOST = "127.0.0.1"
    $env:AUTH_SERVICE_PORT = "50052"
    $env:PDF_TO_MD_SERVICE_HOST = "127.0.0.1"
    $env:PDF_TO_MD_SERVICE_PORT = "50053"
    $env:AI_MODEL_SERVICE_HOST = "127.0.0.1"
    $env:AI_MODEL_SERVICE_PORT = "50054"
    $env:S3_ENDPOINT_URL = "http://127.0.0.1:9000"
    $env:S3_ACCESS_KEY = "minio"
    $env:S3_SECRET_KEY = "minio123456"
    $env:S3_REGION = "us-east-1"
    $env:DEBUG = "true"
    $env:OMP_NUM_THREADS = "2"
    $env:MKL_NUM_THREADS = "2"
    $env:OPENBLAS_NUM_THREADS = "2"
    $env:NUMEXPR_NUM_THREADS = "2"
    $env:VECLIB_MAXIMUM_THREADS = "2"
    $env:NUMBA_NUM_THREADS = "2"
    $env:PYTORCH_CUDA_ALLOC_CONF = "max_split_size_mb:512"
    
    # Create logs directory
    $logsDir = Join-Path $apiDir "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -Path $logsDir -ItemType Directory -Force
    }
    
    # Start service in background with logging
    $logFile = Join-Path $logsDir "api.log"
    $errorFile = Join-Path $logsDir "api_error.log"
    
    # Устанавливаем переменные окружения в текущем процессе
    $env:NEO4J_URI = "bolt://127.0.0.1:7687"
    $env:NEO4J_USER = "neo4j"
    $env:NEO4J_PASSWORD = "password"
    $env:LAYOUT_SERVICE_HOST = "127.0.0.1"
    $env:LAYOUT_SERVICE_PORT = "50051"  # Rust service port
    $env:AUTH_SERVICE_HOST = "127.0.0.1"
    $env:AUTH_SERVICE_PORT = "50052"
    $env:PDF_TO_MD_SERVICE_HOST = "127.0.0.1"
    $env:PDF_TO_MD_SERVICE_PORT = "50053"
    $env:AI_MODEL_SERVICE_HOST = "127.0.0.1"
    $env:AI_MODEL_SERVICE_PORT = "50054"
    $env:S3_ENDPOINT_URL = "http://127.0.0.1:9000"
    $env:S3_ACCESS_KEY = "minio"
    $env:S3_SECRET_KEY = "minio123456"
    $env:S3_REGION = "us-east-1"
    $env:DEBUG = "true"
    $env:OMP_NUM_THREADS = "2"
    $env:MKL_NUM_THREADS = "2"
    $env:OPENBLAS_NUM_THREADS = "2"
    $env:NUMEXPR_NUM_THREADS = "2"
    $env:VECLIB_MAXIMUM_THREADS = "2"
    $env:NUMBA_NUM_THREADS = "2"
    $env:PYTORCH_CUDA_ALLOC_CONF = "max_split_size_mb:512"
    
    $process = Start-Process -FilePath "poetry" -ArgumentList "run", "python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000" -WorkingDirectory $apiDir -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errorFile -PassThru
    
    Start-Sleep -Seconds 5
    
    if (Test-Port -Port 8000 -ServiceName "API") {
        Write-ColorOutput "API service started on port 8000" $SuccessColor
        return $true
    } else {
        Write-ColorOutput "API service failed to start" $ErrorColor
        if ($process -and !$process.HasExited) {
            $process.Kill()
        }
        return $false
    }
}

function Show-Status {
    Write-ColorOutput "`n=== Knowledge Map Services Status ===" $InfoColor

    $services = @(
        @{Name="Neo4j"; Port=7687; URL="http://localhost:7474"},
        @{Name="Redis"; Port=6379; URL=""},
        @{Name="MinIO S3"; Port=9000; URL="http://localhost:9001"},
        @{Name="Auth gRPC"; Port=50052; URL=""},
        @{Name="AI Model gRPC"; Port=50054; URL=""},
        @{Name="PDF to MD gRPC"; Port=50053; URL=""},
        @{Name="PDF to MD HTTP API"; Port=8002; URL="http://localhost:8002"},
        @{Name="API"; Port=8000; URL="http://localhost:8000"}
    )
    
    foreach ($service in $services) {
        $status = if (Test-Port -Port $service.Port -ServiceName $service.Name) { "[OK] Running" } else { "[X] Stopped" }
        $color = if ($status -like "*OK*") { $SuccessColor } else { $ErrorColor }
        
        Write-ColorOutput "$($service.Name): $status (port $($service.Port))" $color
        if ($service.URL) {
            Write-ColorOutput "  URL: $($service.URL)" $InfoColor
        }
    }
    
    Write-ColorOutput "`nClient runs separately with: bun dev" $WarningColor
}

function Stop-ServiceByPort {
    param(
        [int]$Port,
        [string]$ServiceName
    )

    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        foreach ($connection in $connections) {
            $processId = $connection.OwningProcess
            if ($processId -and $processId -gt 0) {
                try {
                    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
                    if ($process) {
                        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                        Write-ColorOutput "Stopped $ServiceName on port $Port (PID: $processId)" $InfoColor
                        return $true
                    }
                }
                catch {
                    # Process might have already exited
                }
            }
        }
    }
    catch {
        # Ignore errors
    }
    return $false
}

function Stop-AuthService {
    Write-ColorOutput "Stopping Auth service..." $InfoColor
    Stop-ServiceByPort -Port 50052 -ServiceName "Auth gRPC"
}

function Stop-AIService {
    Write-ColorOutput "Stopping AI Model service..." $InfoColor
    Stop-ServiceByPort -Port 50054 -ServiceName "AI Model gRPC"
}

function Stop-PdfToMdService {
    Write-ColorOutput "Stopping PDF to MD service..." $InfoColor
    $grpcStopped = Stop-ServiceByPort -Port 50053 -ServiceName "PDF to MD gRPC"
    $httpStopped = Stop-ServiceByPort -Port 8002 -ServiceName "PDF to MD HTTP"
    return ($grpcStopped -or $httpStopped)
}

function Stop-ApiService {
    Write-ColorOutput "Stopping API service..." $InfoColor
    Stop-ServiceByPort -Port 8000 -ServiceName "API"
}

function Stop-AllServices {
    Write-ColorOutput "Stopping all services..." $InfoColor

    # Stop processes by ports
    $ports = @(8000, 8002, 50053, 50052, 50054)

    foreach ($port in $ports) {
        try {
            $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
            foreach ($connection in $connections) {
                $processId = $connection.OwningProcess
                if ($processId -and $processId -gt 0) {
                    try {
                        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
                        if ($process) {
                            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                            Write-ColorOutput "Stopped process on port $port (PID: $processId, Name: $($process.ProcessName))" $InfoColor
                        }
                    }
                    catch {
                        # Process might have already exited
                    }
                }
            }
        }
        catch {
            # Ignore errors
        }
    }

    # Also try to stop processes by name patterns
    $processNames = @("python", "uvicorn", "poetry")
    foreach ($processName in $processNames) {
        try {
            $processes = Get-Process -Name $processName -ErrorAction SilentlyContinue
            foreach ($process in $processes) {
                try {
                    # Check if process is related to our services by checking command line
                    $commandLine = (Get-WmiObject Win32_Process -Filter "ProcessId = $($process.Id)").CommandLine
                    if ($commandLine -and ($commandLine -like "*src/app*" -or $commandLine -like "*grpc_server*" -or $commandLine -like "*uvicorn*")) {
                        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                        Write-ColorOutput "Stopped $processName process (PID: $($process.Id))" $InfoColor
                    }
                }
                catch {
                    # Ignore errors
                }
            }
        }
        catch {
            # Ignore errors
        }
    }

    Stop-DockerServices
    Write-ColorOutput "All services stopped" $SuccessColor
}

function Start-AuthServiceInteractive {
    Write-ColorOutput "Starting Auth service in interactive mode..." $InfoColor
    $authDir = Join-Path $ScriptRoot "auth"

    # Install dependencies
    Write-ColorOutput "Installing dependencies for auth..." $InfoColor
    Push-Location $authDir
    poetry install --no-root 2>&1 | Out-Null
    Pop-Location

    # Generate proto files
    Write-ColorOutput "Generating proto files for auth..." $InfoColor
    Push-Location $authDir
    poetry run python -m grpc_tools.protoc -I proto --python_out=src --grpc_python_out=src proto/auth.proto
    Pop-Location

    # Set environment variables
    $env:NEO4J_URI = "bolt://127.0.0.1:7687"
    $env:NEO4J_ENCRYPTED = "false"
    $env:REDIS_URL = "redis://127.0.0.1:6379"
    $env:GRPC_HOST = "0.0.0.0"
    $env:GRPC_PORT = "50052"
    $env:SECRET_KEY = "your-secret-key-change-in-production"
    $env:ALGORITHM = "HS256"
    $env:ACCESS_TOKEN_EXPIRE_MINUTES = "30"
    $env:PASSWORD_MIN_LENGTH = "8"
    $env:RECOVERY_KEYS_COUNT = "10"
    $env:RECOVERY_KEY_LENGTH = "16"
    $env:LOGIN_ATTEMPTS_LIMIT = "5"
    $env:LOGIN_ATTEMPTS_WINDOW = "300"

    Write-ColorOutput "Starting Auth service on port 50052..." $SuccessColor
    Write-ColorOutput "Press Ctrl+C to stop" $WarningColor
    Push-Location $authDir
    poetry run python -m src.main
    Pop-Location
}

function Start-AIServiceInteractive {
    Write-ColorOutput "Starting AI Model service in interactive mode..." $InfoColor
    $aiDir = Join-Path $ScriptRoot "ai"

    # Install dependencies
    Write-ColorOutput "Installing dependencies for ai..." $InfoColor
    Push-Location $aiDir
    poetry install 2>&1 | Out-Null
    Pop-Location

    # Generate proto files
    Write-ColorOutput "Generating proto files for ai..." $InfoColor
    Push-Location $aiDir
    poetry run python -m grpc_tools.protoc -I./proto --python_out=./src --grpc_python_out=./src ./proto/ai_model.proto
    Pop-Location

    # Set environment variables
    $env:GRPC_HOST = "0.0.0.0"
    $env:GRPC_PORT = "50054"
    $env:MODEL_CACHE_DIR = "D:/Data/Data_Knowledge_Map/ai_models"
    $env:DEFAULT_MODEL = "meta-llama/Llama-3.2-1B-Instruct"
    $env:MODEL_DEVICE = "auto"
    $env:LOG_LEVEL = "INFO"

    # Load Hugging Face token from .env file
    $envFile = Join-Path $ScriptRoot ".env"
    if (Test-Path $envFile) {
        $envContent = Get-Content $envFile
        foreach ($line in $envContent) {
            if ($line -match "^HUGGING_FACE_TOKEN=(.+)$") {
                $env:HUGGING_FACE_TOKEN = $matches[1]
                Write-ColorOutput "Loaded Hugging Face token from .env" $InfoColor
                break
            }
        }
    }

    Write-ColorOutput "Starting AI Model service on port 50054..." $SuccessColor
    Write-ColorOutput "Press Ctrl+C to stop" $WarningColor
    Push-Location $aiDir
    poetry run python src/grpc_server.py
    Pop-Location
}

function Start-PdfToMdServiceInteractive {
    Write-ColorOutput "Starting PDF to MD service in interactive mode..." $InfoColor
    $pdfToMdDir = Join-Path $ScriptRoot "pdf_to_md"

    # Install dependencies
    Write-ColorOutput "Installing dependencies for pdf_to_md..." $InfoColor
    Push-Location $pdfToMdDir
    poetry lock 2>&1 | Out-Null
    poetry install 2>&1 | Out-Null
    Pop-Location

    # Generate proto files
    Write-ColorOutput "Generating proto files for pdf_to_md..." $InfoColor
    Push-Location $pdfToMdDir
    poetry run python -m grpc_tools.protoc --proto_path=proto --python_out=src --grpc_python_out=src proto/pdf_to_md.proto

    # Generate AI Model proto files for PDF-to-MD service
    Write-ColorOutput "Generating AI Model proto files for pdf_to_md..." $InfoColor
    poetry run python -m grpc_tools.protoc -I../ai/proto --python_out=./src --grpc_python_out=./src ../ai/proto/ai_model.proto
    Pop-Location

    # Set environment variables
    $env:PYTHONUNBUFFERED = "1"
    $env:OMP_NUM_THREADS = "2"
    $env:MKL_NUM_THREADS = "2"
    $env:OPENBLAS_NUM_THREADS = "2"
    $env:NUMEXPR_NUM_THREADS = "2"
    $env:VECLIB_MAXIMUM_THREADS = "2"
    $env:NUMBA_NUM_THREADS = "2"
    $env:PYTORCH_CUDA_ALLOC_CONF = "max_split_size_mb:512"
    $env:S3_ENDPOINT_URL = "http://127.0.0.1:9000"
    $env:S3_ACCESS_KEY = "minio"
    $env:S3_SECRET_KEY = "minio123456"
    $env:S3_REGION = "us-east-1"

    Write-ColorOutput "Starting PDF to MD service on port 50053..." $SuccessColor
    Write-ColorOutput "Press Ctrl+C to stop" $WarningColor
    Push-Location $pdfToMdDir
    poetry run python src/grpc_server.py
    Pop-Location
}

function Start-ApiServiceInteractive {
    Write-ColorOutput "Starting API service in interactive mode..." $InfoColor
    $apiDir = Join-Path $ScriptRoot "api"

    # Install dependencies
    Write-ColorOutput "Installing dependencies for api..." $InfoColor
    Push-Location $apiDir
    poetry install 2>&1 | Out-Null
    Pop-Location

    # Generate proto files
    Write-ColorOutput "Generating proto files for api..." $InfoColor
    Push-Location $apiDir

    # Create utils/generated directory if it doesn't exist
    if (-not (Test-Path "utils/generated")) {
        New-Item -Path "utils/generated" -ItemType Directory -Force | Out-Null
    }

    $graphProto = Join-Path $ScriptRoot "worker_distributed_layering_rust\proto\graph_layout.proto"
    $authProto  = Join-Path $ScriptRoot "auth\proto\auth.proto"
    $pdfProto   = Join-Path $ScriptRoot "pdf_to_md\proto\pdf_to_md.proto"
    $aiProto    = Join-Path $ScriptRoot "ai\proto\ai_model.proto"

    $incGraph = Split-Path $graphProto -Parent
    $incAuth  = Split-Path $authProto  -Parent
    $incPdf   = Split-Path $pdfProto   -Parent
    $incAI    = Split-Path $aiProto    -Parent

    poetry run python -m grpc_tools.protoc `
        -I"$incGraph" -I"$incAuth" -I"$incPdf" -I"$incAI" `
        --python_out=./utils/generated `
        --grpc_python_out=./utils/generated `
        "$graphProto" "$authProto" "$pdfProto" "$aiProto"

    if (-not (Test-Path "utils/generated/__init__.py")) {
        New-Item -Path "utils/generated/__init__.py" -ItemType File -Force | Out-Null
    }

    # Fix imports
    $grpcFiles = @("utils/generated/graph_layout_pb2_grpc.py", "utils/generated/auth_pb2_grpc.py", "utils/generated/pdf_to_md_pb2_grpc.py", "utils/generated/ai_model_pb2_grpc.py")
    foreach ($file in $grpcFiles) {
        if (Test-Path $file) {
            (Get-Content $file) `
                -replace "import graph_layout_pb2 as graph_layout__pb2", "from . import graph_layout_pb2 as graph_layout__pb2" `
                -replace "import auth_pb2 as auth__pb2", "from . import auth_pb2 as auth__pb2" `
                -replace "import pdf_to_md_pb2 as pdf_to_md__pb2", "from . import pdf_to_md_pb2 as pdf_to_md__pb2" `
                -replace "import ai_model_pb2 as ai_model__pb2", "from . import ai_model_pb2 as ai_model__pb2" | Set-Content $file
        }
    }
    Pop-Location

    # Set environment variables
    $env:NEO4J_URI = "bolt://127.0.0.1:7687"
    $env:NEO4J_ENCRYPTED = "false"
    $env:NEO4J_USER = "neo4j"
    $env:NEO4J_PASSWORD = "password"
    $env:LAYOUT_SERVICE_HOST = "127.0.0.1"
    $env:LAYOUT_SERVICE_PORT = "50051"
    $env:AUTH_SERVICE_HOST = "127.0.0.1"
    $env:AUTH_SERVICE_PORT = "50052"
    $env:PDF_TO_MD_SERVICE_HOST = "127.0.0.1"
    $env:PDF_TO_MD_SERVICE_PORT = "50053"
    $env:AI_MODEL_SERVICE_HOST = "127.0.0.1"
    $env:AI_MODEL_SERVICE_PORT = "50054"
    $env:S3_ENDPOINT_URL = "http://127.0.0.1:9000"
    $env:S3_ACCESS_KEY = "minio"
    $env:S3_SECRET_KEY = "minio123456"
    $env:S3_REGION = "us-east-1"
    $env:DEBUG = "true"
    $env:OMP_NUM_THREADS = "2"
    $env:MKL_NUM_THREADS = "2"
    $env:OPENBLAS_NUM_THREADS = "2"
    $env:NUMEXPR_NUM_THREADS = "2"
    $env:VECLIB_MAXIMUM_THREADS = "2"
    $env:NUMBA_NUM_THREADS = "2"
    $env:PYTORCH_CUDA_ALLOC_CONF = "max_split_size_mb:512"

    Write-ColorOutput "Starting API service on port 8000..." $SuccessColor
    Write-ColorOutput "Press Ctrl+C to stop" $WarningColor
    Push-Location $apiDir
    poetry run python -m uvicorn src.app:app --host 0.0.0.0 --port 8000
    Pop-Location
}

function Restart-IndividualService {
    param(
        [string]$ServiceName
    )

    Write-ColorOutput "=== Restarting $ServiceName service (interactive mode) ===" $InfoColor

    switch ($ServiceName.ToLower()) {
        "auth" {
            Stop-AuthService
            Start-Sleep -Seconds 2
            Start-AuthServiceInteractive
        }
        "ai" {
            Stop-AIService
            Start-Sleep -Seconds 2
            Start-AIServiceInteractive
        }
        "pdf_to_md" {
            Stop-PdfToMdService
            Start-Sleep -Seconds 2
            Start-PdfToMdServiceInteractive
        }
        "api" {
            Stop-ApiService
            Start-Sleep -Seconds 2
            Start-ApiServiceInteractive
        }
        default {
            Write-ColorOutput "Unknown service: $ServiceName" $ErrorColor
            Write-ColorOutput "Available services: auth, ai, pdf_to_md, api" $InfoColor
            return $false
        }
    }
}

function Show-Logs {
    param(
        [string]$ServiceName = ""
    )
    
    if ($ServiceName -eq "") {
        Write-ColorOutput "Available services for log monitoring:" $InfoColor
        Write-ColorOutput "  - neo4j (Docker)" $InfoColor
        Write-ColorOutput "  - redis (Docker)" $InfoColor
        Write-ColorOutput "  - s3 (Docker)" $InfoColor
        Write-ColorOutput "  - auth (Host)" $InfoColor
        Write-ColorOutput "  - ai (Host)" $InfoColor
        Write-ColorOutput "  - pdf_to_md (Host)" $InfoColor
        Write-ColorOutput "  - api (Host)" $InfoColor
        Write-ColorOutput "`nUsage: .\start_local_dev.ps1 -Logs -Service <service_name>" $WarningColor
        Write-ColorOutput "Example: .\start_local_dev.ps1 -Logs -Service api" $WarningColor
        return
    }
    
    switch ($ServiceName.ToLower()) {
        "neo4j" {
            Write-ColorOutput "Showing Neo4j logs (Docker)..." $InfoColor
            Write-ColorOutput "Press Ctrl+C to stop monitoring" $WarningColor
            docker-compose logs -f neo4j
        }
        "redis" {
            Write-ColorOutput "Showing Redis logs (Docker)..." $InfoColor
            Write-ColorOutput "Press Ctrl+C to stop monitoring" $WarningColor
            docker-compose logs -f redis
        }
        "s3" {
            Write-ColorOutput "Showing MinIO S3 logs (Docker)..." $InfoColor
            Write-ColorOutput "Press Ctrl+C to stop monitoring" $WarningColor
            docker-compose logs -f s3
        }
        "auth" {
            Write-ColorOutput "Showing Auth service logs (Host)..." $InfoColor
            Write-ColorOutput "Press Ctrl+C to stop monitoring" $WarningColor

            $authDir = Join-Path $ScriptRoot "auth"
            $logFile = Join-Path $authDir "logs\auth.log"
            $errorFile = Join-Path $authDir "logs\auth_error.log"

            if (Test-Path $logFile) {
                Write-ColorOutput "Monitoring log file: $logFile" $InfoColor
                if (Test-Path $errorFile) {
                    Write-ColorOutput "Also monitoring error file: $errorFile" $InfoColor
                }
                Get-Content $logFile -Wait -Tail 50
            } else {
                Write-ColorOutput "Log file not found: $logFile" $ErrorColor
                Write-ColorOutput "Auth service may not be running or logging is not configured." $WarningColor
            }
        }
        "ai" {
            Write-ColorOutput "Showing AI Model service logs (Host)..." $InfoColor
            Write-ColorOutput "Press Ctrl+C to stop monitoring" $WarningColor

            $aiDir = Join-Path $ScriptRoot "ai"
            $logFile = Join-Path $aiDir "logs\ai_model.log"
            $errorFile = Join-Path $aiDir "logs\ai_model_error.log"

            if (Test-Path $logFile) {
                Write-ColorOutput "Monitoring log file: $logFile" $InfoColor
                if (Test-Path $errorFile) {
                    Write-ColorOutput "Also monitoring error file: $errorFile" $InfoColor
                }
                Get-Content $logFile -Wait -Tail 50
            } else {
                Write-ColorOutput "Log file not found: $logFile" $ErrorColor
                Write-ColorOutput "AI Model service may not be running or logging is not configured." $WarningColor
            }
        }
        "pdf_to_md" {
            Write-ColorOutput "Showing PDF to MD service logs (Host)..." $InfoColor
            Write-ColorOutput "Press Ctrl+C to stop monitoring" $WarningColor
            
            $pdfToMdDir = Join-Path $ScriptRoot "pdf_to_md"
            $logFile = Join-Path $pdfToMdDir "logs\pdf_to_md.log"
            $errorFile = Join-Path $pdfToMdDir "logs\pdf_to_md_error.log"
            
            if (Test-Path $logFile) {
                Write-ColorOutput "Monitoring log file: $logFile" $InfoColor
                if (Test-Path $errorFile) {
                    Write-ColorOutput "Also monitoring error file: $errorFile" $InfoColor
                }
                Get-Content $logFile -Wait -Tail 50
            } else {
                Write-ColorOutput "Log file not found: $logFile" $ErrorColor
                Write-ColorOutput "PDF to MD service may not be running or logging is not configured." $WarningColor
            }
        }
        "api" {
            Write-ColorOutput "Showing API service logs (Host)..." $InfoColor
            Write-ColorOutput "Press Ctrl+C to stop monitoring" $WarningColor
            
            $apiDir = Join-Path $ScriptRoot "api"
            $logFile = Join-Path $apiDir "logs\api.log"
            $errorFile = Join-Path $apiDir "logs\api_error.log"
            
            if (Test-Path $logFile) {
                Write-ColorOutput "Monitoring log file: $logFile" $InfoColor
                if (Test-Path $errorFile) {
                    Write-ColorOutput "Also monitoring error file: $errorFile" $InfoColor
                }
                Get-Content $logFile -Wait -Tail 50
            } else {
                Write-ColorOutput "Log file not found: $logFile" $ErrorColor
                Write-ColorOutput "API service may not be running or logging is not configured." $WarningColor
            }
        }
        default {
            Write-ColorOutput "Unknown service: $ServiceName" $ErrorColor
            Write-ColorOutput "Available services: neo4j, redis, s3, auth, ai, pdf_to_md, api" $InfoColor
        }
    }
}

# Main logic
if ($Stop) {
    Stop-AllServices
    exit 0
}

if ($Status) {
    Show-Status
    exit 0
}

if ($Logs) {
    Show-Logs -ServiceName $Service
    exit 0
}

# Handle selective service restart
if ($Service -and -not $Logs) {
    Restart-IndividualService -ServiceName $Service
    # Note: Service runs in foreground, so we never reach this point unless user stops it
    exit 0
}

if ($Restart) {
    Stop-AllServices
    Start-Sleep -Seconds 3
}

if ($HostOnly) {
    Write-ColorOutput "=== Restarting Host Services Only ===" $InfoColor
    Write-ColorOutput "Docker services (neo4j, redis, s3) will not be touched" $WarningColor
    Write-ColorOutput ""

    # Check that Docker services are already running
    Write-ColorOutput "Checking Docker services are running..." $InfoColor
    if (-not (Test-Port -Port 7687 -ServiceName "Neo4j")) {
        Write-ColorOutput "Neo4j (port 7687) is not running. Please start Docker services first." $ErrorColor
        Write-ColorOutput "Run: .\start_local_dev.ps1" $InfoColor
        exit 1
    }
    if (-not (Test-Port -Port 6379 -ServiceName "Redis")) {
        Write-ColorOutput "Redis (port 6379) is not running. Please start Docker services first." $ErrorColor
        Write-ColorOutput "Run: .\start_local_dev.ps1" $InfoColor
        exit 1
    }
    if (-not (Test-Port -Port 9000 -ServiceName "S3")) {
        Write-ColorOutput "S3/MinIO (port 9000) is not running. Please start Docker services first." $ErrorColor
        Write-ColorOutput "Run: .\start_local_dev.ps1" $InfoColor
        exit 1
    }
    Write-ColorOutput "All Docker services are running" $SuccessColor

    # Stop only host services
    Write-ColorOutput "`nStopping host services..." $InfoColor

    # Stop Auth service
    Write-ColorOutput "Stopping Auth service..." $InfoColor
    $authProcesses = Get-Process | Where-Object { $_.ProcessName -eq "python" -and $_.CommandLine -like "*auth_service.py*" }
    if ($authProcesses) {
        $authProcesses | Stop-Process -Force
        Write-ColorOutput "Auth service stopped" $SuccessColor
    }

    # Stop PDF to MD service
    Write-ColorOutput "Stopping PDF to MD service..." $InfoColor
    $pdfProcesses = Get-Process | Where-Object { $_.ProcessName -eq "python" -and $_.CommandLine -like "*pdf_to_md_service.py*" }
    if ($pdfProcesses) {
        $pdfProcesses | Stop-Process -Force
        Write-ColorOutput "PDF to MD service stopped" $SuccessColor
    }

    # Stop API service
    Write-ColorOutput "Stopping API service..." $InfoColor
    $apiProcesses = Get-Process | Where-Object { $_.ProcessName -eq "python" -and $_.CommandLine -like "*uvicorn*" }
    if ($apiProcesses) {
        $apiProcesses | Stop-Process -Force
        Write-ColorOutput "API service stopped" $SuccessColor
    }

    Start-Sleep -Seconds 2

    # Start host services
    Write-ColorOutput "`n1. Starting Auth service..." $InfoColor
    $authResult = Start-AuthService
    if (-not $authResult) {
        Write-ColorOutput "Auth service failed to start - continuing with other services" $WarningColor
    }

    Write-ColorOutput "`n2. Starting AI Model service..." $InfoColor
    $aiResult = Start-AIService
    if (-not $aiResult) {
        Write-ColorOutput "AI Model service failed to start - continuing with other services" $WarningColor
    }

    Write-ColorOutput "`n3. Starting PDF to MD service..." $InfoColor
    $pdfToMdResult = Start-PdfToMdService
    if (-not $pdfToMdResult) {
        Write-ColorOutput "PDF to MD service failed to start - continuing with other services" $WarningColor
    }

    Write-ColorOutput "`n4. Starting API service..." $InfoColor
    $apiResult = Start-ApiService
    if (-not $apiResult) {
        Write-ColorOutput "API service failed to start - continuing with other services" $WarningColor
    }

    Write-ColorOutput "`n=== Host services restart completed ===" $SuccessColor
    Show-Status

    Write-ColorOutput "`nDocker services were not restarted:" $InfoColor
    Write-ColorOutput "  - Neo4j (port 7687)" $InfoColor
    Write-ColorOutput "  - Redis (port 6379)" $InfoColor
    Write-ColorOutput "  - S3/MinIO (port 9000)" $InfoColor

    exit 0
}

Write-ColorOutput "=== Starting Knowledge Map Microservices ===" $InfoColor
Write-ColorOutput "Version: PowerShell script for local development" $InfoColor
Write-ColorOutput ""

# Stop any existing services first
Write-ColorOutput "Stopping any existing services..." $InfoColor
Stop-AllServices
Start-Sleep -Seconds 2

# Check for Docker
try {
    docker --version | Out-Null
    Write-ColorOutput "Docker found" $SuccessColor
    
    # Check if Docker daemon is running
    try {
        $null = docker info 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "Docker daemon is running" $SuccessColor
        } else {
            throw "Docker daemon not running"
        }
    }
    catch {
        Write-ColorOutput "Docker daemon is not running. Please start Docker Desktop first." $ErrorColor
        Write-ColorOutput "You can start Docker Desktop from Start menu or run: Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'" $WarningColor
        exit 1
    }
}
catch {
    Write-ColorOutput "Docker not found. Install Docker Desktop" $ErrorColor
    exit 1
}

# Check for Poetry
try {
    poetry --version | Out-Null
    Write-ColorOutput "Poetry found" $SuccessColor
}
catch {
    Write-ColorOutput "Poetry not found. Install Poetry: https://python-poetry.org/docs/#installation" $ErrorColor
    exit 1
}


# Start services
Write-ColorOutput "`n1. Starting Docker services..." $InfoColor
Start-DockerServices

Write-ColorOutput "`n2. Starting Auth service..." $InfoColor
$authResult = Start-AuthService
if (-not $authResult) {
    Write-ColorOutput "Auth service failed to start - continuing with other services" $WarningColor
}

Write-ColorOutput "`n3. Starting AI Model service..." $InfoColor
$aiResult = Start-AIService
if (-not $aiResult) {
    Write-ColorOutput "AI Model service failed to start - continuing with other services" $WarningColor
}

Write-ColorOutput "`n4. Starting PDF to MD service..." $InfoColor
$pdfToMdResult = Start-PdfToMdService
if (-not $pdfToMdResult) {
    Write-ColorOutput "PDF to MD service failed to start - continuing with other services" $WarningColor
}

Write-ColorOutput "`n5. Starting API service..." $InfoColor
$apiResult = Start-ApiService
if (-not $apiResult) {
    Write-ColorOutput "API service failed to start - continuing with other services" $WarningColor
}

Write-ColorOutput "`n=== Startup completed ===" $SuccessColor
Show-Status

Write-ColorOutput "`nTo stop all services run:" $WarningColor
Write-ColorOutput "  .\start_local_dev.ps1 -Stop" $WarningColor
Write-ColorOutput "`nTo restart only host services (keep Docker running):" $WarningColor
Write-ColorOutput "  .\start_local_dev.ps1 -HostOnly" $WarningColor
Write-ColorOutput "`nTo restart individual service (interactive mode with live logs):" $WarningColor
Write-ColorOutput "  .\start_local_dev.ps1 -Service <service_name>" $WarningColor
Write-ColorOutput "  Example: .\start_local_dev.ps1 -Service pdf_to_md" $WarningColor
Write-ColorOutput "  Available: auth, ai, pdf_to_md, api" $InfoColor
Write-ColorOutput "  Note: Service runs in foreground with live output. Press Ctrl+C to stop." $InfoColor
Write-ColorOutput "`nTo check status run:" $WarningColor
Write-ColorOutput "  .\start_local_dev.ps1 -Status" $WarningColor
Write-ColorOutput "`nTo view logs run:" $WarningColor
Write-ColorOutput "  .\start_local_dev.ps1 -Logs -Service <service_name>" $WarningColor
Write-ColorOutput "  Example: .\start_local_dev.ps1 -Logs -Service api" $WarningColor
Write-ColorOutput "`n🦀 Rust Graph Layout service can be started independently:" $SuccessColor
Write-ColorOutput "  cd worker_distributed_layering_rust && cargo run --release" $InfoColor
Write-ColorOutput "  - gRPC: localhost:50051" $InfoColor
Write-ColorOutput "  - Metrics: http://localhost:9090/metrics" $InfoColor