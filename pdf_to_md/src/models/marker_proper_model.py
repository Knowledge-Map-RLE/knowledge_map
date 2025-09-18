"""Модель Marker Proper для преобразования PDF в Markdown"""
import logging
from pathlib import Path as SysPath
from typing import Optional, Dict, Any, Callable

from .create_pdf_to_markdown_marker_proper import convert_pdf_to_markdown_marker_proper

logger = logging.getLogger(__name__)


class MarkerProperModel:
    """Модель Marker Proper для конвертации PDF в Markdown"""
    
    def __init__(self):
        self.name = "marker_proper"
        self.description = "Marker Proper - улучшенная модель конвертации PDF в Markdown"
    
    async def convert_pdf_to_markdown(
        self, 
        tmp_dir: SysPath, 
        *, 
        on_progress: Optional[Callable[[dict], None]] = None, 
        doc_id: Optional[str] = None
    ) -> SysPath:
        """
        Конвертирует PDF в Markdown с использованием Marker Proper
        
        Args:
            tmp_dir: Временная директория с PDF файлом
            on_progress: Callback для отслеживания прогресса
            doc_id: ID документа для логирования
            
        Returns:
            Путь к директории с результатами конвертации
        """
        logger.info(f"[marker_proper] Запуск конвертации в: {tmp_dir}")
        
        # Находим PDF файл
        pdf_files = list(tmp_dir.glob("*.pdf"))
        if not pdf_files:
            raise RuntimeError("PDF файл не найден в временной директории")
        
        pdf_path = pdf_files[0]
        logger.info(f"[marker_proper] Найден PDF файл: {pdf_path}")
        
        try:
            # Инициализация
            if on_progress:
                on_progress({
                    'type': 'doc' if doc_id else 'models',
                    'doc_id': doc_id,
                    'percent': 5,
                    'phase': 'init',
                    'message': 'Инициализация Marker Proper'
                })
            
            # Создаем временную папку для Marker
            temp_input_dir = tmp_dir / "temp_input"
            temp_input_dir.mkdir(parents=True, exist_ok=True)
            
            # Копируем PDF в временную папку
            temp_pdf_path = temp_input_dir / pdf_path.name
            import shutil
            shutil.copy2(str(pdf_path), str(temp_pdf_path))
            
            try:
                # Запускаем Marker через subprocess с отслеживанием прогресса
                await self._run_marker_with_progress(
                    temp_input_dir, 
                    temp_pdf_path, 
                    on_progress=on_progress, 
                    doc_id=doc_id
                )
                
                # Поиск результатов
                if on_progress:
                    on_progress({
                        'type': 'doc' if doc_id else 'models',
                        'doc_id': doc_id,
                        'percent': 85,
                        'phase': 'searching',
                        'message': 'Поиск результатов конвертации'
                    })
                
                # Ищем результаты в temp_input_dir
                result_dir = self._find_result_directory(temp_input_dir, pdf_path.stem)
                if not result_dir:
                    raise RuntimeError("Marker Proper не создал результаты конвертации")
                
                logger.info(f"[marker_proper] Найдены результаты в: {result_dir}")
                
                # Собираем результаты
                await self._collect_outputs(result_dir, tmp_dir, pdf_path.stem)
                
                # Завершение
                if on_progress:
                    on_progress({
                        'type': 'doc' if doc_id else 'models',
                        'doc_id': doc_id,
                        'percent': 100,
                        'phase': 'completed',
                        'message': 'Конвертация завершена успешно'
                    })
                
                logger.info("[marker_proper] Конвертация завершена успешно")
                return tmp_dir
                
            finally:
                # Удаляем временную папку
                if temp_input_dir.exists():
                    shutil.rmtree(temp_input_dir)
                
        except Exception as e:
            logger.error(f"[marker_proper] Ошибка конвертации: {e}")
            raise
    
    async def _run_marker_with_progress(
        self, 
        temp_input_dir: SysPath, 
        temp_pdf_path: SysPath,
        *, 
        on_progress: Optional[Callable[[dict], None]] = None, 
        doc_id: Optional[str] = None
    ) -> None:
        """Запускает Marker через subprocess с отслеживанием прогресса"""
        import subprocess
        import threading
        import os
        import asyncio
        import re
        
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        
        logger.info(f"[marker_proper] Запуск Marker для: {temp_input_dir}")
        
        try:
            # Команда Marker
            cmd = ["marker", str(temp_input_dir)]
            logger.info(f"[marker_proper] Команда: {' '.join(cmd)}")
            
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

            # Паттерны для извлечения прогресса
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
                        
                        # Проксируем логи Marker
                        if on_progress:
                            message = ("STDERR: " if is_err else "") + line
                            payload = {
                                'type': 'doc' if doc_id else 'models',
                                'doc_id': doc_id,
                                'phase': 'processing',
                                'last_message': message
                            }
                            
                            # Извлекаем реальный прогресс
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
                                            new_pct = 5 + int(ratio * 74)
                                    except Exception:
                                        pass
                                    break
                            
                            if new_pct is None:
                                m = tqdm_percent_pattern.search(line)
                                if m:
                                    try:
                                        p = int(m.group('pct'))
                                        if 0 <= p < 80:
                                            new_pct = max(5, min(79, p))
                                    except Exception:
                                        pass
                            
                            if new_pct is None:
                                for pat, pct in stage_patterns:
                                    if pat.search(line):
                                        new_pct = pct
                                        break
                            
                            if new_pct is None and network_activity_pattern.search(line):
                                new_pct = max(6, state['last_pct'])
                            
                            if new_pct is not None and new_pct > state['last_pct'] and new_pct < 80:
                                state['last_pct'] = new_pct
                                payload['percent'] = new_pct
                            
                            _emit_progress(payload)
                            
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass

            t_out = threading.Thread(target=_reader, args=(proc.stdout, stdout_lines, False), daemon=True)
            t_err = threading.Thread(target=_reader, args=(proc.stderr, stderr_lines, True), daemon=True)
            t_out.start(); t_err.start()

            try:
                proc.wait(timeout=1800)  # 30 минут таймаут
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise RuntimeError("Marker timeout after 1800s")
            finally:
                t_out.join(timeout=1)
                t_err.join(timeout=1)

            logger.info(f"[marker_proper] Marker завершился с кодом: {proc.returncode}")
            if stdout_lines:
                logger.info("[marker_proper] Marker stdout:\n%s", "\n".join(stdout_lines))
            if stderr_lines:
                logger.warning("[marker_proper] Marker stderr:\n%s", "\n".join(stderr_lines))
            
            # Проверяем код возврата
            if proc.returncode != 0:
                logger.error(f"[marker_proper] Marker failed with return code {proc.returncode}")
                logger.error(f"[marker_proper] Stdout: {stdout_lines}")
                logger.error(f"[marker_proper] Stderr: {stderr_lines}")
                raise RuntimeError(f"Marker failed with return code {proc.returncode}")
            
            logger.info(f"[marker_proper] Marker завершился успешно с кодом {proc.returncode}")
                
        except subprocess.TimeoutExpired as e:
            logger.error(f"[marker_proper] Marker timeout after 1800s")
            raise RuntimeError(f"Marker timeout: {e}")
        except FileNotFoundError as e:
            logger.error(f"[marker_proper] Marker command not found: {e}")
            raise RuntimeError(f"Marker not found: {e}")
        except Exception as e:
            logger.error(f"[marker_proper] Marker execution error: {e}")
            raise

    def _find_result_directory(self, temp_input_dir: SysPath, pdf_name_without_ext: str) -> Optional[SysPath]:
        """Находит директорию с результатами конвертации"""
        
        logger.info(f"[marker_proper] Поиск результатов для PDF: {pdf_name_without_ext}")
        
        # Marker создает результаты в temp_input_dir
        if temp_input_dir.exists():
            logger.info(f"[marker_proper] Проверяем temp_input_dir: {temp_input_dir}")
            # Ищем markdown файл прямо в temp_input_dir
            for item in temp_input_dir.iterdir():
                logger.info(f"[marker_proper] Найден файл/папка: {item} (файл: {item.is_file()}, расширение: {item.suffix})")
                if item.is_file() and item.suffix == '.md':
                    logger.info(f"[marker_proper] Найден markdown файл: {item}")
                    return temp_input_dir
        
        # Также проверяем стандартные места (fallback)
        import site
        bases = [
            temp_input_dir / "conversion_results",
            SysPath("/tmp/marker_output"),
        ]
        
        # Проверяем site-packages
        try:
            site_packages = site.getsitepackages()
            for sp in site_packages:
                bases.append(SysPath(sp) / "conversion_results")
        except Exception:
            pass
        
        newest_dir: Optional[SysPath] = None
        newest_mtime: float = -1.0
        
        for base in bases:
            logger.info(f"[marker_proper] Проверяем базовую папку: {base}")
            if not base.exists():
                logger.info(f"[marker_proper] Папка не существует: {base}")
                continue
                
            # Ищем папки с результатами
            candidates = list(base.glob(f"*{pdf_name_without_ext}*"))
            logger.info(f"[marker_proper] Найдено кандидатов с именем PDF: {candidates}")
            if not candidates:
                candidates = list(base.glob("*"))
                logger.info(f"[marker_proper] Найдено всех кандидатов: {candidates}")
                
            for d in candidates:
                try:
                    if d.is_dir():
                        mtime = d.stat().st_mtime
                        if mtime > newest_mtime:
                            newest_dir, newest_mtime = d, mtime
                except Exception:
                    pass
        
        if newest_dir:
            logger.info(f"[marker_proper] Используем папку результатов: {newest_dir}")
            return newest_dir
        
        logger.warning(f"[marker_proper] Результаты не найдены ни в одной из папок: {bases}")
        return None
    
    async def _collect_outputs(
        self, 
        result_dir: SysPath, 
        tmp_dir: SysPath, 
        pdf_stem: str
    ) -> None:
        """Собирает результаты конвертации"""
        logger.info(f"[marker_proper] Сбор результатов из: {result_dir}")
        
        import shutil
        
        # Ищем Markdown файлы
        md_files = list(result_dir.glob("*.md"))
        if md_files:
            # Копируем markdown в tmp_dir
            source_md = md_files[0]
            dest_md = tmp_dir / f"{pdf_stem}.md"
            
            content = source_md.read_text(encoding="utf-8", errors="ignore")
            dest_md.write_text(content, encoding="utf-8", errors="ignore")
            
            logger.info(f"[marker_proper] Markdown скопирован: {dest_md} (размер: {len(content)} символов)")
        else:
            logger.warning(f"[marker_proper] Markdown файлы не найдены в {result_dir}")
        
        # Копируем изображения
        image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]
        copied_images = 0
        
        for ext in image_extensions:
            for img_file in result_dir.glob(ext):
                try:
                    dest_img = tmp_dir / img_file.name
                    shutil.copy2(str(img_file), str(dest_img))
                    copied_images += 1
                    logger.info(f"[marker_proper] Скопировано изображение: {img_file.name}")
                except Exception as e:
                    logger.warning(f"[marker_proper] Не удалось скопировать {img_file.name}: {e}")
        
        if copied_images:
            logger.info(f"[marker_proper] Всего скопировано изображений: {copied_images}")


def _emit_progress(payload: dict) -> None:
    """Безопасно отправляет прогресс из фонового потока"""
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        callback = payload.get('callback')
        if callback:
            if asyncio.iscoroutinefunction(callback):
                asyncio.run_coroutine_threadsafe(callback(payload), loop)
            else:
                loop.call_soon_threadsafe(callback, payload)
    except Exception as e:
        logger.debug(f"[marker_proper] on_progress emit failed: {e}")


# Глобальный экземпляр модели
marker_proper_model = MarkerProperModel()
