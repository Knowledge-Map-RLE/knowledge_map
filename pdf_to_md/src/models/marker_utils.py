"""Утилиты для работы с Marker"""
import hashlib
import asyncio
import tempfile
import shutil
import logging
import sys
import os
import site
from pathlib import Path as SysPath
import re
from typing import Callable, Optional
import inspect
import threading

logger = logging.getLogger(__name__)

# Глобальный флаг инициализации моделей Marker
_marker_models_initialized = False
_marker_models_lock = threading.Lock()


def _compute_md5(data: bytes) -> str:
    """Вычисляет MD5 хеш для данных"""
    md5 = hashlib.md5()
    md5.update(data)
    return md5.hexdigest()


def _ensure_marker_models_initialized():
    """Инициализирует модели Marker один раз при первом использовании"""
    global _marker_models_initialized
    
    with _marker_models_lock:
        if _marker_models_initialized:
            logger.info("[marker] Модели уже инициализированы")
            return True
            
        try:
            logger.info("[marker] Начинаем инициализацию моделей Marker...")
            
            # Добавляем локальные модели в Python path
            local_models_path = SysPath("/app/marker_models")
            if local_models_path.exists():
                import sys
                if str(local_models_path) not in sys.path:
                    sys.path.insert(0, str(local_models_path))
                    logger.info(f"[marker] Добавлен путь к локальным моделям: {local_models_path}")
            
            # Проверяем, что marker-pdf доступен
            import marker
            logger.info("[marker] Модуль marker импортирован успешно")
            
            # Проверяем доступность convert модуля
            try:
                from marker.convert import convert_single_pdf
                logger.info("[marker] Модуль marker.convert доступен")
                
                # Проверяем что можем импортировать основные модули Marker
                try:
                    import marker.models
                    import marker.settings
                    logger.info("[marker] Основные модули Marker импортированы успешно")
                    
                    _marker_models_initialized = True
                    logger.info("[marker] Модели Marker готовы к использованию")
                    return True
                    
                except ImportError as e:
                    logger.warning(f"[marker] Ошибка импорта основных модулей Marker: {e}")
                    # Устанавливаем флаг в любом случае, так как convert_single_pdf доступен
                    _marker_models_initialized = True
                    logger.info("[marker] Модели Marker готовы к использованию (через convert_single_pdf)")
                    return True
                    
            except ImportError as e:
                logger.warning(f"[marker] marker.convert недоступен: {e}")
                logger.info("[marker] Будем использовать fallback на subprocess")
                # Не устанавливаем флаг, чтобы попробовать снова при следующем вызове
                return False
            
        except Exception as e:
            logger.error(f"[marker] Ошибка инициализации моделей: {e}")
            logger.info("[marker] Будем использовать fallback на subprocess")
            # Не устанавливаем флаг, чтобы попробовать снова при следующем вызове
            return False


async def initialize_marker_models():
    """Асинхронная инициализация моделей Marker при старте API"""
    try:
        # Запускаем в отдельном потоке, чтобы не блокировать event loop
        result = await asyncio.get_event_loop().run_in_executor(
            None, _ensure_marker_models_initialized
        )
        return result
    except Exception as e:
        logger.error(f"[marker] Ошибка асинхронной инициализации моделей: {e}")
        return False


