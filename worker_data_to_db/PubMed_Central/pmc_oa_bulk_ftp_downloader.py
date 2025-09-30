import ftplib
import logging
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry

# ================== Конфигурация ==================

BASE_URL = 'ftp.ncbi.nlm.nih.gov'
BASE_DIR = '/pub/pmc/oa_bulk/oa_comm/xml/'
LOCAL_DIR = Path('E:/Данные/PubMed_Central')

ROOT_DIR = Path(__file__).resolve().parents[1]  # worker_data_to_db
LOG_FILE = (ROOT_DIR / 'logs' / 'pmc_oa_bulk_download.log')
MAX_WORKERS = 4            # зарезервировано для будущей параллелизации
RETRIES = 3                # число повторных попыток пользовательских этапов
CHUNK_SIZE = 4 * 1024 * 1024   # 4 MiB

# ================== Логирование ==================

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

# ================== HTTP Сессия с Retry ==================

session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET", "HEAD"],
)
adapter = HTTPAdapter(max_retries=retries)
session.mount('https://', adapter)
session.mount('http://', adapter)

# ================== Утилиты ==================

def ftp_list_tar_gz() -> list[str]:
    """Вернёт список всех .tar.gz-файлов в каталоге PMC OA Bulk (comm/xml)."""
    with ftplib.FTP(BASE_URL) as ftp:
        ftp.login()
        ftp.cwd(BASE_DIR)
        names = ftp.nlst()
    return [n for n in names if n.endswith('.tar.gz')]


# ================== Загрузка файлов ==================

def download_file_remote(filename: str) -> None:
    """
    Скачивает один файл с докачкой (без проверки MD5), с экспоненциальным бэкоффом.
    """
    url = f"https://{BASE_URL}{BASE_DIR}{filename}"
    dest = LOCAL_DIR / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    tmp = dest.with_suffix(dest.suffix + '.part')

    for attempt in range(1, RETRIES + 1):
        try:
            resume = tmp.stat().st_size if tmp.exists() else 0
            headers = {"Range": f"bytes={resume}-"} if resume else {}
            mode = 'ab' if resume else 'wb'

            with session.get(url, stream=True, headers=headers, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get('Content-Length', 0)) + resume
                logger.info(f"[START] {filename}: total={total/1e6:.1f} MiB, resume={resume}")

                downloaded = resume
                with tmp.open(mode) as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded * 100 / total
                            logger.info(f"[{filename}] {downloaded/1e6:.1f}/{total/1e6:.1f} MiB ({pct:.1f}%)")

            # После полной записи
            tmp.replace(dest)
            logger.info(f"[OK] {filename}: скачан")
            return

        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"[ERROR] {filename} attempt {attempt}/{RETRIES}: {e}; retry in {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"Failed to download {filename} after {RETRIES} attempts")


# ================== Основные функции ==================

def download_all_files() -> bool:
    """Скачивает все .tar.gz файлы из каталога PMC OA Bulk в LOCAL_DIR."""
    files = ftp_list_tar_gz()
    if not files:
        logger.error('Не найдено файлов для загрузки')
        return False

    logger.info(f"Найдено {len(files)} файлов для загрузки")

    success_count = 0
    error_count = 0

    for i, filename in enumerate(sorted(files), 1):
        logger.info(f"[{i}/{len(files)}] Загружаем: {filename}")
        try:
            download_file_remote(filename)
            logger.info(f"[OK] {filename} скачан успешно")
            success_count += 1
        except Exception as e:
            logger.error(f"[ERROR] {filename} не удалось скачать: {e}")
            error_count += 1

    logger.info(f"Загрузка завершена: {success_count} успешно, {error_count} с ошибками")
    return error_count == 0


def download_one_file(archive_name: str):
    """
    Скачивает один конкретный архив по имени (например, 'comm_use.A-B.xml.tar.gz').
    """
    return download_file_remote(archive_name)


if __name__ == '__main__':
    start = time.time()
    success = download_all_files()
    if success:
        logger.info(f"Загрузка завершена успешно за {time.time() - start:.1f}s")
    else:
        logger.error('Загрузка завершена с ошибками')
        sys.exit(1)