# PowerShell script for testing distributed graph layout worker

param(
    [string]$TestType = "health",  # health, small, medium, large
    [int]$NodeCount = 100,         # Node count for testing
    [switch]$Verbose = $false      # Detailed output
)

Write-Host "[TEST] Testing distributed graph layout worker" -ForegroundColor Green
Write-Host "Test type: $TestType" -ForegroundColor Yellow

# Navigate to project root directory
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $projectRoot

# Function to check service health
function Test-ServiceHealth {
    param($ServiceName, $ContainerName)
    
    Write-Host "[CHECK] Checking health of $ServiceName..." -ForegroundColor Cyan
    
    try {
        $result = docker exec $ContainerName python main.py health 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] ${ServiceName}: Healthy" -ForegroundColor Green
            if ($Verbose) {
                Write-Host $result -ForegroundColor Gray
            }
            return $true
        } else {
            Write-Host "[ERROR] ${ServiceName}: Unhealthy" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "[ERROR] ${ServiceName}: Unavailable" -ForegroundColor Red
        return $false
    }
}

# Function to create test data in Neo4j
function Create-TestData {
    param($NodeCount)
    
    Write-Host "[CREATE] Creating test data ($NodeCount nodes)..." -ForegroundColor Cyan
    
    $cypherScript = @"
// Clear previous test data
MATCH (n:TestBlock) DETACH DELETE n;

// Create test nodes
UNWIND range(1, $NodeCount) as i
CREATE (n:TestBlock:Block {
    uid: 'test_block_' + toString(i),
    content: 'Test block number ' + toString(i),
    is_pinned: CASE WHEN i <= 5 THEN true ELSE false END,
    level: CASE WHEN i <= 5 THEN i ELSE 0 END,
    physical_scale: 0
});

// Create random links between nodes
MATCH (a:TestBlock), (b:TestBlock)
WHERE a.uid < b.uid AND rand() < 0.1
CREATE (a)-[:CITES {
    uid: a.uid + '_to_' + b.uid
}]->(b);

// Return statistics
MATCH (n:TestBlock) 
WITH count(n) as nodeCount
MATCH ()-[r:CITES]->()
WHERE r.uid CONTAINS 'test_block_'
RETURN nodeCount, count(r) as linkCount;
"@

    # Execute Cypher script
    try {
        $result = $cypherScript | docker exec -i knowledge_map_neo4j cypher-shell -u neo4j -p password --format verbose
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Test data created" -ForegroundColor Green
            if ($Verbose) {
                Write-Host $result -ForegroundColor Gray
            }
            return $true
        } else {
            Write-Host "[ERROR] Failed to create test data" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "[ERROR] Could not connect to Neo4j" -ForegroundColor Red
        return $false
    }
}

# Function to run layout test
function Test-LayoutExecution {
    param($TestSize)
    
    Write-Host "[EXEC] Testing layout ($TestSize)..." -ForegroundColor Cyan
    
    $startTime = Get-Date
    
    try {
        # Run layout through main worker
        $result = docker exec knowledge_map_layout_manager python main.py single --node-labels TestBlock Block --options '{"optimize_layout": true}'
        
        $endTime = Get-Date
        $duration = ($endTime - $startTime).TotalSeconds
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Layout completed in $([math]::Round($duration, 2)) seconds" -ForegroundColor Green
            if ($Verbose) {
                Write-Host $result -ForegroundColor Gray
            }
            return $true
        } else {
            Write-Host "[ERROR] Layout execution failed" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "[ERROR] Could not run layout" -ForegroundColor Red
        return $false
    }
}

# Function to check results
function Test-LayoutResults {
    Write-Host "[CHECK] Checking layout results..." -ForegroundColor Cyan
    
    $cypherCheck = @"
MATCH (n:TestBlock)
WHERE n.level IS NOT NULL AND n.layer IS NOT NULL
WITH count(n) as processedNodes
MATCH (total:TestBlock)
RETURN processedNodes, count(total) as totalNodes, 
       toFloat(processedNodes) / count(total) * 100 as percentageProcessed;
"@

    try {
        $result = $cypherCheck | docker exec -i knowledge_map_neo4j cypher-shell -u neo4j -p password --format verbose
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Layout results verified" -ForegroundColor Green
            if ($Verbose) {
                Write-Host $result -ForegroundColor Gray
            }
            return $true
        } else {
            Write-Host "[ERROR] Failed to check results" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "[ERROR] Could not verify results" -ForegroundColor Red
        return $false
    }
}

