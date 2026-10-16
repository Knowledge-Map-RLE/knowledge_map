[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$utf8Encoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8Encoding
$OutputEncoding = $utf8Encoding
try { chcp.com 65001 | Out-Null } catch { }

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $repositoryRoot 'tmp\pdf_to_md\service-state.json'
$reservedPorts = @(50053, 8002)

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

function Test-RecordedProcessIdentity {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)]$Record
    )

    if ($Process.ProcessName -notin @('python', 'pythonw')) {
        return $false
    }

    if (-not $Record.startedUtc) {
        return $false
    }

    try {
        $expectedStart = [DateTime]::Parse(
            [string]$Record.startedUtc,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind
        )
        $actualStart = $Process.StartTime.ToUniversalTime()
        return [Math]::Abs(($actualStart - $expectedStart.ToUniversalTime()).TotalSeconds) -lt 2
    }
    catch {
        return $false
    }
}

function Stop-ProcessTree {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }

    if ($process.ProcessName -notin @('python', 'pythonw')) {
        throw "Не останавливаю PID $ProcessId ($($process.ProcessName)): порт зарезервирован для pdf_to_md, но процесс не похож на Python-сервис."
    }

    if (-not $Quiet) {
        Write-Host "Останавливаю pdf_to_md: PID $ProcessId, процесс $($process.ProcessName)"
    }

    $taskkillPath = Join-Path $env:WINDIR 'System32\taskkill.exe'
    & $taskkillPath /PID $ProcessId /T /F 2>&1 | Out-Null
    $process.Refresh()
    if (-not $process.HasExited) {
        Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    }
}

$state = $null
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "Не удалось прочитать состояние pdf_to_md '$statePath': $($_.Exception.Message)"
    }
}

$knownProcesses = @{}
foreach ($name in @('grpc', 'rest')) {
    $record = $state.$name
    if (-not $record -or -not $record.pid) {
        continue
    }

    $processId = [int]$record.pid
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process -and (Test-RecordedProcessIdentity -Process $process -Record $record)) {
        $knownProcesses[$processId] = $true
    }
}

$listenerProcesses = @{}
foreach ($port in $reservedPorts) {
    foreach ($processId in Get-ListeningProcessIds -Port $port) {
        $listenerProcesses[$processId] = $port
    }
}

$processIds = @(@($knownProcesses.Keys) + @($listenerProcesses.Keys) | Sort-Object -Unique)
foreach ($processId in $processIds) {
    $processId = [int]$processId
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
        continue
    }

    if (-not $knownProcesses.ContainsKey($processId) -and $process.ProcessName -notin @('python', 'pythonw')) {
        $port = $listenerProcesses[$processId]
        throw "Порт $port занят чужим процессом PID $processId ($($process.ProcessName)); он оставлен без изменений."
    }

    if ($PSCmdlet.ShouldProcess("PID $processId", 'Завершить процесс и его дочерние процессы')) {
        Stop-ProcessTree -ProcessId $processId
    }
}

if ($WhatIfPreference) {
    return
}

foreach ($port in $reservedPorts) {
    $deadline = [DateTime]::UtcNow.AddSeconds(8)
    while ((Get-ListeningProcessIds -Port $port).Count -gt 0 -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 250
    }

    $remaining = @(Get-ListeningProcessIds -Port $port)
    if ($remaining.Count -gt 0) {
        throw "Порт $port всё ещё занят PID $($remaining -join ', '). Запустите stop.ps1 от имени пользователя-владельца процесса или администратора."
    }
}

if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    if ($PSCmdlet.ShouldProcess($statePath, 'Удалить файл состояния остановленного сервиса')) {
        Remove-Item -LiteralPath $statePath -Force
    }
}

if (-not $Quiet) {
    if ($processIds.Count -eq 0) {
        Write-Host 'pdf_to_md уже остановлен; порты 50053 и 8002 свободны.'
    }
    else {
        Write-Host 'pdf_to_md остановлен; порты 50053 и 8002 свободны.'
    }
}
