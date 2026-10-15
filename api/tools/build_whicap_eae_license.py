"""Собирает воспроизводимую лицензию EAE-1 для локального определения WHICAP."""
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.categorical_licenses import VERSION


ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "eval" / "whole_map_forecast" / "primary-cohort-expansion-codex-v1"
ARTICLE_ID = "manly2008-complete"
KNOWLEDGE_IDS = tuple(f"K{number}" for number in range(64, 71))
OUTPUT = CASE / "categorical-licenses-21-whicap-eae-v1.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _class_binding(article_id: str, concept: dict, text_ru: str) -> dict:
    concept_id = concept["id"]
    return {
        "id": f"{article_id}::concept:{concept_id}",
        "local_id": f"concept:{concept_id}",
        "kind": "concept",
        "concept_id": concept_id,
        "text_en": concept["display_text"],
        "text_ru": text_ru,
    }


def _source_evidence(article: dict, knowledge: dict) -> list[dict]:
    source = article["source"]
    units = {unit["id"]: unit for unit in source["units"]}
    required_ids = sorted({
        unit_id
        for statement in knowledge["semantic_frame"]["statements"]
        for unit_id in statement["provenance"]["unit_ids"]
    })
    evidence = []
    for unit_id in required_ids:
        unit = units[unit_id]
        quote = source["text"][unit["start"]:unit["end"]]
        require(unit["end"] <= source["content_end"] and quote == unit["text"],
                "Source evidence coordinates or text changed")
        evidence.append({
            "unit_id": unit_id,
            "start": unit["start"],
            "end": unit["end"],
            "text": quote,
            "sha256": sha256(quote.encode("utf-8")).hexdigest(),
        })
    return evidence


def _make_entry(article: dict, knowledge: dict, concepts: dict, scope: dict) -> dict:
    article_id = article["article_id"]
    knowledge_id = knowledge["knowledge_id"]
    statements = knowledge["semantic_frame"]["statements"]

    if knowledge_id == "K64":
        licensed_statement = "K64S4"
        license_kind = "explicit_class_disjointness"
        form = "E"
        subject_concept = concepts["C72"]
        object_concept = concepts["C76"]
        subject_ru = "MCI в классификации WHICAP"
        object_ru = "Участники с диагнозом деменции на том же согласительном визите"
        reason = "Статья прямо исключает диагноз деменции на том же WHICAP-консенсусном визите при классификации MCI."
        scope_reason = "Локальное операционное определение WHICAP для каждой согласительной оценки; перенос на другие системы диагностики не предполагается."
    else:
        require(knowledge_id in {f"K{number}" for number in range(65, 71)},
                "Unexpected WHICAP knowledge selected for licensing")
        licensed_statement = knowledge_id + "S1"
        license_kind = "subtype_inclusion"
        form = "A"
        native_statement = next(statement for statement in statements
                                if statement["statement_id"] == licensed_statement)
        roles = {role["role"]: role.get("concept_id") for role in native_statement["roles"]}
        subject_concept = concepts[roles["subtype"]]
        object_concept = concepts[roles["class"]]
        subject_ru = "Подтип MCI в классификации WHICAP: " + subject_concept["display_text"]
        object_ru = "MCI в классификации WHICAP"
        reason = "Явное включение подтипа в локальную классификацию WHICAP лицензируется без переноса на иные когорты или диагностические схемы."
        scope_reason = "Подтип и его общий класс относятся только к WHICAP и к той же согласительной оценке, что и исходное определение MCI."

    subject = _class_binding(article_id, subject_concept, subject_ru)
    object_ = _class_binding(article_id, object_concept, object_ru)
    clause = {
        "form": form,
        "subject": subject["id"],
        "object": object_["id"],
        "scope": deepcopy(scope),
    }
    annotations = []
    for statement in statements:
        if statement["statement_id"] == licensed_statement:
            annotations.append({
                "statement_id": statement["statement_id"],
                "decision": "license_definition",
                "license_kind": license_kind,
                "reason_ru": reason,
                "bindings": {"subject": subject, "object": object_},
                "clause": deepcopy(clause),
            })
        else:
            annotations.append({
                "statement_id": statement["statement_id"],
                "decision": "retain_unconverted",
                "reason_ru": "Остальная часть составного знания сохраняется без категорической проекции.",
                "clause": None,
            })

    return {
        "article_id": article_id,
        "run_id": article["run_id"],
        "source_sha256": article["source"]["sha256"],
        "graph_sha256": fingerprint(article["graph"]),
        "knowledge_id": knowledge_id,
        "knowledge_sha256": fingerprint(knowledge),
        "reason_ru": reason,
        "scope": deepcopy(scope),
        "scope_reason_ru": scope_reason,
        "evidence": _source_evidence(article, knowledge),
        "statements": annotations,
    }


def build_audit() -> dict:
    prior = _read_json(CASE / "categorical-licenses-21-subtypes.json")
    manifest = _read_json(CASE / "source-manifest-21.json")
    manifest_article = next(item for item in manifest["sources"]
                            if item["reference"]["article_id"] == ARTICLE_ID)
    article = _read_json(Path(manifest_article["path"]))
    require(article["article_id"] == ARTICLE_ID
            and article["run_id"] == manifest_article["reference"]["run_id"],
            "WHICAP source run differs from frozen manifest")
    require(sha256(article["source"]["text"].encode("utf-8")).hexdigest()
            == article["source"]["sha256"], "WHICAP source hash differs")
    require(prior["author"] == "Codex" and prior["model_calls"] == 0
            and prior["expert_validated"] is False,
            "Prior analytical audit provenance differs")

    article_concepts = {concept["id"]: concept for concept in article["graph"]["concepts"]}
    knowledge = {item["knowledge_id"]: item for item in article["graph"]["knowledge"]}
    require(set(KNOWLEDGE_IDS) <= set(knowledge), "WHICAP definition blocks are incomplete")
    require(article_concepts["C1"]["display_text"] == "WHICAP"
            and article_concepts["C72"]["display_text"] == "WHICAP MCI"
            and "dementia" in article_concepts["C76"]["display_text"].casefold(),
            "WHICAP class identities differ from the source graph")

    scope = {
        "study_group": ARTICLE_ID,
        "time": None,
        "modality": None,
        "conditions": [
            "WHICAP MCI classification is applied at each assessment visit after the consensus conference",
            "At the same WHICAP consensus visit, MCI excludes a dementia diagnosis and the six subtype definitions are source-local",
            "No equivalence across other diagnostic schemes or cohorts is asserted",
        ],
    }
    preserved = [deepcopy(entry) for entry in prior["entries"]
                 if entry["article_id"] != ARTICLE_ID]
    require(len(preserved) == 2, "Expected only the two previously licensed review definitions")
    entries = preserved + [
        _make_entry(article, knowledge[kid], article_concepts, scope)
        for kid in KNOWLEDGE_IDS
    ]
    return {
        "version": VERSION,
        "author": "Codex",
        "model_calls": 0,
        "expert_validated": False,
        "entries": entries,
    }


def main() -> None:
    encoded = json.dumps(build_audit(), ensure_ascii=False, indent=2) + "\n"
    if OUTPUT.exists():
        require(OUTPUT.read_text(encoding="utf-8") == encoded,
                "Refusing to overwrite a different immutable WHICAP audit")
    else:
        OUTPUT.write_text(encoded, encoding="utf-8", newline="\n")
    print(json.dumps({"path": str(OUTPUT), "entries": len(json.loads(encoded)["entries"]),
                      "version": VERSION, "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
