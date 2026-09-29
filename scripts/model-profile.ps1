param(
    [ValidateSet("list", "use", "validate")]
    [string]$Command = "list",
    [string]$Profile
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$registryPath = Join-Path $root "config\models.toml"
$registryPythonPath = Join-Path $root "shared\model_registry"
$existingPythonPath = [Environment]::GetEnvironmentVariable("PYTHONPATH")
if ([string]::IsNullOrWhiteSpace($existingPythonPath)) {
    $env:PYTHONPATH = $registryPythonPath
} else {
    $env:PYTHONPATH = $registryPythonPath + ";" + $existingPythonPath
}

Push-Location (Join-Path $root "ai")
try {
    if ($Command -eq "list") {
        poetry run python -c "from model_registry import ModelRegistry; r=ModelRegistry(r'$registryPath'); print(f'active_profile={r.active_profile_name}'); [print(f'{p.name}: {p.display_name} | provider={p.provider} | model={p.model_id} | context={p.context_length}') for p in r.profiles]"
        exit 0
    }

    if ($Command -eq "validate") {
        poetry run python -c "from model_registry import ModelRegistry; r=ModelRegistry(r'$registryPath'); print(f'OK: {len(r.profiles)} profiles, active={r.active_profile_name}')"
        exit 0
    }

    if ([string]::IsNullOrWhiteSpace($Profile)) {
        throw "Specify -Profile <name> for the use command"
    }

    poetry run python -c "from model_registry import ModelRegistry; r=ModelRegistry(r'$registryPath'); r.profile(r'$Profile'); print('Profile is valid')"
    $content = Get-Content -Raw -LiteralPath $registryPath
    $activeProfilePattern = '(?m)^active_profile\s*=\s*"[^"]+"\s*$'
    if (-not [regex]::IsMatch($content, $activeProfilePattern)) {
        throw "active_profile was not found in models.toml"
    }
    $updated = [regex]::Replace($content, $activeProfilePattern, "active_profile = `"$Profile`"")
    $rolePattern = '(?m)^(ui_chat|article_extraction|knowledge_core)\s*=\s*"[^"]+"\s*$'
    $roleMatches = [regex]::Matches($updated, $rolePattern)
    if ($roleMatches.Count -ne 3) {
        throw "Expected exactly three model role mappings in models.toml; found $($roleMatches.Count)"
    }
    $updated = [regex]::Replace($updated, $rolePattern, {
        param($match)
        "$($match.Groups[1].Value) = `"$Profile`""
    })
    [IO.File]::WriteAllText($registryPath, $updated, [Text.UTF8Encoding]::new($false))
    Write-Host "Active profile: $Profile"
    Write-Host "All model roles now use: $Profile"
    Write-Host "Restart the AI service on port 50059 and the API service on port 8000."
}
finally {
    Pop-Location
}
