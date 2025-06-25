#!/usr/bin/env powershell

Write-Host "🚀 Обновление алгоритма закреплённых блоков..." -ForegroundColor Green

# 1. Тестируем алгоритм локально
Write-Host "`n📋 Тестируем алгоритм локально..." -ForegroundColor Cyan
python test_pinned_simple.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Тест алгоритма провален!" -ForegroundColor Red
    Read-Host "Нажмите Enter для продолжения в любом случае..."
} else {
    Write-Host "✅ Локальный тест успешен!" -ForegroundColor Green
}

# 2. Останавливаем существующие процессы
Write-Host "`n🛑 Останавливаем существующие сервисы..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.ProcessName -like "*python*" -and $_.CommandLine -like "*grpc*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process | Where-Object { $_.ProcessName -like "*python*" -and $_.CommandLine -like "*uvicorn*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# Проверяем и освобождаем порты
$layeringPort = Get-NetTCPConnection -LocalPort 50051 -ErrorAction SilentlyContinue
if ($layeringPort) {
    $process = $layeringPort.OwningProcess
    Write-Host "Освобождаем порт 50051 (PID: $process)..." -ForegroundColor Red
    Stop-Process -Id $process -Force -ErrorAction SilentlyContinue
}

$apiPort = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($apiPort) {
    $process = $apiPort.OwningProcess
    Write-Host "Освобождаем порт 8000 (PID: $process)..." -ForegroundColor Red
    Stop-Process -Id $process -Force -ErrorAction SilentlyContinue
}

Start-Sleep 2

# 3. Запускаем layering сервис
Write-Host "`n🔧 Запускаем layering сервис..." -ForegroundColor Cyan
$layeringPath = Join-Path $PWD "layering"
Start-Process powershell -ArgumentList "-Command", "Set-Location '$layeringPath'; Write-Host 'Starting layering service...'; poetry run python src/main.py" -WindowStyle Minimized

# Ждём запуска layering сервиса
Write-Host "Ожидаем запуска layering сервиса..." -ForegroundColor Yellow
Start-Sleep 5

# Проверяем что сервис запустился
$layeringRunning = Get-NetTCPConnection -LocalPort 50051 -ErrorAction SilentlyContinue
if ($layeringRunning) {
    Write-Host "✅ Layering сервис запущен на порту 50051" -ForegroundColor Green
} else {
    Write-Host "❌ Layering сервис не запустился!" -ForegroundColor Red
}

# 4. Запускаем API сервис
Write-Host "`n🌐 Запускаем API сервис..." -ForegroundColor Cyan
$apiPath = Join-Path $PWD "api"
Start-Process powershell -ArgumentList "-Command", "Set-Location '$apiPath'; Write-Host 'Starting API service...'; poetry run uvicorn main:app --host 0.0.0.0 --port 8000" -WindowStyle Minimized

# Ждём запуска API сервиса
Write-Host "Ожидаем запуска API сервиса..." -ForegroundColor Yellow
Start-Sleep 5

# Проверяем что API сервис запустился
$apiRunning = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($apiRunning) {
    Write-Host "✅ API сервис запущен на порту 8000" -ForegroundColor Green
} else {
    Write-Host "❌ API сервис не запустился!" -ForegroundColor Red
}

Write-Host "`n🎯 Статус сервисов:" -ForegroundColor Green
Write-Host "   - Layering сервис: http://localhost:50051" -ForegroundColor White
Write-Host "   - API сервис: http://localhost:8000" -ForegroundColor White
Write-Host "   - Frontend: http://localhost:5173" -ForegroundColor White

Write-Host "`n💡 Теперь можете:" -ForegroundColor Cyan
Write-Host "   1. Открыть браузер на http://localhost:5173" -ForegroundColor White
Write-Host "   2. Закрепить любой блок правой кнопкой мыши" -ForegroundColor White
Write-Host "   3. Проверить что он переходит на новый уровень" -ForegroundColor White

Read-Host "`nНажмите Enter для завершения..." 