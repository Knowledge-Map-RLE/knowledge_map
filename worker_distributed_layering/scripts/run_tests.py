#!/usr/bin/env python3
"""
Скрипт для запуска тестов с различными опциями.
Поддерживает фильтрацию по типам тестов, автозапуск при изменениях и другие возможности.
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from typing import List, Optional


def run_command(cmd: List[str], cwd: Optional[Path] = None) -> int:
    """Запускает команду и возвращает код возврата"""
    try:
        result = subprocess.run(cmd, cwd=cwd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n❌ Тесты прерваны пользователем")
        return 1
    except Exception as e:
        print(f"❌ Ошибка при запуске команды: {e}")
        return 1


def run_tests(
    test_pattern: Optional[str] = None,
    markers: Optional[str] = None,
    watch: bool = False,
    coverage: bool = True,
    verbose: bool = True,
    parallel: bool = False,
    num_workers: int = 4
) -> int:
    """Запускает тесты с указанными параметрами"""
    
    # Базовые команды poetry
    cmd = ["poetry", "run", "pytest"]
    
    # Добавляем опции
    if verbose:
        cmd.append("-v")
    
    if coverage:
        cmd.extend(["--cov=src", "--cov-report=term-missing"])
    
    if parallel:
        cmd.extend(["-n", str(num_workers)])
    
    if markers:
        cmd.extend(["-m", markers])
    
    if test_pattern:
        cmd.append(test_pattern)
    
    if watch:
        cmd.extend(["-f", "--tb=short"])
    
    print(f"🚀 Запуск тестов: {' '.join(cmd)}")
    return run_command(cmd, cwd=Path(__file__).parent.parent)


def run_specific_test_suite(suite: str) -> int:
    """Запускает конкретный набор тестов"""
    suites = {
        "topological": "tests/test_topological_sort.py",
        "validation": "tests/test_topological_validation.py",
        "neo4j": "tests/test_neo4j_client.py",
        "distributed": "tests/test_distributed_layout.py",
        "tasks": "tests/test_tasks.py",
        "all": "tests/"
    }
    
    if suite not in suites:
        print(f"❌ Неизвестный набор тестов: {suite}")
        print(f"Доступные наборы: {', '.join(suites.keys())}")
        return 1
    
    test_path = suites[suite]
    return run_tests(test_pattern=test_path)


def run_with_watch() -> int:
    """Запускает тесты в режиме наблюдения за изменениями"""
    print("👀 Запуск тестов в режиме наблюдения за изменениями...")
    print("Нажмите Ctrl+C для остановки")
    
    # Устанавливаем pytest-watch если не установлен
    try:
        subprocess.run(["poetry", "run", "pip", "install", "pytest-watch"], check=True)
    except subprocess.CalledProcessError:
        print("⚠️ Не удалось установить pytest-watch, используем обычный режим")
        return run_tests(watch=True)
    
    cmd = ["poetry", "run", "ptw", "--runner", "pytest", "-v", "--tb=short"]
    return run_command(cmd, cwd=Path(__file__).parent.parent)


def run_performance_tests() -> int:
    """Запускает тесты производительности"""
    print("⚡ Запуск тестов производительности...")
    return run_tests(markers="performance", coverage=False)


def run_integration_tests() -> int:
    """Запускает интеграционные тесты"""
    print("🔗 Запуск интеграционных тестов...")
    return run_tests(markers="integration")


def run_unit_tests() -> int:
    """Запускает unit тесты"""
    print("🧪 Запуск unit тестов...")
    return run_tests(markers="unit")


def run_coverage_report() -> int:
    """Генерирует отчет о покрытии кода"""
    print("📊 Генерация отчета о покрытии кода...")
    
    # Запускаем тесты с покрытием
    cmd = [
        "poetry", "run", "pytest",
        "--cov=src",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--cov-report=term-missing",
        "-v"
    ]
    
    result = run_command(cmd, cwd=Path(__file__).parent.parent)
    
    if result == 0:
        print("✅ Отчет о покрытии создан:")
        print("   📁 HTML отчет: htmlcov/index.html")
        print("   📄 XML отчет: coverage.xml")
    
    return result


def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(
        description="Скрипт для запуска тестов топологической сортировки",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Запуск всех тестов
  python scripts/run_tests.py

  # Запуск только тестов топологической сортировки
  python scripts/run_tests.py --suite topological

  # Запуск тестов в режиме наблюдения
  python scripts/run_tests.py --watch

  # Запуск тестов производительности
  python scripts/run_tests.py --performance

  # Запуск с параллельным выполнением
  python scripts/run_tests.py --parallel --workers 8

  # Генерация отчета о покрытии
  python scripts/run_tests.py --coverage-report
        """
    )
    
    parser.add_argument(
        "--suite", "-s",
        choices=["topological", "validation", "neo4j", "distributed", "tasks", "all"],
        help="Запустить конкретный набор тестов"
    )
    
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Запустить тесты в режиме наблюдения за изменениями"
    )
    
    parser.add_argument(
        "--performance", "-p",
        action="store_true",
        help="Запустить тесты производительности"
    )
    
    parser.add_argument(
        "--integration", "-i",
        action="store_true",
        help="Запустить интеграционные тесты"
    )
    
    parser.add_argument(
        "--unit", "-u",
        action="store_true",
        help="Запустить unit тесты"
    )
    
    parser.add_argument(
        "--parallel", "-P",
        action="store_true",
        help="Запустить тесты параллельно"
    )
    
    parser.add_argument(
        "--workers", "-W",
        type=int,
        default=4,
        help="Количество воркеров для параллельного выполнения (по умолчанию: 4)"
    )
    
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Отключить отчет о покрытии кода"
    )
    
    parser.add_argument(
        "--coverage-report",
        action="store_true",
        help="Генерировать подробный отчет о покрытии кода"
    )
    
    parser.add_argument(
        "--pattern",
        help="Шаблон для фильтрации тестов (например: test_topological*)"
    )
    
    parser.add_argument(
        "--markers", "-m",
        help="Маркеры для фильтрации тестов (например: 'not slow')"
    )
    
    args = parser.parse_args()
    
    # Проверяем, что мы в правильной директории
    if not Path("pyproject.toml").exists():
        print("❌ Ошибка: pyproject.toml не найден. Запустите скрипт из корневой директории проекта.")
        return 1
    
    # Выполняем соответствующие действия
    if args.coverage_report:
        return run_coverage_report()
    
    if args.watch:
        return run_with_watch()
    
    if args.performance:
        return run_performance_tests()
    
    if args.integration:
        return run_integration_tests()
    
    if args.unit:
        return run_unit_tests()
    
    if args.suite:
        return run_specific_test_suite(args.suite)
    
    # Обычный запуск тестов
    return run_tests(
        test_pattern=args.pattern,
        markers=args.markers,
        coverage=not args.no_coverage,
        parallel=args.parallel,
        num_workers=args.workers
    )


if __name__ == "__main__":
    sys.exit(main())
