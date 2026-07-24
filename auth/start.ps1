Set-Location $PSScriptRoot

$port = 50057

Write-Host "Starting Auth gRPC server on port $port..." -ForegroundColor Cyan

# Pre-warm (создаёт .pyc кэш)
Write-Host "Pre-warming imports..."
poetry run python -c "
import src.config
import src.models
import src.schemas
import src.utils
print('Pre-warm OK')
" 2>&1 | Out-Null

# Запуск
poetry run python -m src.main
