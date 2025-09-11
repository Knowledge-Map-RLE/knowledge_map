# Makefile для управления тестами и разработкой
# Использование: make <команда>

.PHONY: help install test test-topological test-validation test-all test-watch test-coverage test-performance test-integration test-unit clean lint format type-check setup-hooks

# Цвета для вывода
GREEN=\033[0;32m
YELLOW=\033[1;33m
RED=\033[0;31m
NC=\033[0m # No Color

help: ## Показать справку по доступным командам
	@echo "$(GREEN)Доступные команды:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Примеры использования:$(NC)"
	@echo "  make test-topological    # Запустить тесты топологической сортировки"
	@echo "  make test-watch          # Запустить тесты в режиме наблюдения"
	@echo "  make test-coverage       # Генерировать отчет о покрытии"
	@echo "  make lint                # Проверить стиль кода"
	@echo "  make format              # Отформатировать код"

install: ## Установить зависимости
	@echo "$(GREEN)📦 Установка зависимостей...$(NC)"
	poetry install
	@echo "$(GREEN)✅ Зависимости установлены$(NC)"

setup-hooks: ## Настроить pre-commit хуки
	@echo "$(GREEN)🔧 Настройка pre-commit хуков...$(NC)"
	poetry run pre-commit install
	@echo "$(GREEN)✅ Pre-commit хуки настроены$(NC)"

test: ## Запустить все тесты
	@echo "$(GREEN)🧪 Запуск всех тестов...$(NC)"
	poetry run pytest -v

test-topological: ## Запустить тесты топологической сортировки
	@echo "$(GREEN)🔍 Запуск тестов топологической сортировки...$(NC)"
	poetry run pytest tests/test_topological_sort.py -v

test-validation: ## Запустить тесты валидации топологического порядка
	@echo "$(GREEN)✅ Запуск тестов валидации...$(NC)"
	poetry run pytest tests/test_topological_validation.py -v

test-all: ## Запустить все тесты с покрытием
	@echo "$(GREEN)🧪 Запуск всех тестов с покрытием...$(NC)"
	poetry run pytest --cov=src --cov-report=term-missing --cov-report=html:htmlcov -v

test-watch: ## Запустить тесты в режиме наблюдения за изменениями
	@echo "$(GREEN)👀 Запуск тестов в режиме наблюдения...$(NC)"
	@echo "$(YELLOW)Нажмите Ctrl+C для остановки$(NC)"
	poetry run ptw --runner "pytest -v --tb=short"

test-coverage: ## Генерировать подробный отчет о покрытии кода
	@echo "$(GREEN)📊 Генерация отчета о покрытии...$(NC)"
	poetry run pytest --cov=src --cov-report=html:htmlcov --cov-report=xml:coverage.xml --cov-report=term-missing -v
	@echo "$(GREEN)✅ Отчет создан:$(NC)"
	@echo "  📁 HTML: htmlcov/index.html"
	@echo "  📄 XML: coverage.xml"

test-performance: ## Запустить тесты производительности
	@echo "$(GREEN)⚡ Запуск тестов производительности...$(NC)"
	poetry run pytest -m performance -v

test-integration: ## Запустить интеграционные тесты
	@echo "$(GREEN)🔗 Запуск интеграционных тестов...$(NC)"
	poetry run pytest -m integration -v

test-unit: ## Запустить unit тесты
	@echo "$(GREEN)🧪 Запуск unit тестов...$(NC)"
	poetry run pytest -m unit -v

test-parallel: ## Запустить тесты параллельно
	@echo "$(GREEN)🚀 Запуск тестов параллельно...$(NC)"
	poetry run pytest -n auto -v

lint: ## Проверить стиль кода
	@echo "$(GREEN)🔍 Проверка стиля кода...$(NC)"
	poetry run flake8 src tests --max-line-length=100 --extend-ignore=E203,W503
	@echo "$(GREEN)✅ Проверка стиля завершена$(NC)"

format: ## Отформатировать код
	@echo "$(GREEN)🎨 Форматирование кода...$(NC)"
	poetry run black src tests --line-length=100
	poetry run isort src tests --profile=black --line-length=100
	@echo "$(GREEN)✅ Код отформатирован$(NC)"

type-check: ## Проверить типы
	@echo "$(GREEN)🔍 Проверка типов...$(NC)"
	poetry run mypy src --ignore-missing-imports
	@echo "$(GREEN)✅ Проверка типов завершена$(NC)"

check-all: lint type-check test ## Запустить все проверки
	@echo "$(GREEN)✅ Все проверки пройдены$(NC)"

clean: ## Очистить временные файлы
	@echo "$(GREEN)🧹 Очистка временных файлов...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type f -name "coverage.xml" -delete
	find . -type f -name ".coverage" -delete
	@echo "$(GREEN)✅ Очистка завершена$(NC)"

# Команды для разработки
dev-setup: install setup-hooks ## Полная настройка окружения разработки
	@echo "$(GREEN)🚀 Окружение разработки настроено$(NC)"

dev-test: test-topological test-validation ## Быстрые тесты для разработки
	@echo "$(GREEN)✅ Быстрые тесты пройдены$(NC)"

# Команды для CI/CD
ci-test: ## Тесты для CI/CD
	@echo "$(GREEN)🤖 Запуск тестов для CI/CD...$(NC)"
	poetry run pytest --cov=src --cov-report=xml --cov-report=term-missing --junitxml=test-results.xml -v

ci-lint: ## Проверки для CI/CD
	@echo "$(GREEN)🤖 Запуск проверок для CI/CD...$(NC)"
	poetry run flake8 src tests --max-line-length=100 --extend-ignore=E203,W503
	poetry run mypy src --ignore-missing-imports
	poetry run black --check src tests --line-length=100
	poetry run isort --check-only src tests --profile=black --line-length=100

# Специальные команды для топологической сортировки
test-topo-full: ## Полный тест топологической сортировки
	@echo "$(GREEN)🔍 Полный тест топологической сортировки...$(NC)"
	poetry run pytest tests/test_topological_sort.py tests/test_topological_validation.py -v --cov=src.algorithms.topological_sort --cov-report=term-missing

test-topo-watch: ## Тесты топологической сортировки в режиме наблюдения
	@echo "$(GREEN)👀 Тесты топологической сортировки в режиме наблюдения...$(NC)"
	poetry run ptw tests/test_topological_sort.py tests/test_topological_validation.py --runner "pytest -v --tb=short"

# Команды для отладки
debug-test: ## Запустить тесты с подробным выводом
	@echo "$(GREEN)🐛 Запуск тестов с подробным выводом...$(NC)"
	poetry run pytest -vvv --tb=long --capture=no

debug-topological: ## Отладка тестов топологической сортировки
	@echo "$(GREEN)🐛 Отладка тестов топологической сортировки...$(NC)"
	poetry run pytest tests/test_topological_sort.py -vvv --tb=long --capture=no

# Статистика
stats: ## Показать статистику тестов
	@echo "$(GREEN)📊 Статистика тестов:$(NC)"
	@echo "Всего тестов:"
	@poetry run pytest --collect-only -q | grep -c "test session starts" || echo "0"
	@echo "Тесты топологической сортировки:"
	@poetry run pytest tests/test_topological_sort.py --collect-only -q | grep -c "test session starts" || echo "0"
	@echo "Тесты валидации:"
	@poetry run pytest tests/test_topological_validation.py --collect-only -q | grep -c "test session starts" || echo "0"
