#!/usr/bin/env python3
"""Development startup script"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    """Start development environment"""
    print("🚀 Starting PDF to Markdown Service Development Environment")
    
    # Check if we're in the right directory
    if not Path("pyproject.toml").exists():
        print("❌ Error: pyproject.toml not found. Please run from project root.")
        sys.exit(1)
    
    # Set development environment variables
    env = os.environ.copy()
    env.update({
        "DEBUG": "true",
        "LOG_LEVEL": "DEBUG",
        "API_HOST": "0.0.0.0",
        "API_PORT": "8002",
        "GRPC_PORT": "50053",
        "MAX_FILE_SIZE_MB": "50",
        "CONVERSION_TIMEOUT_SECONDS": "300"
    })
    
    print("📋 Environment variables set:")
    for key, value in env.items():
        if key in ["DEBUG", "LOG_LEVEL", "API_HOST", "API_PORT", "GRPC_PORT", "MAX_FILE_SIZE_MB", "CONVERSION_TIMEOUT_SECONDS"]:
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
    
    # Start the service
    print("🎯 Starting FastAPI server...")
    print("📖 API Documentation: http://localhost:8002/docs")
    print("🔍 Health Check: http://localhost:8002/health")
    print("🛑 Press Ctrl+C to stop")
    
    try:
        subprocess.run([
            "poetry", "run", "uvicorn", 
            "src.app:app", 
            "--host", "0.0.0.0", 
            "--port", "8002", 
            "--reload"
        ], env=env)
    except KeyboardInterrupt:
        print("\n👋 Development server stopped")

if __name__ == "__main__":
    main()
