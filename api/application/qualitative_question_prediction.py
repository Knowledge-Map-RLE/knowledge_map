"""Изолированный качественный опыт с фиксацией прогнозов до ретроспективной оценки."""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, timedelta
import logging
from time import perf_counter

from application.ports.question_prediction import ResearchMaps, QuestionForecastStore
from application.ports.qualitative_forecast_engine import QualitativeForecastEngine
from application.question_prediction import load_runs, validate_metadata_scope
from domain.article_maps import fingerprint, require
from domain.question_prediction import ForecastQuestion
from domain.research_semantics import project_map, VERSION as SEMANTICS_VERSION
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256
from domain.qualitative_question_prediction import (
    QualitativePolicy, VERSION, fit_qualitative_forecast, family_time_plan, evaluate_qualitative_holdout,
)

log = logging.getLogger(__name__)
BINDING = {"workflow_version": "qualitative-question-workflow-2", "predictor_version": VERSION,
           "semantics_version": SEMANTICS_VERSION, "normalizer_version": NORMALIZER_VERSION,
           "dictionary_sha256": DICTIONARY_SHA256}


class SealQualitativeQuestionExperiment:
    def __init__(self, maps: ResearchMaps, store: QuestionForecastStore, engine: QualitativeForecastEngine | None = None):
        self.maps, self.store = maps, store
        self.engine = engine

    def execute(self, references, registry, annotations, episodes, question_raw, policy_raw, owner, analysis_scope="primary"):
        start = perf_counter()
        require(analysis_scope in {"primary", "sensitivity"}, "Unknown qualitative analysis scope")
        question = ForecastQuestion.parse(question_raw)
        analysis_binding = {**BINDING, **self.engine.analysis_binding} if self.engine else BINDING
        fit = self.engine.fit if self.engine else fit_qualitative_forecast
        evaluate = self.engine.evaluate if self.engine else evaluate_qualitative_holdout
        policy = QualitativePolicy.parse(policy_raw, question)
        require(all(a.get("context_revision", {}).get("scope", analysis_scope) == analysis_scope for a in annotations.values()),
                "Context annotation scope differs from qualitative analysis scope")
        maps = load_runs(self.maps, references, owner)
        validate_metadata_scope(maps, registry, annotations)
        require(len({m["source"]["sha256"] for m in maps}) == len(maps), "Duplicate full text in qualitative corpus")
        plan = family_time_plan(registry, question)
        binding = {"analysis_binding": analysis_binding, "analysis_scope": analysis_scope, "owner": owner, "sources": references, "registry": registry,
                   "annotations_sha256": fingerprint(annotations), "episodes_sha256": fingerprint(episodes),
                   "policy": policy.to_dict(), "policy_sha256": fingerprint(policy.to_dict()), "question": asdict(question),
                   "fold_plan": plan, "maps": [{"article_id": m["article_id"], "graph_sha256": fingerprint(m["graph"]),
                                                "source_sha256": m["source"]["sha256"]} for m in maps]}
        run_id = fingerprint(binding)
        projected = [c for m in maps for c in project_map(m, registry[m["article_id"]], annotations.get(m["article_id"]))]
        claims = {(c.evidence.article_id, c.claim_id): c for c in projected}
        map_index = {m["article_id"]: m for m in maps}
        artifact = {"run_id": run_id, "binding": binding, **fit(claims, episodes, map_index, question, policy)}
        folds = []
        for fold in plan:
            training_ids = set(fold["training"])
            train = {k: c for k, c in claims.items() if k[0] in training_ids}
            training_families = sorted({c.evidence.family for c in train.values() if c.evidence.family})
            require(fold["family"] not in training_families, "Heldout family leaked into retrospective training")
            selected_episodes = [e for e in episodes if all(tuple(r) in train for r in [*e["premises"], e["conclusion"]])]
            cutoff = (date.fromisoformat(fold["first_publication"]) - timedelta(days=1)).isoformat()
            fold_question = replace(question, cutoff=cutoff)
            fold_binding = {"parent_run_id": run_id, "analysis_binding": analysis_binding, "owner": owner, "fold": fold,
                            "training_families": training_families, "training_claims_sha256": fingerprint([c.to_dict() for _, c in sorted(train.items())]),
                            "episodes_sha256": fingerprint(selected_episodes), "question": asdict(fold_question), "policy_sha256": binding["policy_sha256"]}
            if self.engine:
                fold_binding["structured_training_features_sha256"] = self.engine.binding_for(train)
            fold_id = fingerprint(fold_binding)
            forecast = {"run_id": fold_id, "binding": fold_binding,
                        **fit(train, selected_episodes, {a: map_index[a] for a in training_ids}, fold_question, policy)}
            # Сначала сохраняется прогноз на прошлом; оценки удержанной семьи в нём отсутствуют.
            self.store.seal(fold_id, forecast)
            sealed = self.store.read_seal(fold_id)
            require(sealed["binding"] == fold_binding, "Retrospective seal binding differs")
            targets = [c for c in projected if c.evidence.article_id in fold["heldout"]]
            evaluation_binding = {"forecast_run_id": fold_id, "prediction_sha256": fingerprint(sealed),
                                  "target_claims_sha256": fingerprint([c.to_dict() for c in targets]), "analysis_binding": analysis_binding}
            evaluation = {"evaluation_id": fingerprint(evaluation_binding), "binding": evaluation_binding,
                          **evaluate(sealed, targets)}
            self.store.save_evaluation(fold_id, evaluation["evaluation_id"], evaluation)
            folds.append({"plan": fold, "forecast_run_id": fold_id, "evaluation_id": evaluation["evaluation_id"],
                          "training_source_count": len(training_ids), "training_family_count": len(training_families),
                          "eligible_training_claims": forecast["eligible_question_claim_count"],
                          "eligible_training_families": sorted({row["original"]["evidence"]["family"] for row in forecast["observations"] if row["projected"]}),
                          "historical_episodes": len(selected_episodes), "diagnostics": forecast["diagnostics"],
                          "evaluation": evaluation})
        artifact["retrospective_folds"] = folds
        empirical_families = sorted({c.evidence.family for c in projected if any(row["reference"] == [c.evidence.article_id, c.claim_id]
                                   and row["projected"] for row in artifact["observations"])})
        heldout_forecasts = sum(f["evaluation"]["modes"]["semantic"]["issued_answers"] for f in folds if f["evaluation"]["eligible_target_claims"])
        checks = {"primary_confirmatory_scope": analysis_scope == "primary", "five_full_text_sources": len(maps) >= 5, "two_question_relevant_independent_families": len(empirical_families) >= 2,
                  "historical_learning_present": bool(artifact["rules"]["semantic"]), "question_forecast_present": bool(artifact["modes"]["semantic"]),
                  "nonempty_retrospective_family_time_forecast": heldout_forecasts > 0}
        if self.engine:
            checks["scorable_structured_family_time_forecast"] = any(
                f["evaluation"]["modes"]["semantic"].get("scorable_answers", 0) > 0 for f in folds)
        # Непустая база известных ответов никогда не открывает чтение будущей цели.
        artifact["readiness"] = {"status": "ready_for_independent_target" if all(checks.values()) else "needs_rule_or_context_evidence",
                                 "checks": checks, "failed_checks": [k for k, v in checks.items() if not v],
                                 "independent_families": empirical_families, "target_reading_allowed": all(checks.values()),
                                 "expert_validated": False, "retrospective_validation_is_prospective_evidence": False}
        self.store.seal(run_id, artifact)
        result = self.store.read_seal(run_id)
        log.info("qualitative_question sealed run=%s sources=%s claims=%s folds=%s semantic=%s dependency=%s gate=%s elapsed=%.3f",
                 run_id, len(maps), len(claims), len(folds), len(result["modes"]["semantic"]), len(result["modes"]["dependency"]),
                 result["readiness"]["status"], perf_counter() - start)
        return result
