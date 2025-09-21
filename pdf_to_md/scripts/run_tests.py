#!/usr/bin/env python3
"""Test runner script with comprehensive reporting"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
import time


def run_command(cmd, description=""):
    """Run command and return result"""
    print(f"🔄 {description}")
    print(f"   Command: {' '.join(cmd)}")
    
    start_time = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    end_time = time.time()
    
    duration = end_time - start_time
    
    if result.returncode == 0:
        print(f"✅ {description} - SUCCESS ({duration:.2f}s)")
        if result.stdout:
            print(f"   Output: {result.stdout.strip()}")
    else:
        print(f"❌ {description} - FAILED ({duration:.2f}s)")
        if result.stderr:
            print(f"   Error: {result.stderr.strip()}")
        if result.stdout:
            print(f"   Output: {result.stdout.strip()}")
    
    return result


def run_unit_tests():
    """Run unit tests"""
    print("🧪 Running Unit Tests")
    print("=" * 50)
    
    cmd = [
        "poetry", "run", "pytest", 
        "tests/", 
        "-m", "unit",
        "-v",
        "--tb=short",
        "--durations=10"
    ]
    
    result = run_command(cmd, "Unit Tests")
    return result.returncode == 0


def run_integration_tests():
    """Run integration tests"""
    print("\n🔗 Running Integration Tests")
    print("=" * 50)
    
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "-m", "integration", 
        "-v",
        "--tb=short",
        "--durations=10"
    ]
    
    result = run_command(cmd, "Integration Tests")
    return result.returncode == 0


def run_api_tests():
    """Run API tests"""
    print("\n🌐 Running API Tests")
    print("=" * 50)
    
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "-m", "api",
        "-v", 
        "--tb=short",
        "--durations=10"
    ]
    
    result = run_command(cmd, "API Tests")
    return result.returncode == 0


def run_all_tests():
    """Run all tests"""
    print("\n🚀 Running All Tests")
    print("=" * 50)
    
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "-v",
        "--tb=short", 
        "--durations=10",
        "--maxfail=5"
    ]
    
    result = run_command(cmd, "All Tests")
    return result.returncode == 0


def run_tests_with_coverage():
    """Run tests with coverage report"""
    print("\n📊 Running Tests with Coverage")
    print("=" * 50)
    
    # Clean previous coverage data
    run_command(["poetry", "run", "coverage", "erase"], "Clean Coverage Data")
    
    # Run tests with coverage
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "--cov=src",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--cov-fail-under=80",
        "-v"
    ]
    
    result = run_command(cmd, "Tests with Coverage")
    
    if result.returncode == 0:
        print("\n📈 Coverage Report Generated:")
        print("   - Terminal: Displayed above")
        print("   - HTML: htmlcov/index.html")
        print("   - XML: coverage.xml")
    
    return result.returncode == 0


def run_specific_test(test_path):
    """Run specific test file or test function"""
    print(f"\n🎯 Running Specific Test: {test_path}")
    print("=" * 50)
    
    cmd = [
        "poetry", "run", "pytest",
        test_path,
        "-v",
        "--tb=short"
    ]
    
    result = run_command(cmd, f"Specific Test: {test_path}")
    return result.returncode == 0


def run_fast_tests():
    """Run fast tests (exclude slow tests)"""
    print("\n⚡ Running Fast Tests")
    print("=" * 50)
    
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "-m", "not slow",
        "-v",
        "--tb=short",
        "--durations=5"
    ]
    
    result = run_command(cmd, "Fast Tests")
    return result.returncode == 0


def run_parallel_tests():
    """Run tests in parallel"""
    print("\n🔄 Running Tests in Parallel")
    print("=" * 50)
    
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "-n", "auto",  # Use pytest-xdist for parallel execution
        "-v",
        "--tb=short"
    ]
    
    result = run_command(cmd, "Parallel Tests")
    return result.returncode == 0


def check_test_environment():
    """Check if test environment is properly set up"""
    print("🔍 Checking Test Environment")
    print("=" * 50)
    
    # Check if poetry is available
    poetry_result = run_command(["poetry", "--version"], "Poetry Version")
    if poetry_result.returncode != 0:
        print("❌ Poetry not found. Please install Poetry first.")
        return False
    
    # Check if dependencies are installed
    deps_result = run_command(["poetry", "install"], "Install Dependencies")
    if deps_result.returncode != 0:
        print("❌ Failed to install dependencies.")
        return False
    
    # Check if test directory exists
    if not Path("tests").exists():
        print("❌ Tests directory not found.")
        return False
    
    # Check if src directory exists
    if not Path("src").exists():
        print("❌ Source directory not found.")
        return False
    
    print("✅ Test environment is ready!")
    return True


def generate_test_report():
    """Generate comprehensive test report"""
    print("\n📋 Generating Test Report")
    print("=" * 50)
    
    # Run tests with coverage
    success = run_tests_with_coverage()
    
    if success:
        print("\n🎉 Test Report Generated Successfully!")
        print("\n📊 Report Locations:")
        print("   - HTML Coverage Report: htmlcov/index.html")
        print("   - XML Coverage Report: coverage.xml")
        print("   - Test Results: See output above")
        
        # Try to open HTML report if on Windows
        if os.name == 'nt':
            try:
                import webbrowser
                html_path = Path("htmlcov/index.html").absolute()
                if html_path.exists():
                    print(f"   - Opening HTML report: {html_path}")
                    webbrowser.open(f"file://{html_path}")
            except Exception as e:
                print(f"   - Could not open HTML report: {e}")
    else:
        print("\n❌ Test Report Generation Failed!")
    
    return success


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="PDF to Markdown Service Test Runner")
    parser.add_argument(
        "test_type",
        nargs="?",
        choices=[
            "unit", "integration", "api", "all", "coverage", 
            "fast", "parallel", "report", "check"
        ],
        default="all",
        help="Type of tests to run"
    )
    parser.add_argument(
        "--test-path",
        help="Specific test file or test function to run"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    print("🧪 PDF to Markdown Service - Test Runner")
    print("=" * 60)
    
    # Check environment first
    if not check_test_environment():
        sys.exit(1)
    
    success = False
    
    if args.test_path:
        success = run_specific_test(args.test_path)
    elif args.test_type == "unit":
        success = run_unit_tests()
    elif args.test_type == "integration":
        success = run_integration_tests()
    elif args.test_type == "api":
        success = run_api_tests()
    elif args.test_type == "all":
        success = run_all_tests()
    elif args.test_type == "coverage":
        success = run_tests_with_coverage()
    elif args.test_type == "fast":
        success = run_fast_tests()
    elif args.test_type == "parallel":
        success = run_parallel_tests()
    elif args.test_type == "report":
        success = generate_test_report()
    elif args.test_type == "check":
        success = True  # Already checked above
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 All tests completed successfully!")
        sys.exit(0)
    else:
        print("❌ Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
