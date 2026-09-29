Set-Location "D:\Knowledge_Map\api"
$registryPythonPath = (Resolve-Path "..\shared\model_registry").Path
$existingPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH")
if ([string]::IsNullOrWhiteSpace($existingPythonPath)) {
    $env:PYTHONPATH = $registryPythonPath
} else {
    $env:PYTHONPATH = $registryPythonPath + ";" + $existingPythonPath
}
poetry run python -m uvicorn web.app:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 120
