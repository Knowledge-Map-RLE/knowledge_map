#!/usr/bin/env python3
"""gRPC server startup script"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    """Start gRPC server"""
    print("🚀 Starting PDF to Markdown gRPC Server")
    
    # Check if we're in the right directory
    if not Path("pyproject.toml").exists():
        print("❌ Error: pyproject.toml not found. Please run from project root.")
        sys.exit(1)
    
    # Set environment variables
    env = os.environ.copy()
    env.update({
        "DEBUG": "true",
        "LOG_LEVEL": "DEBUG",
        "GRPC_PORT": "50053",
        "MAX_FILE_SIZE_MB": "50",
        "CONVERSION_TIMEOUT_SECONDS": "300"
    })
    
    print("📋 Environment variables set:")
    for key, value in env.items():
        if key in ["DEBUG", "LOG_LEVEL", "GRPC_PORT", "MAX_FILE_SIZE_MB", "CONVERSION_TIMEOUT_SECONDS"]:
            print(f"  {key}={value}")
    
    # Check if poetry is available
    try:
        subprocess.run(["poetry", "--version"], check=True, capture_output=True)
        print("✅ Poetry found")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Error: Poetry not found. Please install Poetry first.")
        sys.exit(1)
    
    # Install dependencies if needed
    print("📦 Checking dependencies...")
    try:
        subprocess.run(["poetry", "install"], check=True)
        print("✅ Dependencies installed")
    except subprocess.CalledProcessError:
        print("❌ Error: Failed to install dependencies")
        sys.exit(1)
    
    # Start the gRPC server
    print("🎯 Starting gRPC server...")
    print("🔌 gRPC Server: localhost:50053")
    print("🛑 Press Ctrl+C to stop")
    
    try:
        subprocess.run([
            "poetry", "run", "python", "-m", "src.grpc_app"
        ], env=env)
    except KeyboardInterrupt:
        print("\n👋 gRPC server stopped")

if __name__ == "__main__":
    main()
