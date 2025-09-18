"""Утилиты для работы с хешированием"""
import hashlib
from typing import Dict, Any
from pathlib import Path as SysPath


def _compute_md5(data: bytes) -> str:
    """Вычисляет MD5 хеш для данных"""
    md5 = hashlib.md5()
    md5.update(data)
    return md5.hexdigest()


async def _collect_marker_outputs(conv_dir: SysPath, pdf_stem: str) -> Dict[str, Any]:
    """Собирает результаты конвертации из папки (совместимость)"""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"[hash_utils] Сбор результатов из: {conv_dir}")
    
    outputs: Dict[str, Any] = {}
    
    # Ищем Markdown файлы
    md_files = list(conv_dir.glob("*.md"))
    if md_files:
        outputs["markdown"] = md_files[0]
        logger.info(f"[hash_utils] Найден Markdown файл: {md_files[0]}")
    else:
        logger.warning(f"[hash_utils] Markdown файлы не найдены в {conv_dir}")
    
    # Ищем JSON метаданные
    json_meta = list(conv_dir.glob("*_meta.json"))
    if json_meta:
        outputs["meta"] = json_meta[0]
        logger.info(f"[hash_utils] Найден meta файл: {json_meta[0]}")
    
    # Ищем изображения
    image_files = list(conv_dir.glob("*.png")) + list(conv_dir.glob("*.jpg")) + list(conv_dir.glob("*.jpeg"))
    if image_files:
        logger.info(f"[hash_utils] Найдено изображений: {len(image_files)}")
    
    outputs["images_dir"] = conv_dir
    return outputs
