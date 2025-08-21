# PowerShell script for starting distributed graph layout worker
# Optimized for Windows system with 16GB RAM

param(
    [string]$Mode = "dev",  # dev, production, monitoring
    [switch]$Build = $false,  # Rebuild images
    [switch]$Logs = $false   # Show logs after startup
)

Write-Host "[START] Starting distributed graph layout worker" -ForegroundColor Green
Write-Host "Mode: $Mode" -ForegroundColor Yellow

# Navigate to project root directory
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $projectRoot

# Check Docker availability
try {
    docker --version | Out-Null
    Write-Host "[OK] Docker is available" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not installed or unavailable" -ForegroundColor Red
    exit 1
}

# Check Docker Compose availability
try {
    docker-compose --version | Out-Null
    Write-Host "[OK] Docker Compose is available" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker Compose is not installed or unavailable" -ForegroundColor Red
    exit 1
}

# Determine profiles for startup
$profiles = @()
switch ($Mode) {
    "dev" { 
        $profiles = @("layout_worker_manager", "layout_worker_1", "layout_persistence_worker")
        Write-Host "[MODE] Development mode: minimal configuration" -ForegroundColor Cyan
    }
    "production" { 
        $profiles = @("layout_worker_manager", "layout_worker_1", "layout_optimization_worker", "layout_persistence_worker")
        Write-Host "[MODE] Production mode: full configuration" -ForegroundColor Cyan
    }
    "monitoring" { 
        $profiles = @("layout_worker_manager", "layout_worker_1", "layout_persistence_worker", "layout_flower")
        Write-Host "[MODE] Monitoring mode: includes Flower" -ForegroundColor Cyan
    }
    default {
        Write-Host "[ERROR] Unknown mode: $Mode" -ForegroundColor Red
        Write-Host "Available modes: dev, production, monitoring" -ForegroundColor Yellow
        exit 1
    }
}

# Rebuild images if needed
if ($Build) {
    Write-Host "[BUILD] Rebuilding images..." -ForegroundColor Yellow
    
    # Stop workers before rebuild
    foreach ($service in $profiles) {
        Write-Host "Stopping $service..." -ForegroundColor Gray
        docker-compose stop $service 2>$null
    }
    
    # Rebuild images
    docker-compose build layout_worker_manager
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Image build failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Images rebuilt" -ForegroundColor Green
}

# Check dependencies (Neo4j and Redis)
Write-Host "[CHECK] Checking dependencies..." -ForegroundColor Yellow

$neo4jRunning = docker-compose ps neo4j | Select-String "Up"
$redisRunning = docker-compose ps redis | Select-String "Up"

if (-not $neo4jRunning) {
    Write-Host "[WARN] Neo4j is not running. Starting..." -ForegroundColor Yellow
    docker-compose up -d neo4j
    
    # Wait for Neo4j readiness
    Write-Host "Waiting for Neo4j readiness..." -ForegroundColor Gray
    $timeout = 60
    $elapsed = 0
    do {
        Start-Sleep -Seconds 5
        $elapsed += 5
        $healthCheck = docker-compose ps neo4j | Select-String "healthy"
        if ($healthCheck) {
            Write-Host "[OK] Neo4j is ready" -ForegroundColor Green
            break
        }
        if ($elapsed -ge $timeout) {
            Write-Host "[ERROR] Neo4j not ready after $timeout seconds" -ForegroundColor Red
            exit 1
        }
        Write-Host "Neo4j not ready yet, waiting... ($elapsed/$timeout sec)" -ForegroundColor Gray
    } while ($true)
}

if (-not $redisRunning) {
    Write-Host "[WARN] Redis is not running. Starting..." -ForegroundColor Yellow
    docker-compose up -d redis
    
    # Wait for Redis readiness
    Start-Sleep -Seconds 10
    $redisCheck = docker-compose ps redis | Select-String "healthy"
    if ($redisCheck) {
        Write-Host "[OK] Redis is ready" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Redis is not ready" -ForegroundColor Red
        exit 1
    }
}

# Start workers
Write-Host "[START] Starting layout workers..." -ForegroundColor Green

foreach ($service in $profiles) {
    Write-Host "Starting $service..." -ForegroundColor Cyan
    docker-compose up -d $service
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to start $service" -ForegroundColor Red
        exit 1
    }
}

# Check service status
Start-Sleep -Seconds 5
Write-Host "" -ForegroundColor Yellow
Write-Host "[STATUS] Service status:" -ForegroundColor Yellow
foreach ($service in $profiles) {
    $status = docker-compose ps $service
    if ($status | Select-String "Up") {
        Write-Host "[OK] ${service}: Running" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] ${service}: Failed" -ForegroundColor Red
    }
}

# Show available endpoints
Write-Host "" -ForegroundColor Yellow
Write-Host "[ENDPOINTS] Available endpoints:" -ForegroundColor Yellow
Write-Host "  Worker metrics: http://localhost:9100/metrics" -ForegroundColor Cyan
if ($Mode -eq "monitoring") {
    Write-Host "  Flower (Celery UI): http://localhost:5555" -ForegroundColor Cyan
}
Write-Host "  Neo4j Browser: http://localhost:7474" -ForegroundColor Cyan

# Show useful commands
Write-Host "" -ForegroundColor Yellow
Write-Host "[COMMANDS] Useful commands:" -ForegroundColor Yellow
Write-Host "  Logs: docker-compose logs -f layout_worker_manager" -ForegroundColor Gray
Write-Host "  Stop: docker-compose stop layout_worker_manager layout_worker_1 layout_persistence_worker" -ForegroundColor Gray
Write-Host "  Status: docker-compose ps | findstr layout" -ForegroundColor Gray
Write-Host "  Health: docker exec knowledge_map_layout_manager python main.py health" -ForegroundColor Gray

# Show logs if requested
if ($Logs) {
    Write-Host "" -ForegroundColor Yellow
    Write-Host "[LOGS] Worker logs (Ctrl+C to exit):" -ForegroundColor Yellow
    docker-compose logs -f layout_worker_manager
}

Write-Host "" -ForegroundColor Yellow
Write-Host "[SUCCESS] Distributed layout worker started!" -ForegroundColor Green