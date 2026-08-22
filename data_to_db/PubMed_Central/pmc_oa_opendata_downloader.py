"""
PubMed Central загрузчик из s3://pmc-oa-opendata.

Layer: Infrastructure — Data acquisition
Responsibility: скачивание статей PMC (XML + изображения из XML) с докачкой.
                Использует CSV-инвентаризацию бакета pmc-oa-opendata.

Не скачиваются: TXT, PDF, JSON и прочие файлы статей.
"""
import gzip
import json
import logging
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from lxml import etree as LET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger(__name__)

BUCKET_NAME = "pmc-oa-opendata"
INVENTORY_PREFIX = "inventory-reports/pmc-oa-opendata/metadata/"

DATA_ROOT = Path("..") / "data"
ARTICLES_DIR = DATA_ROOT / "PubMed_Central"
CACHE_DIR = Path("logs")
PREFIXES_CACHE_FILE = CACHE_DIR / "pmc_inventory_prefixes.json"
PREFIXES_TTL_SECONDS = 24 * 3600

MAX_WORKERS = 10
CHUNK_SIZE = 4 * 1024 * 1024

DONE_MARKER = ".done"

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".svg", ".webp", ".bmp",
}
MANIFEST_DATE_RE = re.compile(
    r"^inventory-reports/pmc-oa-opendata/metadata/\d{4}-\d{2}-\d{2}T\d{2}-\d{2}Z/$"
)


