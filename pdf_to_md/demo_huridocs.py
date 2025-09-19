#!/usr/bin/env python3
"""
Демонстрационный скрипт для модели HURIDOCS/pdf-document-layout-analysis
Показывает полный процесс: загрузка модели -> конвертация PDF -> сохранение в S3
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
import tempfile
import shutil
import json
from datetime import datetime

# Добавляем путь к src для импорта модулей
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.models.huridocs_model import huridocs_model

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Путь к тестовому PDF файлу
TEST_PDF_PATH = r"D:\Knowledge_Map\knowledge_map\personal_folder\The FEBS Journal - 2013 - Antony - The hallmarks of Parkinson s disease.pdf"

class S3Simulator:
    """Симулятор S3 для демонстрации сохранения файлов"""
    
    def __init__(self, local_dir: str = "s3_simulation"):
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(exist_ok=True)
        logger.info(f"📁 S3 симулятор инициализирован: {self.local_dir.absolute()}")
    
    async def save_markdown(self, content: str, doc_id: str) -> str:
        """Сохраняет markdown в S3 (симуляция)"""
        filename = f"{doc_id}.md"
        filepath = self.local_dir / filename
        
        filepath.write_text(content, encoding="utf-8")
        
        # Симулируем S3 URL
        s3_url = f"s3://knowledge-map-bucket/markdown/{filename}"
        logger.info(f"💾 Markdown сохранен в S3: {s3_url}")
        logger.info(f"📁 Локальная копия: {filepath}")
        
        return s3_url
    
    async def save_images(self, images: dict, doc_id: str) -> list:
        """Сохраняет изображения в S3 (симуляция)"""
        s3_urls = []
        
        for img_name, img_data in images.items():
            filepath = self.local_dir / img_name
            filepath.write_bytes(img_data)
            
            s3_url = f"s3://knowledge-map-bucket/images/{doc_id}/{img_name}"
            s3_urls.append(s3_url)
            logger.info(f"🖼️ Изображение сохранено в S3: {s3_url}")
        
        return s3_urls
    
    async def save_metadata(self, metadata: dict, doc_id: str) -> str:
        """Сохраняет метаданные в S3 (симуляция)"""
        filename = f"{doc_id}_metadata.json"
        filepath = self.local_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        s3_url = f"s3://knowledge-map-bucket/metadata/{filename}"
        logger.info(f"📊 Метаданные сохранены в S3: {s3_url}")
        
        return s3_url

async def demo_full_workflow():
    """Демонстрирует полный рабочий процесс"""
    
    logger.info("🚀 ДЕМОНСТРАЦИЯ: Полный рабочий процесс HURIDOCS")
    logger.info("=" * 60)
    
    # Проверяем PDF файл
    if not os.path.exists(TEST_PDF_PATH):
        logger.error(f"❌ PDF файл не найден: {TEST_PDF_PATH}")
        return False
    
    # Инициализируем S3 симулятор
    s3 = S3Simulator()
    
    # Создаем временную директорию
    with tempfile.TemporaryDirectory(prefix="huridocs_demo_") as temp_dir:
        temp_path = Path(temp_dir)
        logger.info(f"📁 Временная директория: {temp_path}")
        
        # Копируем PDF
        pdf_name = Path(TEST_PDF_PATH).name
        temp_pdf_path = temp_path / pdf_name
        shutil.copy2(TEST_PDF_PATH, temp_pdf_path)
        
        # Генерируем doc_id
        doc_id = f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"🆔 ID документа: {doc_id}")
        
        # Callback для прогресса
        def progress_callback(payload):
            logger.info(f"📊 Прогресс: {payload.get('percent', 0)}% - {payload.get('message', '')}")
        
        try:
            # ЭТАП 1: Конвертация PDF в Markdown
            logger.info("\n🔄 ЭТАП 1: Конвертация PDF в Markdown")
            logger.info("-" * 40)
            
            result_dir = await huridocs_model.convert_pdf_to_markdown(
                temp_path,
                on_progress=progress_callback,
                doc_id=doc_id
            )
            
            # Читаем результаты
            pdf_stem = Path(pdf_name).stem
            markdown_path = result_dir / f"{pdf_stem}.md"
            metadata_path = result_dir / f"{pdf_stem}_metadata.json"
            
            if not markdown_path.exists():
                logger.error("❌ Markdown файл не создан")
                return False
            
            markdown_content = markdown_path.read_text(encoding="utf-8")
            metadata = {}
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            
            # Собираем изображения
            images = {}
            image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]
            for ext in image_extensions:
                for img_file in result_dir.glob(ext):
                    images[img_file.name] = img_file.read_bytes()
            
            logger.info(f"✅ Конвертация завершена!")
            logger.info(f"📄 Markdown: {len(markdown_content)} символов")
            logger.info(f"🖼️ Изображения: {len(images)} файлов")
            logger.info(f"📊 Метаданные: {len(metadata)} полей")
            
            # ЭТАП 2: Сохранение в S3
            logger.info("\n💾 ЭТАП 2: Сохранение в S3")
            logger.info("-" * 40)
            
            # Сохраняем markdown
            markdown_s3_url = await s3.save_markdown(markdown_content, doc_id)
            
            # Сохраняем изображения
            image_s3_urls = await s3.save_images(images, doc_id)
            
            # Сохраняем метаданные
            metadata_s3_url = await s3.save_metadata(metadata, doc_id)
            
            # ЭТАП 3: Подготовка данных для клиента
            logger.info("\n🌐 ЭТАП 3: Подготовка данных для клиента")
            logger.info("-" * 40)
            
            client_data = {
                "doc_id": doc_id,
                "status": "completed",
                "markdown_url": markdown_s3_url,
                "images": image_s3_urls,
                "metadata_url": metadata_s3_url,
                "created_at": datetime.now().isoformat(),
                "model_used": "HURIDOCS/pdf-document-layout-analysis",
                "stats": {
                    "text_length": len(markdown_content),
                    "images_count": len(images),
                    "pages_processed": metadata.get("total_pages", 0)
                }
            }
            
            # Сохраняем данные для клиента
            client_data_path = s3.local_dir / f"{doc_id}_client_data.json"
            with open(client_data_path, 'w', encoding='utf-8') as f:
                json.dump(client_data, f, ensure_ascii=False, indent=2)
            
            logger.info("✅ Данные для клиента подготовлены!")
            logger.info(f"📋 Клиентские данные: {client_data_path}")
            
            # ЭТАП 4: Демонстрация результата
            logger.info("\n🎉 ЭТАП 4: Результат")
            logger.info("-" * 40)
            
            logger.info("📊 СТАТИСТИКА:")
            logger.info(f"   📄 Документ: {doc_id}")
            logger.info(f"   📝 Текст: {len(markdown_content)} символов")
            logger.info(f"   🖼️ Изображения: {len(images)} файлов")
            logger.info(f"   📊 Страниц: {metadata.get('total_pages', 0)}")
            
            logger.info("\n🔗 S3 URLS:")
            logger.info(f"   📄 Markdown: {markdown_s3_url}")
            logger.info(f"   📊 Метаданные: {metadata_s3_url}")
            for i, img_url in enumerate(image_s3_urls, 1):
                logger.info(f"   🖼️ Изображение {i}: {img_url}")
            
            logger.info("\n📄 ПРЕВЬЮ MARKDOWN:")
            logger.info("-" * 40)
            preview = markdown_content[:300] + "..." if len(markdown_content) > 300 else markdown_content
            logger.info(preview)
            
            logger.info("\n🎯 ГОТОВО ДЛЯ КЛИЕНТА!")
            logger.info("Клиент может использовать данные из client_data.json для:")
            logger.info("  - Отображения markdown для разметки")
            logger.info("  - Загрузки изображений")
            logger.info("  - Отображения метаданных")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка в демонстрации: {e}")
            return False

async def main():
    """Основная функция"""
    
    logger.info("🎬 ДЕМОНСТРАЦИЯ HURIDOCS/pdf-document-layout-analysis")
    logger.info("=" * 60)
    logger.info("Этот скрипт демонстрирует полный рабочий процесс:")
    logger.info("1. Загрузка модели HURIDOCS")
    logger.info("2. Конвертация PDF в Markdown")
    logger.info("3. Сохранение в S3 (симуляция)")
    logger.info("4. Подготовка данных для клиента")
    logger.info("=" * 60)
    
    success = await demo_full_workflow()
    
    if success:
        logger.info("\n🎉 ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        logger.info("📁 Все файлы сохранены в папке: s3_simulation/")
        logger.info("🌐 Модель готова к использованию в продакшене!")
    else:
        logger.error("\n💥 ДЕМОНСТРАЦИЯ НЕ УДАЛАСЬ!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
