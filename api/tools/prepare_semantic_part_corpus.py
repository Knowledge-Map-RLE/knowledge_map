"""Готовит строгий 19-карточный корпус для свободного прогноза частей."""
import json
import re
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.evidence_origin_audit import validate_origins
from domain.statistical_context_audit import audit_models
from domain.whole_map_context import audit_index


ROOT = Path(__file__).resolve().parents[2]
CORPUS_MANIFEST = ROOT / "eval/whole_map_forecast/action-result-family-ranking-v2/runs/b1ddd644e7aec027ed39c69a5068497046e400d25c8229627316129f8914a732/source-manifest.json"
AUDITED_RUN = ROOT / "eval/whole_map_forecast/full-corpus-logical-v1/runs/54050ae89c98067f334bd6281d19d56cacd9f13d59d3999b82dff5589a9b9d88"
OUTPUT = ROOT / "eval/whole_map_forecast/semantic-parts-v1/full-corpus-19-prepared-v1"

# Семейства проверены по заголовкам и описаниям собственных выборок в источниках.
# Отдельные утверждения этих карт намеренно остаются unresolved_origin.
EXTRA_SOURCE_META = {
    "larrieu2002-codex": ("paquid-cohort", "PAQUID"),
    "luck2010": ("leipzig-longitudinal-study-of-the-aged", "Leipzig Longitudinal Study of the Aged"),
    "manly2008-complete": ("northern-manhattan-multiethnic-aging-cohort", "Inwood"),
    "roberts2012": ("mayo-clinic-study-of-aging-olmsted-county", "Mayo Clinic Study of Aging"),
    "katz2012": ("einstein-aging-study", "Einstein Aging Study"),
    "PMC3683032": ("sydney-memory-and-ageing-study", "Sydney Memory and Ageing Study"),
    "PMC6199791": ("life-randomized-trial", "Lifestyle Interventions and Independence for Elders"),
    "caracciolo2008": ("kungsholmen-project", "Kungsholmen Project"),
}

