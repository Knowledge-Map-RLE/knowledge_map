"""Offline integrity check for published Article Pipeline DSL cases.

Run from ``api`` with Poetry:
    poetry run python ../eval/validate_article_pipeline_gold.py --limit 2

The command is intentionally read-only: it emits a concise console summary and
never creates JSON reports or rewrites DSL artifacts.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "knowledge_map_core" / "pipeline"))
sys.path.insert(0, str(ROOT / "shared" / "knowledge"))

from knowledge_contracts.validation import ValidationError  # noqa: E402
from knowledge_contracts.block_dsl import (  # noqa: E402
    DIRECT_ASSERTION_TYPES, DSL_FIELDS, subject_operation_issues,
)
from knowledge_pipeline.caption_units import caption_unit_ids  # noqa: E402
from knowledge_pipeline.dsl_rows import missing_required_fields, parse_dsl_rows  # noqa: E402
from knowledge_pipeline.reference_stripping import strip_references_info  # noqa: E402
from knowledge_pipeline.semantic_extraction import is_layout_only_fragment  # noqa: E402


CORPUS = ROOT / "eval" / "article_pipeline_gold"
_HTML_TAG_RE = re.compile(r"</?[a-z][^>]*>", re.IGNORECASE)
_TERM_RE = re.compile(r"[a-zа-яё]{2,}", re.IGNORECASE)
_SNAKE_CASE_VALUE_RE = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", re.IGNORECASE)
_CLAUSE_CONNECTIVE_RE = re.compile(
    r"\b(?:whereas|whilst|while|but|although)\b|"
    r"\b(?:which|that)\s+(?:is|are|was|were|can|could|may|might|will|has|have)\b|"
    r"\band\s+(?:consequently\s*,?\s*)?(?:[\w-]+\s+){0,8}"
    r"(?:is|are|was|were|has|have|can|may|might|will|do|does|show(?:s|ed)?|"
    r"demonstrat(?:e|es|ed)|indicat(?:e|es|ed)|contribut(?:e|es|ed)|differentiat(?:e|es|ed)|"
    r"increase[sd]?|decrease[sd]?|predict(?:s|ed)?|cause[sd]?|affect(?:s|ed)?|"
    r"lead(?:s|ing)?|result(?:s|ed)?|support(?:s|ed)?|inhibit(?:s|ed)?|"
    r"improv(?:es|ed)|worsen(?:s|ed)?|remain(?:s|ed)?|generat(?:e|es|ed)|"
    r"protect(?:s|ed)|perform(?:s|ed)?|peaks?)\b",
    re.IGNORECASE,
)
_STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "were", "article", "text"}
_METADATA_LINE_RE = re.compile(
    r"^\s*(?:\*\*)?(?:authors?|авторы|journal|журнал|doi|orcid|funding|финансирование|"
    r"conflict of interest|конфликт интересов|corresponding author|дата публикации)"
    r"(?:\*\*)?\s*:\s*.*$",
    re.IGNORECASE,
)
_CONTEXT_ONLY_TYPES = {
    "text", "image", "metadata", "reference", "funding", "interest_conflict",
    "versions", "code",
}
_EDITORIAL_TEXT_RE = re.compile(
    r"\b(?:acknowledg(?:e)?ments?|author contributions?|conflict of interest|"
    r"competing interests?|data availability|funding statement|copyright|license)\b|"
    r"благодарност|вклад автор|конфликт интересов|финансирован|доступность данных",
    re.IGNORECASE,
)
_MAX_DISPLAYED_FINDINGS_PER_CASE = 100
_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s<>]+$", re.IGNORECASE)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _standalone_doi(value: object) -> str | None:
    """Normalize a source unit only when its entire content is a DOI token."""
    if not isinstance(value, str):
        return None
    candidate = re.sub(r"^\s*(?:[*+-]\s*)?(?:doi\s*:\s*)?", "", value, flags=re.IGNORECASE)
    candidate = re.sub(
        r"^(?:https?://)?(?:dx\.)?doi\.org/", "", candidate, flags=re.IGNORECASE,
    ).strip()
    if not _DOI_RE.fullmatch(candidate):
        return None
    return candidate.casefold()


def _metadata_duplicate_coverage(rows: list[dict], unit_text: dict[str, str]) -> dict[str, str]:
    """Map standalone DOI source units to the T1 row that stores the same DOI.

    Article headers sometimes repeat the DOI as its own Markdown bullet. The
    runtime consolidates such T1 metadata rows and retains their provenance
    internally, while the exported DSL keeps only the primary ``unit=``. This
    narrow equivalence preserves coverage validation without weakening it for
    arbitrary omitted source units.
    """
    metadata_dois = {
        _standalone_doi(row["data"].get("doi")): row["tag"]
        for row in rows if row.get("blockType") == "metadata"
    }
    metadata_dois.pop(None, None)
    return {
        unit_id: metadata_dois[doi]
        for unit_id, text in unit_text.items()
        if (doi := _standalone_doi(text)) in metadata_dois
    }


def _missing_source_unit_ids(
    source_unit_ids: list[str], row_unit_ids: set[str], unit_text: dict[str, str],
    metadata_duplicate_units: dict[str, str],
) -> list[str]:
    """Return uncovered content units, excluding explicitly non-content layout fragments."""
    return sorted(
        unit_id
        for unit_id in set(source_unit_ids) - row_unit_ids
        if unit_id not in metadata_duplicate_units
        and not is_layout_only_fragment(unit_text.get(unit_id, ""))
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _semantic_findings(rows: list[dict], unit_text: dict[str, str]) -> list[str]:
    """Return deterministic source-grounding warnings without rejecting paraphrases."""
    findings: list[str] = []
    for row in rows:
        if row["blockType"] in {"text", "image", "metadata"}:
            continue
        unit = row["data"]["unit"]
        source_terms = {term.lower() for term in _TERM_RE.findall(unit_text[unit]) if term.lower() not in _STOPWORDS}
        row_terms: set[str] = set()
        snake_case_fields: set[str] = set()
        for dsl_key, spec in DSL_FIELDS[row["blockType"]].items():
            if spec.kind in {"ref", "refs", "ref_groups"}:
                continue
            value = row["data"].get(spec.json_field)
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, str):
                    continue
                if dsl_key in {"sub", "obj", "ctx", "name", "term", "definition"} \
                        and _SNAKE_CASE_VALUE_RE.search(item):
                    snake_case_fields.add(dsl_key)
                normalized = item.strip().lower()
                if normalized in {"article text", "#", ">", "/tr", "<td>", "</td>"}:
                    findings.append(
                        f"# WARNING SEMANTIC_VALUE_REVIEW row={row['tag']} unit={unit} "
                        f"field={dsl_key} kind=placeholder"
                    )
                elif _HTML_TAG_RE.search(item):
                    findings.append(
                        f"# WARNING SEMANTIC_VALUE_REVIEW row={row['tag']} unit={unit} "
                        f"field={dsl_key} kind=html_markup"
                    )
                row_terms.update(term.lower() for term in _TERM_RE.findall(item) if term.lower() not in _STOPWORDS)
        if snake_case_fields:
            findings.append(
                f"# DSL_SPACING_WARN row={row['tag']} unit={unit} "
                f"fields={','.join(sorted(snake_case_fields))}"
            )
        if row_terms and source_terms and not row_terms.intersection(source_terms):
            findings.append(f"# SOURCE_GROUNDING_WARN row={row['tag']} unit={unit} matched_terms=0")
    return findings


def _semantic_coverage_warnings(rows: list[dict], unit_text: dict[str, str]) -> list[str]:
    """Flag prose units represented only by context/text rows, without guessing labels.

    This is an audit warning, not an automatic rejection: a reviewer must decide
    whether the prose actually states a claim or is editorial/context-only.
    """
    semantic_by_unit: dict[str, list[dict]] = {}
    for row in rows:
        if row["blockType"] not in _CONTEXT_ONLY_TYPES:
            semantic_by_unit.setdefault(row["data"]["unit"], []).append(row)
    findings: list[str] = []
    for unit, text in unit_text.items():
        semantic_rows = semantic_by_unit.get(unit, [])
        statement_rows = [row for row in semantic_rows if row["blockType"] == "statement"]
        if semantic_rows:
            # This is a human-review signal, not a completeness verdict: a
            # connector can join coordinated objects rather than two claims.
            connectors = _CLAUSE_CONNECTIVE_RE.findall(text)
            if (connectors and len(statement_rows) == len(semantic_rows)
                    and len(statement_rows) < len(connectors) + 1):
                findings.append(
                    f"# COMPOUND_CLAIM_REVIEW unit={unit} statements={len(statement_rows)} "
                    f"clause_connectives={len(connectors)}"
                )
            continue
        body_lines = []
        for line in text.splitlines():
            if not line.strip() or re.match(r"^\s{0,3}#{1,6}\s+", line):
                continue
            if _METADATA_LINE_RE.match(line):
                continue
            body_lines.append(line)
        body = _HTML_TAG_RE.sub(" ", " ".join(body_lines))
        if _EDITORIAL_TEXT_RE.search(body):
            continue
        words = _TERM_RE.findall(body)
        if len(words) >= 4:
            findings.append(
                f"# SEMANTIC_COVERAGE_WARN unit={unit} rows=context_only words={len(words)}"
            )
    return findings


def _validate_case(case: dict, dsl_filename: str = "gold.dsl") -> tuple[int, list[str]]:
    pmc_id = case["pmc_id"]
    findings: list[str] = []
    directory = CORPUS / case["path"]
    article_path, dsl_path, units_path, meta_path = (directory / "article.md", directory / dsl_filename,
                                                       directory / "source_units.json", directory / "meta.json")
    _require(article_path.is_file() and dsl_path.is_file() and units_path.is_file() and meta_path.is_file(),
             f"{pmc_id}: missing article.md, {dsl_filename}, source_units.json, or meta.json")

    # Path.read_text uses universal newlines, matching offsets and checksums
    # created from the source Markdown on Windows and Linux alike.
    article = article_path.read_text(encoding="utf-8")
    units_document = json.loads(units_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    _require(_sha256(article) == meta.get("article_sha256"), f"{pmc_id}: article checksum mismatch")
    source_text, expected_references_removed = strip_references_info(article)
    _require(units_document.get("schema_version") == 1, f"{pmc_id}: unsupported source_units schema")
    _require(units_document.get("coordinate_space") == "pipeline_source_after_reference_stripping",
             f"{pmc_id}: wrong source-unit coordinate space")
    _require(units_document.get("offset_encoding") == "unicode_codepoints",
             f"{pmc_id}: wrong source-unit offset encoding")
    _require(units_document.get("source_sha256") == _sha256(source_text),
             f"{pmc_id}: pipeline source checksum mismatch")
    _require(units_document.get("source_text_length") == len(source_text),
             f"{pmc_id}: pipeline source length mismatch")
    _require(units_document.get("references_removed") == expected_references_removed,
             f"{pmc_id}: reference stripping metadata mismatch")

    units = units_document.get("source_units")
    _require(isinstance(units, list) and units, f"{pmc_id}: source_units are missing")
    ids: list[str] = []
    previous_end = 0
    unit_text: dict[str, str] = {}
    for unit in units:
        unit_id, start, end, text = unit.get("id"), unit.get("start"), unit.get("end"), unit.get("text")
        _require(isinstance(unit_id, str) and isinstance(start, int) and isinstance(end, int),
                 f"{pmc_id}: malformed source unit")
        _require(start >= previous_end and start < end <= len(source_text),
                 f"{pmc_id}: invalid span for {unit_id}")
        _require(source_text[start:end] == text, f"{pmc_id}: source text mismatch for {unit_id}")
        ids.append(unit_id)
        unit_text[unit_id] = text
        previous_end = end
    _require(len(ids) == len(set(ids)), f"{pmc_id}: duplicate source-unit id")
    _require(ids == [f"S{i}" for i in range(1, len(ids) + 1)], f"{pmc_id}: non-canonical source-unit ids")

    rows = parse_dsl_rows(dsl_path.read_text(encoding="utf-8"), ids)
    by_tag = {row["tag"]: row for row in rows}
    for row in rows:
        _require(not row["data"].get("_extra"), f"{pmc_id}: {row['tag']} has unknown DSL fields")
        missing = missing_required_fields(row)
        _require(not missing, f"{pmc_id}: {row['tag']} lacks required DSL fields: {', '.join(missing)}")
        if row["blockType"] == "statement":
            issues = subject_operation_issues(row["data"])
            blocking_issues = [
                issue for issue in issues if "hides a relative assertion" not in issue
            ]
            _require(not blocking_issues,
                     f"{pmc_id}: {row['tag']} invalid subject: {'; '.join(blocking_issues)}")
            for issue in issues:
                if issue not in blocking_issues:
                    findings.append(
                        f"# WARNING RELATIVE_CLAUSE_REVIEW row={row['tag']} "
                        f"unit={row['data']['unit']} detail={' '.join(issue.split())}"
                    )
            reference = row["data"].get("subjectStatementRef")
            if reference:
                target = by_tag.get(reference)
                _require(target is not None and target["blockType"] in DIRECT_ASSERTION_TYPES
                         and target["tag"] != row["tag"],
                         f"{pmc_id}: {row['tag']} subref= must cite another direct assertion")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_reference(tag: str) -> None:
        _require(tag not in visiting, f"{pmc_id}: cyclic subref= at {tag}")
        if tag in visited:
            return
        visiting.add(tag)
        reference = by_tag[tag]["data"].get("subjectStatementRef")
        if reference:
            visit_reference(reference)
        visiting.remove(tag)
        visited.add(tag)

    for tag in by_tag:
        visit_reference(tag)
    tags = [row["tag"] for row in rows]
    _require(tags == [f"B{i}" for i in range(1, len(rows) + 1)],
             f"{pmc_id}: DSL tags are not consecutive")

    row_units = {row["data"]["unit"] for row in rows}
    unexpected_units = sorted(row_units - set(ids))
    metadata_duplicate_units = _metadata_duplicate_coverage(rows, unit_text)
    missing_units = _missing_source_unit_ids(ids, row_units, unit_text, metadata_duplicate_units)
    if missing_units or unexpected_units:
        findings.append(
            f"# ERROR SOURCE_UNIT_COVERAGE missing={','.join(missing_units)} "
            f"unexpected={','.join(unexpected_units)}"
        )
    profile = {"sentences": [{"start": unit["start"], "end": unit["end"]} for unit in units]}
    mandatory_caption_units = caption_unit_ids(profile, source_text)
    image_units = {row["data"]["unit"] for row in rows if row["blockType"] == "image"}
    missing_captions = sorted(mandatory_caption_units - image_units)
    if missing_captions:
        findings.append(
            f"# ERROR MANDATORY_CAPTION_COVERAGE missing_units={','.join(missing_captions)}"
        )
    findings.extend(_semantic_findings(rows, unit_text))
    findings.extend(_semantic_coverage_warnings(rows, unit_text))
    return len(rows), findings


def main(limit: int = 2, run_version: int | None = None) -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    cases = manifest.get("cases", [])
    _require(manifest.get("article_count") == 20 and len(cases) == 20,
             "article_pipeline_gold must contain exactly 20 cases")
    _require(len({case.get("pmc_id") for case in cases}) == 20, "duplicate PMCID in manifest")

    _require(1 <= limit <= 20, "--limit must be between 1 and 20")
    _require(run_version is None or run_version > 0, "--run-version must be positive")
    dsl_filename = "gold.dsl" if run_version is None else f"run-v{run_version}.dsl"
    total_rows = 0
    warning_count = 0
    failed_cases: list[str] = []
    for case in cases[:limit]:
        try:
            rows, findings = _validate_case(case, dsl_filename)
        except (ValidationError, KeyError, TypeError, json.JSONDecodeError) as exc:
            failed_cases.append(case["pmc_id"])
            print(f"# ERROR case={case['pmc_id']} detail={' '.join(str(exc).split())}")
            continue
        total_rows += rows
        warning_count += len(findings)
        case_failed = False
        for finding in findings[:_MAX_DISPLAYED_FINDINGS_PER_CASE]:
            print(f"{finding} case={case['pmc_id']}")
            if finding.startswith("# ERROR"):
                case_failed = True
        # Fatal coverage findings are emitted before heuristic warnings. If a
        # case has many findings, keep the console report readable while still
        # giving the full finding count in its summary.
        if len(findings) > _MAX_DISPLAYED_FINDINGS_PER_CASE:
            print(f"# FINDINGS_TRUNCATED case={case['pmc_id']} "
                  f"omitted={len(findings) - _MAX_DISPLAYED_FINDINGS_PER_CASE}")
        if any(finding.startswith("# ERROR") for finding in findings):
            case_failed = True
        if case_failed:
            failed_cases.append(case["pmc_id"])
        print(f"# CASE case={case['pmc_id']} status={'FAIL' if case_failed else 'PASS'} "
              f"DSL_ROWS={rows} FINDINGS={len(findings)}")
    status = "FAIL" if failed_cases else "PASS"
    print(f"# {status} ARTICLE_PIPELINE_DSL ARTIFACT={dsl_filename} CASES={limit} FAILED={len(failed_cases)} "
          f"DSL_ROWS={total_rows} FINDINGS={warning_count}")
    if failed_cases:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2,
                        help="Leading manifest cases to validate; default: 2")
    parser.add_argument("--run-version", type=int,
                        help="Validate unreviewed run-vN.dsl instead of gold.dsl")
    args = parser.parse_args()
    try:
        main(args.limit, args.run_version)
    except (ValidationError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"FAIL ARTICLE_PIPELINE_GOLD {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
