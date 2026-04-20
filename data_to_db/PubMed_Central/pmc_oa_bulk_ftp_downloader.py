"""
PMC OA Bulk архивов - загрузка в S3.
"""
import ftplib
import io
import logging
import sys
import os
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import requests
from requests.adapters import HTTPAdapter, Retry

BASE_URL = 'ftp.ncbi.nlm.nih.gov'
BASE_DIR = '/pub/pmc/deprecated/oa_bulk/oa_comm/xml/'
ARCHIVE_BUCKET = 'knowledge-map-data'
ARCHIVE_PREFIX = 'archives/pmc/'

ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_FILE = (ROOT_DIR / 'logs' / 'pmc_oa_bulk_download.log')
MAX_WORKERS = 4
RETRIES = 3
CHUNK_SIZE = 4 * 1024 * 1024

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504], allowed_methods=["GET", "HEAD"])
adapter = HTTPAdapter(max_retries=retries)
session.mount('https://', adapter)
session.mount('http://', adapter)

_s3_client = None

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        from s3_client import get_s3_client as _get
        _s3_client = _get()
    return _s3_client

def ftp_list_tar_gz() -> list[str]:
    """Список всех .tar.gz на FTP."""
    with ftplib.FTP(BASE_URL) as ftp:
        ftp.login()
        ftp.cwd(BASE_DIR)
        names = ftp.nlst()
    return [n for n in names if n.endswith('.tar.gz')]

def archive_exists_in_s3(filename: str) -> bool:
    """Проверяет есть ли архив в S3."""
    s3 = get_s3_client()
    key = f"{ARCHIVE_PREFIX}{filename}"
    try:
        return s3.s3.head_object(Bucket=ARCHIVE_BUCKET, Key=key) is not None
    except Exception:
        return False

def download_to_s3(filename: str, resume_byte: int = 0) -> bool:
    """Скачивает архив напрямую в S3."""
    url = f"https://{BASE_URL}{BASE_DIR}{filename}"
    s3_key = f"{ARCHIVE_PREFIX}{filename}"

    for attempt in range(1, RETRIES + 1):
        try:
            headers = {"Range": f"bytes={resume_byte}-"} if resume_byte else {}
            mode = 'ab' if resume_byte else 'wb'

            with session.get(url, stream=True, headers=headers, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get('Content-Length', 0)) + resume_byte
                logger.info(f"[START] {filename}: total={total/1e6:.1f} MiB, resume={resume_byte}")

                buffer = io.BytesIO()
                downloaded = resume_byte
                
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    buffer.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 / total
                        logger.info(f"[{filename}] {downloaded/1e6:.1f}/{total/1e6:.1f} MiB ({pct:.1f}%)")

                buffer.seek(0)
                s3 = get_s3_client()
                s3.s3.put_object(Bucket=ARCHIVE_BUCKET, Key=s3_key, Body=buffer.getvalue())
                logger.info(f"[OK] {filename}: uploaded to S3")
                return True

        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"[ERROR] {filename} attempt {attempt}/{RETRIES}: {e}; retry in {wait}s")
            time.sleep(wait)

    logger.error(f"[FAIL] {filename}: after {RETRIES} attempts")
    return False

def download_file_remote(filename: str) -> bool:
    """Скачивает архив в S3, проверяя существующий."""
    if archive_exists_in_s3(filename):
        logger.info(f"[SKIP] {filename}: already in S3")
        return True

    return download_to_s3(filename)

def download_all_files() -> bool:
    """Скачивает все архивы PMC в S3 и сразу парсит каждый."""
    files = ftp_list_tar_gz()
    if not files:
        logger.error('No files found on FTP')
        return False

    logger.info(f"Downloading all {len(files)} files from FTP")

    success_count = 0
    error_count = 0

    for i, filename in enumerate(sorted(files), 1):
        logger.info(f"[{i}/{len(files)}] Downloading and processing: {filename}")
        try:
            if download_file_remote(filename):
                # Сразу парсим загруженный архив
                from .pmc_oa_bulk_to_db import parse_archive_from_s3
                s3_key = f"archives/pmc/{filename}"
                parse_archive_from_s3(s3_key)
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.error(f"[ERROR] {filename}: {e}")
            error_count += 1

    logger.info(f"Complete: {success_count} ok, {error_count} errors")
    return error_count == 0

if __name__ == '__main__':
    start = time.time()
    success = download_all_files()
    if success:
        logger.info(f"Done in {time.time() - start:.1f}s")
    else:
        logger.error('Completed with errors')
        sys.exit(1)