$ErrorActionPreference = 'Stop'

# Консоль, включая русские сообщения, работает в UTF-8.
$utf8Encoding = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8Encoding
[Console]::OutputEncoding = $utf8Encoding
$OutputEncoding = $utf8Encoding
try { chcp.com 65001 | Out-Null } catch { }

$serviceRoot = $PSScriptRoot
$repositoryRoot = Split-Path -Parent $serviceRoot
$stateDirectory = Join-Path $repositoryRoot 'tmp\pdf_to_md'
$statePath = Join-Path $stateDirectory 'service-state.json'
$temporaryStatePath = Join-Path $stateDirectory 'service-state.tmp.json'
$stopScript = Join-Path $serviceRoot 'stop.ps1'
$serviceMutex = [System.Threading.Mutex]::new($false, 'KnowledgeMapPdfToMdService-50053')
$mutexOwned = $false
Set-Location $serviceRoot

# Локальная разработка использует те же фиксированные порты, что и production.
$env:OTEL_EXPORTER_OTLP_ENDPOINT = 'http://127.0.0.1:4317'
$env:OTEL_SERVICE_NAME = 'pdf_to_md'
$env:OTEL_SERVICE_VERSION = '0.1.0'
$env:OTEL_METRIC_EXPORT_INTERVAL = '30000'
$env:LOG_FORMAT = 'logfmt'
$env:HF_HOME = [System.IO.Path]::GetFullPath((Join-Path $serviceRoot '..\tmp\indra_models'))
Remove-Item Env:INDRA_OCR_MODEL_DIR -ErrorAction SilentlyContinue

$grpcProcess = $null
$restProcess = $null
$cleanupRequired = $false
$serviceState = [ordered]@{ grpc = $null; rest = $null }

function Save-ServiceState {
    New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null
    $json = $serviceState | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($temporaryStatePath, $json, $utf8Encoding)
    Move-Item -LiteralPath $temporaryStatePath -Destination $statePath -Force
}

function Register-ServiceProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process
    )

    $Process.Refresh()
    $serviceState[$Name] = @{
        pid = [int]$Process.Id
        startedUtc = $Process.StartTime.ToUniversalTime().ToString('o')
    }
    Save-ServiceState
}

function Get-ListeningProcessIds {
    param([Parameter(Mandatory = $true)][int]$Port)

    $ids = @()
    try {
        $ids += @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
            ForEach-Object { [int]$_.OwningProcess })
    }
    catch {
        # netstat остаётся доступным на Windows, если модуль NetTCPIP недоступен.
    }

    if ($ids.Count -eq 0) {
        foreach ($line in (& netstat.exe -ano -p tcp 2>$null)) {
            if ($line -match '^\s*TCP\s+\S+:(?<port>\d+)\s+\S+\s+LISTENING\s+(?<pid>\d+)\s*$' -and
                [int]$Matches.port -eq $Port) {
                $ids += [int]$Matches.pid
            }
        }
    }

    return @($ids | Sort-Object -Unique)
}

function Wait-ForListener {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "Процесс сервиса завершился до открытия порта $Port (код $($Process.ExitCode))"
        }
        if ((Get-ListeningProcessIds -Port $Port).Count -gt 0) {
            return
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "Сервис не начал слушать фиксированный порт $Port за $TimeoutSeconds секунд"
}

try {
    try {
        $mutexOwned = $serviceMutex.WaitOne(0)
    }
    catch [System.Threading.AbandonedMutexException] {
        # Предыдущая оболочка аварийно завершилась; текущий запуск забирает её блокировку.
        $mutexOwned = $true
    }
    if (-not $mutexOwned) {
        throw 'pdf_to_md уже запущен или запускается. Остановите его через .\stop.ps1 перед повторным запуском.'
    }

    Write-Host 'Проверяю и очищаю оставшиеся процессы pdf_to_md на портах 50053 и 8002.'
    # Убираем экземпляры, оставшиеся от прежнего запуска, включая дочерний Python-процесс Poetry.
    & $stopScript -Quiet

    # Предзагружаем OCR- и math-веса в локальный кэш до запуска серверов.
    New-Item -ItemType Directory -Force -Path $env:HF_HOME | Out-Null
    poetry run python -c "import os, indra_ocr; indra_ocr.load(threads=int(os.getenv('INDRA_THREADS', '1')), dpi=int(os.getenv('INDRA_DPI', '200')), mode='ocr', math=True); print('Веса Indra OCR и math готовы')"
    if ($LASTEXITCODE -ne 0) {
        throw 'Не удалось подготовить веса Indra OCR; сервисы не запущены'
    }

    # Путь берётся из текущего Poetry-окружения: PID принадлежит Python-серверу,
    # а не промежуточному poetry.exe, поэтому его можно корректно завершить.
    $pythonExecutable = (& poetry env info --executable | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        throw 'Не удалось определить Python-интерпретатор Poetry-окружения'
    }

    $grpcProcess = Start-Process `
        -FilePath $pythonExecutable `
        -ArgumentList @('-m', 'src.grpc_server') `
        -WorkingDirectory $serviceRoot `
        -NoNewWindow `
        -PassThru
    $cleanupRequired = $true
    Register-ServiceProcess -Name 'grpc' -Process $grpcProcess
    Wait-ForListener -Port 50053 -Process $grpcProcess -TimeoutSeconds 30
    Write-Host 'gRPC сервис готов: порт 50053'

    $restProcess = Start-Process `
        -FilePath $pythonExecutable `
        -ArgumentList @('-m', 'uvicorn', 'src.app:app', '--host', '0.0.0.0', '--port', '8002', '--reload') `
        -WorkingDirectory $serviceRoot `
        -NoNewWindow `
        -PassThru
    Register-ServiceProcess -Name 'rest' -Process $restProcess
    Wait-ForListener -Port 8002 -Process $restProcess -TimeoutSeconds 30
    Write-Host 'REST сервис готов: порт 8002. Для штатной остановки нажмите Ctrl+C или выполните .\stop.ps1.'

    while ($true) {
        Start-Sleep -Seconds 1
        if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
            Write-Host 'Остановка pdf_to_md запрошена через stop.ps1.'
            break
        }
        foreach ($process in @($grpcProcess, $restProcess)) {
            $process.Refresh()
            if ($process.HasExited) {
                throw "Процесс сервиса PID $($process.Id) неожиданно завершился (код $($process.ExitCode))"
            }
        }
    }
}
finally {
    if ($cleanupRequired) {
        # stop.ps1 завершает серверы и их дочерние процессы по PID и портам.
        & $stopScript -Quiet
    }
    if ($mutexOwned) {
        $serviceMutex.ReleaseMutex()
    }
    $serviceMutex.Dispose()
}
