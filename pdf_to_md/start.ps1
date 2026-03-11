Set-Location $PSScriptRoot

# Start gRPC server in background
Write-Host "Starting gRPC server on port 50053..."
$grpc = Start-Process -NoNewWindow -PassThru -FilePath "poetry" `
    -ArgumentList "run", "python", "-m", "src.grpc_server"

# Start REST server with reload
Write-Host "Starting REST server on port 8002..."
try {
    poetry run python -m uvicorn src.app:app --host 0.0.0.0 --port 8002 --reload
} finally {
    # Stop gRPC server when REST server exits
    if ($grpc -and !$grpc.HasExited) {
        Stop-Process -Id $grpc.Id -Force
        Write-Host "gRPC server stopped."
    }
}
