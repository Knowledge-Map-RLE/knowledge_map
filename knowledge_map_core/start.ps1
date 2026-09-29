Set-Location $PSScriptRoot
$registryPythonPath = (Resolve-Path "..\shared\model_registry").Path
$existingPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH")
if ([string]::IsNullOrWhiteSpace($existingPythonPath)) {
    $env:PYTHONPATH = $registryPythonPath
} else {
    $env:PYTHONPATH = $registryPythonPath + ";" + $existingPythonPath
}

Write-Host "Starting Knowledge Language gRPC server on port 50056..."
poetry run python -m src.main
