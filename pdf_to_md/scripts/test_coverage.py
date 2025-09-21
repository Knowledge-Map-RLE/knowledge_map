#!/usr/bin/env python3
"""Test coverage analysis and reporting script"""

import os
import sys
import subprocess
import webbrowser
from pathlib import Path
import json


def run_coverage_analysis():
    """Run comprehensive coverage analysis"""
    print("📊 PDF to Markdown Service - Coverage Analysis")
    print("=" * 60)
    
    # Clean previous coverage data
    print("🧹 Cleaning previous coverage data...")
    subprocess.run(["poetry", "run", "coverage", "erase"], check=True)
    
    # Run tests with coverage
    print("🧪 Running tests with coverage...")
    cmd = [
        "poetry", "run", "pytest",
        "tests/",
        "--cov=src",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--cov-report=json:coverage.json",
        "-v"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("❌ Tests failed!")
        print(result.stdout)
        print(result.stderr)
        return False
    
    print("✅ Tests completed successfully!")
    return True


def analyze_coverage_data():
    """Analyze coverage data and generate insights"""
    print("\n📈 Analyzing Coverage Data")
    print("=" * 40)
    
    coverage_json = Path("coverage.json")
    if not coverage_json.exists():
        print("❌ Coverage JSON file not found!")
        return False
    
    try:
        with open(coverage_json, 'r') as f:
            data = json.load(f)
        
        total_coverage = data['totals']['percent_covered']
        total_lines = data['totals']['num_statements']
        covered_lines = data['totals']['covered_lines']
        missing_lines = data['totals']['missing_lines']
        
        print(f"📊 Overall Coverage: {total_coverage:.1f}%")
        print(f"📝 Total Lines: {total_lines}")
        print(f"✅ Covered Lines: {covered_lines}")
        print(f"❌ Missing Lines: {missing_lines}")
        
        # Analyze by file
        print("\n📁 Coverage by File:")
        print("-" * 40)
        
        files = data['files']
        for file_path, file_data in files.items():
            if file_path.startswith('src/'):
                coverage = file_data['summary']['percent_covered']
                lines = file_data['summary']['num_statements']
                covered = file_data['summary']['covered_lines']
                missing = file_data['summary']['missing_lines']
                
                status = "🟢" if coverage >= 90 else "🟡" if coverage >= 70 else "🔴"
                print(f"{status} {file_path}: {coverage:.1f}% ({covered}/{lines})")
                
                if missing > 0 and coverage < 90:
                    print(f"   Missing lines: {missing}")
        
        # Coverage recommendations
        print("\n💡 Coverage Recommendations:")
        print("-" * 40)
        
        low_coverage_files = [
            (path, data['summary']['percent_covered'])
            for path, data in files.items()
            if path.startswith('src/') and data['summary']['percent_covered'] < 80
        ]
        
        if low_coverage_files:
            print("🔴 Files with low coverage (< 80%):")
            for file_path, coverage in sorted(low_coverage_files, key=lambda x: x[1]):
                print(f"   - {file_path}: {coverage:.1f}%")
        else:
            print("🟢 All files have good coverage (≥ 80%)!")
        
        # Test recommendations
        print("\n🧪 Test Recommendations:")
        print("-" * 40)
        
        if total_coverage < 80:
            print("🔴 Overall coverage is below 80%. Consider adding more tests.")
        elif total_coverage < 90:
            print("🟡 Overall coverage is good but could be improved.")
        else:
            print("🟢 Excellent coverage! Keep up the good work!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error analyzing coverage data: {e}")
        return False


def generate_coverage_report():
    """Generate detailed coverage report"""
    print("\n📋 Generating Coverage Report")
    print("=" * 40)
    
    # Check if coverage files exist
    html_report = Path("htmlcov/index.html")
    xml_report = Path("coverage.xml")
    json_report = Path("coverage.json")
    
    if not html_report.exists():
        print("❌ HTML coverage report not found!")
        return False
    
    print("📊 Coverage Reports Generated:")
    print(f"   - HTML Report: {html_report.absolute()}")
    print(f"   - XML Report: {xml_report.absolute()}")
    print(f"   - JSON Report: {json_report.absolute()}")
    
    # Try to open HTML report
    try:
        if os.name == 'nt':  # Windows
            webbrowser.open(f"file://{html_report.absolute()}")
            print("🌐 Opening HTML coverage report in browser...")
        else:  # Unix-like systems
            print(f"🌐 To view HTML report, open: file://{html_report.absolute()}")
    except Exception as e:
        print(f"⚠️  Could not open browser: {e}")
    
    return True


def check_coverage_thresholds():
    """Check if coverage meets minimum thresholds"""
    print("\n🎯 Checking Coverage Thresholds")
    print("=" * 40)
    
    coverage_json = Path("coverage.json")
    if not coverage_json.exists():
        print("❌ Coverage data not found!")
        return False
    
    try:
        with open(coverage_json, 'r') as f:
            data = json.load(f)
        
        total_coverage = data['totals']['percent_covered']
        
        # Define thresholds
        thresholds = {
            "Minimum": 70,
            "Good": 80,
            "Excellent": 90
        }
        
        print("📊 Coverage Thresholds:")
        for level, threshold in thresholds.items():
            status = "✅" if total_coverage >= threshold else "❌"
            print(f"   {status} {level} ({threshold}%): {total_coverage:.1f}%")
        
        # Check individual file thresholds
        print("\n📁 File-level Coverage:")
        files = data['files']
        low_coverage_files = []
        
        for file_path, file_data in files.items():
            if file_path.startswith('src/'):
                coverage = file_data['summary']['percent_covered']
                if coverage < 80:
                    low_coverage_files.append((file_path, coverage))
        
        if low_coverage_files:
            print("🔴 Files below 80% coverage:")
            for file_path, coverage in sorted(low_coverage_files, key=lambda x: x[1]):
                print(f"   - {file_path}: {coverage:.1f}%")
        else:
            print("🟢 All files meet 80% coverage threshold!")
        
        return total_coverage >= 70  # Minimum threshold
        
    except Exception as e:
        print(f"❌ Error checking thresholds: {e}")
        return False


def generate_coverage_summary():
    """Generate coverage summary for CI/CD"""
    print("\n📝 Generating Coverage Summary")
    print("=" * 40)
    
    coverage_json = Path("coverage.json")
    if not coverage_json.exists():
        print("❌ Coverage data not found!")
        return False
    
    try:
        with open(coverage_json, 'r') as f:
            data = json.load(f)
        
        total_coverage = data['totals']['percent_covered']
        total_lines = data['totals']['num_statements']
        covered_lines = data['totals']['covered_lines']
        missing_lines = data['totals']['missing_lines']
        
        # Generate summary file
        summary = {
            "total_coverage": round(total_coverage, 2),
            "total_lines": total_lines,
            "covered_lines": covered_lines,
            "missing_lines": missing_lines,
            "status": "pass" if total_coverage >= 80 else "fail",
            "timestamp": data.get('timestamp', 'unknown')
        }
        
        with open("coverage_summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
        print("📄 Coverage summary saved to: coverage_summary.json")
        print(f"📊 Total Coverage: {total_coverage:.1f}%")
        print(f"📝 Status: {summary['status'].upper()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating summary: {e}")
        return False


def main():
    """Main function"""
    if len(sys.argv) > 1:
        command = sys.argv[1]
    else:
        command = "full"
    
    success = True
    
    if command == "run":
        success = run_coverage_analysis()
    elif command == "analyze":
        success = analyze_coverage_data()
    elif command == "report":
        success = generate_coverage_report()
    elif command == "thresholds":
        success = check_coverage_thresholds()
    elif command == "summary":
        success = generate_coverage_summary()
    elif command == "full":
        # Run full coverage analysis
        success = run_coverage_analysis()
        if success:
            success = analyze_coverage_data()
            if success:
                success = generate_coverage_report()
                if success:
                    success = check_coverage_thresholds()
                    if success:
                        success = generate_coverage_summary()
    else:
        print("❌ Unknown command. Available commands:")
        print("   - run: Run tests with coverage")
        print("   - analyze: Analyze coverage data")
        print("   - report: Generate coverage report")
        print("   - thresholds: Check coverage thresholds")
        print("   - summary: Generate coverage summary")
        print("   - full: Run complete coverage analysis")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Coverage analysis completed successfully!")
        sys.exit(0)
    else:
        print("❌ Coverage analysis failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
