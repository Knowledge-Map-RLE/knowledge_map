#!/usr/bin/env python3
"""Script to check refactoring results"""

import os
import sys
from pathlib import Path
import subprocess

def check_file_structure():
    """Check if new file structure is in place"""
    print("🔍 Checking file structure...")
    
    required_files = [
        "src/core/__init__.py",
        "src/core/config.py",
        "src/core/exceptions.py",
        "src/core/logger.py",
        "src/core/types.py",
        "src/core/validators.py",
        "src/api/__init__.py",
        "src/api/routes.py",
        "src/api/schemas.py",
        "src/api/middleware.py",
        "src/api/dependencies.py",
        "src/services/__init__.py",
        "src/services/conversion_service.py",
        "src/services/model_service.py",
        "src/services/file_service.py",
        "src/services/models/__init__.py",
        "src/services/models/base_model.py",
        "src/services/models/huridocs_model.py",
        "src/services/models/marker_model.py",
        "src/grpc_services/__init__.py",
        "src/grpc_services/pdf_to_md_servicer.py",
        "src/app.py",
        "src/grpc_app.py",
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/test_core/test_config.py",
        "tests/test_core/test_validators.py",
        "scripts/start_dev.py",
        "scripts/start_grpc.py",
        "README.md",
        "MIGRATION.md"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing files:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        return False
    else:
        print("✅ All required files present")
        return True

def check_imports():
    """Check if imports work correctly"""
    print("🔍 Checking imports...")
    
    try:
        # Test core imports
        sys.path.insert(0, str(Path("src")))
        
        from core.config import settings
        from core.exceptions import PDFConversionError
        from core.logger import get_logger
        from core.types import ConversionResult
        from core.validators import validate_pdf_file
        
        from services.conversion_service import ConversionService
        from services.model_service import ModelService
        from services.file_service import FileService
        
        print("✅ All imports successful")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def check_code_quality():
    """Check code quality with linting tools"""
    print("🔍 Checking code quality...")
    
    try:
        # Check with flake8
        result = subprocess.run([
            "poetry", "run", "flake8", "src", "--count", "--select=E9,F63,F7,F82", "--show-source", "--statistics"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ No critical linting errors found")
        else:
            print("⚠️  Linting issues found:")
            print(result.stdout)
            return False
        
        # Check with mypy (if available)
        try:
            result = subprocess.run([
                "poetry", "run", "mypy", "src", "--ignore-missing-imports"
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Type checking passed")
            else:
                print("⚠️  Type checking issues found:")
                print(result.stdout)
        except FileNotFoundError:
            print("ℹ️  mypy not available, skipping type checking")
        
        return True
        
    except Exception as e:
        print(f"❌ Code quality check failed: {e}")
        return False

def check_tests():
    """Check if tests can run"""
    print("🔍 Checking tests...")
    
    try:
        result = subprocess.run([
            "poetry", "run", "pytest", "tests/test_core/", "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Tests pass")
            return True
        else:
            print("❌ Tests failed:")
            print(result.stdout)
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Test check failed: {e}")
        return False

def check_dependencies():
    """Check if dependencies are properly configured"""
    print("🔍 Checking dependencies...")
    
    try:
        # Check if pyproject.toml is valid
        result = subprocess.run([
            "poetry", "check"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Dependencies configuration is valid")
            return True
        else:
            print("❌ Dependencies configuration error:")
            print(result.stdout)
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Dependencies check failed: {e}")
        return False

def main():
    """Main check function"""
    print("🚀 PDF to Markdown Service - Refactoring Check")
    print("=" * 50)
    
    checks = [
        ("File Structure", check_file_structure),
        ("Dependencies", check_dependencies),
        ("Imports", check_imports),
        ("Code Quality", check_code_quality),
        ("Tests", check_tests)
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n📋 {name}")
        print("-" * 20)
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ {name} check failed with exception: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:20} {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All checks passed! Refactoring is successful.")
        return 0
    else:
        print("⚠️  Some checks failed. Please review the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
