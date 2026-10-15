"""Адресная подготовка контрольных входов шести утверждённых карт; без генерации и публикации карт."""
from __future__ import annotations
import argparse
import ctypes
import json
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))
from domain.article_maps import require, parse_json_response, fingerprint
from domain.research_semantics import source_span
from infrastructure.immutable_files import write_immutable
from tools.import_codex_article_map import prohibit_generation
from tools.run_schema6_prediction import common_owner


def main():
    parser = argparse.ArgumentParser()
    for name in ("references", "metadata", "manual", "seed", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    require(bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required")
    prohibit_generation()
    from infrastructure.config import settings
    from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
    refs = parse_json_response(args.references.read_text(encoding="utf-8"))
    manual = parse_json_response(args.manual.read_text(encoding="utf-8"))
    seed = parse_json_response(args.seed.read_text(encoding="utf-8"))
    metadata = parse_json_response(args.metadata.read_text(encoding="utf-8"))
    repo = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    try:
        owner = common_owner(repo, refs)
        maps = {r["article_id"]: repo.get(r["article_id"], r["pipeline_id"], owner, r["run_id"]) for r in refs}
        by_pmc = {m["article_id"].split("-")[2].upper(): m for m in maps.values()}
        require(set(by_pmc) == {"PMC10000452", "PMC5436834", "PMC6416157", "PMC7789349", "PMC8775386", "PMC8918697"}, "Pilot corpus differs")
        registry, annotations, controls = {}, {}, {"version": seed["version"], "author": "Codex", "expert_validated": False, "pairs": []}
        for pmc, m in by_pmc.items():
            publication = next(row for row in metadata if row["pmcid"] == pmc)
            registry[m["article_id"]] = {"article_id": m["article_id"], "run_id": m["run_id"], "source_sha256": m["source"]["sha256"],
                "available_on": publication["firstPublicationDate"], "metadata_source": publication["url"], "title": publication["title"],
                "document_type": "primary_cross_sectional" if pmc == "PMC8775386" else "primary_longitudinal_methodology" if pmc == "PMC10000452" else "review",
                "family": "cretan-aging-cohort" if pmc in {"PMC10000452", "PMC8775386"} else None,
                "presentation": "unknown" if pmc in {"PMC10000452", "PMC8775386"} else "review"}
            annotations[m["article_id"]] = {"run_id": m["run_id"], "source_sha256": m["source"]["sha256"], "graph_sha256": fingerprint(m["graph"]),
                "author": "Codex", "expert_validated": False, "kind": "supplementary_control_atoms", "replaces": [], "claims": []}
        for pair in seed["pairs"]:
            original = next(p for p in manual["pairs"] if p["id"] == pair["id"])
            row = {k: pair[k] for k in ("id", "expected_relations", "note_ru")}
            row["citation"] = original["direct_citation_to_this_source_at_target_fragment"]
            for endpoint, fragments_key in (("left", "target_fragments"), ("right", "source_fragments")):
                fragments = original[fragments_key]
                require(len({f["article_id"] for f in fragments}) == 1, "Control spans mix articles")
                m = by_pmc[fragments[0]["article_id"].upper()]
                require(all(f["source_sha256"] == m["source"]["sha256"] for f in fragments), "Control source hash differs")
                spans = [source_span(m["source"], f["start"], f["end"], f["text"]) for f in fragments]
                ids = []
                for i, definition in enumerate(pair[endpoint], 1):
                    claim_id = pair["id"] + ("L" if endpoint == "left" else "R") + str(i)
                    annotations[m["article_id"]]["claims"].append({**definition, "claim_id": claim_id, "spans": spans,
                        "text": definition["predicate"] + ": " + "; ".join(f"{r}={v}" for r, v in definition["roles"].items())})
                    ids.append(claim_id)
                row[endpoint] = {"article_id": m["article_id"], "claim_ids": ids}
            controls["pairs"].append(row)
        # Трудные реальные контроли. Источники сохраняются дословно, включая ошибку единицы в утверждённой цели.
        cv = lambda v: {"status": "known", "value": v} if v else {"status": "not_applicable", "value": None}
        cases = [
            ("H01", "PMC10000452", "K5", "PMC6416157", "K19", "mci incidence", {"subject": "MCI", "group": "ages 75–79"},
             [{"name": "incidence", "value": 22.5, "unit": "%"}], [{"name": "incidence", "value": 22.5, "unit": "per 1000 person-years"}],
             {"time": cv(None)}, {"time": cv(None)}, "unit_mismatch", "22,5% в цели против 22,5 на 1000 человеко-лет в источнике. Утверждённая карта не исправлена молча."),
            ("H02", "PMC10000452", "K33", "PMC8775386", "K19", "record duration", {"subject": "CAC actigraphy recording"},
             [{"name": "duration", "value": 7, "unit": "day"}], [{"name": "duration", "value": 3, "unit": "day"}],
             {"phase": cv("phase iii")}, {"phase": cv("phase ii")}, "context_mismatch", "Семидневная Phase III и трёхдневная Phase II — разные выполненные процедуры."),
            ("H03", "PMC10000452", "K29", "PMC8775386", "K13", "sample size", {"subject": "CAC analytic sample"},
             [{"name": "n", "value": 151, "unit": "person"}], [{"name": "n", "value": 117, "unit": "person"}],
             {"phase": cv("phase iii"), "sample": cv("longitudinal 151")}, {"phase": cv("phase ii"), "sample": cv("cross sectional 117")},
             "context_mismatch", "Разные аналитические выборки одной когорты нельзя объединять или считать независимыми повторениями."),
            ("H04", "PMC10000452", "K24", "PMC8775386", "K12", "selection criterion", {"subject": "CAC phase II control group"},
             [{"name": "MMSE comparator", "value": ">=24", "unit": None}], [{"name": "MMSE comparator", "value": ">24", "unit": None}],
             {"phase": cv("phase ii")}, {"phase": cv("phase ii")}, "partial", "Порог >=24 отличается от >24. Совпадение размеров группы не разрешает устранить различие критерия."),
        ]
        for ident, lpmc, lk, rpmc, rk, predicate, roles, lm, rm, lc, rc, expected, note in cases:
            row = {"id": ident, "expected_relations": [expected], "note_ru": note, "citation": False}
            for end, pmc, kid, measurements, context in (("left", lpmc, lk, lm, lc), ("right", rpmc, rk, rm, rc)):
                m = by_pmc[pmc]; k = next(k for k in m["graph"]["knowledge"] if k["knowledge_id"] == kid)
                units = {u["id"]: u for u in m["source"]["units"]}
                spans = [source_span(m["source"], units[u]["start"], units[u]["end"]) for u in k["provenance"]["unit_ids"]]
                claim_id = ident + ("L" if end == "left" else "R")
                annotations[m["article_id"]]["claims"].append({"claim_id": claim_id, "knowledge_id": kid, "predicate": predicate,
                    "roles": roles, "measurements": measurements, "context": context, "negated": False, "spans": spans, "text": k["display_text"]})
                row[end] = {"article_id": m["article_id"], "claim_ids": [claim_id]}
            controls["pairs"].append(row)
        question = {"question_id": "baseline-il6-later-cognitive-decline-1",
            "text_en": "Is elevated baseline IL-6 associated with subsequent cognitive decline in older adults without dementia?",
            "text_ru": "Связан ли повышенный исходный IL-6 с последующим когнитивным снижением у пожилых людей без деменции?",
            "predicate": "associated with", "roles": {"exposure": "elevated baseline IL-6", "outcome": "subsequent cognitive decline"},
            "context": {"species": cv("human"), "population": cv("older adults without dementia"), "design": cv("longitudinal")},
            "cutoff": "2022-12-31", "horizon_end": "2025-12-31", "limit": 20}
        source_refs = [r for r in refs if r["article_id"] != by_pmc["PMC10000452"]["article_id"]]
        source_ids = {r["article_id"] for r in source_refs}
        audit = {"references": refs, "registry": registry, "annotations": annotations, "controls": controls}
        sources = {"references": source_refs, "registry": {k: v for k, v in registry.items() if k in source_ids},
                   "annotations": {k: v for k, v in annotations.items() if k in source_ids}, "episodes": [], "question": question}
        args.output.mkdir(parents=True, exist_ok=True)
        for name, value in (("audit.manifest.json", audit), ("sources.manifest.json", sources), ("publication-metadata.json", metadata), ("control-seed.json", seed)):
            path = args.output / name; encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
            write_immutable(path, encoded)
        print(json.dumps({"prepared": True, "sources": len(source_refs), "controls": len(controls["pairs"]), "annotated_claims": sum(len(a["claims"]) for a in annotations.values()),
                          "target_in_training": False, "model_calls": 0}))
    finally: repo.close()


if __name__ == "__main__": main()
