"""Утилиты для работы с Marker CLI в тестах"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def check_marker_cli_available() -> bool:
    """Проверяет, доступен ли Marker CLI"""
    # Пробуем разные способы запуска Marker
    commands = [
        (['marker', '--help'], 10),
        (['poetry', 'run', 'marker', '--help'], 30),  # Poetry может занимать больше времени
        (['python', '-m', 'marker', '--help'], 10)
    ]
    
    for cmd, timeout in commands:
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            if result.returncode == 0:
                logger.info(f"✅ Marker CLI найден через: {' '.join(cmd)}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug(f"❌ Команда {' '.join(cmd)} не сработала: {e}")
            continue
    
    logger.error("❌ Marker CLI не найден ни одним из способов")
    return False


def check_marker_models_available() -> bool:
    """Проверяет, доступны ли модели Marker"""
    models_dir = Path("./marker_models")
    if not models_dir.exists():
        logger.error("❌ Папка marker_models не найдена")
        return False
    
    # Проверяем наличие папки hub с моделями
    hub_dir = models_dir / "hub"
    if not hub_dir.exists():
        logger.error("❌ Папка marker_models/hub не найдена")
        return False
    
    # Проверяем наличие файлов моделей
    model_files = list(hub_dir.rglob("*.safetensors")) + list(hub_dir.rglob("*.bin"))
    if len(model_files) == 0:
        logger.error("❌ Файлы моделей не найдены в marker_models/hub")
        return False
    
    logger.info(f"✅ Найдено {len(model_files)} файлов моделей в marker_models/hub")
    return True


def setup_marker_environment() -> bool:
    """Настраивает окружение для Marker CLI"""
    # Устанавливаем переменные окружения для использования локальных моделей
    os.environ["HF_HOME"] = str(Path("./marker_models/hub").absolute())
    os.environ["TRANSFORMERS_CACHE"] = str(Path("./marker_models/hub").absolute())
    os.environ["TORCH_HOME"] = str(Path("./marker_models").absolute())
    
    # Добавляем папку с моделями в PYTHONPATH
    marker_models_path = str(Path("./marker_models").absolute())
    if marker_models_path not in os.environ.get("PYTHONPATH", ""):
        current_pythonpath = os.environ.get("PYTHONPATH", "")
        if current_pythonpath:
            os.environ["PYTHONPATH"] = f"{marker_models_path}:{current_pythonpath}"
        else:
            os.environ["PYTHONPATH"] = marker_models_path
    
    logger.info(f"Настроено окружение Marker: HF_HOME={os.environ['HF_HOME']}")
    return True


def download_marker_models_if_needed() -> bool:
    """Загружает модели Marker, если они недоступны"""
    if check_marker_models_available():
        logger.info("✅ Модели Marker уже доступны")
        return True
    
    logger.info("🔄 Модели Marker недоступны, запускаем загрузку...")
    
    try:
        # Запускаем скрипт загрузки моделей
        result = subprocess.run(
            ['python', 'download_marker_models.py'],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=1800  # 30 минут на загрузку
        )
        
        if result.returncode == 0:
            logger.info("✅ Модели Marker успешно загружены")
            return True
        else:
            logger.error(f"❌ Ошибка загрузки моделей: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ Таймаут при загрузке моделей Marker")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке моделей: {e}")
        return False


def prepare_test_pdf() -> Optional[Path]:
    """Подготавливает тестовый PDF файл"""
    # Используем реальный PDF из personal_folder
    source_pdf = Path("../personal_folder/The FEBS Journal - 2013 - Antony - The hallmarks of Parkinson s disease.pdf")
    
    if not source_pdf.exists():
        logger.error(f"❌ Тестовый PDF не найден: {source_pdf}")
        return None
    
    # Создаем временную копию для тестов
    temp_dir = Path(tempfile.mkdtemp(prefix="marker_test_"))
    test_pdf = temp_dir / "test_parkinson.pdf"
    
    try:
        shutil.copy2(source_pdf, test_pdf)
        logger.info(f"✅ Тестовый PDF подготовлен: {test_pdf}")
        return test_pdf
    except Exception as e:
        logger.error(f"❌ Ошибка копирования PDF: {e}")
        return None


def run_marker_conversion(input_pdf: Path, output_dir: Path) -> Tuple[bool, str, str]:
    """Запускает конвертацию PDF через Marker CLI"""
    try:
        # Создаем входную папку для Marker
        input_dir = input_pdf.parent / "input"
        input_dir.mkdir(exist_ok=True)
        
        # Копируем PDF в входную папку
        marker_input = input_dir / input_pdf.name
        shutil.copy2(input_pdf, marker_input)
        
        # Запускаем Marker
        result = subprocess.run(
            ['marker', str(input_dir)],
            capture_output=True,
            text=True,
            timeout=600,  # 10 минут на конвертацию
            cwd=input_pdf.parent
        )
        
        return result.returncode == 0, result.stdout, result.stderr
        
    except subprocess.TimeoutExpired:
        return False, "", "Таймаут при конвертации"
    except Exception as e:
        return False, "", str(e)


def cleanup_temp_files(temp_path: Path):
    """Очищает временные файлы"""
    try:
        if temp_path.exists():
            shutil.rmtree(temp_path)
            logger.info(f"✅ Временные файлы очищены: {temp_path}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось очистить временные файлы: {e}")


def ensure_marker_ready() -> bool:
    """Проверяет и подготавливает Marker для тестов"""
    # Настраиваем окружение
    setup_marker_environment()
    
    # Проверяем CLI
    if not check_marker_cli_available():
        logger.error("❌ Marker CLI недоступен")
        return False
    
    # Проверяем/загружаем модели
    if not download_marker_models_if_needed():
        logger.error("❌ Не удалось подготовить модели Marker")
        return False
    
    logger.info("✅ Marker готов к использованию в тестах")
    return True
