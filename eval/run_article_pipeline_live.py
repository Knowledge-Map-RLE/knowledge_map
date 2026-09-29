"""Run a bounded live Article Pipeline evaluation and save unreviewed DSL.

Run from ``api`` with Poetry::

    poetry run python ../eval/run_article_pipeline_live.py --limit 2

The default is deliberately two articles. A technically successful run is not
expert-reviewed gold: every produced result is saved as ``run-vN.dsl`` and
``gold.dsl`` is never changed by this script. Legacy ``gold.json`` is untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "shared" / "model_registry"))

from knowledge_contracts.block_dsl import DSL_FIELDS
from knowledge_contracts.block_types import KEY_TO_LEGACY_INT
from knowledge_contracts.validation import ValidationError, require
from knowledge_pipeline.dsl_diagnostics import render_warning_report
from knowledge_pipeline.dsl_rows import escape_dsl_value, parse_dsl_rows
from knowledge_pipeline.pipeline import ArticlePipeline
from knowledge_pipeline.prompts import PROMPT_VERSION

from infrastructure.config import model_registry, resolve_model_profile
from infrastructure.article_pipeline import LinguisticGateway, SemanticGateway


CORPUS = ROOT / "eval" / "article_pipeline_gold"


async def _checkpoint(_result: dict[str, Any]) -> None:
    """Keep this eval in memory: the requested artifact is DSL only."""


def _write_text_atomic(path: Path, text: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _ensure_case_output_writable(cases: list[dict[str, Any]]) -> None:
    """Fail before paid inference if any selected case cannot save its artifacts."""
    for case in cases:
        case_dir = CORPUS / case["path"]
        probe = case_dir / f".article-pipeline-write-check-{uuid4().hex}.tmp"
        probe_created = False
        try:
            _write_text_atomic(probe, "# temporary DSL output-write check\n")
            probe_created = True
        except OSError as exc:
            raise ValidationError(
                f"Cannot write DSL artifacts in '{case_dir}': {exc}. "
                "Run the command from a shell with write access or grant Modify permission."
            ) from exc
        finally:
            if probe_created:
                try:
                    probe.unlink(missing_ok=True)
                except OSError as exc:
                    raise ValidationError(
                        f"Cannot remove DSL output-write check '{probe}': {exc}"
                    ) from exc


def _run_artifact_path(case_dir: Path, prefix: str) -> Path:
    """Return a collision-free artifact path without replacing earlier runs."""
    base = f"{prefix}-v{PROMPT_VERSION}"
    candidate = case_dir / f"{base}.dsl"
    suffix = 2
    while candidate.exists():
        candidate = case_dir / f"{base}-{suffix}.dsl"
        suffix += 1
    return candidate


def _serialize_value(value: Any, kind: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if kind in ("refs", "strs"):
        require(isinstance(value, list), f"Expected list value, got {value!r}")
        return "[" + ",".join(str(item) for item in value) + "]"
    return str(value)


def _serialize_dsl(blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    tag_by_instance = {
        block["instanceId"]: block["data"]["tag"]
        for block in blocks if block.get("instanceId")
    }
    for block in blocks:
        block_type = block["blockType"]
        data = block["data"]
        field_specs = DSL_FIELDS[block_type]
        extra = data.get("_extra") or {}
        require(not extra, f"{block_type}/{data.get('tag')} has unknown DSL fields: {sorted(extra)}")
        code = KEY_TO_LEGACY_INT[block_type]
        segments = [f"B T{code} {data['tag']}"]
        for dsl_key, spec in field_specs.items():
            value = data.get(spec.json_field)
            if value is None or value == "" or value == []:
                continue
            if spec.json_field == "subjectStatementRef":
                require(value in tag_by_instance,
                        f"{data['tag']} has an unresolved subref= UUID")
                value = tag_by_instance[value]
            rendered = escape_dsl_value(_serialize_value(value, spec.kind))
            require("\x00" not in rendered, f"{data['tag']} contains an unrepresentable NUL value")
            segments.append(f"{dsl_key}={rendered}")
        segments.append(f"unit={data['unit']}")
        lines.append(" | ".join(segments))
    return "\n".join(lines) + "\n"


def _error_lines(case: dict[str, Any], result: dict[str, Any] | None, detail: str,
                 rejected_dsl: tuple[str, ...] | list[str] = ()) -> str:
    lines = [f"# ERROR case={case['pmc_id']} detail={' '.join(detail.split())}"]
    if result:
        coverage = result.get("coverage", {})
        missing = coverage.get("uncovered_sentence_ids", [])
        captions = coverage.get("uncovered_caption_unit_ids", [])
        if missing:
            lines.append(f"# COVERAGE case={case['pmc_id']} missing_units={','.join(missing)}")
        if captions:
            lines.append(f"# CAPTION_COVERAGE case={case['pmc_id']} missing_units={','.join(captions)}")
    for attempt, rejected in enumerate(rejected_dsl, 1):
        lines.append(f"# REJECTED_DSL attempt={attempt}")
        lines.extend("# " + row for row in rejected.splitlines())
    return "\n".join(lines) + "\n"


def _warnings_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for step in result.get("model_steps", []):
        for finding in step.get("warnings", []):
            if isinstance(finding, dict) and finding.get("severity") == "warning":
                warnings.append(finding)
    return warnings


def _warning_lines(case: dict[str, Any], result: dict[str, Any]) -> str:
    """Serialize advisory findings as DSL comments, never as JSON output."""
    return render_warning_report(
        case["pmc_id"], PROMPT_VERSION, _warnings_from_result(result),
    )


async def _run_case(case: dict[str, Any], batch_sentences: int | None) -> dict[str, Any]:
    started = time.perf_counter()
    pmc_id = case["pmc_id"]
    case_dir = CORPUS / case["path"]
    article = (case_dir / "article.md").read_text(encoding="utf-8")
    mode = "whole_article" if batch_sentences is None else f"batches_of_{batch_sentences}"
    print(f"START case={pmc_id} source_chars={len(article)} mode={mode}", flush=True)
    def _first_token(seconds: float) -> None:
        print(f"STREAM case={pmc_id} event=first_token seconds={seconds}", flush=True)

    pipeline = ArticlePipeline(
        LinguisticGateway(),
        SemanticGateway(on_first_token=_first_token),
        batch_sentences=batch_sentences,
    )
    result = await pipeline.run(
        f"live-eval-{pmc_id}", article, _checkpoint,
    )
    success = result.get("success") is True
    warnings = _warnings_from_result(result)
    if warnings:
        warnings_path = _run_artifact_path(case_dir, "run-warning")
        _write_text_atomic(warnings_path, _warning_lines(case, result))
        print(f"DSL_WARNINGS case={pmc_id} path={warnings_path}", flush=True)
    if result.get("blocks") and result.get("linguistic_profile") and result.get("source"):
        dsl = _serialize_dsl(result["blocks"])
        unit_ids = [f"S{i + 1}" for i in range(len(result["linguistic_profile"]["sentences"]))]
        parsed = parse_dsl_rows(dsl, unit_ids)
        require(len(parsed) == len(result["blocks"]), f"{pmc_id}: DSL roundtrip row count mismatch")
        output_path = _run_artifact_path(case_dir, "run")
        _write_text_atomic(output_path, dsl)
        print(f"DSL_OUTPUT case={pmc_id} path={output_path}", flush=True)
    else:
        parsed = []
    retries = sum(step.get("retries", 0) for step in result.get("model_steps", []))
    uncovered = len(result.get("coverage", {}).get("uncovered_sentence_ids", []))
    if not success:
        errors_path = _run_artifact_path(case_dir, "run-error")
        _write_text_atomic(errors_path, _error_lines(case, result, result.get("error", "pipeline failed")))
        print(f"DSL_ERRORS case={pmc_id} path={errors_path}", flush=True)
    return {"success": success, "rows": len(parsed), "retries": retries,
            "uncovered": uncovered, "warnings": len(warnings),
            "elapsed": round(time.perf_counter() - started, 3),
            "error": result.get("error", "") if not success else ""}


async def _main(batch_sentences: int | None, limit: int,
                case_ids: list[str] | None = None,
                preflight_only: bool = False) -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    all_cases = manifest.get("cases", [])
    require(manifest.get("article_count") == 20 and len(all_cases) == 20,
            "article_pipeline_gold must contain exactly 20 cases")
    require(1 <= limit <= 20, "--limit must be between 1 and 20")
    if case_ids:
        require(len(case_ids) == len(set(case_ids)), "--case values must be unique")
        cases_by_id = {case["pmc_id"]: case for case in all_cases}
        unknown_cases = [case_id for case_id in case_ids if case_id not in cases_by_id]
        require(not unknown_cases, "unknown --case ids: " + ", ".join(unknown_cases))
        requested_cases = set(case_ids)
        cases = [case for case in all_cases if case["pmc_id"] in requested_cases]
    else:
        cases = all_cases[:limit]

    _ensure_case_output_writable(cases)
    if preflight_only:
        for case in cases:
            print(f"WRITE_PREFLIGHT=PASS case={case['pmc_id']} "
                  f"directory={CORPUS / case['path']}", flush=True)
        return

    profile = model_registry.profile(resolve_model_profile("article_extraction"))
    model_name = profile.profile_name
    provider_kind = profile.provider.kind
    mode = "whole_article" if batch_sentences is None else f"batches_of_{batch_sentences}"
    print(f"MODEL_PROFILE={model_name} PROVIDER={provider_kind} "
          f"MODEL={profile.profile.model_id} REASONING={profile.profile.reasoning_effort} "
          f"MODE={mode} PROMPT_VERSION={PROMPT_VERSION}", flush=True)

    total_rows = total_retries = total_uncovered = total_warnings = 0
    failed_cases: list[str] = []
    for case in cases:
        try:
            report = await _run_case(case, batch_sentences)
        except Exception as exc:  # noqa: BLE001 - report one case and continue corpus eval
            failed_cases.append(case["pmc_id"])
            error = f"{type(exc).__name__}: {' '.join(str(exc).split())}"
            rejected_dsl = getattr(exc, "rejected_dsl", ())
            errors_path = _run_artifact_path(CORPUS / case["path"], "run-error")
            report_saved = False
            try:
                _write_text_atomic(errors_path, _error_lines(case, None, error, rejected_dsl))
                report_saved = True
                print(f"DSL_ERRORS case={case['pmc_id']} path={errors_path}", flush=True)
            except OSError as write_error:
                print(f"DSL_ERROR_PERSIST_FAILED case={case['pmc_id']} "
                      f"path={errors_path} error_type={type(write_error).__name__}",
                      flush=True)
            report_status = errors_path.name if report_saved else "not_saved"
            print(f"FAIL {case['pmc_id']} error_type={type(exc).__name__} "
                  f"report={report_status}", flush=True)
            continue
        total_rows += report["rows"]
        total_retries += report["retries"]
        total_uncovered += report["uncovered"]
        total_warnings += report["warnings"]
        if not report["success"]:
            failed_cases.append(case["pmc_id"])
            print(f"FAIL {case['pmc_id']} {report['error']}", flush=True)
            continue
        print(f"PASS {case['pmc_id']} DSL_ROWS={report['rows']} WARNINGS={report['warnings']} "
              f"RETRIES={report['retries']} "
              f"UNCOVERED={report['uncovered']} ELAPSED_SECONDS={report['elapsed']}", flush=True)
    status = "PASS" if not failed_cases else "FAIL"
    print(f"{status} ARTICLE_PIPELINE_LIVE CASES={len(cases)} FAILED={len(failed_cases)} "
          f"DSL_ROWS={total_rows} RETRIES={total_retries} UNCOVERED={total_uncovered} "
          f"WARNINGS={total_warnings} "
          f"OUTPUT={CORPUS / 'cases'}", flush=True)
    if failed_cases:
        raise ValidationError("failed cases: " + ", ".join(failed_cases))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=None,
                        help="Source sentences per request for local profiles; OpenAI Responses always receives the whole article")
    parser.add_argument("--limit", type=int, default=2,
                        help="Leading manifest cases to run; default: 2")
    parser.add_argument("--case", action="append", dest="case_ids",
                        help="Run only this manifest PMC case; repeat for multiple cases")
    parser.add_argument("--preflight-only", action="store_true",
                        help="Check artifact write access for selected cases without calling the model")
    args = parser.parse_args()
    if args.batch is not None:
        require(args.batch > 0, "--batch must be positive")
    extraction_profile = model_registry.profile(resolve_model_profile("article_extraction"))
    is_responses_provider = extraction_profile.provider.kind == "openai_responses"
    if is_responses_provider and args.batch is not None:
        parser.error("--batch is not supported for OpenAI Responses profiles; the whole article is sent in one call")
    batch_sentences = None if is_responses_provider else (args.batch or 50)
    try:
        asyncio.run(_main(batch_sentences, args.limit, args.case_ids, args.preflight_only))
    except (ValidationError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"FAIL ARTICLE_PIPELINE_LIVE {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
