#!/usr/bin/env python3
"""Demo script for testing capabilities"""

import os
import sys
import subprocess
import time
from pathlib import Path


def print_header(title):
    """Print formatted header"""
    print("\n" + "=" * 60)
    print(f"🎯 {title}")
    print("=" * 60)


def print_step(step, description):
    """Print formatted step"""
    print(f"\n📋 Step {step}: {description}")
    print("-" * 40)


def run_demo_command(cmd, description, capture_output=True):
    """Run command and display results"""
    print(f"🔄 {description}")
    print(f"   Command: {' '.join(cmd)}")
    
    start_time = time.time()
    
    if capture_output:
        result = subprocess.run(cmd, capture_output=True, text=True)
    else:
        result = subprocess.run(cmd)
    
    end_time = time.time()
    duration = end_time - start_time
    
    if result.returncode == 0:
        print(f"✅ SUCCESS ({duration:.2f}s)")
        if capture_output and result.stdout:
            # Show first few lines of output
            lines = result.stdout.strip().split('\n')
            for line in lines[:5]:
                print(f"   {line}")
            if len(lines) > 5:
                print(f"   ... and {len(lines) - 5} more lines")
    else:
        print(f"❌ FAILED ({duration:.2f}s)")
        if capture_output and result.stderr:
            print(f"   Error: {result.stderr.strip()}")
    
    return result.returncode == 0


def demo_environment_check():
    """Demo environment check"""
    print_step(1, "Checking Test Environment")
    
    # Check Poetry
    success = run_demo_command(
        ["poetry", "--version"],
        "Checking Poetry installation"
    )
    
    if not success:
        print("❌ Poetry not found. Please install Poetry first.")
        return False
    
    # Check dependencies
    success = run_demo_command(
        ["poetry", "install", "--no-root"],
        "Installing dependencies"
    )
    
    if not success:
        print("❌ Failed to install dependencies.")
        return False
    
    # Check test structure
    if not Path("tests").exists():
        print("❌ Tests directory not found.")
        return False
    
    if not Path("src").exists():
        print("❌ Source directory not found.")
        return False
    
    print("✅ Environment is ready for testing!")
    return True


def demo_unit_tests():
    """Demo unit tests"""
    print_step(2, "Running Unit Tests")
    
    # Run core tests
    success = run_demo_command(
        ["poetry", "run", "pytest", "tests/test_core/", "-v", "--tb=short"],
        "Testing core components (config, validators)"
    )
    
    if success:
        print("✅ Core components are working correctly!")
    else:
        print("❌ Some core tests failed.")
    
    return success


def demo_service_tests():
    """Demo service tests"""
    print_step(3, "Running Service Tests")
    
    # Run service tests
    success = run_demo_command(
        ["poetry", "run", "pytest", "tests/test_services/", "-v", "--tb=short"],
        "Testing service layer (conversion, model, file services)"
    )
    
    if success:
        print("✅ Service layer is working correctly!")
    else:
        print("❌ Some service tests failed.")
    
    return success


def demo_api_tests():
    """Demo API tests"""
    print_step(4, "Running API Tests")
    
    # Run API tests
    success = run_demo_command(
        ["poetry", "run", "pytest", "tests/test_api/", "-v", "--tb=short"],
        "Testing API layer (routes, schemas)"
    )
    
    if success:
        print("✅ API layer is working correctly!")
    else:
        print("❌ Some API tests failed.")
    
    return success


def demo_integration_tests():
    """Demo integration tests"""
    print_step(5, "Running Integration Tests")
    
    # Run integration tests
    success = run_demo_command(
        ["poetry", "run", "pytest", "tests/test_integration/", "-v", "--tb=short"],
        "Testing integration between components"
    )
    
    if success:
        print("✅ Integration tests passed!")
    else:
        print("❌ Some integration tests failed.")
    
    return success


