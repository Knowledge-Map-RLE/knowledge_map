# PDF to Markdown Service - Makefile
# Provides convenient commands for testing, development, and deployment

.PHONY: help install test test-unit test-integration test-api test-all test-coverage test-quick lint format clean dev run-grpc run-api docs

# Default target
help:
	@echo "PDF to Markdown Service - Available Commands:"
	@echo ""
	@echo "📦 Installation:"
	@echo "  install          Install dependencies with Poetry"
	@echo "  install-dev      Install development dependencies"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  test             Run all tests"
	@echo "  test-unit        Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-api         Run API tests only"
	@echo "  test-coverage    Run tests with coverage report"
	@echo "  test-quick       Run quick tests (exclude slow tests)"
	@echo "  test-parallel    Run tests in parallel"
	@echo ""
	@echo "🔍 Code Quality:"
	@echo "  lint             Run all linting tools"
	@echo "  format           Format code with black and isort"
	@echo "  type-check       Run type checking with mypy"
	@echo ""
	@echo "🚀 Development:"
	@echo "  dev              Start development server (FastAPI)"
	@echo "  run-api          Start API server"
	@echo "  run-grpc         Start gRPC server"
	@echo "  run-both         Start both API and gRPC servers"
	@echo ""
	@echo "📚 Documentation:"
	@echo "  docs             Generate documentation"
	@echo "  docs-serve       Serve documentation locally"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  clean            Clean temporary files and caches"
	@echo "  clean-all        Clean everything including dependencies"
	@echo "  update           Update dependencies"
	@echo ""

# Installation
install:
	@echo "📦 Installing dependencies..."
	poetry install --no-root

install-dev:
	@echo "📦 Installing development dependencies..."
	poetry install

# Testing
test:
	@echo "🧪 Running all tests..."
	poetry run python scripts/run_tests.py all

test-unit:
	@echo "🧪 Running unit tests..."
	poetry run python scripts/run_tests.py unit

test-integration:
	@echo "🧪 Running integration tests..."
	poetry run python scripts/run_tests.py integration

test-api:
	@echo "🧪 Running API tests..."
	poetry run python scripts/run_tests.py api

test-coverage:
	@echo "📊 Running tests with coverage..."
	poetry run python scripts/test_coverage.py full

test-quick:
	@echo "⚡ Running quick tests..."
	poetry run python scripts/quick_test.py quick

test-parallel:
	@echo "🔄 Running tests in parallel..."
	poetry run python scripts/run_tests.py parallel

# Code Quality
lint:
	@echo "🔍 Running linting tools..."
	poetry run python scripts/quick_test.py lint

format:
	@echo "🎨 Formatting code..."
	poetry run black src tests
	poetry run isort src tests
	@echo "✅ Code formatted!"

type-check:
	@echo "🔬 Running type checking..."
	poetry run mypy src

# Development
dev:
	@echo "🚀 Starting development server..."
	poetry run python scripts/start_dev.py

run-api:
	@echo "🌐 Starting API server..."
	poetry run python src/app.py

run-grpc:
	@echo "🔗 Starting gRPC server..."
	poetry run python src/grpc_app.py

run-both:
	@echo "🚀 Starting both servers..."
	@echo "Starting API server in background..."
	poetry run python src/app.py &
	@echo "Starting gRPC server in background..."
	poetry run python src/grpc_app.py &
	@echo "Both servers started. Press Ctrl+C to stop."

# Documentation
docs:
	@echo "📚 Generating documentation..."
	poetry run sphinx-build -b html docs docs/_build/html

docs-serve:
	@echo "📚 Serving documentation..."
	@echo "Documentation available at: http://localhost:8000"
	cd docs/_build/html && python -m http.server 8000

# Maintenance
clean:
	@echo "🧹 Cleaning temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -f coverage.xml coverage.json coverage_summary.json
	@echo "✅ Cleaned!"

clean-all: clean
	@echo "🧹 Cleaning everything..."
	rm -rf .venv
	rm -rf dist
	rm -rf build
	@echo "✅ Everything cleaned!"

update:
	@echo "📦 Updating dependencies..."
	poetry update

# CI/CD helpers
ci-test:
	@echo "🤖 Running CI tests..."
	poetry run python scripts/run_tests.py all
	poetry run python scripts/test_coverage.py full

ci-lint:
	@echo "🤖 Running CI linting..."
	poetry run python scripts/quick_test.py lint

# Docker helpers
docker-build:
	@echo "🐳 Building Docker image..."
	docker build -t pdf-to-md-service .

docker-run:
	@echo "🐳 Running Docker container..."
	docker run -p 8002:8002 -p 50053:50053 pdf-to-md-service

# Development helpers
check-env:
	@echo "🔍 Checking environment..."
	poetry run python scripts/run_tests.py check

setup-dev:
	@echo "🛠️  Setting up development environment..."
	poetry install
	poetry run python scripts/run_tests.py check
	@echo "✅ Development environment ready!"

# Test specific files
test-file:
	@if [ -z "$(FILE)" ]; then \
		echo "❌ Please specify FILE=path/to/test.py"; \
		exit 1; \
	fi
	@echo "🧪 Running specific test file: $(FILE)"
	poetry run python scripts/run_tests.py --test-path $(FILE)

# Coverage specific
coverage-html:
	@echo "📊 Opening coverage HTML report..."
	@if [ -f "htmlcov/index.html" ]; then \
		if command -v xdg-open > /dev/null; then \
			xdg-open htmlcov/index.html; \
		elif command -v open > /dev/null; then \
			open htmlcov/index.html; \
		else \
			echo "📊 Coverage report available at: htmlcov/index.html"; \
		fi \
	else \
		echo "❌ Coverage report not found. Run 'make test-coverage' first."; \
	fi

# Performance testing
test-performance:
	@echo "⚡ Running performance tests..."
	poetry run pytest tests/ -m "not slow" --durations=0 -v

# Security testing
test-security:
	@echo "🔒 Running security tests..."
	poetry run bandit -r src/
	poetry run safety check

# All-in-one development command
dev-setup: install-dev check-env
	@echo "🎉 Development environment is ready!"
	@echo ""
	@echo "Quick commands:"
	@echo "  make test-quick    - Run quick tests"
	@echo "  make dev          - Start development server"
	@echo "  make lint         - Check code quality"
	@echo "  make format       - Format code"
