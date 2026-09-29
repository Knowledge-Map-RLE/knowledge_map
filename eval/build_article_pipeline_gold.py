"""Create the manually curated DSL gold corpus from Neo4j full-text snapshots.

The only database operations are ``MATCH`` reads.  Each case stores the
immutable full Markdown article and one human-authored evaluation unit; it does
not claim a complete manual semantic decomposition of the whole article.

Run from ``api`` with Poetry:
    poetry run python ../eval/build_article_pipeline_gold.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "api"
sys.path.insert(0, str(API))

from neo4j import GraphDatabase  # noqa: E402

from infrastructure.config import settings  # noqa: E402
from infrastructure.s3.s3_storage import get_s3_client  # noqa: E402


GOLD_ROOT = ROOT / "eval" / "article_pipeline_gold"

# These are human-authored DSL reference statements.  ``source_unit`` is an
# exact sentence from the source article, not model output.  The annotations
# deliberately exercise quantities, modality, methods, comparisons and limits.
MANUAL_CASES = (
    ("PMC10000452", "In total, 151 individuals completed the Phase III evaluation.", "B T4 B1 | sub=Phase III evaluation | pred=included | obj=151 individuals | unit=S1"),
    ("PMC10000584", "Various studies have substantiated the chances of obesity inducing accelerated aging.", "B T4 B1 | sub=obesity | pred=may induce | obj=accelerated aging | epi=author_interpretation | unit=S1"),
    ("PMC10000897", "This study evaluated the effects of hanging the carcass by the Achilles tendon (AS) versus pelvic suspension (PS) on meat quality traits.", "B T4 B1 | sub=carcass suspension | pred=was evaluated for | obj=meat quality traits | unit=S1"),
    ("PMC10000969", "Mitochondrial dysfunction is a well-established phenomenon in the pathophysiology of many neurological diseases, including Alzheimer’s disease (AD).", "B T4 B1 | sub=mitochondrial dysfunction | pred=is associated with | obj=Alzheimer disease pathophysiology | unit=S1"),
    ("PMC10001272", "Using a large sample of 15 countries over 1950–2019, we show that LC-E and LC-G, as well as their multi-population counterparts, can consistently improve the forecasting accuracy of the competing LC and Li–Lee models in both single- and multi-population scenarios.", "B T4 B1 | sub=LC-E and LC-G | pred=can improve | obj=forecasting accuracy | epi=author_interpretation | unit=S1"),
    ("PMC10001331", "The sample comprised 15 informal caregivers who provided intensive care for patients with chronic respiratory failure for more than six months.", "B T4 B1 | sub=study sample | pred=comprised | obj=15 informal caregivers | unit=S1"),
    ("PMC10001353", "Advanced aging is caused by a combination of factors: lifestyle, diet, external and internal factors, as well as oxidative stress (OS).", "B T4 B1 | sub=oxidative stress | pred=contributes to | obj=advanced aging | unit=S1"),
    ("PMC10001413", "These novel iron chelators exhibit neuroprotective activities by attenuating relevant neurodegenerative pathology, promoting positive behavior changes, and up-regulating neuroprotective signaling pathways.", "B T4 B1 | sub=novel iron chelators | pred=exhibit | obj=neuroprotective activities | unit=S1"),
    ("PMC10001821", "This longitudinal mixed-methods study, carried out in 2021 in Italy and the Netherlands, enrolled 62 individuals.", "B T4 B1 | sub=longitudinal mixed-methods study | pred=enrolled | obj=62 individuals | unit=S1"),
    ("PMC10001833", "However, the evidence from human studies has been limited.", "B T4 B1 | sub=evidence from human studies | pred=was | obj=limited | epi=limitation | unit=S1"),
    ("PMC10001974", "Data on 7040 adults aged ≥50 were acquired from a COVID-19 sub-study of the English Longitudinal Study of Ageing (ELSA).", "B T4 B1 | sub=COVID-19 ELSA sub-study | pred=included | obj=7040 adults aged 50 years or older | unit=S1"),
    ("PMC10002395", "BFA was naturally aged into BFA-Natural aging (BFA-N) in the soil environment of southern China, and to simulate BFA-N, BFA was also artificially acid aged into BFA-Acid aging (BFA-A).", "B T4 B1 | sub=BFA | pred=was naturally aged into | obj=BFA-N | unit=S1"),
    ("PMC10002471", "Using multivariate Scaled Subprofile Model (SSM) analysis, we sought to identify a network pattern in structural neuroimaging reflecting the regionally distributed association of plasma Hcy with subcortical gray matter (SGM) volumes and its relation to other health risk factors and cognition in 160 healthy older adults, ages 50–89.", "B T4 B1 | sub=SSM analysis | pred=examined | obj=160 healthy older adults | unit=S1"),
    ("PMC10002495", "Whole-brain iron increased with age and voxel-wise QSM indicated higher susceptibility with age in various brain areas including the basal ganglia.", "B T4 B1 | sub=whole-brain iron | pred=increased with | obj=age | unit=S1"),
    ("PMC10002543", "The HA matrix was isolated and purified from rooster comb and characterised physicochemically and molecularly.", "B T4 B1 | sub=HA matrix | pred=was isolated from | obj=rooster comb | unit=S1"),
    ("PMC10002641", "In one strain, offspring of young mothers lived 20% longer than offspring of old mothers, whereas there were no significant effects of maternal age on lifespan for the other strains.", "B T4 B1 | sub=offspring of young mothers | pred=lived 20 percent longer than | obj=offspring of old mothers | unit=S1"),
    ("PMC10002668", "We generated single-cell transcriptomic atlases across the lifespan of Caenorhabditis elegans under different pro-longevity conditions (http://mengwanglab.org/atlas).", "B T4 B1 | sub=single-cell transcriptomic atlases | pred=were generated for | obj=Caenorhabditis elegans lifespan | unit=S1"),
    ("PMC10002830", "Higher ER density was generally associated with lower gray matter volume and blood flow, and with higher mitochondria ATP production, possibly reflecting compensatory mechanisms.", "B T4 B1 | sub=higher ER density | pred=was associated with | obj=lower gray matter volume | epi=author_interpretation | unit=S1"),
    ("PMC10002864", "Aging is associated with significant modifications in immune system cells, toward a decline in immunosurveillance, which, in turn, leads to chronic elevation of inflammation/oxidative stress, increasing the risk of (co)morbidities.", "B T4 B1 | sub=aging | pred=is associated with | obj=immune system cell modifications | unit=S1"),
    ("PMC10002910", "The recent tendency to delay pregnancy has increased the incidence of age-related infertility, as female reproductive competence decreases with aging.", "B T4 B1 | sub=female reproductive competence | pred=decreases with | obj=aging | unit=S1"),
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_case_dir(pmc_id: str) -> Path:
    if not pmc_id.startswith("PMC") or not pmc_id[3:].isdigit():
        raise ValueError(f"Unsafe PMCID: {pmc_id}")
    return GOLD_ROOT / "cases" / pmc_id.lower()


async def _download_text(key: str) -> str:
    text = await get_s3_client().download_text(settings.S3_BUCKET_NAME, key)
    if not text or not text.strip():
        raise RuntimeError(f"S3 object is empty or unavailable: {key}")
    return text


async def main() -> None:
    GOLD_ROOT.mkdir(parents=True, exist_ok=True)
    case_ids = [case[0] for case in MANUAL_CASES]
    if len(case_ids) != 20 or len(set(case_ids)) != len(case_ids):
        raise RuntimeError("The gold corpus must contain exactly 20 unique PMCIDs")
    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    try:
        records = driver.execute_query(
            "MATCH (d:Document) WHERE d.pmc_id IN $ids "
            "RETURN d.pmc_id AS pmc_id, d.uid AS uid, d.title AS title, "
            "d.user_md_s3_key AS user_key, d.formatted_md_s3_key AS formatted_key, "
            "d.docling_raw_md_s3_key AS raw_key, d.doi AS doi",
            ids=case_ids,
            database_="neo4j",
        ).records
    finally:
        driver.close()
    by_pmc = {record["pmc_id"]: record.data() for record in records}
    missing = sorted(set(case_ids) - set(by_pmc))
    if missing:
        raise RuntimeError(f"Missing Neo4j documents: {', '.join(missing)}")

    prepared_cases = []
    for pmc_id, quote, dsl in MANUAL_CASES:
        record = by_pmc[pmc_id]
        key = record["user_key"] or record["formatted_key"] or record["raw_key"]
        if not key:
            raise RuntimeError(f"{pmc_id} has no Markdown S3 key")
        article = await _download_text(key)
        start = article.find(quote)
        if start < 0:
            raise RuntimeError(f"Manual source unit was not found verbatim in {pmc_id}: {quote[:100]!r}")
        end = start + len(quote)
        meta = {
            "schema_version": 1,
            "pmc_id": pmc_id,
            "document_uid": record["uid"],
            "article_title": record["title"],
            "doi": record["doi"] or "",
            "source": {"system": "neo4j+s3", "bucket": settings.S3_BUCKET_NAME, "key": key},
            "article_sha256": _sha256(article),
            "annotation_scope": "manual_evaluation_slice",
            "annotator": "Codex (manual, no LLM)",
            "needs_expert_review": True,
        }
        gold = {
            "schema_version": 1,
            "pipeline": "article_to_slg_to_dsl_to_knowledge_map",
            "dsl_format": "B T4 Bn | sub=... | pred=... | obj=... | unit=S<n>",
            "source_units": [{"id": "S1", "start": start, "end": end, "text": quote}],
            "dsl": dsl,
            "expected": {
                "assertion_count": 1,
                "minimum_concept_count": 2,
                "minimum_structural_row_count": 3,
                "minimum_knowledge_map_node_count": 3,
                "provenance_required": True,
                "semantic_fidelity": "requires_expert_review",
            },
        }
        prepared_cases.append((pmc_id, article, meta, gold, record["title"]))

    manifest_cases = []
    for pmc_id, article, meta, gold, title in prepared_cases:
        case_dir = _safe_case_dir(pmc_id)
        if case_dir.exists():
            raise RuntimeError(f"Refusing to overwrite existing manual case: {case_dir}")
        case_dir.mkdir(parents=True)
        (case_dir / "article.md").write_text(article, encoding="utf-8")
        (case_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (case_dir / "gold.json").write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_cases.append({"pmc_id": pmc_id, "path": f"cases/{pmc_id.lower()}", "title": title})
        print(f"created {pmc_id}: {len(article)} characters")

    manifest = {
        "schema_version": 1,
        "pipeline": "article_to_slg_to_dsl_to_knowledge_map",
        "article_count": len(manifest_cases),
        "annotation_scope": "one manually curated source unit per full-text article",
        "cases": manifest_cases,
    }
    (GOLD_ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
