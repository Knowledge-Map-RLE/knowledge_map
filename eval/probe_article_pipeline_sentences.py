"""Probe a few source sentences with the production DSL extraction path.

Run from ``api`` with Poetry::

    poetry run python ../eval/probe_article_pipeline_sentences.py

The probe writes only a versioned, unreviewed DSL candidate. It never touches
``gold.dsl`` or the other 19 articles.
"""
from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Source text can contain scientific Unicode (for example, Greek allele symbols).
# Keep streaming probe output lossless on Windows consoles with a legacy code page.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "shared" / "model_registry"))

from infrastructure.article_pipeline import LinguisticGateway, SemanticGateway  # noqa: E402
from knowledge_contracts.validation import require  # noqa: E402
from knowledge_pipeline.pipeline import (  # noqa: E402
    linguistic_profile,
    source_revision,
    source_units,
)
from knowledge_pipeline.reference_stripping import strip_references_info  # noqa: E402
from knowledge_pipeline.caption_units import caption_unit_ids  # noqa: E402
from knowledge_pipeline.semantic_extraction import (  # noqa: E402
    DslExtractionError,
    _render_repaired_row,
    extract_structural_rows,
)
from knowledge_pipeline.prompts import PROMPT_VERSION  # noqa: E402

CASE_DIR = ROOT / "eval" / "article_pipeline_gold" / "cases" / "pmc10000452"


def next_artifact_path(filename: str) -> Path:
    """Return a non-existing DSL artifact path so prior run evidence is kept."""
    path = CASE_DIR / filename
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    run_number = 2
    while True:
        candidate = CASE_DIR / f"{stem}-run{run_number}{suffix}"
        if not candidate.exists():
            return candidate
        run_number += 1


async def main(start_unit: str, count: int) -> None:
    article = (CASE_DIR / "article.md").read_text(encoding="utf-8")
    source, _ = strip_references_info(article)
    source_document = json.loads((CASE_DIR / "source_units.json").read_text(encoding="utf-8"))
    require(
        hashlib.sha256(source.encode("utf-8")).hexdigest()
        == source_document["source_sha256"],
        "Source-unit snapshot does not match the article",
    )
    units_by_id = {unit["id"]: unit for unit in source_document["source_units"]}
    match = re.fullmatch(r"S([1-9][0-9]*)", start_unit)
    require(bool(match), "--start-unit must use the S<n> format")
    first_number = int(match.group(1))
    unit_ids = tuple(f"S{number}" for number in range(first_number, first_number + count))
    missing_units = [unit_id for unit_id in unit_ids if unit_id not in units_by_id]
    require(not missing_units, "Unknown source units: " + ", ".join(missing_units))
    units = [units_by_id[unit_id] for unit_id in unit_ids]
    for unit in units:
        require(source[unit["start"]:unit["end"]] == unit["text"],
                f"Source span mismatch for {unit['id']}")
        print(f"SOURCE {unit['id']}: {unit['text'].strip()}", flush=True)

    # Match the production pipeline's deterministic semantic gate: the probe
    # must receive NLP dependencies, not only the selected source text/spans.
    source_record = source_revision(source_document["article_id"], source)
    require(source_record["id"] == source_document["source_revision_id"],
            "Source revision snapshot does not match the article")
    print("NLP request=full_article_for_production_dependency_checks", flush=True)
    linguistic_document = await LinguisticGateway()(source)
    profile = linguistic_profile(source_record, linguistic_document)
    profiled_units = {unit["id"]: unit for unit in source_units(profile, source)}
    for unit in units:
        profiled = profiled_units.get(unit["id"])
        require(profiled is not None
                and profiled["start"] == unit["start"]
                and profiled["end"] == unit["end"]
                and profiled["text"] == unit["text"],
                f"Current NLP sentence boundaries differ from snapshot for {unit['id']}")

    def on_first_token(seconds: float) -> None:
        print(f"STREAM event=first_token seconds={seconds}", flush=True)

    try:
        rows, step = await extract_structural_rows(
            SemanticGateway(on_first_token=on_first_token),
            {"source": source,
             "source_units": units,
             "caption_unit_ids": sorted(
                 set(unit_ids).intersection(caption_unit_ids(profile, source))
             ),
             "linguistic_profile": profile},
            list(unit_ids),
        )
    except DslExtractionError as exc:
        report_path = next_artifact_path(
            f"run-error-v{PROMPT_VERSION}-NLP-{unit_ids[0]}-{unit_ids[-1]}.dsl"
        )
        report = [
            f"# RUN_ERROR prompt_version={PROMPT_VERSION} scope=PMC10000452:"
            f"{unit_ids[0]}-{unit_ids[-1]}",
            f"# ERROR: {exc}",
            "# STATUS: no candidate accepted; gold.dsl unchanged.",
        ]
        for attempt, rejected in enumerate(exc.rejected_dsl, start=1):
            report.append(f"# REJECTED_DSL attempt={attempt}")
            report.extend("# " + line for line in rejected.splitlines())
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        print(f"RUN_ERROR output={report_path}", flush=True)
        print("\n".join(report), flush=True)
        raise
    output = "\n".join(_render_repaired_row(row) for row in rows) + "\n"
    path = next_artifact_path(
        f"probe-v{PROMPT_VERSION}-NLP-{unit_ids[0]}-{unit_ids[-1]}.dsl"
    )
    print(f"PROBE model={step['model_call'].get('model', 'configured')} "
          f"rows={len(rows)} retries={step['retries']} output={path}", flush=True)
    print(output, flush=True)
    path.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a focused DSL probe on consecutive units of PMC10000452.")
    parser.add_argument("--start-unit", default="S7", help="First source unit, for example S10")
    parser.add_argument("--count", type=int, default=3, help="Number of consecutive source units")
    args = parser.parse_args()
    require(args.count > 0, "--count must be positive")
    asyncio.run(main(args.start_unit, args.count))