# Дата и её точность взяты из записей PubMed; месячная дата Manly нормализована к первому числу месяца.
EXTRA_PUBLICATION_META = {
    "larrieu2002-codex": {"published_on": "2002-11-26", "date_precision": "day", "pmid": "12451203"},
    "luck2010": {"published_on": "2010-09-14", "date_precision": "day", "pmid": "20840461"},
    "manly2008-complete": {"published_on": "2008-04-01", "date_precision": "month", "pmid": "18300306"},
    "roberts2012": {"published_on": "2012-01-25", "date_precision": "day", "pmid": "22282647"},
    "katz2012": {"published_on": "2011-12-14", "date_precision": "day", "pmid": "22156756"},
    "PMC3683032": {"published_on": "2013-06-14", "date_precision": "day", "pmid": "23799051"},
    "PMC6199791": {"published_on": "2018-10-24", "date_precision": "day", "pmid": "30352583"},
    "caracciolo2008": {"published_on": "2008-01-09", "date_precision": "day", "pmid": "18184916"},
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_sha256(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def evidence_for(unit):
    text = unit["text"]
    return {"unit_id": unit["id"], "start": unit["start"], "end": unit["end"],
            "text": text, "sha256": sha256(text.encode("utf-8")).hexdigest()}


def unresolved_source_record(article_id, dataset_family, marker, article):
    source = article["source"]
    units = {unit["id"]: unit for unit in source["units"]}
    folded_marker = re.sub(r"\s+", " ", marker).casefold()
    marker_units = [unit for unit in source["units"]
                    if folded_marker in re.sub(r"\s+", " ", unit["text"]).casefold()]
    require(marker_units, f"Не найдено подтверждение набора данных: {article_id}")

    referenced = set()
    knowledge_rows = []
    for knowledge in article["graph"]["knowledge"]:
        statements = []
        for statement in knowledge["semantic_frame"]["statements"]:
            evidence_ids = list(statement["provenance"]["unit_ids"])
            require(evidence_ids and set(evidence_ids) <= units.keys(),
                    f"Неверные исходные фрагменты: {article_id}/{knowledge['knowledge_id']}")
            referenced.update(evidence_ids)
            statements.append({
                "statement_id": statement["statement_id"],
                "origin": "unresolved_origin",
                "reason_ru": "Индивидуальное происхождение этого утверждения для расширенного корпуса ещё не проверено; не учитывать его как подтверждённый первичный результат.",
                "annotation_method_ru": "Консервативная фиксация непроверенного происхождения без смысловой классификации.",
                "evidence_unit_ids": evidence_ids,
            })
        knowledge_rows.append({
            "knowledge_id": knowledge["knowledge_id"],
            "knowledge_sha256": fingerprint(knowledge),
            "statements": statements,
        })

    metadata_unit = marker_units[0]
    referenced.add(metadata_unit["id"])
    return {
        "article_id": article_id,
        "document_kind": "primary_study",
        "dataset_family": dataset_family,
        "reason_ru": f"Первичное исследование и набор данных {dataset_family} определены по сохранённому заголовку и описанию выборки. Происхождение каждого отдельного утверждения оставлено непроверенным.",
        "evidence": [evidence_for(units[unit_id]) for unit_id in sorted(referenced)],
        "run_id": article["run_id"],
        "source_sha256": source["sha256"],
        "graph_sha256": fingerprint(article["graph"]),
        "knowledge": knowledge_rows,
    }


def main():
    source_manifest = read_json(CORPUS_MANIFEST)
    prior_manifest = read_json(AUDITED_RUN / "source-manifest.json")
    context_audit = read_json(AUDITED_RUN / "context-audit.json")
    model_audit = read_json(AUDITED_RUN / "model-audit.json")
    prior_origin = read_json(AUDITED_RUN / "origin-audit.json")
    prior_sources_by_id = {
        entry["reference"]["article_id"]: entry for entry in prior_manifest["sources"]
    }

    articles = []
    forecast_sources = []
    for entry in source_manifest["sources"]:
        path = Path(entry.get("path") or entry["map_path"])
        raw = path.read_bytes()
        article = json.loads(raw)
        require(sha256(raw).hexdigest() == (entry.get("file_sha256") or entry["map_sha256"]),
                f"Хеш карты изменился: {entry['article_id']}")
        article_id = article["article_id"]
        require(article_id == entry["article_id"], f"Идентификатор карты изменился: {article_id}")
        prior_entry = prior_sources_by_id.get(article_id, {})
        publication_meta = EXTRA_PUBLICATION_META.get(article_id, {})
        published_on = (entry.get("published_on") or prior_entry.get("published_on")
                        or publication_meta.get("published_on"))
        require(published_on and re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_on),
                f"Нет точной ISO-даты публикации: {article_id}")
        articles.append(article)
        forecast_sources.append({
            "reference": {"article_id": article_id, "pipeline_id": article["pipeline_id"], "run_id": article["run_id"]},
            "path": str(path.resolve()),
            "file_sha256": sha256(raw).hexdigest(),
            "graph_sha256": fingerprint(article["graph"]),
            "source_sha256": article["source"]["sha256"],
            "family": entry.get("support_family") or f"publication:{article_id}",
            "published_on": published_on,
            "published_on_precision": publication_meta.get("date_precision") or "day",
            "publication_metadata_url": (f"https://pubmed.ncbi.nlm.nih.gov/{publication_meta['pmid']}/"
                                          if publication_meta else prior_entry.get("publication_metadata_url")),
            "title": entry.get("title") or article.get("title") or article_id,
            "support_note": "Группа публикации; независимость участников отдельно не удостоверена.",
        })

    require(len(articles) == 19 and len({m["article_id"] for m in articles}) == 19,
            "Ожидались ровно 19 различных карт")
    require(all(m["article_id"] != "PMC10000452" and
                m["source"]["sha256"] != "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
                for m in articles), "Целевой источник PMC10000452 попал в корпус")

    prior_ids = {record["article_id"] for record in prior_origin["sources"]}
    article_by_id = {article["article_id"]: article for article in articles}
    prior_subset = {**prior_origin,
                    "sources": [deepcopy(record) for record in prior_origin["sources"]
                                if record["article_id"] in article_by_id]}
    require({record["article_id"] for record in prior_subset["sources"]} == prior_ids,
            "Предыдущий аудит содержит статью вне нового корпуса")
    validate_origins([article_by_id[article_id] for article_id in sorted(prior_ids)], prior_subset)

    added_ids = set(article_by_id) - prior_ids
    require(added_ids == set(EXTRA_SOURCE_META), "Набор новых источников отличается от явного реестра")
    origin_audit = {**prior_origin, "sources": [deepcopy(record) for record in prior_subset["sources"]]}
    for article_id in sorted(added_ids):
        dataset_family, marker = EXTRA_SOURCE_META[article_id]
        origin_audit["sources"].append(
            unresolved_source_record(article_id, dataset_family, marker, article_by_id[article_id]))
    origin_audit["sources"].sort(key=lambda record: record["article_id"])

    # Существующие контекстные аудиты применимы только к совпадающим картам;
    # остальные утверждения сохраняются как неизвестные и не получают догаданных условий.
    audit_index(articles, context_audit)
    audit_models(articles, model_audit)
    validate_origins(articles, origin_audit)

    metadata = {
        "corpus_revision": "19 явных карт схемы 6; цель PMC10000452 не включена",
        "formalization_compatibility": "schema6_diagnostic_mixed_prompt_versions",
        "evaluation": "диагностический свободный прогноз, не слепая оценка целевой статьи",
        "target_article_id_excluded": "PMC10000452",
        "target_cohort_overlap_ru": "Карта PMC8775386 относится к Cretan Aging Cohort и не должна использоваться в отдельной слепой оценке PMC10000452.",
        "origin_policy_ru": "Восемь добавленных первичных источников имеют подтверждённые названия наборов данных, но происхождение каждого утверждения оставлено unresolved_origin и не засчитывается как первичный результат.",
        "family_definition_ru": "Семейство публикации применяется только для учёта повторов; независимость участников не подразумевается.",
        "training_cutoff": "2022-12-31",
        "expert_validated": False,
        "model_calls": 0,
    }
    manifest = {"metadata": metadata, "sources": forecast_sources}
    preparation = {
        "author": "Codex",
        "expert_validated": False,
        "model_calls": 0,
        "network_calls": 0,
        "source_count": len(articles),
        "preserved_origin_audit_sources": len(prior_ids),
        "added_primary_maps_with_unresolved_claim_origins": len(added_ids),
        "added_article_ids": sorted(added_ids),
        "target_article_excluded": "PMC10000452",
        "target_source_sha256_excluded": "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8",
        "cohort_overlap_warning_ru": "PMC8775386 и PMC10000452 относятся к одной когорте; подготовленный корпус не является независимым holdout для этой цели.",
        "input_sha256": {
            "corpus_manifest": file_sha256(CORPUS_MANIFEST),
            "prior_source_manifest": file_sha256(AUDITED_RUN / "source-manifest.json"),
            "context_audit": file_sha256(AUDITED_RUN / "context-audit.json"),
            "model_audit": file_sha256(AUDITED_RUN / "model-audit.json"),
            "prior_origin_audit": file_sha256(AUDITED_RUN / "origin-audit.json"),
        },
        "validated": {"prior_origin_subset": True, "context_bindings": True, "model_bindings": True,
                       "complete_conservative_origin_registry": True},
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT / "source-manifest.json", manifest)
    write_json(OUTPUT / "context-audit.json", context_audit)
    write_json(OUTPUT / "model-audit.json", model_audit)
    write_json(OUTPUT / "origin-audit.json", origin_audit)
    write_json(OUTPUT / "preparation-audit.json", preparation)
    (OUTPUT / "prepare_semantic_part_corpus.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({"prepared": str(OUTPUT), "sources": len(articles),
                      "preserved_origin_sources": len(prior_ids),
                      "unresolved_origin_sources": len(added_ids),
                      "target_excluded": True, "target_cohort_overlap_disclosed": True,
                      "model_calls": 0, "network_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