async def _run_marker_on_pdf(tmp_dir: SysPath, *, on_progress: Optional[Callable[[dict], None]] = None, doc_id: Optional[str] = None, ensure_markdown: bool = True) -> SysPath:
    """Конвертирует PDF в Markdown, используя проверенную логику из create_pdf_to_markdown_marker_proper.py"""
    logger.info(f"[marker] Запуск конвертации: tmp_dir={tmp_dir}")
    
    # Сразу используем subprocess для избежания зависания на инициализации моделей
    logger.info("[marker] Используем subprocess для обработки PDF")
    
    pdf_files = list(tmp_dir.glob("*.pdf"))
    if not pdf_files:
        raise RuntimeError("PDF файл не найден в временной директории")
    pdf_path = pdf_files[0]
    logger.info(f"[marker] Найден PDF файл: {pdf_path}")

    # Таймаут
    try:
        timeout_sec = int(os.getenv("MARKER_TIMEOUT_SEC", "3600"))  # Увеличиваем до 1 часа
        logger.info(f"[marker] MARKER_TIMEOUT_SEC из env: {os.getenv('MARKER_TIMEOUT_SEC')}, используем: {timeout_sec}")
    except Exception:
        timeout_sec = 3600
        logger.info(f"[marker] Ошибка чтения MARKER_TIMEOUT_SEC, используем по умолчанию: {timeout_sec}")

    # Создаем временную папку для Marker (он ожидает папку, а не файл)
    temp_input_dir = tmp_dir / "temp_input"
    temp_input_dir.mkdir(parents=True, exist_ok=True)
    
    # Копируем PDF в временную папку
    temp_pdf_path = temp_input_dir / pdf_path.name
    shutil.copy2(str(pdf_path), str(temp_pdf_path))

    def _run_marker() -> None:
        """Запускает Marker через subprocess для избежания зависания"""
        logger.info(f"[marker] Запуск Marker через subprocess для: {temp_input_dir}")
        logger.info(f"[marker] Таймаут: {timeout_sec} сек")
        logger.info(f"[marker] PDF файл: {temp_pdf_path}")
        
        try:
            # Сразу используем subprocess для избежания зависания на инициализации моделей
            _run_marker_subprocess()
            
            # Проверяем что subprocess создал результат
            result_dir = _find_result_directory()
            if not result_dir or not result_dir.exists():
                raise RuntimeError("Marker не создал markdown файл через subprocess")
            
            logger.info(f"[marker] Конвертация завершена, результаты в: {result_dir}")
                
        except Exception as e:
            logger.error(f"[marker] Marker execution error: {e}")
            raise RuntimeError(f"Marker не создал markdown файл: {e}")
    
    def _find_result_directory() -> Optional[SysPath]:
        """Находит директорию с результатами конвертации"""
        from pathlib import Path
        from typing import Optional
        
        # Marker subprocess создает результаты в temp_input_dir
        # Ищем любой markdown файл в temp_input_dir
        if temp_input_dir.exists():
            for item in temp_input_dir.iterdir():
                if item.is_file() and item.suffix == '.md':
                    logger.info(f"[marker] Найден markdown файл: {item}")
                    return temp_input_dir
        
        # Также проверяем стандартные места
        bases = [
            temp_input_dir / "conversion_results",
            temp_input_dir,
            Path("/tmp/marker_output"),
        ]
        
        for base in bases:
            if base.exists():
                for item in base.iterdir():
                    if item.is_dir():
                        # Ищем любой markdown файл в подпапке
                        for md_file in item.glob("*.md"):
                            logger.info(f"[marker] Найден markdown файл: {md_file}")
                            return item
        
        return None
    
    def _run_marker_subprocess() -> None:
        """Fallback: запускает Marker через subprocess и проксирует реальные логи Marker в on_progress"""
        import subprocess
        import threading
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        
        logger.info(f"[marker] Запуск subprocess Marker для: {temp_input_dir}")
        
        try:
            # Используем правильную команду для Marker
            # Marker ожидает папку с PDF файлами, а не конкретный файл
            cmd = ["marker", str(temp_input_dir)]
            logger.info(f"[marker] Команда: {' '.join(cmd)}")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                env=env,
            )

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            state = {"last_pct": 5, "total": None, "current": 0}

            import re
            page_patterns = [
                re.compile(r"page\s+(?P<cur>\d+)\s*/\s*(?P<tot>\d+)", re.IGNORECASE),
                re.compile(r"processing\s+page\s+(?P<cur>\d+)\s+of\s+(?P<tot>\d+)", re.IGNORECASE),
                re.compile(r"\[(?P<cur>\d+)\/(?:\s*)?(?P<tot>\d+)\]", re.IGNORECASE),
            ]
            stage_patterns: list[tuple[re.Pattern[str], int]] = [
                (re.compile(r"download|load model|weights", re.IGNORECASE), 10),
                (re.compile(r"detect|detection", re.IGNORECASE), 20),
                (re.compile(r"ocr|recognition", re.IGNORECASE), 40),
                (re.compile(r"layout|segment", re.IGNORECASE), 55),
                (re.compile(r"markdown|export|write", re.IGNORECASE), 70),
            ]
            # tqdm-подобные строки: ".. 23%|" — вытащим процент
            tqdm_percent_pattern = re.compile(r"(?P<pct>\d{1,3})%\|")
            # Ранние этапы загрузки моделей/ресурсов (сетевые логи)
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
                        # Проксируем последние сообщения без подделки процентов
                        try:
                            payload = {
                                'type': 'doc' if doc_id else 'models',
                                'doc_id': doc_id,
                                'phase': 'processing',
                                'last_message': ("STDERR: " if is_err else "") + line
                            }
                            # Пытаемся извлечь реальный прогресс по страницам
                            new_pct = None
                            for pat in page_patterns:
                                m = pat.search(line)
                                if m:
                                    try:
                                        cur = int(m.group('cur'))
                                        tot = int(m.group('tot'))
                                        if tot > 0 and 0 <= cur <= tot:
                                            state['total'] = tot
                                            state['current'] = max(state['current'], cur)
                                            ratio = min(1.0, max(0.0, state['current'] / float(tot)))
                                            # Диапазон 5..79 для этапа обработки
                                            new_pct = 5 + int(ratio * 74)
                                    except Exception:
                                        pass
                                    break
                            # Если страниц нет — попробуем вытащить процент из tqdm
                            if new_pct is None:
                                m = tqdm_percent_pattern.search(line)
                                if m:
                                    try:
                                        p = int(m.group('pct'))
                                        # Ограничим рабочим диапазоном до 79
                                        if 0 <= p < 80:
                                            new_pct = max(5, min(79, p))
                                    except Exception:
                                        pass
                            # Если нет процентов — попробуем по стадиям
                            if new_pct is None:
                                for pat, pct in stage_patterns:
                                    if pat.search(line):
                                        new_pct = pct
                                        break
                            # Если только сетевые/загрузочные логи — пометим минимум прогресса
                            if new_pct is None and network_activity_pattern.search(line):
                                new_pct = max(6, state['last_pct'])
                            if new_pct is not None and new_pct > state['last_pct'] and new_pct < 80:
                                state['last_pct'] = new_pct
                                payload['percent'] = new_pct
                            _emit_progress(payload)
                        except Exception:
                            pass
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass

            t_out = threading.Thread(target=_reader, args=(proc.stdout, stdout_lines, False), daemon=True)
            t_err = threading.Thread(target=_reader, args=(proc.stderr, stderr_lines, True), daemon=True)
            t_out.start(); t_err.start()

            try:
                proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise RuntimeError(f"Marker timeout after {timeout_sec}s")
            finally:
                t_out.join(timeout=1)
                t_err.join(timeout=1)

            logger.info(f"[marker] Marker завершился с кодом: {proc.returncode}")
            if stdout_lines:
                logger.info("[marker] Marker stdout:\n%s", "\n".join(stdout_lines))
            if stderr_lines:
                logger.warning("[marker] Marker stderr:\n%s", "\n".join(stderr_lines))
            if proc.returncode != 0:
                logger.error(f"[marker] Marker failed with return code {proc.returncode}")
                raise RuntimeError("Marker failed")
                
        except subprocess.TimeoutExpired as e:
            logger.error(f"[marker] Marker timeout after {timeout_sec}s")
            raise RuntimeError(f"Marker timeout: {e}")
        except FileNotFoundError as e:
            logger.error(f"[marker] Marker command not found: {e}")
            raise RuntimeError(f"Marker not found: {e}")
        except Exception as e:
            logger.error(f"[marker] Marker execution error: {e}")
            raise

    # Подготовим безопасный эмиттер прогресса для вызовов из фоновых потоков
    current_loop = asyncio.get_running_loop()

    def _emit_progress(payload: dict) -> None:
        if not on_progress:
            return
        try:
            if inspect.iscoroutinefunction(on_progress):
                asyncio.run_coroutine_threadsafe(on_progress(payload), current_loop)
            else:
                current_loop.call_soon_threadsafe(on_progress, payload)
        except Exception as _e:
            try:
                logger.debug(f"[marker] on_progress emit failed: {_e}")
            except Exception:
                pass

    # Запускаем с таймаутом и реальным прогрессом
    try:
        _emit_progress({'type': 'doc' if doc_id else 'models', 'doc_id': doc_id, 'percent': 5, 'phase': 'init', 'message': 'Инициализация моделей Marker'})

        # Запускаем конвертацию с прогрессом
        await asyncio.wait_for(asyncio.to_thread(_run_marker), timeout=timeout_sec)
        
        _emit_progress({'type': 'doc' if doc_id else 'models', 'doc_id': doc_id, 'percent': 80, 'phase': 'processing', 'message': 'Конвертация PDF завершена, поиск результатов'})

    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"Marker timeout: процесс не завершился за {timeout_sec} сек") from exc
    except Exception as e:
        logger.error(f"[marker] Error with Marker: {e}")
        raise

    # Сначала пробуем взять результат прямо из temp_input_dir (как делает CLI marker)
    md_candidates: list[SysPath] = []
    local_md_files = list((temp_input_dir).glob("*.md"))
    if local_md_files:
        try:
            content = local_md_files[0].read_text(encoding="utf-8", errors="ignore")
            out_md = tmp_dir / f"{pdf_path.stem}.md"
            out_md.write_text(content, encoding="utf-8", errors="ignore")
            md_candidates = [out_md]
            logger.info(f"[marker] Markdown найден в temp_input и скопирован: {out_md} (размер: {len(content)} символов)")
            # Копируем изображения, если они лежат рядом
            image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]
            copied_images = 0
            for ext in image_extensions:
                for img_file in temp_input_dir.glob(ext):
                    try:
                        dest_img = tmp_dir / img_file.name
                        shutil.copy2(str(img_file), str(dest_img))
                        copied_images += 1
                    except Exception as e:
                        logger.warning(f"[marker] Не удалось скопировать {img_file.name}: {e}")
            if copied_images:
                logger.info(f"[marker] Скопировано изображений из temp_input: {copied_images}")
        except Exception as e:
            logger.warning(f"[marker] Ошибка при копировании результата из temp_input: {e}")

    # Если в temp_input результата нет — ищем в site-packages/conversion_results (как в образце)
    if not md_candidates:
        pdf_name_without_ext = pdf_path.stem
        logger.info(f"[marker] Поиск результатов для: {pdf_name_without_ext}")
        
        _emit_progress({'type': 'doc' if doc_id else 'models', 'doc_id': doc_id, 'percent': 85, 'phase': 'searching', 'message': 'Поиск результатов конвертации'})
        
        bases = [SysPath(p) for p in site.getsitepackages()] + [
            SysPath("/usr/local/lib/python3.12/site-packages"),
        ]
        logger.info("[marker] Поиск результатов в conversion_results базах: %s", ", ".join([str(b) for b in bases]))
        
        newest_dir: Optional[SysPath] = None
        newest_mtime: float = -1.0
        for base in bases:
            conv = base / "conversion_results"
            logger.info("[marker] Проверяем: %s", conv)
            if not conv.exists():
                continue
            candidates = list(conv.glob(f"*{pdf_name_without_ext}*"))
            if not candidates:
                candidates = list(conv.glob("*"))
            for d in candidates:
                try:
                    mtime = d.stat().st_mtime
                    if d.is_dir() and mtime > newest_mtime:
                        newest_dir, newest_mtime = d, mtime
                except Exception:
                    pass
        if newest_dir:
            logger.info(f"[marker] Используем папку результатов: {newest_dir}")
            md_files = list(newest_dir.glob("*.md"))
            if md_files:
                content = md_files[0].read_text(encoding="utf-8", errors="ignore")
                out_md = tmp_dir / f"{pdf_path.stem}.md"
                out_md.write_text(content, encoding="utf-8", errors="ignore")
                md_candidates = [out_md]
                logger.info(f"[marker] Markdown скопирован: {out_md} (размер: {len(content)} символов)")
                _emit_progress({'type': 'doc' if doc_id else 'models', 'doc_id': doc_id, 'percent': 95, 'phase': 'copying', 'message': 'Копирование изображений'})
                image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]
                copied_images = 0
                for ext in image_extensions:
                    for img_file in newest_dir.glob(ext):
                        try:
                            dest_img = tmp_dir / img_file.name
                            shutil.copy2(str(img_file), str(dest_img))
                            copied_images += 1
                            logger.info(f"[marker] Скопировано изображение: {img_file.name}")
                        except Exception as e:
                            logger.warning(f"[marker] Не удалось скопировать {img_file.name}: {e}")
                if copied_images:
                    logger.info(f"[marker] Всего скопировано изображений: {copied_images}")
            else:
                logger.warning(f"[marker] В папке {newest_dir} нет markdown файлов")

    if not md_candidates and ensure_markdown:
        raise RuntimeError("Marker не создал markdown файл в целевой директории")

    _emit_progress({'type': 'doc' if doc_id else 'models', 'doc_id': doc_id, 'percent': 100, 'phase': 'done', 'message': 'finished'})
            
    logger.info("[marker] Конвертация завершена")
    return tmp_dir


async def _collect_marker_outputs(conv_dir: SysPath, pdf_stem: str) -> dict[str, SysPath]:
    """Собирает результаты Marker из папки конвертации"""
    logger.info(f"[marker] Поиск результатов в: {conv_dir}")
    
    outputs: dict[str, SysPath] = {}
    
    # Marker создает результаты в той же папке
    result_dir = conv_dir
    
    # Ищем Markdown файлы
    md_files = list(result_dir.glob("*.md"))
    if md_files:
        outputs["markdown"] = md_files[0]
        logger.info(f"[marker] Найден Markdown файл: {md_files[0]}")
    else:
        logger.warning(f"[marker] Markdown файлы не найдены в {result_dir}")
    
    # Ищем JSON метаданные
    json_meta = list(result_dir.glob("*_meta.json"))
    if json_meta:
        outputs["meta"] = json_meta[0]
        logger.info(f"[marker] Найден meta файл: {json_meta[0]}")
    
    # Ищем изображения
    image_files = list(result_dir.glob("*.png")) + list(result_dir.glob("*.jpg")) + list(result_dir.glob("*.jpeg"))
    if image_files:
        logger.info(f"[marker] Найдено изображений: {len(image_files)}")
    
    outputs["images_dir"] = result_dir
    return outputs
