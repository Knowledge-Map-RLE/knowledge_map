import ftplib
import hashlib
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry

# ================== Конфигурация ==================

BASE_URL = "ftp.ncbi.nlm.nih.gov"
BASE_DIR = "/pubmed/baseline/"
LOCAL_DIR = Path("D:/Данные/PubMed")
LOG_FILE = Path("./logs/download_all_xml_gz.log")
MAX_WORKERS = 8            # число потоков для параллелизации
RETRIES = 3                # число повторных попыток пользовательских этапов
CHUNK_SIZE = 4 * 1024 * 1024   # 4 MiB

# ================== Логирование ==================

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
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
    allowed_methods=["GET", "HEAD"]
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

# ================== Утилиты ==================

def ftp_list_xml_gz() -> list[str]:
    """Вернёт список всех .xml.gz-файлов на FTP."""
    with ftplib.FTP(BASE_URL) as ftp:
        ftp.login()
        ftp.cwd(BASE_DIR)
        names = ftp.nlst()
    return [n for n in names if n.endswith(".xml.gz")]

def get_remote_md5(filename: str) -> str:
    """Скачивает .md5 через HTTPS и возвращает реальный MD5-хеш."""
    url = f"https://{BASE_URL}{BASE_DIR}{filename}.md5"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    text = r.text.strip()
    # Найдём MD5-хеш формата 32 hex-символа
    m = re.search(r"\b[0-9a-fA-F]{32}\b", text)
    if not m:
        raise ValueError(f"Не удалось распарсить MD5 из: {text!r}")
    return m.group(0).lower()

def calc_md5(path: Path) -> str:
    """Считает MD5 локального файла."""
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()

# ================== Загрузка файлов ==================

def download_file_remote(filename: str) -> None:
    """
    Скачивает один файл с докачкой, проверкой MD5 и экспоненциальным бэкоффом.
    """
    url = f"https://{BASE_URL}{BASE_DIR}{filename}"
    dest = LOCAL_DIR / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    remote_md5 = get_remote_md5(filename)

    # Если уже есть и целый — пропускаем
    if dest.exists() and calc_md5(dest) == remote_md5:
        logger.info(f"[SKIP] {filename}: уже загружен и MD5 OK")
        return

    tmp = dest.with_suffix(dest.suffix + ".part")

    for attempt in range(1, RETRIES + 1):
        try:
            resume = tmp.stat().st_size if tmp.exists() else 0
            headers = {"Range": f"bytes={resume}-"} if resume else {}
            mode = "ab" if resume else "wb"

            with session.get(url, stream=True, headers=headers, timeout=60) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0)) + resume
                logger.info(f"[START] {filename}: total={total/1e6:.1f} MiB, resume={resume}")

                downloaded = resume
                with tmp.open(mode) as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        pct = downloaded * 100 / total
                        logger.info(f"[{filename}] {downloaded/1e6:.1f}/{total/1e6:.1f} MiB ({pct:.1f}%)")

            # После полной записи
            tmp.replace(dest)

            md5_local = calc_md5(dest)
            if md5_local != remote_md5:
                logger.warning(f"[MD5-FAIL] {filename}: {md5_local} != {remote_md5}")
                dest.unlink(missing_ok=True)
                tmp.unlink(missing_ok=True)
                raise IOError("MD5 mismatch after download")

            logger.info(f"[OK] {filename}: MD5 verified")
            return

        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"[ERROR] {filename} attempt {attempt}/{RETRIES}: {e}; retry in {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"Failed to download {filename} after {RETRIES} attempts")


def verify_all_downloads() -> bool:
    """
    Проверяет, что на сервере и локально скачано и присутствует ровно одинаковое
    множество файлов, без пропусков номеров.
    Возвращает True, если всё в порядке, иначе False.
    """
    # Получаем список файлов с FTP и локальный список
    server_files = sorted(ftp_list_xml_gz())
    local_files = sorted([p.name for p in LOCAL_DIR.glob("pubmed*.xml.gz")])

    # Считаем
    count_server = len(server_files)
    count_local = len(local_files)
    logger.info(f"На сервере: {count_server} файлов, локально: {count_local} файлов")

    # Ищем пропуски и лишние
    missing = [f for f in server_files if f not in local_files]
    extra   = [f for f in local_files  if f not in server_files]

    if missing:
        logger.error(f"Отсутствуют файлы ({len(missing)}): {missing[:5]}{'...' if len(missing)>5 else ''}")
    if extra:
        logger.warning(f"Лишние файлы ({len(extra)}): {extra[:5]}{'...' if len(extra)>5 else ''}")

    # Проверяем, что номера идут без пропусков
    # Извлечём номер из имени вида pubmedNNnXXXX.xml.gz
    import re
    nums = sorted(int(re.search(r"(\d+)\.xml\.gz$", f).group(1)) for f in server_files)
    if nums:
        expected = list(range(nums[0], nums[-1] + 1))
        if nums != expected:
            missing_idxs = set(expected) - set(nums)
            logger.error(f"Пропущенные номера между {nums[0]} и {nums[-1]}: {sorted(missing_idxs)[:5]}{'...' if len(missing_idxs)>5 else ''}")

    ok = (count_server == count_local) and not missing
    if ok:
        logger.info("✅ Проверка завершена: все файлы на месте и без пропусков.")
    else:
        logger.error("❌ Проверка завершена: найдены расхождения.")
    return ok

# ================== Основные функции ==================

def download_all_files():
    """Скачивает все .xml.gz в LOCAL_DIR параллельно."""
    files = ftp_list_xml_gz()
    total = len(files)
    logger.info(f"Найдено {total} файлов, старт загрузки в {MAX_WORKERS} потоков")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {exe.submit(download_file_remote, fn): fn for fn in files}
        for i, fut in enumerate(as_completed(futures), start=1):
            fn = futures[fut]
            try:
                fut.result()
                logger.info(f"[{i}/{total}] {fn} скачан успешно")
            except Exception as e:
                logger.error(f"[{i}/{total}] {fn} не удалось скачать: {e}")
    
    success = verify_all_downloads()
    if not success:
        logger.error("Не все файлы скачаны корректно.")
    return success

def download_one_file(pmid: str):
    """
    Скачивает один файл по PMID,
    если имя файла совпадает c '<pmid>.xml.gz'.
    """
    filename = f"{pmid}.xml.gz"
    return download_file_remote(filename)