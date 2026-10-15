"""Отбирает только проверяемые исходные случаи для последующей логической разметки."""
from collections import Counter, defaultdict
from hashlib import sha256

from domain.article_maps import fingerprint, require

VERSION = "source-bound-categorical-candidate-screen-2"
CATEGORICAL_PREDICATES = {
    "subtype_of", "class_inclusion", "class_disjointness", "class_overlap", "class_noninclusion",
}
QUANTIFIERS = {"all", "every", "each", "no", "none", "some", "at_least_one"}


def _evidence(source, statement):
    text = source["text"]
    result = []
    for span in statement["provenance"]["source_spans"]:
        start, end = span["start"], span["end"]
        require(type(start) is int and type(end) is int and 0 <= start < end <= source["content_end"],
                "Logical candidate source coordinates are invalid")
        quoted = text[start:end]
        quoted_sha256 = sha256(quoted.encode("utf-8")).hexdigest()
        require(quoted and (span.get("sha256") is None or span["sha256"] == quoted_sha256),
                "Logical candidate source fragment differs")
        result.append({"start": start, "end": end, "section_id": span["section_id"],
                       "sha256": quoted_sha256, "text": quoted})
    require(result, "Logical candidate has no source fragment")
    return result


def inspect_maps(maps):
    require(maps and len({m["article_id"] for m in maps}) == len(maps), "Unique explicit maps are required")
    totals = Counter()
    by_source = defaultdict(Counter)
    candidates = []
    for m in maps:
        require(m["graph_schema_version"] == 6, "Schema 6 is required for this audit")
        source = m["source"]
        require(sha256(source["text"].encode("utf-8")).hexdigest() == source["sha256"],
                "Source text hash differs")
        for knowledge in m["graph"]["knowledge"]:
            totals["canonical_blocks"] += 1
            by_source[m["article_id"]]["canonical_blocks"] += 1
            frame = knowledge["semantic_frame"]
            parent_reasons = []
            if knowledge["knowledge_kind"] == "definition":
                parent_reasons.append("definition_kind")
            for statement in frame["statements"]:
                predicate = statement["predicate"]
                quantifier = statement["quantifier"]
                reasons = list(parent_reasons)
                if predicate in CATEGORICAL_PREDICATES:
                    reasons.append("categorical_relation_predicate")
                if quantifier in QUANTIFIERS:
                    reasons.append("explicit_categorical_quantifier")
                if not reasons:
                    continue
                totals["candidate_statements"] += 1
                by_source[m["article_id"]]["candidate_statements"] += 1
                if predicate in CATEGORICAL_PREDICATES and quantifier in QUANTIFIERS:
                    totals["explicit_relation_and_quantifier"] += 1
                    by_source[m["article_id"]]["explicit_relation_and_quantifier"] += 1
                if statement["modality"] is not None:
                    totals["modal_candidates"] += 1
                if statement["conditions"] or statement["temporal_context"] is not None:
                    totals["conditioned_candidates"] += 1
                if statement["negated"] or quantifier in {"no", "none"}:
                    totals["negative_candidates"] += 1
                candidates.append({
                    "article_id": m["article_id"], "article_title": m["article_title"],
                    "pmcid": m.get("source", {}).get("pmcid"), "run_id": m["run_id"],
                    "source_sha256": source["sha256"], "knowledge_id": knowledge["knowledge_id"],
                    "knowledge_kind": knowledge["knowledge_kind"], "parent_kind": knowledge["kind"],
                    "parent_logic": frame["logic"], "display_text_en": knowledge["display_text"],
                    "parent_frame": frame, "statement_id": statement["statement_id"],
                    "predicate": predicate, "roles": statement["roles"], "quantifier": quantifier,
                    "negated": statement["negated"], "modality": statement["modality"],
                    "conditions": statement["conditions"], "temporal_context": statement["temporal_context"],
                    "attributes": statement["qualifiers"]["attributes"],
                    "selection_reasons": reasons, "source_evidence": _evidence(source, statement),
                    "source_scope": "article_context_requires_attribution_review",
                    "scope_requires_manual_resolution": True,
                    "licensed_for_inference": False,
                    "note_ru": "Кандидат для ручной проверки; автоматически посылкой не считается.",
                })
    candidates.sort(key=lambda c: (c["pmcid"] or "", c["article_id"], c["knowledge_id"], c["statement_id"]))
    definition_candidates = sum("definition_kind" in c["selection_reasons"] for c in candidates)
    unique_parent_blocks = len({(c["article_id"], c["knowledge_id"]) for c in candidates})
    relation_without_quantifier = sum(
        c["predicate"] in CATEGORICAL_PREDICATES and c["quantifier"] not in QUANTIFIERS
        for c in candidates
    )
    quantifier_without_relation = sum(
        c["quantifier"] in QUANTIFIERS and c["predicate"] not in CATEGORICAL_PREDICATES
        for c in candidates
    )
    return {
        "version": VERSION,
        "map_count": len(maps),
        "canonical_blocks": totals["canonical_blocks"],
        "candidate_statement_count": totals["candidate_statements"],
        "definition_kind_candidate_count": definition_candidates,
        "unique_candidate_parent_blocks": unique_parent_blocks,
        "categorical_relation_without_quantifier_count": relation_without_quantifier,
        "quantifier_without_categorical_relation_count": quantifier_without_relation,
        "explicit_relation_and_quantifier_count": totals["explicit_relation_and_quantifier"],
        "modal_candidate_count": totals["modal_candidates"],
        "conditioned_candidate_count": totals["conditioned_candidates"],
        "negative_candidate_count": totals["negative_candidates"],
        "operator_coverage_is_complete": False,
        "licensed_inferences": 0,
        "new_empirical_predictions": 0,
        "graph_advantage_demonstrated": False,
        "model_calls": 0,
        "candidates_by_source": {key: dict(value) for key, value in sorted(by_source.items())},
        "candidates": candidates,
        "policy_ru": "Отбор создаёт очередь для ручной разметки. Предикат, описание вида definition или наличие квантора сами по себе не лицензируют посылку; область действия и смысл проверяются по полному источнику.",
    }


