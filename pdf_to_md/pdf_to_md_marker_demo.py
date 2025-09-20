#!/usr/bin/env python3
"""
Простое решение для преобразования PDF в Markdown с использованием Marker
Поддерживает как самостоятельный запуск, так и использование сторонними скриптами
"""
import os
import sys
import json
import subprocess
import shutil
import threading
import time
import logging
import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict, Any, Tuple

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Настройка логгера для Marker (отключаем пропагацию к корневому логгеру)
marker_logger = logging.getLogger('marker')
marker_logger.setLevel(logging.INFO)
marker_logger.propagate = False  # Отключаем пропагацию к корневому логгеру

# Создание обработчика для вывода в консоль
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Форматирование сообщений для Marker
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Добавление обработчика к логгеру Marker
marker_logger.addHandler(console_handler)

def log_progress(message, level="INFO"):
    """Логирование только критически важных сообщений и прогресса"""
    icons = {
        "SUCCESS": "✅", 
        "ERROR": "❌",
        "PROGRESS": "🔄"
    }
    icon = icons.get(level, "")
    formatted_message = f"{icon} {message}" if icon else message
    
    if level == "ERROR":
        logging.error(formatted_message)
    elif level == "SUCCESS":
        logging.info(formatted_message)
    elif level == "PROGRESS":
        logging.info(formatted_message)
    # Убираем все остальные логи (INFO, WARNING, DEBUG)

