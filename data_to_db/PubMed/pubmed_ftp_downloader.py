"""
PubMed загрузчик (baseline / updatefiles).

Layer: Infrastructure — Data acquisition
Responsibility: скачивание XML.gz-архивов PubMed с докачкой (HTTP Range),
                проверкой целостности по MD5 и подсчётом прогресса.
"""
import json
import logging
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests

# Пути: PubMed/pubmed_ftp_downloader.py -> data_to_db
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from downloader_utils import (
    make_session,
    parse_ftp_xmlgz_listing,
    parse_md5_file,
    resumable_download,
    verify_file,
)

logger = logging.getLogger(__name__)

FTP_BASE = "https://ftp.ncbi.nlm.nih.gov"
CACHE_DIR = Path("logs") / "ftp_cache"

MD5_TTL_SECONDS = 6 * 3600


class PubMedDownloader:
    """Скачивает архивы PubMed из одного каталога FTP в локальную папку."""

    def __init__(self, name: str, ftp_dir: str, local_dir: Path):
        self.name = name
        self.ftp_dir = ftp_dir
        self.local_dir = Path(local_dir)
        self.session = make_session()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._md5_cache_file = CACHE_DIR / f"{name.lower().replace(' ', '_')}_md5.json"
        self._md5_cache: Dict[str, Optional[str]] = self._load_md5_cache()
        self._verified_cache_file = CACHE_DIR / f"{name.lower().replace(' ', '_')}_verified.json"
        self._verified: Dict[str, List[int]] = self._load_verified_cache()

    # ------------------------------------------------------------------ MD5
    def _load_md5_cache(self) -> Dict[str, Optional[str]]:
        if not self._md5_cache_file.exists():
            return {}
        try:
            return json.loads(self._md5_cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_md5_cache(self):
        try:
            self._md5_cache_file.write_text(
                json.dumps(self._md5_cache, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            logger.warning(f"[{self.name}] Cannot save MD5 cache: {e}")

    def _load_verified_cache(self) -> Dict[str, List[int]]:
        if not self._verified_cache_file.exists():
            return {}
        try:
            return json.loads(self._verified_cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_verified_cache(self):
        try:
            self._verified_cache_file.write_text(
                json.dumps(self._verified, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            logger.warning(f"[{self.name}] Cannot save verified cache: {e}")

    def get_remote_md5(self, filename: str) -> Optional[str]:
        """Возвращает MD5 удалённого файла (с кэшем)."""
        if filename in self._md5_cache:
            return self._md5_cache[filename]
        url = f"{FTP_BASE}{self.ftp_dir}{filename}.md5"
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            md5 = parse_md5_file(r.text)
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to fetch MD5 for {filename}: {e}")
            md5 = None
        self._md5_cache[filename] = md5
        self._save_md5_cache()
        return md5

    # ---------------------------------------------------------------- Файлы
    def list_remote_files(self) -> Dict[str, Dict[str, Optional[str]]]:
        """Список удалённых .xml.gz файлов в каталоге."""
        html = self.session.get(f"{FTP_BASE}{self.ftp_dir}", timeout=30).text
        return parse_ftp_xmlgz_listing(html)

    def _local_path(self, filename: str) -> Path:
        return self.local_dir / filename

    def file_done(self, filename: str) -> bool:
        """Проверяет, что архив уже скачан и верифицирован.

        Быстрый путь: файл присутствует и его (size, mtime_ns) совпадают с
        ранее проверенным — считаем готовым без повторного MD5-скана.
        """
        local = self._local_path(filename)
        try:
            if not local.is_file() or local.stat().st_size == 0:
                return False
            st = local.stat()
            fp = self._verified.get(filename)
            if fp and (st.st_size, st.st_mtime_ns) == tuple(fp):
                return True
        except OSError:
            return False

        md5 = self.get_remote_md5(filename)
        if verify_file(local, md5):
            try:
                st = local.stat()
                self._verified[filename] = [st.st_size, st.st_mtime_ns]
                self._save_verified_cache()
            except OSError:
                pass
            return True
        self._verified.pop(filename, None)
        return False

    # ----------------------------------------------------------------- Статус
    def get_status(self) -> Tuple[int, int]:
        """Возвращает (скачано_и_проверено, всего_удалённых) файлов."""
        remote = self.list_remote_files()
        if not remote:
            return 0, 0
        total = len(remote)
        done = sum(1 for name in remote if self.file_done(name))
        return done, total

    def download_one(self, filename: str) -> bool:
        """Скачивает один архив с докачкой и проверкой MD5."""
        url = f"{FTP_BASE}{self.ftp_dir}{filename}"
        return resumable_download(url, self._local_path(filename), self.get_remote_md5(filename))

    def download_all(
        self,
        on_progress: Callable[[int, int, str], None],
        should_stop: Optional[Callable[[], bool]] = None,
        wait_if_paused: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Скачивает недостающие архивы с докачкой.

        on_progress(downloaded, total, current_file) вызывается после каждого файла.
        """
        remote = self.list_remote_files()
        if not remote:
            logger.error(f"[{self.name}] No files found on FTP")
            return False

        total = len(remote)
        logger.info(f"[{self.name}] Found {total} files on FTP")

        for i, filename in enumerate(sorted(remote), 1):
            if should_stop and should_stop():
                logger.info(f"[{self.name}] Download stopped by user ({i}/{total})")
                return False
            if wait_if_paused:
                wait_if_paused()
            if should_stop and should_stop():
                return False

            local = self._local_path(filename)
            if self.file_done(filename):
                logger.info(f"[{self.name}] [{i}/{total}] SKIP {filename}: already verified")
                on_progress(i, total, filename)
                continue

            ok = self.download_one(filename)
            if ok:
                logger.info(f"[{self.name}] [{i}/{total}] OK {filename}")
            else:
                logger.error(f"[{self.name}] [{i}/{total}] FAIL {filename}")
            on_progress(i, total, filename)

        logger.info(f"[{self.name}] Download completed")
        return True