class PmcOaOpendataDownloader:
    """Скачивает статьи PubMed Central из открытого бакета pmc-oa-opendata."""

    def __init__(self):
        self.s3 = boto3.client(
            "s3",
            region_name="us-east-1",
            config=Config(signature_version=UNSIGNED),
        )
        self.articles_dir = Path(ARTICLES_DIR)
        self.articles_dir.mkdir(parents=True, exist_ok=True)
        self._prefixes: Optional[List[str]] = None
        self._prefixes_source: Optional[str] = None

    # ------------------------------------------------------------- Инвентарь
    def get_latest_manifest_key(self) -> str:
        """Находит ключ актуального манифеста инвентаризации."""
        result = self.s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=INVENTORY_PREFIX, Delimiter="/")
        dates = [
            p["Prefix"] for p in result.get("CommonPrefixes", [])
            if MANIFEST_DATE_RE.match(p["Prefix"])
        ]
        if not dates:
            raise RuntimeError("Не удалось найти папки инвентаризации pmc-oa-opendata")
        return f"{sorted(dates)[-1]}manifest.json"

    def _list_prefixes_from_inventory(self) -> Tuple[List[str], str]:
        """Читает CSV-файлы инвентаризации и возвращает префиксы статей."""
        manifest_key = self.get_latest_manifest_key()
        logger.info(f"[PMC] Inventory manifest: {manifest_key}")

        manifest = json.loads(
            self.s3.get_object(Bucket=BUCKET_NAME, Key=manifest_key)["Body"].read()
        )
        prefixes: Set[str] = set()

        for file_info in manifest.get("files", []):
            csv_key = file_info["key"]
            logger.info(f"[PMC] Reading inventory CSV: {csv_key}")
            body = self.s3.get_object(Bucket=BUCKET_NAME, Key=csv_key)["Body"]
            with gzip.GzipFile(fileobj=body) as gz:
                for raw_line in gz:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    # Формат CSV: "bucket","key","date","etag"
                    fields = [f.strip('"') for f in line.split(",")]
                    if len(fields) < 2:
                        continue
                    key = fields[1]
                    if key.startswith("metadata/") and key.endswith(".json"):
                        prefix = key.replace("metadata/", "").replace(".json", "")
                        if re.fullmatch(r"PMC\d+\.\d+", prefix):
                            prefixes.add(prefix)

        return sorted(prefixes), manifest_key

    def _load_prefixes_from_cache(self) -> Optional[List[str]]:
        if not PREFIXES_CACHE_FILE.exists():
            return None
        try:
            data = json.loads(PREFIXES_CACHE_FILE.read_text(encoding="utf-8"))
            import time
            if time.time() - data.get("fetched_at", 0) > PREFIXES_TTL_SECONDS:
                return None
            prefixes = data.get("prefixes", [])
            return prefixes if isinstance(prefixes, list) else None
        except (OSError, ValueError):
            return None

    def _save_prefixes_cache(self, prefixes: List[str], source: str):
        import time
        try:
            PREFIXES_CACHE_FILE.write_text(
                json.dumps({"fetched_at": time.time(), "source": source, "prefixes": prefixes}),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning(f"[PMC] Cannot save prefix cache: {e}")

    def list_article_prefixes(self, refresh: bool = False) -> List[str]:
        """Возвращает список префиксов статей PMCxxx.N."""
        if self._prefixes and not refresh:
            return self._prefixes

        cached = None if refresh else self._load_prefixes_from_cache()
        if cached:
            logger.info(f"[PMC] Using cached inventory: {len(cached)} articles")
            self._prefixes = cached
            self._prefixes_source = "cache"
            return cached

        prefixes, manifest_key = self._list_prefixes_from_inventory()
        self._prefixes = prefixes
        self._prefixes_source = manifest_key
        self._save_prefixes_cache(prefixes, manifest_key)
        logger.info(f"[PMC] Inventory loaded: {len(prefixes)} articles")
        return prefixes

    # ---------------------------------------------------------- Локальный вид
    def _article_dir(self, prefix: str) -> Path:
        return self.articles_dir / prefix

    def count_done_articles(self, prefixes: Optional[List[str]] = None) -> int:
        if prefixes is None:
            prefixes = self._load_prefixes_from_cache()
        prefix_set = set(prefixes) if prefixes else None
        done = 0
        try:
            for d in self.articles_dir.iterdir():
                if d.is_dir() and (d / DONE_MARKER).exists():
                    if prefix_set is None or d.name in prefix_set:
                        done += 1
        except OSError as e:
            logger.warning(f"[PMC] Failed to scan articles dir: {e}")
        return done

    def get_status(self) -> Tuple[int, int]:
        """Возвращает (готово_статей, всего_статей)."""
        try:
            prefixes = self.list_article_prefixes()
        except Exception as e:
            logger.error(f"[PMC] Failed to load inventory for status: {e}")
            return self.count_done_articles(), 0
        total = len(prefixes)
        done = self.count_done_articles(prefixes)
        return done, total

    # ----------------------------------------------------------- Скачивание
    def _resumable_download_key(self, key: str, dest_path: Path) -> bool:
        """Скачивает объект S3 в локальный файл с докачкой через Range."""
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = dest_path.with_suffix(dest_path.suffix + ".part")

        if dest_path.exists() and dest_path.stat().st_size > 0:
            return True

        try:
            head = self.s3.head_object(Bucket=BUCKET_NAME, Key=key)
        except Exception as e:
            logger.warning(f"[PMC] head_object failed for {key}: {e}")
            head = None
        total_size = int(head["ContentLength"]) if head else 0

        resume_byte = part_path.stat().st_size if part_path.exists() else 0
        try:
            kwargs = {"Range": f"bytes={resume_byte}-"} if resume_byte else {}
            response = self.s3.get_object(Bucket=BUCKET_NAME, Key=key, **kwargs)
            with open(part_path, "ab" if resume_byte else "wb") as f:
                for chunk in response["Body"].iter_chunks(CHUNK_SIZE):
                    f.write(chunk)
        except Exception as e:
            logger.warning(f"[PMC] Partial download {key}: {e}")
            return False

        if total_size and part_path.stat().st_size < total_size:
            return False
        part_path.replace(dest_path)
        return True

    def extract_image_hrefs(self, xml_path: Path) -> Set[str]:
        """Извлекает из XML имена файлов изображений (graphic/media/inline-graphic)."""
        try:
            root = LET.parse(str(xml_path)).getroot()
        except Exception as e:
            logger.warning(f"[PMC] Failed to parse {xml_path.name}: {e}")
            return set()

        hrefs: Set[str] = set()
        for el in root.iter():
            tag = LET.QName(el).localname if isinstance(el.tag, str) else None
            if tag in ("graphic", "inline-graphic", "media", "supplementary-material"):
                href = (
                    el.get("{http://www.w3.org/1999/xlink}href")
                    or el.get("href")
                    or el.get("xlink:href")
                )
                if href:
                    hrefs.add(Path(href).name)

        return {h for h in hrefs if Path(h).suffix.lower() in IMAGE_EXTENSIONS}

    def _list_existing_image_keys(self, article_id: str) -> Set[str]:
        """Возвращает имена файлов, реально существующих в S3 для статьи."""
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            existing: Set[str] = set()
            for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=f"{article_id}/"):
                for obj in page.get("Contents", []):
                    name = Path(obj["Key"]).name
                    if name and name != f"{article_id}.xml":
                        existing.add(name)
            return existing
        except Exception as e:
            logger.warning(f"[PMC] list_objects failed for {article_id}: {e}")
            return set()

    def _remove_other_versions(self, prefix: str):
        """Удаляет локальные папки старых версий той же статьи (PMCxxxx.N).

        В бакете pmc-oa-opendata версия пакета — суффикс `.N` у имени папки.
        Стабильный идентификатор статьи — PMCID без суффикса (PMCxxxx), он не меняется.
        Старые версии не нужны: их повторная обработка создала бы дубли работы,
        а в базу/S3 они всё равно не попадают (существующие данные не переписываются).
        """
        base = prefix.rsplit(".", 1)[0] if "." in prefix else prefix
        for d in self.articles_dir.iterdir():
            if not d.is_dir():
                continue
            name = d.name
            name_base = name.rsplit(".", 1)[0] if "." in name else name
            if name_base == base and name != prefix:
                shutil.rmtree(d, ignore_errors=True)
                logger.info(f"[PMC] Removed superseded version dir: {name}")

    def download_article(self, prefix: str) -> bool:
        """Скачивает статью: XML + изображения из XML. Возвращает True при успехе."""
        article_id = prefix.rstrip("/")
        article_dir = self._article_dir(article_id)
        done_marker = article_dir / DONE_MARKER

        if done_marker.exists():
            return True

        article_dir.mkdir(parents=True, exist_ok=True)

        xml_key = f"{article_id}/{article_id}.xml"
        xml_path = article_dir / f"{article_id}.xml"

        if not self._resumable_download_key(xml_key, xml_path):
            logger.error(f"[PMC] Failed to download XML: {xml_key}")
            return False

        image_hrefs = self.extract_image_hrefs(xml_path)
        if image_hrefs:
            existing = self._list_existing_image_keys(article_id)
            available = image_hrefs & existing
            missing = image_hrefs - existing
            if missing:
                logger.debug(f"[PMC] {article_id}: {len(missing)} image(s) not in OA bucket, skipping")
            keys = [(f"{article_id}/{href}", article_dir / href) for href in sorted(available)]
            if keys:
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {
                        executor.submit(self._resumable_download_key, key, dest): (key, dest)
                        for key, dest in keys
                    }
                    for future in as_completed(futures):
                        key, _ = futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            logger.warning(f"[PMC] Failed to download {key}: {e}")

        done_marker.write_text(prefix + "\n", encoding="utf-8")
        return True

    def download_all(
        self,
        on_progress: Callable[[int, int, str], None],
        should_stop: Optional[Callable[[], bool]] = None,
        wait_if_paused: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Скачивает статьи с пропуском уже готовых (.done) и докачкой незавершённых."""
        prefixes = self.list_article_prefixes()
        if not prefixes:
            logger.error("[PMC] No articles found in inventory")
            return False

        total = len(prefixes)
        done = self.count_done_articles(prefixes)
        logger.info(f"[PMC] Total articles: {total}, already done: {done}")

        for i, prefix in enumerate(prefixes, 1):
            if should_stop and should_stop():
                logger.info(f"[PMC] Download stopped by user ({i}/{total})")
                return False
            if wait_if_paused:
                wait_if_paused()
            if should_stop and should_stop():
                return False

            if (self._article_dir(prefix) / DONE_MARKER).exists():
                done += 1
                on_progress(done, total, prefix)
                continue

            ok = self.download_article(prefix)
            if ok:
                done += 1
                self._remove_other_versions(prefix)
                logger.info(f"[PMC] [{done}/{total}] OK {prefix}")
            else:
                logger.error(f"[PMC] [{done}/{total}] FAIL {prefix}")
            on_progress(done, total, prefix)

        logger.info("[PMC] Download completed")
        return True
