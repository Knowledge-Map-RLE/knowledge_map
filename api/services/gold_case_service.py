"""
Layer: Application — Services
Package: services.gold_case_service
Responsibility: CRUD золотых эталонов LLM-экстракции на диске (eval/gold):
чтение кейсов, создание из статьи редактора, обновление блоков,
валидация, атомарная запись и контрольные суммы.

Allowed imports: infrastructure.config, src.schemas.gold, tools.llm_extract.metrics
Forbidden imports: fastapi, neomodel (напрямую)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pydantic

from infrastructure.config import settings
from src.schemas.gold import (
    ARTICLE_NAME,
    CASE_FILES,
    CHECKSUM_EXCLUDES,
    CHECKSUMS_NAME,
    GOLD_SCHEMA_VERSION,
    GoldBlock,
    MANIFEST_NAME,
    META_NAME,
    STRUCTURAL_LINES_NAME,
)
from tools.llm_extract.metrics import analyze_uuid_graph


class GoldCaseError(Exception):
    """Базовая ошибка работы с эталонами."""


class GoldCaseNotFound(GoldCaseError):
    """Кейс или документ не найден."""


class GoldCaseConflict(GoldCaseError):
    """Конфликт состояния (документ не аннотирован и т.п.)."""


class GoldCaseValidationError(GoldCaseError):
    """Блоки не прошли валидацию; errors — человекочитаемый список ошибок."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors[:5]) + ("…" if len(errors) > 5 else ""))


# ── Транслитерация для slug ───────────────────────────────────────────────────

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(text: str) -> str:
    """Заголовок -> kebab-case slug (кириллица транслитом), до 80 символов."""
    lowered = (text or "").strip().lower()
    translit = "".join(_TRANSLIT.get(ch, ch) for ch in lowered)
    slug = re.sub(r"[^a-z0-9]+", "-", translit).strip("-")
    return slug[:80].strip("-") or "case"


# ── Валидация блоков (общая с eval/validate_gold.py) ──────────────────────────

def validate_gold_blocks(blocks: Any) -> List[str]:
    """Валидирует список блоков эталона; возвращает список ошибок (пусто = ОК)."""
    if not isinstance(blocks, list) or not blocks:
        return ["blocks должен быть непустым списком"]
    errors: List[str] = []
    seen_ids: Dict[str, int] = {}
    parsed: List[Dict[str, Any]] = []
    for index, block in enumerate(blocks):
        try:
            model = GoldBlock.model_validate(block)
        except pydantic.ValidationError as exc:
            errors.append(f"блок #{index}: {exc.errors()[0]['msg']}")
            continue
        if model.instanceId in seen_ids:
            errors.append(
                f"дубликат instanceId {model.instanceId} "
                f"(блоки #{seen_ids[model.instanceId]} и #{index})"
            )
        else:
            seen_ids[model.instanceId] = index
        parsed.append(block)
    if not parsed:
        return errors
    graph = analyze_uuid_graph(parsed)
    if graph["dangling_refs"]:
        errors.append(
            f"висячие UUID-ссылки: {graph['dangling_refs']} "
            f"(уникальных: {graph['dangling_unique']})"
        )
    return errors


# ── Контрольные суммы (общие с eval/validate_gold.py) ─────────────────────────

def iter_gold_files(gold_root: Path) -> List[Path]:
    return [
        p for p in sorted(Path(gold_root).rglob("*"))
        if p.is_file() and p.name not in CHECKSUM_EXCLUDES
    ]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_checksum_lines(gold_root: Path) -> List[str]:
    root = Path(gold_root)
    return [f"{sha256_of(p)}  {p.relative_to(root).as_posix()}" for p in iter_gold_files(root)]


def write_checksums(gold_root: Path) -> None:
    lines = compute_checksum_lines(gold_root)
    _atomic_write_text(Path(gold_root) / CHECKSUMS_NAME, "\n".join(lines) + "\n")


# ── Атомарная запись ──────────────────────────────────────────────────────────

def _atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Сервис ────────────────────────────────────────────────────────────────────

