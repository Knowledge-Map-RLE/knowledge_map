"""Read pretranslated article-pipeline GOLD content without runtime translation."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from knowledge_contracts.block_dsl import DSL_FIELDS
from knowledge_contracts.validation import ValidationError
from knowledge_pipeline.dsl_rows import parse_dsl_rows

logger = logging.getLogger(__name__)

class GoldLocalizationError(ValueError):
    """A GOLD localization is missing or does not match its immutable source."""


class GoldArticleLocalizationService:
    """Resolve GOLD cases by document UID and validate locale sidecars."""

    def __init__(self, gold_root: Path | None = None) -> None:
        self.gold_root = gold_root or (
            Path(__file__).resolve().parents[2] / "eval" / "article_pipeline_gold"
        )

    def get(
        self,
        document_uid: str,
        locale: str,
        *,
        source_pmc_id: str | None = None,
        pmc_id: str | None = None,
        doi: str | None = None,
    ) -> dict[str, Any] | None:
        """Read the article translation independently of structural editions."""
        return self._load(
            document_uid, locale, include_structure=False,
            source_pmc_id=source_pmc_id, pmc_id=pmc_id, doi=doi,
        )

    def get_structure(
        self,
        document_uid: str,
        locale: str,
        *,
        source_pmc_id: str | None = None,
        pmc_id: str | None = None,
        doi: str | None = None,
    ) -> dict[str, Any] | None:
        """Load the exact source editions used to translate saved blocks."""
        return self._load(
            document_uid, locale, include_structure=True,
            source_pmc_id=source_pmc_id, pmc_id=pmc_id, doi=doi,
        )

    def _load(
        self,
        document_uid: str,
        locale: str,
        *,
        include_structure: bool,
        source_pmc_id: str | None,
        pmc_id: str | None,
        doi: str | None,
    ) -> dict[str, Any] | None:
        if locale not in {"ru", "en"}:
            raise GoldLocalizationError(f"Unsupported article locale: {locale}")

        case = self._case_for_document(
            document_uid,
            source_pmc_id=source_pmc_id,
            pmc_id=pmc_id,
            doi=doi,
        )
        if case is None:
            return None

        article_path = case["directory"] / "article.md"
        try:
            article_bytes = article_path.read_bytes()
        except OSError as exc:
            raise GoldLocalizationError("Could not read GOLD article source") from exc
        article_text = article_bytes.decode("utf-8")
        meta = self._read_json(case["directory"] / "meta.json")
        manifest_pmc_id = case["pmc_id"]
        if self._normalize_identifier(meta.get("document_uid")) != self._normalize_identifier(manifest_pmc_id):
            raise GoldLocalizationError(
                f"GOLD article identity differs from its manifest for {document_uid}"
            )
        if meta.get("pmc_id") and self._normalize_identifier(meta["pmc_id"]) != self._normalize_identifier(manifest_pmc_id):
            raise GoldLocalizationError(
                f"GOLD article PMCID differs from its manifest for {document_uid}"
            )
        if locale == "en":
            result = {
                "locale": "en",
                "document_uid": document_uid,
                "title": meta["article_title"],
                "article_markdown": article_text,
            }
            if include_structure:
                result["rows_by_tag"] = {}
            return result

        sidecar_path = case["directory"] / "translation.ru.json"
        if not sidecar_path.is_file():
            raise GoldLocalizationError(
                f"Russian translation is not available for {document_uid}"
            )
        sidecar = self._read_json(sidecar_path)
        if sidecar.get("schema_version") != 1 or sidecar.get("locale") != "ru":
            raise GoldLocalizationError(
                f"Russian translation schema is unsupported for {document_uid}"
            )
        expected_file_hash = hashlib.sha256(article_bytes).hexdigest()
        if sidecar.get("source_file_sha256") != expected_file_hash:
            raise GoldLocalizationError(
                f"Russian translation source checksum differs for {document_uid}"
            )
        if sidecar.get("source_article_sha256") != meta.get("article_sha256"):
            raise GoldLocalizationError(
                f"Russian translation source article identity differs for {document_uid}"
            )

        translated_article = sidecar.get("article_markdown")
        title = sidecar.get("title")
        if not isinstance(translated_article, str) or not translated_article.strip():
            raise GoldLocalizationError(
                f"Russian article text is empty for {document_uid}"
            )
        if not isinstance(title, str) or not title.strip():
            raise GoldLocalizationError(f"Russian article title is empty for {document_uid}")

        result = {
            "locale": "ru",
            "document_uid": document_uid,
            "title": title,
            "article_markdown": translated_article,
        }
        if not include_structure:
            return result

        rows = sidecar.get("rows_by_tag")
        if not isinstance(rows, dict) or any(
            not isinstance(tag, str)
            or re.fullmatch(r"B[1-9][0-9]*", tag) is None
            or not isinstance(row, dict)
            or not isinstance(row.get("display_text"), str)
            or not row["display_text"].strip()
            for tag, row in rows.items()
        ):
            raise GoldLocalizationError(
                f"Russian structural rows are invalid for {document_uid}"
            )

        result["rows_by_tag"] = rows
        result["_source_rows_by_tag"] = self._source_rows(case["directory"])
        result["_saved_blocks_by_fingerprint"] = self._saved_block_translations(
            case["directory"], expected_file_hash
        )
        return result

    def _source_rows(self, directory: Path) -> dict[str, dict[str, Any]]:
        """Read the exact structural edition translated by rows_by_tag."""
        if (directory / "gold.dsl").is_file():
            units = self._read_json(directory / "source_units.json")["source_units"]
            try:
                dsl = (directory / "gold.dsl").read_text(encoding="utf-8")
            except OSError as exc:
                raise GoldLocalizationError("Could not read GOLD structural source") from exc
        else:
            gold = self._read_json(directory / "gold.json")
            units, dsl = gold["source_units"], gold["dsl"]
        try:
            rows = parse_dsl_rows(dsl, [unit["id"] for unit in units])
        except ValidationError as exc:
            raise GoldLocalizationError("GOLD structural source is invalid") from exc
        unit_text = {unit["id"]: unit["text"] for unit in units}
        for row in rows:
            if row["blockType"] == "text" and not row["data"].get("content"):
                row["data"]["content"] = unit_text[row["data"]["unit"]]
        return {row["tag"]: row for row in rows}

    def _saved_block_translations(self, directory: Path, source_hash: str) -> dict:
        path = directory / "translation.ru.saved-blocks.json"
        if not path.is_file():
            return {}
        saved = self._read_json(path)
        source_dsl = self._read_json(directory / "gold.json").get("dsl")
        if (saved.get("schema_version") != 1 or saved.get("locale") != "ru"
                or saved.get("source_file_sha256") != source_hash
                or not isinstance(source_dsl, str)
                or saved.get("source_structural_sha256") != hashlib.sha256(source_dsl.encode("utf-8")).hexdigest()):
            raise GoldLocalizationError("Saved GOLD block translation source differs")
        entries = saved.get("blocks_by_fingerprint")
        if (not isinstance(entries, dict) or not entries
                or saved.get("source_block_count") != len(entries)
                or any(not isinstance(key, str) or re.fullmatch(r"[a-f0-9]{64}", key) is None
                       or not isinstance(row, dict)
                       or not isinstance(row.get("display_text"), str)
                       or not row["display_text"].strip()
                       for key, row in entries.items())):
            raise GoldLocalizationError("Saved GOLD block translations are invalid")
        return entries

    @staticmethod
    def block_fingerprint(block: dict[str, Any]) -> str:
        """Bind a saved translation to its original type and complete payload."""
        payload = {"blockType": block["blockType"], "data": block.get("data") or {}}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def localize_blocks(self, blocks: list[dict], localization: dict) -> list[dict]:
        if localization["locale"] == "en":
            return blocks
        source_rows = localization["_source_rows_by_tag"]
        saved = localization["_saved_blocks_by_fingerprint"]
        tags_by_id = {block["instanceId"]: (block.get("data") or {}).get("tag")
                      for block in blocks}
        result = []
        for block in blocks:
            data = block.get("data") or {}
            translated = saved.get(self.block_fingerprint(block))
            if translated is None:
                tag = data.get("tag")
                expected = source_rows.get(tag)
                if expected is not None and self._same_source_row(block, expected, tags_by_id):
                    translated = localization["rows_by_tag"].get(tag)
            if translated is None:
                row_id = data.get("tag") or block["instanceId"]
                logger.warning("GOLD block localization mismatch document=%s row=%s type=%s",
                               localization["document_uid"], row_id, block["blockType"])
                raise GoldLocalizationError(
                    f"Russian translation does not match the saved structural row {row_id}"
                )
            item = {**block, "display_text": translated["display_text"]}
            if translated.get("type_name"):
                item["localized_type_name"] = translated["type_name"]
            result.append(item)
        return result

    @staticmethod
    def _same_source_row(block: dict, expected: dict, tags_by_id: dict) -> bool:
        if block["blockType"] != expected["blockType"]:
            return False
        fields = {spec.json_field for spec in DSL_FIELDS.get(block["blockType"], {}).values()}
        fields.update({"tag", "unit", "_extra"})
        actual = {key: value for key, value in (block.get("data") or {}).items() if key in fields}
        statement_ref = actual.get("subjectStatementRef")
        if isinstance(statement_ref, str) and statement_ref in tags_by_id:
            actual["subjectStatementRef"] = tags_by_id[statement_ref]
        return actual == expected["data"]

    @staticmethod
    def localize_graph(graph: dict | None, localized_blocks: list[dict]) -> dict | None:
        if graph is None:
            return None
        by_id = {block["instanceId"]: block for block in localized_blocks}
        nodes = []
        for node in graph.get("nodes", []):
            block = by_id.get(node.get("structural_id") or node.get("id"))
            if block is None or not block.get("display_text"):
                raise GoldLocalizationError(
                    f"Russian translation does not match the saved map node {node.get('id')}"
                )
            nodes.append({**node, "display_text": block["display_text"]})
        return {**graph, "nodes": nodes}

    @staticmethod
    def _normalize_identifier(value: Any) -> str:
        normalized = str(value or "").strip().casefold()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip()
                break
        return normalized

    def _case_for_document(
        self,
        document_uid: str,
        *,
        source_pmc_id: str | None = None,
        pmc_id: str | None = None,
        doi: str | None = None,
    ) -> dict[str, Any] | None:
        manifest = self._read_json(self.gold_root / "manifest.json")
        cases = manifest.get("cases")
        if not isinstance(cases, list):
            raise GoldLocalizationError("GOLD article manifest is invalid")

        requested = {
            self._normalize_identifier(value)
            for value in (document_uid, source_pmc_id, pmc_id, doi)
            if self._normalize_identifier(value)
        }
        matched_cases = []
        for entry in cases:
            if not isinstance(entry, dict):
                continue
            relative = Path(str(entry.get("path", "")))
            case_directory = (self.gold_root / relative).resolve()
            if self.gold_root.resolve() not in case_directory.parents:
                raise GoldLocalizationError("GOLD article path escapes its data directory")
            meta = self._read_json(case_directory / "meta.json")
            known = {
                self._normalize_identifier(value)
                for value in (
                    entry.get("pmc_id"),
                    meta.get("pmc_id"),
                    meta.get("document_uid"),
                    meta.get("doi"),
                )
                if self._normalize_identifier(value)
            }
            if requested & known:
                pmc_id = entry.get("pmc_id") or meta.get("pmc_id") or meta.get("document_uid")
                if not isinstance(pmc_id, str) or not pmc_id.strip():
                    raise GoldLocalizationError("GOLD article manifest entry has no PMCID")
                matched_cases.append({"directory": case_directory, "meta": meta, "pmc_id": pmc_id})
        if len(matched_cases) > 1:
            raise GoldLocalizationError("GOLD article identifiers refer to different cases")
        return matched_cases[0] if matched_cases else None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GoldLocalizationError(f"Could not load GOLD localization data: {path.name}") from exc
        if not isinstance(value, dict):
            raise GoldLocalizationError(f"GOLD JSON root must be an object: {path.name}")
        return value