def demo_coverage_analysis():
    """Demo coverage analysis"""
    print_step(6, "Running Coverage Analysis")
    
    # Run tests with coverage
    success = run_demo_command(
        [
            "poetry", "run", "pytest", "tests/",
            "--cov=src",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "-q"
        ],
        "Running tests with coverage measurement"
    )
    
    if success:
        print("✅ Coverage analysis completed!")
        
        # Show coverage summary
        if Path("htmlcov/index.html").exists():
            print("📊 HTML coverage report generated: htmlcov/index.html")
        
        # Try to show coverage percentage
        try:
            result = subprocess.run(
                ["poetry", "run", "coverage", "report", "--show-missing"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'TOTAL' in line:
                        print(f"📈 {line}")
                        break
        except Exception:
            pass
    else:
        print("❌ Coverage analysis failed.")
    
    return success


def demo_quick_validation():
    """Demo quick validation"""
    print_step(7, "Quick Validation")
    
    # Run quick tests
    success = run_demo_command(
        [
            "poetry", "run", "pytest", "tests/",
            "-m", "not slow",
            "-q",
            "--tb=short"
        ],
        "Running quick validation tests"
    )
    
    if success:
        print("✅ Quick validation passed!")
    else:
        print("❌ Quick validation failed.")
    
    return success


def demo_test_summary():
    """Demo test summary"""
    print_step(8, "Test Summary")
    
    # Count test files
    test_files = list(Path("tests").rglob("test_*.py"))
    print(f"📁 Test files found: {len(test_files)}")
    
    # Count test functions
    try:
        result = subprocess.run(
            ["poetry", "run", "pytest", "--collect-only", "-q"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            test_count = 0
            for line in lines:
                if 'test session starts' in line:
                    continue
                if 'collected' in line:
                    print(f"🧪 {line}")
                    break
    except Exception:
        print("🧪 Test collection completed")
    
    # Show test structure
    print("\n📂 Test Structure:")
    for test_dir in Path("tests").iterdir():
        if test_dir.is_dir():
            test_files_in_dir = list(test_dir.rglob("test_*.py"))
            print(f"   📁 {test_dir.name}: {len(test_files_in_dir)} files")
    
    return True


def main():
    """Main demo function"""
    print_header("PDF to Markdown Service - Testing Demo")
    
    print("""
🎯 This demo will showcase the comprehensive testing system:
   
   • Environment validation
   • Unit tests for core components
   • Service layer testing
   • API testing
   • Integration testing
   • Coverage analysis
   • Quick validation
   • Test summary

🚀 Let's start the testing demo!
""")
    
    # Check if we're in the right directory
    if not Path("pyproject.toml").exists():
        print("❌ Please run this script from the project root directory")
        sys.exit(1)
    
    # Run demo steps
    steps = [
        demo_environment_check,
        demo_unit_tests,
        demo_service_tests,
        demo_api_tests,
        demo_integration_tests,
        demo_coverage_analysis,
        demo_quick_validation,
        demo_test_summary
    ]
    
    results = []
    for step_func in steps:
        try:
            result = step_func()
            results.append(result)
        except KeyboardInterrupt:
            print("\n⏹️  Demo interrupted by user")
            break
        except Exception as e:
            print(f"❌ Error in demo step: {e}")
            results.append(False)
    
    # Final summary
    print_header("Demo Summary")
    
    passed_steps = sum(results)
    total_steps = len(results)
    
    print(f"📊 Results: {passed_steps}/{total_steps} steps completed successfully")
    
    if passed_steps == total_steps:
        print("🎉 All testing capabilities are working perfectly!")
        print("\n🚀 You can now use the following commands:")
        print("   • make test          - Run all tests")
        print("   • make test-coverage - Run with coverage")
        print("   • make test-quick    - Run quick tests")
        print("   • make lint          - Check code quality")
    else:
        print("⚠️  Some steps failed. Check the output above for details.")
        print("\n🔧 Common solutions:")
        print("   • Run 'poetry install' to install dependencies")
        print("   • Check that all test files are present")
        print("   • Ensure you're in the project root directory")
    
    print("\n📚 For more information, see TESTING.md")
    
    return passed_steps == total_steps


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