class GoldCaseService:
    """Хранилище золотых эталонов: каталог gold_root с манифестом и чексуммами."""

    def __init__(self, gold_root: Optional[Path] = None) -> None:
        self.gold_root = Path(gold_root) if gold_root else settings.resolved_gold_dir

    # ── Чтение ────────────────────────────────────────────────────────────

    def case_dir(self, slug: str) -> Path:
        directory = self.gold_root / slug
        if (
            not slug
            or "/" in slug
            or "\\" in slug
            or slug in (".", "..")
            or not (directory / STRUCTURAL_LINES_NAME).is_file()
        ):
            raise GoldCaseNotFound(f"Кейс '{slug}' не найден в {self.gold_root}")
        return directory

    def list_cases(self) -> List[Dict[str, Any]]:
        """Список кейсов из meta.json (без содержимого блоков)."""
        cases: List[Dict[str, Any]] = []
        if not self.gold_root.is_dir():
            return cases
        for directory in sorted(self.gold_root.iterdir()):
            meta_path = directory / META_NAME
            if not directory.is_dir() or not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                meta = {"slug": directory.name}
            cases.append({
                "slug": meta.get("slug", directory.name),
                "article_title": meta.get("article_title", ""),
                "doi": meta.get("doi", ""),
                "lang": meta.get("lang", ""),
                "doc_id": meta.get("doc_id"),
                "needs_review": bool(meta.get("needs_review", False)),
            })
        return cases

    def doc_id_index(self) -> Dict[str, Dict[str, Any]]:
        """Индекс doc_id -> краткая информация о кейсе (для бейджей в UI).

        При нескольких кейсах на один doc_id берётся первый по алфавиту slug.
        """
        index: Dict[str, Dict[str, Any]] = {}
        for case in self.list_cases():
            doc_id = case.get("doc_id")
            if doc_id and doc_id not in index:
                index[doc_id] = case
        return index

    def get_case(self, slug: str) -> Dict[str, Any]:
        """Полный кейс: мета, текст статьи-снапшота и блоки."""
        directory = self.case_dir(slug)
        meta = json.loads((directory / META_NAME).read_text(encoding="utf-8"))
        payload = json.loads(
            (directory / STRUCTURAL_LINES_NAME).read_text(encoding="utf-8")
        )
        article_text = ""
        article_path = directory / ARTICLE_NAME
        if article_path.is_file():
            article_text = article_path.read_text(encoding="utf-8")
        return {
            "success": True,
            "slug": slug,
            "meta": meta,
            "article_text": article_text,
            "blocks": payload.get("blocks", []),
        }

    # ── Запись ────────────────────────────────────────────────────────────

    async def create_case_from_article(
        self,
        doc_id: str,
        annotator: str,
        blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Создаёт кейс из текущего состояния статьи редактора.

        blocks — строки из состояния редактора клиента; если не переданы,
        берутся сохранённые блоки статьи.
        """
        from services.article_editor_service import ArticleEditorService  # тяжёлая зависимость (neomodel)

        article_service = ArticleEditorService()
        article = await article_service.get_article(doc_id)
        if not article:
            raise GoldCaseNotFound(f"Статья '{doc_id}' не найдена")

        text_result = await article_service.get_article_text(doc_id)
        if text_result.get("not_annotated"):
            raise GoldCaseConflict(text_result.get("message", "Документ не аннотирован"))
        article_text = text_result.get("text", "")
        if not article_text.strip():
            raise GoldCaseConflict("Текст статьи пуст")

        if not blocks:
            blocks_result = await article_service.get_blocks(doc_id)
            blocks = blocks_result.get("blocks", [])

        title = article.get("title", "") or article.get("original_filename", "") or "Без названия"
        slug = self._unique_slug(slugify(title))
        now = _now_iso()
        meta: Dict[str, Any] = {
            "slug": slug,
            "schema_version": GOLD_SCHEMA_VERSION,
            "article_title": title,
            "doi": "",
            "lang": "",
            "doc_id": doc_id,
            "source_article": article.get("original_filename") or title,
            "annotator": annotator,
            "annotated_at": now,
            "needs_review": False,
            "notes": "",
        }
        self._write_case(slug, meta, blocks, article_text)
        return self.get_case(slug)

    async def update_case_blocks(
        self, slug: str, annotator: str, blocks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Перезаписывает structural_lines.json и article.md кейса.

        structural_lines.json — выверенные блоки; article.md — свежий снапшот
        исходного текста статьи (не резолв триплетов), синхронизируемый с
        текущим текстом документа редактора.
        """
        from services.article_editor_service import ArticleEditorService  # тяжёлая зависимость (neomodel)

        directory = self.case_dir(slug)
        errors = validate_gold_blocks(blocks)
        if errors:
            raise GoldCaseValidationError([f"[{slug}] {e}" for e in errors])

        meta = json.loads((directory / META_NAME).read_text(encoding="utf-8"))
        meta["updated_at"] = _now_iso()
        meta["updated_by"] = annotator

        article_text: Optional[str] = None
        doc_id = meta.get("doc_id")
        if doc_id:
            article_service = ArticleEditorService()
            text_result = await article_service.get_article_text(doc_id)
            if not text_result.get("not_annotated"):
                candidate = text_result.get("text", "")
                if candidate and candidate.strip():
                    article_text = candidate

        _atomic_write_json(directory / META_NAME, meta)

        payload: Dict[str, Any] = {"schema_version": GOLD_SCHEMA_VERSION}
        payload["blocks"] = blocks
        _atomic_write_json(directory / STRUCTURAL_LINES_NAME, payload)
        if article_text is not None:
            _atomic_write_text(directory / ARTICLE_NAME, article_text)
        write_checksums(self.gold_root)
        return self.get_case(slug)

    # ── Внутреннее ────────────────────────────────────────────────────────

    def _unique_slug(self, base: str) -> str:
        candidate = base
        counter = 2
        while (self.gold_root / candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _write_case(
        self, slug: str, meta: Dict[str, Any], blocks: List[Dict[str, Any]], article_text: str
    ) -> None:
        errors = validate_gold_blocks(blocks)
        if errors:
            raise GoldCaseValidationError(errors)

        directory = self.gold_root / slug
        directory.mkdir(parents=True, exist_ok=False)

        payload: Dict[str, Any] = {"schema_version": GOLD_SCHEMA_VERSION}
        payload["blocks"] = blocks
        _atomic_write_json(directory / STRUCTURAL_LINES_NAME, payload)
        _atomic_write_json(directory / META_NAME, meta)
        _atomic_write_text(directory / CASE_FILES[0], article_text)

        self._upsert_manifest(slug)
        write_checksums(self.gold_root)

    def _upsert_manifest(self, slug: str) -> None:
        manifest_path = self.gold_root / MANIFEST_NAME
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {"version": GOLD_SCHEMA_VERSION, "cases": []}
        slugs = {c.get("slug") for c in manifest.get("cases", [])}
        if slug not in slugs:
            manifest.setdefault("cases", []).append({"slug": slug})
            manifest["cases"] = sorted(manifest["cases"], key=lambda c: c.get("slug", ""))
        _atomic_write_json(manifest_path, manifest)
