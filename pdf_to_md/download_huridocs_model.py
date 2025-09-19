#!/usr/bin/env python3
"""
Скрипт для предзагрузки модели HURIDOCS/pdf-document-layout-analysis
"""
import os
import sys
import logging
from pathlib import Path
from huggingface_hub import hf_hub_download, list_repo_files
import json

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_huridocs_model():
    """Загружает модель HURIDOCS/pdf-document-layout-analysis"""
    
    model_name = "HURIDOCS/pdf-document-layout-analysis"
    models_dir = Path("models")
    model_dir = models_dir / "pdf-document-layout-analysis"
    
    # Создаем директорию для моделей
    model_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"🔄 Загрузка модели {model_name}...")
    logger.info(f"📁 Директория для модели: {model_dir.absolute()}")
    
    try:
        # Получаем список файлов в репозитории
        logger.info("📋 Получение списка файлов модели...")
        files = list_repo_files(model_name)
        logger.info(f"📄 Файлы модели: {files}")
        
        # Загружаем каждый файл
        downloaded_files = []
        for file in files:
            if file.endswith(('.model', '.json', '.md')):
                logger.info(f"📥 Загрузка файла: {file}")
                local_path = hf_hub_download(
                    repo_id=model_name,
                    filename=file,
                    cache_dir=str(model_dir),
                    local_files_only=False
                )
                downloaded_files.append(local_path)
                logger.info(f"✅ Файл загружен: {local_path}")
        
        # Создаем конфигурационный файл
        config = {
            "model_name": model_name,
            "model_type": "lightgbm",
            "files": files,
            "downloaded_files": downloaded_files,
            "description": "HURIDOCS PDF Document Layout Analysis - LightGBM модели для анализа структуры PDF"
        }
        
        config_path = model_dir / "model_config.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info("✅ Модель успешно загружена и сохранена!")
        logger.info(f"📁 Модель сохранена в: {model_dir.absolute()}")
        
        # Проверяем размер модели
        model_size = sum(f.stat().st_size for f in model_dir.rglob('*') if f.is_file())
        model_size_mb = model_size / (1024 * 1024)
        logger.info(f"📊 Размер модели: {model_size_mb:.1f} MB")
        
        return str(model_dir.absolute())
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки модели: {e}")
        return None

def test_model_loading():
    """Тестирует загрузку предзагруженной модели"""
    
    model_name = "HURIDOCS/pdf-document-layout-analysis"
    models_dir = Path("models")
    model_dir = models_dir / "pdf-document-layout-analysis"
    
    if not model_dir.exists():
        logger.error("❌ Модель не найдена. Сначала запустите загрузку.")
        return False
    
    try:
        logger.info("🧪 Тестирование загрузки предзагруженной модели...")
        
        # Проверяем конфигурационный файл
        config_path = model_dir / "model_config.json"
        if not config_path.exists():
            logger.error("❌ Конфигурационный файл не найден.")
            return False
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        logger.info("✅ Модель успешно загружена из локального кэша!")
        logger.info(f"📊 Тип модели: {config.get('model_type', 'unknown')}")
        logger.info(f"📊 Файлы модели: {config.get('files', [])}")
        logger.info(f"📊 Описание: {config.get('description', '')}")
        
        # Проверяем наличие файлов модели
        for file in config.get('files', []):
            if file.endswith('.model'):
                logger.info(f"📄 Файл модели найден: {file}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки модели из кэша: {e}")
        return False

def main():
    """Основная функция"""
    logger.info("🚀 Скрипт предзагрузки модели HURIDOCS/pdf-document-layout-analysis")
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Тестируем загрузку
        success = test_model_loading()
        if success:
            logger.info("🎉 Тест прошел успешно!")
        else:
            logger.error("💥 Тест не прошел!")
            sys.exit(1)
    else:
        # Загружаем модель
        model_path = download_huridocs_model()
        if model_path:
            logger.info("🎉 Загрузка завершена успешно!")
            logger.info(f"📁 Модель доступна по пути: {model_path}")
            logger.info("🧪 Для тестирования запустите: python download_huridocs_model.py test")
        else:
            logger.error("💥 Загрузка не удалась!")
            sys.exit(1)

if __name__ == "__main__":
    main()
