"""Сериализация ручной формализации Codex в проверяемый пакет; моделей здесь нет."""
from __future__ import annotations

import argparse
import ctypes
import json
import shutil
import sys
from hashlib import sha256
from pathlib import Path
from uuid import UUID

API = Path(__file__).resolve().parents[1]
ROOT = API.parent
sys.path.insert(0, str(API))
from application.text_to_development_map import (prompt_binding, extraction_input, dependency_input,
    PROMPT_PATH, DEPENDENCY_PROMPT_PATH, DEPENDENCY_BATCH_SIZE)
from application.publish_article_map import russian_translation
from domain.article_maps import prepare_source, require, digest
from domain.knowledge_development import (validate_development_map, initialize_occurrences,
    apply_development_review, model_contract)
from infrastructure.article_map_offline import render_article_map
from tools.import_codex_article_map import VERIFIED_SOURCES, load_bundle, prohibit_generation


def prepare(case, authored_file, run_id):
    prohibit_generation()
    article_id, source_sha = VERIFIED_SOURCES[case.upper()]
    require(str(UUID(run_id)) == run_id, "Invalid run id")
    gold = ROOT / "eval/article_pipeline_gold/cases" / case.lower()
    folder = gold / "runs" / run_id
    require(not folder.exists(), "An immutable bundle already exists; choose a new run id")
    authored = json.loads(authored_file.read_text(encoding="utf-8"))
    text = (gold / "article.md").read_bytes().decode("utf-8")
    require(digest(text) == source_sha, "Verified source changed")
    source = prepare_source(article_id, text)
    aliases = authored.get("concept_aliases", {})
    keys = {k["key"]: f"K{i+1}" for i, k in enumerate(authored["knowledge"])}
    require(len(keys) == len(authored["knowledge"]), "Duplicate authored key")
    concepts = {}

    def roles(values, uids):
        output = []
        for role, name in values.items():
            if name.startswith("@"):
                output.append({"role": role, "concept_id": None, "knowledge_id": keys[name[1:]]})
            else:
                if name not in concepts:
                    concepts[name] = {"id": f"C{len(concepts)+1}", "display_text": name,
                                      "aliases": aliases.get(name, []), "provenance": {"unit_ids": []}}
                c = concepts[name]
                c["provenance"]["unit_ids"] = list(dict.fromkeys(c["provenance"]["unit_ids"] + uids))
                output.append({"role": role, "concept_id": c["id"], "knowledge_id": None})
        return output

    knowledge = []
    for entry in authored["knowledge"]:
        kid = keys[entry["key"]]
        uids = [f"U{u}" for u in entry["units"]]
        statements = []
        for i, claim in enumerate(entry.get("claims", [{}])):
            claim_units = [f"U{u}" for u in claim.get("units", entry["units"])]
            attributes = entry.get("attrs", {}) | claim.get("attrs", {})
            attrs = []
            for name, value in attributes.items():
                attrs.append({"name": name, "value": value["value"] if isinstance(value, dict) else value,
                              "unit": value.get("unit") if isinstance(value, dict) else None})
            statements.append({"statement_id": f"{kid}S{i+1}", "predicate": claim.get("predicate", entry["predicate"]),
                "roles": roles(entry["roles"] | claim.get("roles", {}), claim_units),
                "quantifier": claim.get("quantifier", entry.get("quantifier")),
                "modality": claim.get("modality", entry.get("modality")),
                "negated": claim.get("negated", entry.get("negated", False)),
                "conditions": list(dict.fromkeys(entry.get("conditions", []) + claim.get("conditions", []))),
                "temporal_context": claim.get("time", entry.get("time")),
                "qualifiers": {"attributes": attrs}, "provenance": {"unit_ids": claim_units}})
        kind = entry.get("kind", "state")
        knowledge.append({"knowledge_id": kid, "kind": kind,
            "knowledge_kind": entry.get("type", "operation" if kind == "action" else "observation"),
            "display_text": entry["en"], "aliases": entry.get("aliases", []),
            "action_status": entry.get("status", "performed") if kind == "action" else None,
            "grounding": entry.get("grounding", "source_explicit"),
            "semantic_frame": {"logic": entry.get("logic", "single"), "statements": statements},
            "provenance": {"unit_ids": uids}})
    extraction = {"schema_version": 6, "concepts": list(concepts.values()), "knowledge": knowledge,
                  "nodes": [], "edges": [], "transitions": []}
    graph = initialize_occurrences(validate_development_map(extraction, source, extraction=True), source)
    occurrences = {n["knowledge_id"]: n["id"] for n in graph["nodes"]}
    transitions = [{"id": f"T{i+1}", "sources": [occurrences[keys[k]] for k in t["sources"]],
        "target": occurrences[keys[t["target"]]], "usage": t["usage"], "reason": t["reason"],
        "unit_ids": [f"U{u}" for u in t["units"]], "conditions": t.get("conditions", [])}
        for i, t in enumerate(authored["transitions"])]
    coverage = {}
    for unit in source["units"]:
        represented = [k["knowledge_id"] for k in knowledge if unit["id"] in k["provenance"]["unit_ids"]]
        reason = None if represented else authored.get("excluded_units", {}).get(unit["id"])
        require(bool(represented) != bool(reason), f"Missing or inconsistent source coverage: {unit['id']}")
        coverage[unit["id"]] = {"knowledge_ids": represented, "excluded_reason": reason}
    # Все проверки содержания предшествуют созданию нового каталога результата.
    folder.mkdir(parents=True)
    def write(name, value):
        with (folder / name).open("x", encoding="utf-8", newline="\n") as f:
            f.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
    for name in ("article.md", "article.xml"):
        shutil.copyfile(gold / name, folder / name)
    shutil.copyfile(authored_file, folder / "authored.json")
    shutil.copyfile(PROMPT_PATH, folder / "prompt.extraction.en.md")
    shutil.copyfile(DEPENDENCY_PROMPT_PATH, folder / "prompt.dependencies.en.md")
    attachments = authored.get("source_attachments", [])
    if attachments:
        write("source.attachments.json", attachments)
        for attachment in attachments:
            media = Path(attachment["media_file"])
            require(media.name == str(media), "Unsafe media filename")
            shutil.copyfile(authored_file.parent / media, folder / media)
    write("source.json", source)
    prompt, dep_prompt = PROMPT_PATH.read_text(encoding="utf-8"), DEPENDENCY_PROMPT_PATH.read_text(encoding="utf-8")
    write("extraction.request.json", {"system": prompt, "user": extraction_input(article_id, text, source, attachments)})
    write("extraction.response.json", extraction)
    groups, completed = [], []
    for i in range(0, len(knowledge), DEPENDENCY_BATCH_SIZE):
        targets = [k["knowledge_id"] for k in knowledge[i:i + DEPENDENCY_BATCH_SIZE]]
        request, response = f"dependencies.{i//40+1}.request.json", f"dependencies.{i//40+1}.response.json"
        write(request, {"system": dep_prompt, "user": dependency_input(article_id, text, source, graph, targets, completed, prompt, attachments)})
        answer = {"occurrences": [], "transitions": [t for t in transitions if graph["nodes"][int(t["target"][1:])-1]["knowledge_id"] in targets]}
        write(response, answer)
        graph = apply_development_review(json.dumps(answer, ensure_ascii=False), graph, source, target_keys=targets)
        groups.append({"targets": targets, "request": request, "response": response})
        completed.extend(targets)
    graph = validate_development_map(model_contract(graph), source)
    labels = {keys[k["key"]]: k["ru"] for k in authored["knowledge"]}
    write("translation.ru.json", labels)
    write("coverage.json", coverage)
    generation = {"kind": "codex_manual", "author": "Codex", "external_llm_calls": 0, "local_llm_calls": 0,
                  "translation_llm_calls": 0, "embedding_calls": 0, "token_usage": None,
                  "token_usage_note": "Codex session usage is unavailable; no provider usage is fabricated."}
    preview = {"article_id": article_id, "pipeline_id": "text_reified", "run_id": run_id,
               "article_title": source["units"][0]["text"].lstrip("# "),
               "graph_schema_version": 6, "builder_version": "3", "graph": graph, "source": source,
               "source_attachments": attachments, "input_fingerprint": source_sha, **prompt_binding(),
               "generation": generation, "translations": {"ru": russian_translation(graph, labels, run_id, generation)},
               "expert_validated": False, "needs_expert_review": True}
    write("map.json", preview)
    write("map.html", render_article_map(preview))
    write("validation.json", {"contract": "passed", "dag": "passed", "provenance": "passed",
        "coverage_units": len(coverage), "analysis": graph["analysis"], "model_calls": 0,
        "scientific_accuracy": "not_assessed"})
    write("report.ru.md", authored["report_ru"] + f"\n\nЗапуск: {run_id}. SHA-256: {source_sha}.\n"
        f"\nКанонических знаний: {len(knowledge)}; слоёв: {graph['analysis']['depth']}. "
        f"Все {len(coverage)} фрагментов учтены.\n\nМодельные вызовы, включая перевод и эмбеддинги: 0. "
        "Результат имеет авторство Codex и требует экспертной проверки. Техническая валидация не доказывает научную точность.\n")
    manifest = {"pmc_id": case.upper(), "article_id": article_id, "run_id": run_id, "source_sha256": source_sha,
                "prompt_binding": prompt_binding(), "generation": generation, "dependency_groups": groups,
                "files": {p.name: sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}}
    write("manifest.json", manifest)
    load_bundle(folder)
    print(json.dumps({"prepared": str(folder), "run_id": run_id, "analysis": graph["analysis"], "model_calls": 0}), flush=True)
    return folder


if __name__ == "__main__":
    require(bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required by AGENTS.md")
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=[p.lower() for p in VERIFIED_SOURCES])
    parser.add_argument("--authored", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    prepare(args.case, args.authored.resolve(), args.run_id)
