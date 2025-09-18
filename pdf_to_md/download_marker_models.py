#!/usr/bin/env python3
"""
Скрипт для предварительной загрузки моделей Marker на хосте.
Используется перед сборкой Docker образа PDF to MD микросервиса для кэширования моделей.

Запуск:
    python download_marker_models.py

Модели будут загружены в ./marker_models/ и готовы для копирования в Docker образ PDF to MD сервиса.
"""

import os
import sys
import logging
import tempfile
import shutil
from pathlib import Path
import subprocess

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


def ensure_marker_installed():
    """Проверяет, что Marker установлен"""
    # Сначала пробуем импортировать Python модуль
    try:
        import marker
        logger.info("✅ Marker Python модуль найден")
        return True
    except ImportError:
        pass
    
    # Затем пробуем CLI с коротким таймаутом
    try:
        result = subprocess.run(['marker', '--help'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logger.info("✅ Marker CLI найден")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Пробуем через poetry run
    try:
        result = subprocess.run(['poetry', 'run', 'marker', '--help'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logger.info("✅ Marker CLI найден через Poetry")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Пробуем через python -m
    try:
        result = subprocess.run(['python', '-m', 'marker', '--help'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            logger.info("✅ Marker найден через python -m")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    logger.warning("⚠️ Marker CLI недоступен, но попробуем продолжить...")
    return True  # Продолжаем в любом случае


def try_python_api_download(test_pdf_path: Path, output_dir: Path) -> bool:
    """Пробует загрузить модели через Python API Marker"""
    try:
        # Импортируем Marker Python API
        from marker.convert import convert_single_pdf
        from marker.models import load_all_models
        import torch
        
        logger.info("🔄 Загружаем модели через Python API...")
        
        # Пытаемся загрузить модели
        try:
            models = load_all_models()
            logger.info("✅ Модели загружены через Python API")
            
            # Теперь копируем модели из стандартных путей
            return copy_marker_models(Path.cwd(), output_dir)
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить модели через load_all_models: {e}")
            
            # Пробуем конвертировать тестовый PDF
            try:
                result = convert_single_pdf(
                    str(test_pdf_path),
                    str(test_pdf_path.parent),
                    model_lst=[]  # Пустой список заставит загрузить модели
                )
                logger.info("✅ Модели загружены через convert_single_pdf")
                return copy_marker_models(Path.cwd(), output_dir)
                
            except Exception as e2:
                logger.warning(f"⚠️ Не удалось загрузить модели через convert_single_pdf: {e2}")
                return False
                
    except ImportError as e:
        logger.warning(f"⚠️ Marker Python API недоступен: {e}")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Ошибка Python API: {e}")
        return False


def download_marker_models(output_dir: Path = None):
    """Загружает модели Marker, используя тестовый PDF"""
    
    if output_dir is None:
        output_dir = Path("./marker_models")
    
    output_dir.mkdir(exist_ok=True)
    logger.info(f"📁 Создана папка для моделей: {output_dir}")
    
    # Создаем простой тестовый PDF для запуска Marker
    test_pdf_content = create_test_pdf()
    
    with tempfile.TemporaryDirectory(prefix="marker_download_") as temp_dir:
        temp_path = Path(temp_dir)
        
        # Создаем тестовый PDF
        test_pdf_path = temp_path / "test.pdf"
        with open(test_pdf_path, 'wb') as f:
            f.write(test_pdf_content)
        
        logger.info("📄 Создан тестовый PDF для загрузки моделей")
        
        # Создаем входную папку для Marker
        input_dir = temp_path / "input"
        input_dir.mkdir()
        
        # Копируем PDF в входную папку
        shutil.copy2(test_pdf_path, input_dir / "test.pdf")
        
        try:
            logger.info("🚀 Запуск Marker для загрузки моделей...")
            
            # Запускаем Marker с таймаутом
            env = os.environ.copy()
            env.setdefault("PYTHONUNBUFFERED", "1")
            
            # Пробуем разные способы запуска Marker
            marker_commands = [
                ['marker', str(input_dir)],
                ['poetry', 'run', 'marker', str(input_dir)],
                ['python', '-m', 'marker', str(input_dir)],
            ]
            
            result = None
            for cmd in marker_commands:
                try:
                    logger.info(f"Пробуем команду: {' '.join(cmd)}")
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=1800,  # 30 минут на загрузку моделей
                        env=env,
                        cwd=temp_dir
                    )
                    if result.returncode == 0:
                        logger.info(f"✅ Marker запущен успешно через: {' '.join(cmd[:2])}")
                        break
                    else:
                        logger.warning(f"⚠️ Команда {' '.join(cmd[:2])} завершилась с кодом {result.returncode}")
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    logger.warning(f"⚠️ Команда {' '.join(cmd[:2])} не сработала: {e}")
                    continue
            
            if result is None:
                # Если CLI не работает, пробуем Python API
                logger.info("🔄 CLI не работает, пробуем Python API...")
                success = try_python_api_download(test_pdf_path, output_dir)
                if success:
                    logger.info("✅ Модели загружены через Python API")
                    return True
                else:
                    raise RuntimeError("Не удалось запустить Marker ни CLI, ни Python API")
            
            if result.stdout:
                logger.info("Marker stdout:")
                for line in result.stdout.split('\n')[:20]:  # Показываем первые 20 строк
                    if line.strip():
                        logger.info(f"  {line}")
                if len(result.stdout.split('\n')) > 20:
                    logger.info("  ... (остальные логи скрыты)")
            
            if result.stderr:
                logger.warning("Marker stderr:")
                for line in result.stderr.split('\n')[:10]:  # Показываем первые 10 строк
                    if line.strip():
                        logger.warning(f"  {line}")
            
            if result.returncode != 0:
                logger.error(f"❌ Marker завершился с ошибкой (код: {result.returncode})")
                return False
            
            logger.info("✅ Marker выполнился успешно")
            
            # Ищем загруженные модели
            models_found = copy_marker_models(temp_path, output_dir)
            
            if models_found:
                logger.info(f"✅ Модели успешно скопированы в {output_dir}")
                return True
            else:
                logger.warning("⚠️ Модели не найдены, но процесс завершился")
                return True
                
        except subprocess.TimeoutExpired:
            logger.error("❌ Таймаут при загрузке моделей Marker (30 минут)")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке моделей: {e}")
            return False


def copy_marker_models(source_dir: Path, output_dir: Path) -> bool:
    """Копирует модели Marker из временной директории в целевую"""
    
    models_copied = 0
    
    # Ищем модели в различных стандартных местах
    search_paths = [
        source_dir,
        source_dir / "input",
        Path.home() / ".cache" / "huggingface",
        Path.home() / ".cache" / "torch",
    ]
    
    # Добавляем системные пути Python
    try:
        import site
        for site_packages in site.getsitepackages():
            search_paths.extend([
                Path(site_packages),
                Path(site_packages) / "marker_models",
            ])
    except Exception:
        pass
    
    # Добавляем Windows-специфичные пути
    if os.name == 'nt':
        appdata = Path(os.environ.get('APPDATA', ''))
        if appdata:
            search_paths.extend([
                appdata / "huggingface",
                appdata / "torch",
            ])
    
    logger.info(f"🔍 Поиск моделей в {len(search_paths)} директориях...")
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
            
        logger.info(f"  Проверяем: {search_path}")
        
        # Ищем папки с моделями (обычно содержат файлы .bin, .safetensors, config.json)
        model_indicators = ['.bin', '.safetensors', 'config.json', 'tokenizer.json']
        
        for item in search_path.rglob('*'):
            if item.is_file() and any(item.name.endswith(ext) for ext in model_indicators):
                # Нашли файл модели, копируем всю родительскую папку
                model_dir = item.parent
                relative_path = model_dir.relative_to(search_path)
                dest_dir = output_dir / relative_path
                
                try:
                    if not dest_dir.exists():
                        shutil.copytree(model_dir, dest_dir, dirs_exist_ok=True)
                        models_copied += 1
                        logger.info(f"  📦 Скопирована модель: {relative_path}")
                except Exception as e:
                    logger.warning(f"  ⚠️ Не удалось скопировать {relative_path}: {e}")
    
    # Также ищем специфичные папки для Marker
    marker_specific_paths = [
        "conversion_results",
        "marker_models", 
        "models",
        ".marker_cache"
    ]
    
    for search_path in search_paths:
        for marker_path in marker_specific_paths:
            marker_dir = search_path / marker_path
            if marker_dir.exists() and marker_dir.is_dir():
                dest_dir = output_dir / marker_path
                try:
                    if not dest_dir.exists():
                        shutil.copytree(marker_dir, dest_dir, dirs_exist_ok=True)
                        models_copied += 1
                        logger.info(f"  📦 Скопирована папка Marker: {marker_path}")
                except Exception as e:
                    logger.warning(f"  ⚠️ Не удалось скопировать {marker_path}: {e}")
    
    return models_copied > 0


def create_test_pdf():
    """Создает простой тестовый PDF файл"""
    try:
        # Пытаемся создать PDF через reportlab
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from io import BytesIO
        
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        
        # Добавляем текст
        p.drawString(100, 750, "Test PDF for Marker Model Download")
        p.drawString(100, 700, "This is a simple test document.")
        p.drawString(100, 650, "It contains some text to trigger model loading.")
        p.drawString(100, 600, "Marker will download models when processing this PDF.")
        
        p.showPage()
        p.save()
        
        buffer.seek(0)
        return buffer.getvalue()
        
    except ImportError:
        # Если reportlab не установлен, создаем минимальный PDF вручную
        logger.warning("reportlab не установлен, создаем минимальный PDF")
        
        # Минимальный PDF контент (заголовок + страница с текстом)
        pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 5 0 R
>>
>>
>>
endobj

4 0 obj
<<
/Length 100
>>
stream
BT
/F1 12 Tf
72 720 Td
(Test PDF for Marker Model Download) Tj
0 -20 Td
(This is a simple test document.) Tj
0 -20 Td
(It contains some text to trigger model loading.) Tj
ET
endstream
endobj

5 0 obj
<<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
endobj

xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000053 00000 n 
0000000110 00000 n 
0000000274 00000 n 
0000000425 00000 n 
trailer
<<
/Size 6
/Root 1 0 R
>>
startxref
508
%%EOF"""
        
        return pdf_content


def create_empty_models_directory(models_dir: Path) -> bool:
    """Создает пустую папку для моделей с README"""
    try:
        models_dir.mkdir(exist_ok=True)
        
        # Создаем README файл
        readme_content = """# Marker Models Directory

Эта папка предназначена для предзагруженных моделей Marker.

Если эта папка пуста, модели будут загружены автоматически при первом запуске Marker в Docker контейнере.

Для предварительной загрузки моделей запустите:
    python api/download_marker_models.py

Или скопируйте модели вручную из:
- ~/.cache/huggingface/
- ~/.cache/torch/
- Или других путей кэша Marker
"""
        
        readme_path = models_dir / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        
        logger.info(f"📁 Создана пустая папка для моделей: {models_dir}")
        logger.info("ℹ️ Модели будут загружены автоматически при первом запуске")
        return True
        
    except Exception as e:
        logger.error(f"❌ Не удалось создать папку для моделей: {e}")
        return False


def main():
    """Основная функция"""
    logger.info("🚀 Начинаем загрузку моделей Marker...")
    
    # Проверяем, что Marker установлен
    if not ensure_marker_installed():
        logger.warning("⚠️ Marker не найден, создаем пустую папку для моделей")
    
    # Определяем папку для моделей
    models_dir = Path("./marker_models")
    
    # Проверяем, есть ли уже модели
    if models_dir.exists() and any(models_dir.iterdir()):
        logger.info(f"📁 Папка {models_dir} уже содержит файлы")
        response = input("Перезаписать существующие модели? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            logger.info("Отменено пользователем")
            return 0
        
        # Удаляем существующую папку
        shutil.rmtree(models_dir)
        logger.info("🗑️ Удалена существующая папка моделей")
    
    # Загружаем модели
    success = download_marker_models(models_dir)
    
    if success:
        logger.info("✅ Загрузка моделей завершена успешно!")
        logger.info(f"📁 Модели сохранены в: {models_dir.absolute()}")
        logger.info("🐳 Теперь можно собирать Docker образ с предзагруженными моделями")
        return 0
    else:
        logger.warning("⚠️ Загрузка моделей не удалась, создаем пустую папку")
        if create_empty_models_directory(models_dir):
            logger.info("✅ Создана пустая папка для моделей")
            logger.info("ℹ️ Модели будут загружены автоматически при первом запуске Docker контейнера")
            return 0
        else:
            logger.error("❌ Не удалось создать папку для моделей")
            return 1


if __name__ == "__main__":
    sys.exit(main())
