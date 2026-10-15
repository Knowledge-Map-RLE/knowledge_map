"""Фиксирует офлайн-аудит эпизодов вмешательство–исход для двух карт schema 6."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.action_result_transfer import extract_article
from domain.article_maps import fingerprint, require
from domain.research_outcome_episodes import VERSION, project_outcome_episodes
from infrastructure.immutable_files import write_immutable


AGEWELL = Path("eval/whole_map_forecast/agewell-digital-coach-codex-map-v2/runs/2cd47128-e8f8-51c6-bd10-c77233a64ec5/map.json")
LIFE = Path("eval/whole_map_forecast/research-corpus-extension-v1/life2018-codex-map-v1/map.json")
OUTPUT = Path("eval/whole_map_forecast/goal-pattern-learning-gap-v1/outcome-episode-comparability-v1/runs")
EXPECTED = {
    "PMC10001821": "6aa007f870725b89840ea397dea6fd12237ea4f0624b9d2b80de14b9c407051d",
    "PMC6199791": "f86de555c3dbdbe4dfc3d589a40a6dd4fbec8170c2cc7e0e56d64937acb7601c",
}


def _load_map(root: Path, relative: Path, article_id: str) -> tuple[dict, str]:
    path = root / relative
    raw = path.read_bytes()
    snapshot = json.loads(raw.decode("utf-8"))
    require(snapshot.get("article_id") == article_id, f"Unexpected article at {relative}")
    require(snapshot.get("source", {}).get("sha256") == EXPECTED[article_id], "Source revision changed")
    require(snapshot.get("graph", {}).get("schema_version") == 6, "Only schema 6 maps are supported")
    return snapshot, sha256(raw).hexdigest()


def _legacy_projection(snapshot: dict) -> dict:
    result = extract_article(snapshot)
    return {
        "operation_families": result["operation_families"],
        "outcome_families": result["outcome_families"],
        "graph_links": result["graph_links"],
        "action_statements_classified": result["coverage"]["action_statements_classified"],
        "action_statements_checked": result["coverage"]["action_statements_checked"],
        "outcome_predicates_classified": result["coverage"]["state_predicates_classified_as_reported_outcome"],
        "state_predicates_checked": result["coverage"]["state_predicates_checked"],
    }


def build_audit(root: Path) -> dict:
    agewell, agewell_hash = _load_map(root, AGEWELL, "PMC10001821")
    life, life_hash = _load_map(root, LIFE, "PMC6199791")
    projections = []
    for snapshot, map_hash in ((agewell, agewell_hash), (life, life_hash)):
        projection = project_outcome_episodes(snapshot)
        projection["map_sha256"] = map_hash
        projection["legacy_action_result_projection"] = _legacy_projection(snapshot)
        projections.append(projection)

    require([row["episode_count"] for row in projections] == [3, 2],
            "The audited transition set changed; review mappings before comparing")
    binding = {
        "version": "outcome-episode-comparability-audit-1",
        "episode_projector": VERSION,
        "projector_sha256": sha256((root / "api/domain/research_outcome_episodes.py").read_bytes()).hexdigest(),
        "inputs": [
            {"article_id": row["article_id"], "run_id": row["run_id"],
             "source_sha256": row["source_sha256"], "map_sha256": row["map_sha256"]}
            for row in projections
        ],
        "scoring": "No predictor, matching score, direction classifier, or goal-success threshold was run.",
        "model_calls": 0,
        "network_calls": 0,
        "neo4j_calls": 0,
    }
    return {
        "run_id": fingerprint(binding),
        "binding": binding,
        "projections": projections,
        "comparability": {
            "shared_high_level_operation": "physical activity intervention or coaching",
            "same_measured_primary_outcome": False,
            "agewell_outcomes": ["physical activity", "well-being/self-efficacy", "socialization"],
            "life_primary_outcome": "ordinal worsening of cognitive frailty over 24 months",
            "agewell_comparator": None,
            "life_comparator": "health education program",
            "agewell_design": "10-week uncontrolled mixed-methods pilot; human support differed by phase",
            "life_design": "randomized LIFE clinical-trial analysis",
            "independent_supporting_publications": 2,
            "suitable_as_same_pattern_training_pair": False,
            "reason": "Interventions, populations, outcome constructs, comparators, and observation windows differ; the two LIFE episodes are primary/sensitivity analyses of one trial.",
        },
        "manual_interpretation": {
            "agewell_outcome_profiles": [
                {"knowledge_id": "K18", "observed_pattern": "physical activity rose in the supported phase and was reported stable later; low-activity proportion fell then rose", "goal_attainment": "unscored", "causal_effect": "not identified"},
                {"knowledge_id": "K19", "observed_pattern": "WHO-5 and GSE-6 rose slightly then fell; SF-12 score tests were significant but direction is not given in this source passage", "goal_attainment": "unscored", "causal_effect": "not identified"},
                {"knowledge_id": "K20", "observed_pattern": "socialization decreased then partly recovered but was described as worse overall", "goal_attainment": "unscored", "causal_effect": "not identified"},
            ],
            "life_outcome_profiles": [
                {"knowledge_id": "K20", "observed_pattern": "lower odds of worsening cognitive frailty for physical activity than health education over 24 months; OR 0.79 (95% CI 0.64–0.98), p=0.032", "goal_attainment": "not scored by this audit", "causal_effect": "reported randomized comparison; not generalized beyond the source trial"},
                {"knowledge_id": "K23", "observed_pattern": "same direction in a secondary ordinal coding; sensitivity result from the same trial, not an independent replication", "goal_attainment": "not scored by this audit", "causal_effect": "reported randomized comparison; not generalized beyond the source trial"},
            ],
            "unprojected_agewell_results": [
                {"knowledge_id": "K21", "reason": "Threshold proportions are in a result block without a direct dependency transition from the intervention."},
                {"knowledge_id": "K22", "reason": "Usability result is linked to measurement and analysis, not to the intervention action."},
                {"knowledge_id": "K23", "reason": "Perceived-usefulness result has no explicit intervention transition."},
            ],
            "legacy_classifier_diagnostic": "The existing broad action/result taxonomy returns no reported-outcome category for either map; the new projection recovers explicit graph-linked outcome episodes but intentionally does not infer direction or success.",
            "no_overall_success_label": True,
        },
        "predictions_made": 0,
        "goal_success_labels_assigned": 0,
        "scientific_accuracy_assessed": False,
        "expert_validated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    audit = build_audit(root)
    output = root / OUTPUT / audit["run_id"]
    audit_text = json.dumps(audit, ensure_ascii=False, indent=2)
    report = "\n".join([
        "# Эпизоды «вмешательство → исход»: проверка представления на двух картах",
        "",
        f"**Запуск:** `{audit['run_id']}`  ",
        f"**Проектор:** `{VERSION}`  ",
        f"**PMC10001821:** `2cd47128-e8f8-51c6-bd10-c77233a64ec5` — 3 явно связанные эпизода  ",
        f"**PMC6199791 (LIFE):** `{audit['projections'][1]['run_id']}` — 2 эпизода, одна публикация и один эксперимент  ",
        "**Модельные, сетевые и Neo4j-вызовы:** 0",
        "",
        "## Что теперь извлекается из карты",
        "",
        "Новый адаптер schema 6 находит выполненное вмешательство, его компаратор, связанные знания о методах и измерении, целевой блок-результат, семантические утверждения и исходные фрагменты с Unicode-координатами. Он исключает статистические действия, где вмешательство выступает переменной модели, и сохраняет явное правило: ребро карты само по себе не утверждает причинность.",
        "",
        "Для PMC10001821 получены три исходных профиля: физическая активность улучшилась в первой фазе и затем оставалась стабильной по формулировке авторов, при этом доля низкой активности частично вернулась; WHO-5 и GSE-6 сначала немного выросли, затем снизились; социализация ухудшилась в целом после разнонаправленных изменений. Поддержка человека совпала с первой фазой, поэтому эффект приложения, коучинга и времени не разделён.",
        "",
        "Для LIFE получены основной и чувствительный анализы одного рандомизированного испытания: физическая активность сравнивалась с программой санитарного просвещения, а целевой исход — ухудшение когнитивной хрупкости за 24 месяца. Основная оценка сообщена как OR 0,79 (95% ДИ 0,64–0,98), p=0,032; второй анализ использует альтернативное кодирование того же исхода и не является независимой публикацией.",
        "",
        "## Что это говорит о пригодности для обучения",
        "",
        "Эти источники полезны для проверки того, сохраняет ли представление измерение, временной профиль, компаратор и ограничения дизайна. Они **не образуют подходящую пару для обучения одному паттерну**: различаются популяции, типы вмешательств, исходы, контроль и длительность. AgeWell не измеряет когнитивную хрупкость, а LIFE не является тестом цифрового коучинга. Положительное направление LIFE нельзя превращать в успех AgeWell, а смешанные исходы AgeWell — в отрицательную контрольную группу.",
        "",
        "В AgeWell карта также содержит пороговые доли SF-12 и оценки удобства/полезности, но они не имеют перехода от вмешательства к результату. Адаптер правильно не достраивает такие рёбра самостоятельно. Это показывает конкретный пробел в самой карте: связь системы с пользовательскими результатами и отдельная связь вмешательства с пороговыми исходами ещё не формализованы.",
        "",
        "Старый классификатор категорий действий и результатов не распознаёт исходовые категории ни в одной из этих карт. Новый адаптер устраняет структурную потерю эпизодов, но пока ничего не прогнозирует и не назначает знак успеха. Для обучения дальше нужны несколько независимых исследований с общим исходом и заранее заданным критерием результата; повторные модели одного исследования должны считаться одной публикацией.",
        "",
        "## Статус",
        "",
        "Это техническая и качественная проверка представления, а не прогноз, не доказательство научной точности и не подтверждение критерия успеха всей Карты Знаний. Порог достижения цели в этих двух статьях не задан единым протоколом, поэтому итоговая метка успеха не присваивалась.",
        "",
        f"Полные эпизоды, карта, запуски, хеши и цитируемые фрагменты: `projection.json` в этой папке. Binding SHA-256: `{fingerprint(audit['binding'])}`.",
        "",
    ])
    files = {"projection.json": audit_text, "report.ru.md": report}
    manifest = {
        "run_id": audit["run_id"], "binding": audit["binding"],
        "files": {name: sha256(content.encode("utf-8")).hexdigest() for name, content in files.items()},
        "expert_validated": False, "model_calls": 0, "network_calls": 0, "neo4j_calls": 0,
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)
    for name, content in files.items():
        write_immutable(output / name, content.encode("utf-8"))
    print(output)
    print(json.dumps({"run_id": audit["run_id"], "episode_counts": [x["episode_count"] for x in audit["projections"]],
                      "same_pattern_pair": audit["comparability"]["suitable_as_same_pattern_training_pair"],
                      "predictions": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