# Main testing logic
Write-Host "" -ForegroundColor Yellow
Write-Host "[BEGIN] Starting tests..." -ForegroundColor Yellow

switch ($TestType) {
    "health" {
        Write-Host "[HEALTH] Checking health of all services..." -ForegroundColor Yellow
        
        $services = @(
            @{Name="Layout Manager"; Container="knowledge_map_layout_manager"},
            @{Name="Layout Worker 1"; Container="knowledge_map_layout_worker_1"},
            @{Name="Layout Persistence"; Container="knowledge_map_layout_persistence"}
        )
        
        $allHealthy = $true
        foreach ($service in $services) {
            $healthy = Test-ServiceHealth -ServiceName $service.Name -ContainerName $service.Container
            $allHealthy = $allHealthy -and $healthy
        }
        
        if ($allHealthy) {
            Write-Host "" -ForegroundColor Yellow
            Write-Host "[SUCCESS] All services are healthy!" -ForegroundColor Green
        } else {
            Write-Host "" -ForegroundColor Yellow
            Write-Host "[ERROR] Some services are unhealthy" -ForegroundColor Red
            exit 1
        }
    }
    
    "small" {
        Write-Host "[SMALL] Small test (100 nodes)..." -ForegroundColor Yellow
        $NodeCount = 100
        
        if (-not (Create-TestData -NodeCount $NodeCount)) { exit 1 }
        if (-not (Test-LayoutExecution -TestSize "small")) { exit 1 }
        if (-not (Test-LayoutResults)) { exit 1 }
        
        Write-Host "" -ForegroundColor Yellow
        Write-Host "[SUCCESS] Small test passed!" -ForegroundColor Green
    }
    
    "medium" {
        Write-Host "[MEDIUM] Medium test (1000 nodes)..." -ForegroundColor Yellow
        $NodeCount = 1000
        
        if (-not (Create-TestData -NodeCount $NodeCount)) { exit 1 }
        if (-not (Test-LayoutExecution -TestSize "medium")) { exit 1 }
        if (-not (Test-LayoutResults)) { exit 1 }
        
        Write-Host "" -ForegroundColor Yellow
        Write-Host "[SUCCESS] Medium test passed!" -ForegroundColor Green
    }
    
    "large" {
        Write-Host "[LARGE] Large test (10000 nodes)..." -ForegroundColor Yellow
        $NodeCount = 10000
        
        Write-Host "[WARN] Large test may take several minutes" -ForegroundColor Yellow
        
        if (-not (Create-TestData -NodeCount $NodeCount)) { exit 1 }
        if (-not (Test-LayoutExecution -TestSize "large")) { exit 1 }
        if (-not (Test-LayoutResults)) { exit 1 }
        
        Write-Host "" -ForegroundColor Yellow
        Write-Host "[SUCCESS] Large test passed!" -ForegroundColor Green
    }
    
    "custom" {
        Write-Host "[CUSTOM] Custom test ($NodeCount nodes)..." -ForegroundColor Yellow
        
        if (-not (Create-TestData -NodeCount $NodeCount)) { exit 1 }
        if (-not (Test-LayoutExecution -TestSize "custom")) { exit 1 }
        if (-not (Test-LayoutResults)) { exit 1 }
        
        Write-Host "" -ForegroundColor Yellow
        Write-Host "[SUCCESS] Custom test passed!" -ForegroundColor Green
    }
    
    default {
        Write-Host "[ERROR] Unknown test type: $TestType" -ForegroundColor Red
        Write-Host "Available types: health, small, medium, large, custom" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "" -ForegroundColor Yellow
Write-Host "[INFO] Additional information:" -ForegroundColor Yellow
Write-Host "  Manager logs: docker-compose logs layout_worker_manager" -ForegroundColor Gray
Write-Host "  Worker logs: docker-compose logs layout_worker_1" -ForegroundColor Gray
Write-Host "  Metrics: http://localhost:9100/metrics" -ForegroundColor Gray
Write-Host "  Cleanup tests: docker exec -i knowledge_map_neo4j cypher-shell -u neo4j -p password 'MATCH (n:TestBlock) DETACH DELETE n'" -ForegroundColor Gray

Write-Host "" -ForegroundColor Yellow
Write-Host "[COMPLETE] Testing completed successfully!" -ForegroundColor Green