def render_ru(audit, base_run_id):
    lines = [
        "# Поиск кандидатов для логических выводов по всей карте", "",
        f"Проверены {audit['map_count']} карт схемы 6 и {audit['canonical_blocks']} канонических знаний.",
        f"Выявлено {audit['candidate_statement_count']} фрагментов-кандидатов для ручной логической разметки.",
        f"Они относятся к {audit['unique_candidate_parent_blocks']} родительским блокам; {audit['definition_kind_candidate_count']} фрагментов находятся в блоках с видом знания «определение».",
        f"У {audit['explicit_relation_and_quantifier_count']} фрагментов одновременно присутствуют типизированное отношение классов и явный квантор. "
        "Эта цифра задаёт очередь проверки, а не число пригодных посылок или выводов.", "",
        f"Отдельно: {audit['categorical_relation_without_quantifier_count']} фрагмента выражают типизированное отношение без явного квантора; "
        f"{audit['quantifier_without_categorical_relation_count']} фрагмент содержит квантор без такого отношения.",
        "Два найденных отношения подтипов относятся к уже вручную лицензированному K9 обзора PMC6416157; этот скрининг не отменяет и не расширяет те лицензии. "
        "Единственное утверждение с явным квантором «некоторые» описывает результат конкретной острой модели и не является универсальным классовым правилом.", "",
        "## Результат по картам", "",
        "| Карта | Кандидатных фрагментов | Отношение и квантор явно заданы |",
        "| --- | ---: | ---: |",
    ]
    for article, counts in audit["candidates_by_source"].items():
        lines.append(f"| {article} | {counts.get('candidate_statements', 0)} | {counts.get('explicit_relation_and_quantifier', 0)} |")
    lines += [
        "", "## Ограничения", "",
        "Это автоматический поиск мест для проверки, не автоматическая разметка их истинности. Отдельно сохранены отрицание, модальность, условия, время, участники, полный родительский блок и исходные фрагменты.",
        "Определение из одной статьи остаётся в области этой статьи, пока источник не обосновывает более общий охват. Кандидат с явным квантором также требует проверки ролей, области действия, совместимости контекстов и достаточности посылок.",
        "Ни одна новая посылка не лицензирована. Выводов и эмпирических прогнозов этот поиск не создаёт; преимущество графа не оценено. Оператор покрывает только указанные классы признаков, поэтому полнота поиска всей карты не заявляется.", "",
        f"Основание: неизменяемый прогон полного корпуса `{base_run_id}`. Модельных и сетевых вызовов — 0.", "",
    ]
    return "\n".join(lines) + "\n"
