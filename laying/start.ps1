Set-Location $PSScriptRoot

Write-Host "Building graph-layout-server (release)..."
cargo build --release

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed"
    exit 1
}

Write-Host "Starting graph-layout-server on port 50051..."
./target/release/graph-layout-server.exe