def monitor_marker_progress_async(process, start_time, total_pages=13, on_progress=None):
    """Мониторинг прогресса Marker с callback для сторонних скриптов"""
    last_output_time = time.time()
    pages_per_sec = 0.14  # Скорость обработки из предыдущих запусков
    estimated_total_time = total_pages / pages_per_sec  # Примерное время в секундах
    
    while process.poll() is None:
        time.sleep(10)  # Проверяем каждые 10 секунд
        
        elapsed = time.time() - start_time
        elapsed_min = int(elapsed // 60)
        elapsed_sec = int(elapsed % 60)
        
        # Вычисляем прогресс на основе скорости обработки
        if elapsed < 20:
            progress = 5
            stage = "Инициализация"
        elif elapsed < 40:
            progress = 15
            stage = "Загрузка моделей"
        else:
            # Рассчитываем прогресс на основе времени и скорости
            estimated_pages_processed = min(total_pages, (elapsed - 40) * pages_per_sec)
            progress = min(90, int(15 + (estimated_pages_processed / total_pages) * 75))
            stage = f"Обработка страниц (~{int(estimated_pages_processed)}/{total_pages})"
        
        # Показываем прогресс каждые 15 секунд
        if time.time() - last_output_time > 15:
            log_progress(f"{stage} ({progress}%)", "PROGRESS")
            
            # Вызываем callback для сторонних скриптов
            if on_progress:
                on_progress({
                    "pages_processed": int(estimated_pages_processed) if elapsed >= 40 else 0,
                    "total_pages": total_pages,
                    "progress_percent": progress,
                    "stage": stage,
                    "elapsed_time": elapsed
                })
            
            last_output_time = time.time()
    
    total_time = time.time() - start_time
    total_min = int(total_time // 60)
    total_sec = int(total_time % 60)
    log_progress(f"Обработка завершена за {total_min}м {total_sec}с", "SUCCESS")

def monitor_marker_progress(process, start_time, total_pages=13):
    """Мониторинг прогресса Marker с расчетом на основе скорости обработки"""
    last_output_time = time.time()
    pages_per_sec = 0.14  # Скорость обработки из предыдущих запусков
    estimated_total_time = total_pages / pages_per_sec  # Примерное время в секундах
    
    while process.poll() is None:
        time.sleep(10)  # Проверяем каждые 10 секунд
        
        elapsed = time.time() - start_time
        elapsed_min = int(elapsed // 60)
        elapsed_sec = int(elapsed % 60)
        
        # Вычисляем прогресс на основе скорости обработки
        if elapsed < 20:
            progress = 5
            stage = "Инициализация"
        elif elapsed < 40:
            progress = 15
            stage = "Загрузка моделей"
        else:
            # Рассчитываем прогресс на основе времени и скорости
            estimated_pages_processed = min(total_pages, (elapsed - 40) * pages_per_sec)
            progress = min(90, int(15 + (estimated_pages_processed / total_pages) * 75))
            stage = f"Обработка страниц (~{int(estimated_pages_processed)}/{total_pages})"
        
        # Показываем прогресс каждые 15 секунд
        if time.time() - last_output_time > 15:
            log_progress(f"{stage} ({progress}%)", "PROGRESS")
            last_output_time = time.time()
    
    total_time = time.time() - start_time
    total_min = int(total_time // 60)
    total_sec = int(total_time % 60)
    log_progress(f"Обработка завершена за {total_min}м {total_sec}с", "SUCCESS")

def parse_marker_output(output_text):
    """Парсинг вывода Marker для извлечения полезной информации"""
    if not output_text:
        return {}
    
    info = {}
    lines = output_text.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Извлекаем информацию о страницах
        if "pages in" in line and "seconds" in line:
            try:
                # Пример: "Inferenced 13 pages in 149.69 seconds, for a throughput of 0.09 pages/sec"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "pages" and i > 0:
                        info["pages_processed"] = int(parts[i-1])
                    elif part == "seconds," and i > 0:
                        info["processing_time"] = float(parts[i-1])
                    elif part == "pages/sec":
                        info["throughput"] = float(parts[i-1])
            except (ValueError, IndexError):
                pass
        
        # Извлекаем информацию о чанках
        if "chunk" in line and "/" in line:
            try:
                # Пример: "for chunk 1/1"
                chunk_part = line.split("chunk")[-1].strip()
                if "/" in chunk_part:
                    current, total = chunk_part.split("/")
                    info["current_chunk"] = int(current)
                    info["total_chunks"] = int(total)
            except (ValueError, IndexError):
                pass
    
    return info

async def convert_pdf_to_markdown_marker_async(
    pdf_path: str, 
    output_dir: str = "markdown_output",
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_complete: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Optional[Dict[str, Any]]:
    """
    Асинхронная конвертация PDF в Markdown с использованием Marker
    
    Args:
        pdf_path: Путь к PDF файлу
        output_dir: Папка для сохранения результатов
        on_progress: Callback для отслеживания прогресса
        on_complete: Callback для получения результата
        
    Returns:
        Словарь с результатами конвертации или None при ошибке
    """
    if not Path(pdf_path).exists():
        error_msg = f"Файл не найден: {pdf_path}"
        if on_complete:
            on_complete({"error": error_msg, "success": False})
        return None
    
    # Создаем директорию для результатов
    Path(output_dir).mkdir(exist_ok=True)
    
    pdf_name = Path(pdf_path).name
    pdf_stem = Path(pdf_path).stem
    markdown_name = f"{pdf_stem}.md"
    markdown_path = Path(output_dir) / markdown_name
    
    # Получаем размер файла для информации
    file_size = Path(pdf_path).stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    
    # Начинаем преобразование
    try:
        # Создаем временную папку для Marker
        temp_input_dir = Path(output_dir) / "temp_input"
        temp_input_dir.mkdir(exist_ok=True)
        
        # Копируем PDF в временную папку
        temp_pdf_path = temp_input_dir / pdf_name
        shutil.copy2(pdf_path, temp_pdf_path)
        
        # Запускаем Marker CLI
        start_time = time.time()
        
        # Настраиваем переменные окружения для логирования Marker
        import os
        env = os.environ.copy()
        env["MARKER_LOG_LEVEL"] = "DEBUG"
        env["MARKER_DEBUG"] = "1"
        env["MARKER_VERBOSE"] = "1"
        # Принудительно отключаем буферизацию для Python
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        # Принудительно отключаем буферизацию для tqdm
        env["TQDM_DISABLE"] = "0"
        env["TQDM_MINITERS"] = "1"
        env["TQDM_MININTERVAL"] = "0.1"
        # Отключаем tqdm для различных компонентов Marker
        env["MARKER_LAYOUT_DISABLE_TQDM"] = "True"
        env["MARKER_LINE_DISABLE_TQDM"] = "True"
        env["MARKER_OCR_DISABLE_TQDM"] = "True"
        env["MARKER_TABLE_DISABLE_TQDM"] = "True"
        # Логирование Marker включено
        
        # Запускаем процесс с включенным логированием Marker
        # Используем bufsize=0 для небуферизованного вывода
        process = subprocess.Popen([
            "marker", "--disable_tqdm", str(temp_input_dir)
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=0, universal_newlines=True)
        
        # Запускаем мониторинг в отдельном потоке
        monitor_thread = threading.Thread(target=monitor_marker_progress_async, args=(process, start_time, 13, on_progress))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Запускаем асинхронное чтение stdout и stderr с извлечением прогресса
        stdout_lines = []
        stderr_lines = []
        state = {"last_pct": 5, "total": None, "current": 0}
        
        # Паттерны для извлечения прогресса (из marker_proper_model.py)
        page_patterns = [
            re.compile(r"page\s+(?P<cur>\d+)\s*/\s*(?P<tot>\d+)", re.IGNORECASE),
            re.compile(r"processing\s+page\s+(?P<cur>\d+)\s+of\s+(?P<tot>\d+)", re.IGNORECASE),
            re.compile(r"\[(?P<cur>\d+)\/(?:\s*)?(?P<tot>\d+)\]", re.IGNORECASE),
        ]
        stage_patterns = [
            (re.compile(r"download|load model|weights", re.IGNORECASE), 10),
            (re.compile(r"detect|detection", re.IGNORECASE), 20),
            (re.compile(r"ocr|recognition", re.IGNORECASE), 40),
            (re.compile(r"layout|segment", re.IGNORECASE), 55),
            (re.compile(r"markdown|export|write", re.IGNORECASE), 70),
        ]
        tqdm_percent_pattern = re.compile(r"(?P<pct>\d{1,3})%\|")
        network_activity_pattern = re.compile(
            r"urllib3|HTTPSConnectionPool|Downloading|download|getaddrinfo|Connection(Error|Refused|Reset)?|HTTPError|Retry|bytes/s|MB/s",
            re.IGNORECASE,
        )

        def _reader(stream, buffer, is_err: bool):
            try:
                for line in iter(stream.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n')
                    buffer.append(line)
                    
                    # Очищаем ANSI escape sequences
                    clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                    clean_line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', clean_line)
                    
                    if clean_line:
                        # Извлекаем реальный прогресс
                        new_pct = None
                        for pat in page_patterns:
                            m = pat.search(clean_line)
                            if m:
                                try:
                                    cur = int(m.group('cur'))
                                    tot = int(m.group('tot'))
                                    if tot > 0 and 0 <= cur <= tot:
                                        state['total'] = tot
                                        state['current'] = max(state['current'], cur)
                                        ratio = min(1.0, max(0.0, state['current'] / float(tot)))
                                        new_pct = 5 + int(ratio * 74)
                                        if on_progress:
                                            on_progress({
                                                "pages_processed": cur,
                                                "total_pages": tot,
                                                "progress_percent": new_pct,
                                                "stage": "processing_pages"
                                            })
                                except Exception:
                                    pass
                                break
                        
                        if new_pct is None:
                            m = tqdm_percent_pattern.search(clean_line)
                            if m:
                                try:
                                    p = int(m.group('pct'))
                                    if 0 <= p < 80:
                                        new_pct = max(5, min(79, p))
                                        if on_progress:
                                            on_progress({
                                                "progress_percent": p,
                                                "stage": "processing"
                                            })
                                except Exception:
                                    pass
                        
                        if new_pct is None:
                            for pat, pct in stage_patterns:
                                if pat.search(clean_line):
                                    new_pct = pct
                                    if on_progress:
                                        on_progress({
                                            "progress_percent": pct,
                                            "stage": "processing"
                                        })
                                    break
                        
                        if new_pct is None and network_activity_pattern.search(clean_line):
                            new_pct = max(6, state['last_pct'])
                            # Сетевая активность
                        
                        if new_pct is not None and new_pct > state['last_pct'] and new_pct < 80:
                            state['last_pct'] = new_pct
                            
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        stdout_thread = threading.Thread(target=_reader, args=(process.stdout, stdout_lines, False), daemon=True)
        stderr_thread = threading.Thread(target=_reader, args=(process.stderr, stderr_lines, True), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        
        # Ждем завершения процесса
        process.wait()
        
        # Ждем завершения потоков чтения
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        
        # Объединяем все строки
        stdout = ''.join(stdout_lines)
        stderr = ''.join(stderr_lines)
        
        # Парсим вывод Marker
        marker_info = parse_marker_output(stdout)
        
        # Marker завершился
        
        # Выводим детальную информацию о процессе
        if marker_info:
            if "pages_processed" in marker_info:
                log_progress(f"Обработано страниц: {marker_info['pages_processed']}", "SUCCESS")
            if "processing_time" in marker_info:
                log_progress(f"Время обработки: {marker_info['processing_time']:.2f} секунд", "SUCCESS")
            if "throughput" in marker_info:
                log_progress(f"Скорость: {marker_info['throughput']:.2f} страниц/сек", "SUCCESS")
            if "current_chunk" in marker_info and "total_chunks" in marker_info:
                pass  # Чанк обработан
        
        # Логи Marker уже выведены асинхронно, дополнительный вывод не нужен
        
        if process.returncode == 0:
            log_progress("Marker конвертация завершена успешно", "SUCCESS")
            
            # Ищем результаты в conversion_results
            conversion_results_dir = None
            
            # Проверяем site-packages
            try:
                import site
                site_packages = site.getsitepackages()
                for sp in site_packages:
                    conv_dir = Path(sp) / "conversion_results"
                    if conv_dir.exists():
                        conversion_results_dir = conv_dir
                        break
            except Exception:
                pass
            
            # Также проверяем стандартные места
            if not conversion_results_dir:
                import os
                user_home = Path.home()
                appdata_path = user_home / "AppData" / "Roaming" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "site-packages" / "conversion_results"
                if appdata_path.exists():
                    conversion_results_dir = appdata_path
            
            if not conversion_results_dir:
                log_progress("Папка conversion_results не найдена", "ERROR")
                return None
            
            # Ищем результаты
            
            # Ищем папку с результатами (Marker создает папку с именем PDF)
            pdf_stem = Path(pdf_path).stem
            result_dirs = list(conversion_results_dir.glob(f"*{pdf_stem}*"))
            
            if not result_dirs:
                # Если не найдено по точному имени, ищем любые папки
                all_dirs = [d for d in conversion_results_dir.glob("*") if d.is_dir()]
                if all_dirs:
                    # Берем самую новую папку
                    result_dirs = [max(all_dirs, key=lambda p: p.stat().st_mtime)]
                    log_progress(f"Используем самую новую папку: {result_dirs[0].name}", "PROGRESS")
            
            if result_dirs:
                result_dir = result_dirs[0]
                log_progress(f"Найдена папка результатов: {result_dir}", "SUCCESS")
                
                # Ищем markdown файл
                markdown_files = list(result_dir.glob("*.md"))
                # Найдены markdown файлы
                
                if markdown_files:
                    source_markdown = markdown_files[0]
                    log_progress(f"Найден markdown файл: {source_markdown.name}", "SUCCESS")
                    
                    # Читаем markdown файл
                    log_progress("Читаем markdown файл...", "PROGRESS")
                    content = source_markdown.read_text(encoding="utf-8", errors="ignore")
                    markdown_path.write_text(content, encoding="utf-8", errors="ignore")
                    log_progress(f"Markdown извлечен, размер: {len(content)} символов", "SUCCESS")
                    
                    # Копируем изображения
                    log_progress("Копируем изображения...", "PROGRESS")
                    image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]
                    copied_images = 0
                    
                    for ext in image_extensions:
                        for img_file in result_dir.glob(ext):
                            try:
                                dest_img = Path(output_dir) / img_file.name
                                shutil.copy2(str(img_file), str(dest_img))
                                copied_images += 1
                                log_progress(f"Скопировано изображение: {img_file.name}", "SUCCESS")
                            except Exception as e:
                                log_progress(f"Не удалось скопировать {img_file.name}: {e}", "ERROR")
                    
                    if copied_images:
                        log_progress(f"Всего скопировано изображений: {copied_images}", "SUCCESS")
                    
                    # Сохраняем markdown файл
                    log_progress("Сохраняем markdown файл...", "PROGRESS")
                    log_progress(f"Markdown сохранен: {markdown_path}", "SUCCESS")
                    
                    # Создаем JSON файл для Label Studio
                    log_progress("Создаем JSON файл для Label Studio...", "PROGRESS")
                    json_path = create_label_studio_json(markdown_path, output_dir)
                    
                    # Удаляем временную папку
                    log_progress("Удаляем временную папку...", "PROGRESS")
                    if temp_input_dir.exists():
                        shutil.rmtree(temp_input_dir)
                    log_progress(f"Временная папка удалена: {temp_input_dir}", "SUCCESS")
                    
                    # Подготавливаем результат
                    result = {
                        "success": True,
                        "markdown_file": str(markdown_path),
                        "json_file": str(json_path),
                        "output_dir": str(output_dir),
                        "pages_processed": marker_info.get("pages_processed", 0),
                        "processing_time": marker_info.get("processing_time", 0),
                        "throughput": marker_info.get("throughput", 0),
                        "file_size_mb": file_size_mb,
                        "images_count": copied_images
                    }
                    
                    # Вызываем callback с результатом
                    if on_complete:
                        on_complete(result)
                    
                    return result
                else:
                    log_progress("Markdown файлы не найдены в результатах", "ERROR")
                    return None
            else:
                log_progress("Папка с результатами не найдена", "ERROR")
                return None
        else:
            log_progress(f"Marker завершился с ошибкой (код: {process.returncode})", "ERROR")
            return None
            
    except Exception as e:
        log_progress(f"Ошибка при конвертации: {e}", "ERROR")
        return None

def convert_pdf_to_markdown_marker(pdf_path, output_dir="markdown_output"):
    """Простое преобразование PDF в Markdown с использованием Marker"""
    
    if not Path(pdf_path).exists():
        log_progress(f"Файл не найден: {pdf_path}", "ERROR")
        return None
    
    # Создаем директорию для результатов
    Path(output_dir).mkdir(exist_ok=True)
    
    pdf_name = Path(pdf_path).name
    pdf_stem = Path(pdf_path).stem
    markdown_name = f"{pdf_stem}.md"
    markdown_path = Path(output_dir) / markdown_name
    
    # Получаем размер файла для информации
    file_size = Path(pdf_path).stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    
    # Начинаем преобразование
    
    try:
        # Создаем временную папку для Marker
        temp_input_dir = Path(output_dir) / "temp_input"
        temp_input_dir.mkdir(exist_ok=True)
        log_progress(f"Создана временная папка: {temp_input_dir}", "DEBUG")
        
        # Копируем PDF в временную папку
        temp_pdf_path = temp_input_dir / pdf_name
        log_progress("Копируем PDF в временную папку...", "PROGRESS")
        shutil.copy2(pdf_path, temp_pdf_path)
        log_progress("PDF скопирован успешно", "SUCCESS")
        
        # Запускаем Marker CLI с детальным мониторингом
        log_progress("Запускаем Marker CLI...", "PROGRESS")
        start_time = time.time()
        
        # Настраиваем переменные окружения для логирования Marker
        import os
        env = os.environ.copy()
        env["MARKER_LOG_LEVEL"] = "DEBUG"
        env["MARKER_DEBUG"] = "1"
        env["MARKER_VERBOSE"] = "1"
        # Принудительно отключаем буферизацию для Python
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        # Принудительно отключаем буферизацию для tqdm
        env["TQDM_DISABLE"] = "0"
        env["TQDM_MINITERS"] = "1"
        env["TQDM_MININTERVAL"] = "0.1"
        # Отключаем tqdm для различных компонентов Marker
        env["MARKER_LAYOUT_DISABLE_TQDM"] = "True"
        env["MARKER_LINE_DISABLE_TQDM"] = "True"
        env["MARKER_OCR_DISABLE_TQDM"] = "True"
        env["MARKER_TABLE_DISABLE_TQDM"] = "True"
        # Логирование Marker включено
        
        # Запускаем процесс с включенным логированием Marker
        # Используем bufsize=0 для небуферизованного вывода
        process = subprocess.Popen([
            "marker", "--disable_tqdm", str(temp_input_dir)
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=0, universal_newlines=True)
        
        # Запускаем мониторинг в отдельном потоке
        monitor_thread = threading.Thread(target=monitor_marker_progress, args=(process, start_time, 13))
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Запускаем асинхронное чтение stdout и stderr с извлечением прогресса
        stdout_lines = []
        stderr_lines = []
        state = {"last_pct": 5, "total": None, "current": 0}
        
        # Паттерны для извлечения прогресса (из marker_proper_model.py)
        page_patterns = [
            re.compile(r"page\s+(?P<cur>\d+)\s*/\s*(?P<tot>\d+)", re.IGNORECASE),
            re.compile(r"processing\s+page\s+(?P<cur>\d+)\s+of\s+(?P<tot>\d+)", re.IGNORECASE),
            re.compile(r"\[(?P<cur>\d+)\/(?:\s*)?(?P<tot>\d+)\]", re.IGNORECASE),
        ]
        stage_patterns = [
            (re.compile(r"download|load model|weights", re.IGNORECASE), 10),
            (re.compile(r"detect|detection", re.IGNORECASE), 20),
            (re.compile(r"ocr|recognition", re.IGNORECASE), 40),
            (re.compile(r"layout|segment", re.IGNORECASE), 55),
            (re.compile(r"markdown|export|write", re.IGNORECASE), 70),
        ]
        tqdm_percent_pattern = re.compile(r"(?P<pct>\d{1,3})%\|")
        network_activity_pattern = re.compile(
            r"urllib3|HTTPSConnectionPool|Downloading|download|getaddrinfo|Connection(Error|Refused|Reset)?|HTTPError|Retry|bytes/s|MB/s",
            re.IGNORECASE,
        )

        def _reader(stream, buffer, is_err: bool):
            try:
                for line in iter(stream.readline, ''):
                    if not line:
                        break
                    line = line.rstrip('\n')
                    buffer.append(line)
                    
                    # Очищаем ANSI escape sequences
                    clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                    clean_line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', clean_line)
                    
                    if clean_line:
                        # Выводим логи Marker
                        if is_err:
                            marker_logger.warning(f"MARKER: {clean_line}")
                        else:
                            marker_logger.info(f"MARKER: {clean_line}")
                        
                        # Извлекаем реальный прогресс
                        new_pct = None
                        for pat in page_patterns:
                            m = pat.search(clean_line)
                            if m:
                                try:
                                    cur = int(m.group('cur'))
                                    tot = int(m.group('tot'))
                                    if tot > 0 and 0 <= cur <= tot:
                                        state['total'] = tot
                                        state['current'] = max(state['current'], cur)
                                        ratio = min(1.0, max(0.0, state['current'] / float(tot)))
                                        new_pct = 5 + int(ratio * 74)
                                        log_progress(f"Обработано страниц: {cur}/{tot} ({new_pct}%)", "PROGRESS")
                                except Exception:
                                    pass
                                break
                        
                        if new_pct is None:
                            m = tqdm_percent_pattern.search(clean_line)
                            if m:
                                try:
                                    p = int(m.group('pct'))
                                    if 0 <= p < 80:
                                        new_pct = max(5, min(79, p))
                                        log_progress(f"Прогресс Marker: {p}%", "PROGRESS")
                                except Exception:
                                    pass
                        
                        if new_pct is None:
                            for pat, pct in stage_patterns:
                                if pat.search(clean_line):
                                    new_pct = pct
                                    # Этап обработки
                                    break
                        
                        if new_pct is None and network_activity_pattern.search(clean_line):
                            new_pct = max(6, state['last_pct'])
                            # Сетевая активность
                        
                        if new_pct is not None and new_pct > state['last_pct'] and new_pct < 80:
                            state['last_pct'] = new_pct
                            
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        stdout_thread = threading.Thread(target=_reader, args=(process.stdout, stdout_lines, False), daemon=True)
        stderr_thread = threading.Thread(target=_reader, args=(process.stderr, stderr_lines, True), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        
        # Ждем завершения процесса
        process.wait()
        
        # Ждем завершения потоков чтения
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        
        # Объединяем все строки
        stdout = ''.join(stdout_lines)
        stderr = ''.join(stderr_lines)
        
        # Парсим вывод Marker
        marker_info = parse_marker_output(stdout)
        
        # Marker завершился
        
        # Выводим детальную информацию о процессе
        if marker_info:
            if "pages_processed" in marker_info:
                log_progress(f"Обработано страниц: {marker_info['pages_processed']}", "SUCCESS")
            if "processing_time" in marker_info:
                log_progress(f"Время обработки: {marker_info['processing_time']:.2f} секунд", "SUCCESS")
            if "throughput" in marker_info:
                log_progress(f"Скорость: {marker_info['throughput']:.2f} страниц/сек", "SUCCESS")
            if "current_chunk" in marker_info and "total_chunks" in marker_info:
                pass  # Чанк обработан
        
        # Логи Marker уже выведены асинхронно, дополнительный вывод не нужен
        
        if process.returncode == 0:
            log_progress("Marker конвертация завершена успешно", "SUCCESS")
            
            # Marker сохраняет результаты в conversion_results папке
            # Ищем папку conversion_results
            import site
            
            log_progress("Ищем папку с результатами...", "PROGRESS")
            
            # Возможные пути для conversion_results
            possible_paths = [
                Path(site.getsitepackages()[0]) / "conversion_results",
                Path.home() / "AppData" / "Roaming" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "site-packages" / "conversion_results",
                Path.cwd() / "conversion_results"
            ]
            
            conversion_results_dir = None
            for path in possible_paths:
                if path.exists():
                    conversion_results_dir = path
                    log_progress(f"Найдена папка conversion_results: {path}", "DEBUG")
                    break
            
            if not conversion_results_dir:
                log_progress("Папка conversion_results не найдена", "ERROR")
                return None
            
            # Ищем результаты
            
            # Ищем папку с результатами (Marker создает папку с именем PDF)
            pdf_stem = Path(pdf_path).stem
            result_dirs = list(conversion_results_dir.glob(f"*{pdf_stem}*"))
            
            if not result_dirs:
                log_progress(f"Не найдено папок с именем '{pdf_stem}', ищем любые папки...", "WARNING")
                # Если не найдено по точному имени, ищем любые папки
                all_dirs = [d for d in conversion_results_dir.glob("*") if d.is_dir()]
                if all_dirs:
                    # Берем самую новую папку
                    result_dirs = [max(all_dirs, key=lambda p: p.stat().st_mtime)]
                    log_progress(f"Используем самую новую папку: {result_dirs[0].name}", "PROGRESS")
            
            if result_dirs:
                result_dir = result_dirs[0]
                log_progress(f"Найдена папка результатов: {result_dir}", "SUCCESS")
                
                # Ищем markdown файл
                markdown_files = list(result_dir.glob("*.md"))
                # Найдены markdown файлы
                
                if markdown_files:
                    source_markdown = markdown_files[0]
                    log_progress(f"Найден markdown файл: {source_markdown.name}", "SUCCESS")
                    
                    # Читаем результат
                    log_progress("Читаем markdown файл...", "PROGRESS")
                    with open(source_markdown, 'r', encoding='utf-8') as f:
                        full_text = f.read()
                    
                    log_progress(f"Markdown извлечен, размер: {len(full_text)} символов", "SUCCESS")
                    
                    # Копируем изображения в папку с результатами
                    log_progress("Копируем изображения...", "PROGRESS")
                    image_extensions = ['*.jpeg', '*.jpg', '*.png', '*.gif', '*.bmp']
                    image_count = 0
                    for ext in image_extensions:
                        image_files = list(result_dir.glob(ext))
                        for image_file in image_files:
                            dest_image_path = Path(output_dir) / image_file.name
                            shutil.copy2(image_file, dest_image_path)
                            image_count += 1
                            log_progress(f"Скопировано изображение: {image_file.name}", "SUCCESS")
                    
                    if image_count > 0:
                        log_progress(f"Всего скопировано изображений: {image_count}", "SUCCESS")
                    else:
                        log_progress("Изображения не найдены", "WARNING")
                    
                    # Сохраняем markdown в финальную папку
                    log_progress("Сохраняем markdown файл...", "PROGRESS")
                    with open(markdown_path, 'w', encoding='utf-8') as f:
                        f.write(full_text)
                    
                    log_progress(f"Markdown сохранен: {markdown_path}", "SUCCESS")
                    
                    # Создаем JSON файл для Label Studio (опционально)
                    log_progress("Создаем JSON файл для Label Studio...", "PROGRESS")
                    json_path = create_label_studio_tasks(output_dir, markdown_name, "marker")
                    
                    return str(markdown_path), json_path
                else:
                    log_progress("Markdown файл не найден в результатах", "ERROR")
                    log_progress(f"Содержимое папки результатов {result_dir}:", "DEBUG")
                    for item in result_dir.iterdir():
                        log_progress(f"  - {item.name} ({'файл' if item.is_file() else 'папка'})", "DEBUG")
                    return None
            else:
                log_progress("Папка с результатами не найдена", "ERROR")
                log_progress(f"Содержимое conversion_results: {conversion_results_dir}", "DEBUG")
                if conversion_results_dir.exists():
                    for item in conversion_results_dir.iterdir():
                        log_progress(f"  - {item.name} ({'файл' if item.is_file() else 'папка'})", "DEBUG")
                return None
        else:
            log_progress(f"Marker конвертация не удалась (код: {process.returncode})", "ERROR")
            if stderr:
                log_progress(f"Ошибка: {stderr}", "ERROR")
            return None
            
    except FileNotFoundError:
        log_progress("Marker не найден. Установите: pip install marker-pdf", "ERROR")
        return None
    except Exception as e:
        log_progress(f"Ошибка Marker конвертации: {e}", "ERROR")
        import traceback
        log_progress("Детали ошибки:", "DEBUG")
        for line in traceback.format_exc().split('\n'):
            if line.strip():
                log_progress(f"  {line.strip()}", "DEBUG")
        return None
    finally:
        # Удаляем временную папку
        if 'temp_input_dir' in locals() and temp_input_dir.exists():
            log_progress("Удаляем временную папку...", "PROGRESS")
            shutil.rmtree(temp_input_dir)
            log_progress(f"Временная папка удалена: {temp_input_dir}", "SUCCESS")

def create_label_studio_json(markdown_path: Path, output_dir: str) -> str:
    """Создание JSON файла для Label Studio"""
    json_name = f"{markdown_path.stem}_marker_tasks.json"
    json_path = Path(output_dir) / json_name
    
    tasks = [
        {
            "data": {
                "markdown": f"http://localhost:9002/markdown/{markdown_path.name}"
            }
        }
    ]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    log_progress(f"JSON файл создан: {json_path}", "SUCCESS")
    return str(json_path)

def create_label_studio_tasks(output_dir, markdown_name, converter_type):
    """Создание JSON файла для Label Studio"""
    
    json_name = f"{Path(markdown_name).stem}_{converter_type}_tasks.json"
    json_path = f"{output_dir}/{json_name}"
    
    tasks = [
        {
            "data": {
                "markdown": f"http://localhost:9002/markdown/{markdown_name}"
            }
        }
    ]
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    
    log_progress(f"JSON файл создан: {json_path}", "SUCCESS")
    return json_path

def run_async_conversion(pdf_path: str, output_dir: str = "markdown_output"):
    """
    Синхронная обертка для асинхронной конвертации
    Используется для совместимости со сторонними скриптами
    """
    result = None
    
    def on_progress(progress_data):
        """Callback для прогресса"""
        print(f"Прогресс: {progress_data['progress_percent']}% - {progress_data['stage']}")
        if 'pages_processed' in progress_data:
            print(f"Страниц обработано: {progress_data['pages_processed']}/{progress_data['total_pages']}")
    
    def on_complete(complete_data):
        """Callback для завершения"""
        nonlocal result
        result = complete_data
        if complete_data.get('success'):
            print(f"Конвертация завершена успешно!")
            print(f"Результаты в папке: {complete_data['output_dir']}")
        else:
            print(f"Ошибка конвертации: {complete_data.get('error', 'Неизвестная ошибка')}")
    
    # Запускаем асинхронную конвертацию
    asyncio.run(convert_pdf_to_markdown_marker_async(
        pdf_path, 
        output_dir, 
        on_progress=on_progress, 
        on_complete=on_complete
    ))
    
    return result

def main():
    """Основная функция"""
    # Проверяем аргументы командной строки
    if len(sys.argv) < 2:
        # Если нет аргументов, используем тестовый файл автоматически
        test_pdf = "../personal_folder/The FEBS Journal - 2013 - Antony - The hallmarks of Parkinson s disease.pdf"
        if Path(test_pdf).exists():
            pdf_path = test_pdf
        else:
            log_progress("Тестовый PDF файл не найден. Укажите путь к PDF файлу как аргумент.", "ERROR")
            return
    else:
        pdf_path = sys.argv[1]
    
    # Опциональная папка выхода
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "markdown_output"
    
    # Преобразование PDF в Markdown
    result = convert_pdf_to_markdown_marker(pdf_path, output_dir)
    
    if result:
        markdown_path, json_path = result
        log_progress("Готово!", "SUCCESS")
        log_progress(f"Файл готов: {markdown_path}", "SUCCESS")
    else:
        log_progress("Преобразование не удалось", "ERROR")

# Пример использования для сторонних скриптов
"""
Пример использования для сторонних скриптов:

# Синхронное использование
from pdf_to_md_marker_demo import run_async_conversion

result = run_async_conversion("path/to/file.pdf", "output_dir")
if result and result.get('success'):
    print(f"Результаты в: {result['output_dir']}")
    print(f"Markdown файл: {result['markdown_file']}")
    print(f"JSON файл: {result['json_file']}")
    print(f"Обработано страниц: {result['pages_processed']}")
    print(f"Время обработки: {result['processing_time']} сек")
    print(f"Скорость: {result['throughput']} страниц/сек")
    print(f"Размер файла: {result['file_size_mb']} MB")
    print(f"Изображений: {result['images_count']}")

# Асинхронное использование
import asyncio
from pdf_to_md_marker_demo import convert_pdf_to_markdown_marker_async

async def my_progress_callback(progress_data):
    print(f"Прогресс: {progress_data['progress_percent']}% - {progress_data['stage']}")
    if 'pages_processed' in progress_data:
        print(f"Страниц: {progress_data['pages_processed']}/{progress_data['total_pages']}")

async def my_complete_callback(result_data):
    if result_data.get('success'):
        print(f"Готово! Результаты в: {result_data['output_dir']}")
        # Здесь можно загрузить результаты в S3
    else:
        print(f"Ошибка: {result_data.get('error')}")

async def main_async():
    result = await convert_pdf_to_markdown_marker_async(
        "path/to/file.pdf",
        "output_dir",
        on_progress=my_progress_callback,
        on_complete=my_complete_callback
    )
    return result

# Запуск асинхронной версии
# asyncio.run(main_async())
"""

if __name__ == "__main__":
    main()
