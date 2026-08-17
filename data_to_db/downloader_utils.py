"""
Общие утилиты для загрузчиков данных.

Layer: Infrastructure — Data acquisition
Responsibility: докачка файлов (HTTP Range), проверка целостности (MD5),
                разбор HTML-листинга каталогов FTP по HTTPS.
"""
import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter, Retry

logger = logging.getLogger(__name__)

CHUNK_SIZE = 4 * 1024 * 1024
RETRIES = 5
BACKOFF_BASE = 2


def make_session() -> requests.Session:
    """HTTP-сессия с ретраями на сетевые ошибки и 5xx."""
    session = requests.Session()
    retries = Retry(
        total=RETRIES,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def md5_of_file(path: Path) -> str:
    """Вычисляет MD5 файла."""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, expected_md5: Optional[str] = None) -> bool:
    """Проверяет, что файл существует и соответствует ожидаемой целостности.

    Если expected_md5 задан — сверяем MD5, иначе достаточно ненулевого размера.
    """
    if not path.exists() or not path.is_file():
        return False
    if path.stat().st_size == 0:
        return False
    if not expected_md5:
        return True
    try:
        return md5_of_file(path).lower() == expected_md5.lower()
    except OSError:
        return False


def resumable_download(
    url: str,
    dest_path: Path,
    expected_md5: Optional[str] = None,
) -> bool:
    """Скачивает файл с поддержкой докачки (HTTP Range) и проверкой MD5.

    Аргументы:
        url: прямой HTTPS-адрес файла.
        dest_path: конечный путь; временный файл пишется как "<name>.part".
        expected_md5: ожидаемый MD5 для проверки (необязательно).

    Возвращает:
        True, если файл скачан полностью и прошёл проверку.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")

    if verify_file(dest_path, expected_md5):
        return True

    session = make_session()

    for attempt in range(1, RETRIES + 1):
        try:
            resume_byte = part_path.stat().st_size if part_path.exists() else 0
            headers = {"Range": f"bytes={resume_byte}-"} if resume_byte else {}
            with session.get(url, stream=True, headers=headers, timeout=60) as r:
                if r.status_code == 416:
                    # Диапазон вне размера файла — файл уже скачан полностью.
                    part_path.replace(dest_path)
                    return verify_file(dest_path, expected_md5)
                r.raise_for_status()

                total = int(r.headers.get("Content-Length", 0)) + resume_byte
                if r.status_code == 200 and resume_byte:
                    # Сервер проигнорировал Range — начинаем с нуля.
                    resume_byte = 0
                    total = int(r.headers.get("Content-Length", 0))
                    part_path.write_bytes(b"")

                downloaded = resume_byte
                with open(part_path, "ab" if resume_byte else "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)

                if total and downloaded >= total:
                    part_path.replace(dest_path)
                    if verify_file(dest_path, expected_md5):
                        return True
                    logger.warning(
                        f"[{dest_path.name}] MD5 mismatch, restarting download"
                    )
                    part_path.unlink(missing_ok=True)
                else:
                    # Соединение прервано — оставляем .part для следующей докачки.
                    logger.warning(
                        f"[{dest_path.name}] partial download {downloaded}/{total}"
                    )
                    return False
        except Exception as e:
            wait = BACKOFF_BASE ** attempt
            logger.warning(
                f"[ERROR] {url} attempt {attempt}/{RETRIES}: {e}; retry in {wait}s"
            )
            time.sleep(wait)

    logger.error(f"[FAIL] {url}: after {RETRIES} attempts")
    return False


def parse_ftp_xmlgz_listing(html: str) -> Dict[str, Dict[str, Optional[str]]]:
    """Разбирает HTML-листинг каталога FTP (по HTTPS) на файлы .xml.gz.

    Возвращает {имя_файла: {"md5": имя_md5_файла или None}}.
    """
    xml_gz = set(re.findall(r'href="([^"]+\.xml\.gz)"', html))
    md5_names = set(re.findall(r'href="([^"]+\.xml\.gz\.md5)"', html))
    result: Dict[str, Dict[str, Optional[str]]] = {}
    for name in xml_gz:
        md5_name = name + ".md5"
        result[name] = {"md5": md5_name if md5_name in md5_names else None}
    return result


def parse_md5_file(content: str) -> Optional[str]:
    """Извлекает MD5 из содержимого файла .md5 (формат NCBI)."""
    match = re.search(r"\b[0-9a-fA-F]{32}\b", content)
    if match:
        return match.group(0).lower()
    return None
