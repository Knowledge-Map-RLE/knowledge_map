#!/usr/bin/env python3
"""Quick test runner for development"""

import os
import sys
import subprocess
import time
from pathlib import Path


def run_quick_tests():
    """Run quick tests for development"""
    print("⚡ Quick Test Runner - PDF to Markdown Service")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not Path("src").exists() or not Path("tests").exists():
        print("❌ Please run this script from the project root directory")
        sys.exit(1)
    
    # Run fast tests only
    print("🧪 Running fast tests (excluding slow tests)...")
    
    start_time = time.time()
    
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "-m", "not slow",
        "-v",
        "--tb=short",
        "--durations=5",
        "--maxfail=3"
    ]
    
    result = subprocess.run(cmd)
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\n⏱️  Tests completed in {duration:.2f} seconds")
    
    if result.returncode == 0:
        print("✅ All quick tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        return False


def run_specific_tests():
    """Run specific test categories"""
    print("🎯 Running specific test categories")
    print("=" * 40)
    
    test_categories = [
        ("Unit Tests", ["-m", "unit"]),
        ("Core Tests", ["tests/test_core/"]),
        ("API Tests", ["-m", "api"]),
        ("Service Tests", ["tests/test_services/"]),
    ]
    
    results = {}
    
    for category, args in test_categories:
        print(f"\n🧪 Running {category}...")
        
        cmd = [
            "poetry", "run", "pytest",
            "tests/",
            *args,
            "-v",
            "--tb=short"
        ]
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        end_time = time.time()
        
        duration = end_time - start_time
        success = result.returncode == 0
        
        results[category] = {
            "success": success,
            "duration": duration,
            "output": result.stdout,
            "error": result.stderr
        }
        
        status = "✅" if success else "❌"
        print(f"{status} {category} - {duration:.2f}s")
        
        if not success and result.stderr:
            print(f"   Error: {result.stderr.strip()}")
    
    # Summary
    print("\n📊 Test Summary:")
    print("-" * 30)
    
    passed = sum(1 for r in results.values() if r["success"])
    total = len(results)
    
    for category, result in results.items():
        status = "✅" if result["success"] else "❌"
        print(f"{status} {category}: {result['duration']:.2f}s")
    
    print(f"\n🎯 Results: {passed}/{total} categories passed")
    
    return passed == total


def run_coverage_quick():
    """Run quick coverage check"""
    print("📊 Quick Coverage Check")
    print("=" * 30)
    
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "-m", "not slow",
        "--cov=src",
        "--cov-report=term-missing",
        "--cov-fail-under=70",
        "-q"
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("✅ Coverage check passed!")
        return True
    else:
        print("❌ Coverage check failed!")
        return False


def run_linting():
    """Run code linting"""
    print("🔍 Running Code Linting")
    print("=" * 30)
    
    # Run black
    print("🎨 Running Black formatter...")
    black_result = subprocess.run([
        "poetry", "run", "black", "--check", "src", "tests"
    ])
    
    # Run isort
    print("📦 Running isort...")
    isort_result = subprocess.run([
        "poetry", "run", "isort", "--check-only", "src", "tests"
    ])
    
    # Run flake8
    print("🔍 Running flake8...")
    flake8_result = subprocess.run([
        "poetry", "run", "flake8", "src", "tests"
    ])
    
    # Run mypy
    print("🔬 Running mypy...")
    mypy_result = subprocess.run([
        "poetry", "run", "mypy", "src"
    ])
    
    results = {
        "Black": black_result.returncode == 0,
        "isort": isort_result.returncode == 0,
        "flake8": flake8_result.returncode == 0,
        "mypy": mypy_result.returncode == 0
    }
    
    print("\n📊 Linting Results:")
    for tool, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {tool}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("✅ All linting checks passed!")
    else:
        print("❌ Some linting checks failed!")
    
    return all_passed


def main():
    """Main function"""
    if len(sys.argv) > 1:
        command = sys.argv[1]
    else:
        command = "quick"
    
    success = True
    
    if command == "quick":
        success = run_quick_tests()
    elif command == "specific":
        success = run_specific_tests()
    elif command == "coverage":
        success = run_coverage_quick()
    elif command == "lint":
        success = run_linting()
    elif command == "all":
        print("🚀 Running all quick checks...")
        success = run_linting()
        if success:
            success = run_quick_tests()
        if success:
            success = run_coverage_quick()
    else:
        print("❌ Unknown command. Available commands:")
        print("   - quick: Run quick tests")
        print("   - specific: Run specific test categories")
        print("   - coverage: Run quick coverage check")
        print("   - lint: Run code linting")
        print("   - all: Run all quick checks")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 Quick checks completed successfully!")
        sys.exit(0)
    else:
        print("❌ Quick checks failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
