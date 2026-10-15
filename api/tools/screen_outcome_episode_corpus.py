"""Сканирует зафиксированные карты на явные эпизоды вмешательство–исход."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.action_result_transfer import extract_article
from domain.article_maps import fingerprint, require
from domain.research_outcome_episodes import VERSION, project_outcome_episodes
from infrastructure.immutable_files import write_immutable


CORPUS_MANIFEST = Path("eval/whole_map_forecast/action-result-family-ranking-v2/input/source-manifest.json")
AGEWELL_MAP = Path("eval/whole_map_forecast/agewell-digital-coach-codex-map-v2/runs/2cd47128-e8f8-51c6-bd10-c77233a64ec5/map.json")
OUTPUT = Path("eval/whole_map_forecast/goal-pattern-learning-gap-v1/outcome-episode-corpus-screen-v4/runs")
AGEWELL_SOURCE_SHA256 = "6aa007f870725b89840ea397dea6fd12237ea4f0624b9d2b80de14b9c407051d"


def _load_bound_map(root: Path, item: dict) -> tuple[dict, str]:
    path = Path(item["map_path"])
    raw = path.read_bytes()
    map_hash = sha256(raw).hexdigest()
    require(map_hash == item["map_sha256"], f"Map hash differs: {item['article_id']}")
    snapshot = json.loads(raw.decode("utf-8"))
    require(snapshot.get("article_id") == item["article_id"], "Article identity changed")
    require(snapshot.get("run_id") == item["run_id"], "Map run changed")
    require(snapshot.get("source", {}).get("sha256") == item["source_sha256"], "Source revision changed")
    return snapshot, map_hash


def _legacy_summary(snapshot: dict) -> dict:
    legacy = extract_article(snapshot)
    return {
        "operation_families": legacy["operation_families"],
        "outcome_families": legacy["outcome_families"],
        "graph_links": legacy["graph_links"],
        "classified_action_statements": legacy["coverage"]["action_statements_classified"],
        "total_action_statements": legacy["coverage"]["action_statements_checked"],
        "classified_reported_outcome_states": legacy["coverage"]["state_predicates_classified_as_reported_outcome"],
        "total_states": legacy["coverage"]["state_predicates_checked"],
    }


def _screen(snapshot: dict, map_hash: str, support_family: str) -> tuple[dict, dict | None]:
    projection = project_outcome_episodes(snapshot)
    projection["map_sha256"] = map_hash
    projection["support_family"] = support_family
    summary = {
        "article_id": snapshot["article_id"],
        "run_id": snapshot["run_id"],
        "source_sha256": snapshot["source"]["sha256"],
        "map_sha256": map_hash,
        "support_family": support_family,
        "episode_count": projection["episode_count"],
        "outcome_knowledge_ids": [e["outcome_knowledge_id"] for e in projection["episodes"]],
        "intervention_knowledge_ids": sorted({k for e in projection["episodes"] for k in e["intervention_knowledge_ids"]}),
        "comparator_knowledge_ids": sorted({k for e in projection["episodes"] for k in e["comparator_knowledge_ids"]}),
        "legacy_action_result_projection": _legacy_summary(snapshot),
    }
    return summary, projection if projection["episode_count"] else None


def build_screen(root: Path) -> dict:
    manifest_path = root / CORPUS_MANIFEST
    manifest_bytes = manifest_path.read_bytes()
    corpus = json.loads(manifest_bytes.decode("utf-8"))
    require(len(corpus["sources"]) == 19, "Frozen input must contain the audited 19-map corpus")
    rows, episode_maps = [], []
    for item in corpus["sources"]:
        snapshot, map_hash = _load_bound_map(root, item)
        summary, projection = _screen(snapshot, map_hash, item["support_family"])
        rows.append(summary)
        if projection:
            episode_maps.append(projection)

    agewell_path = root / AGEWELL_MAP
    agewell_bytes = agewell_path.read_bytes()
    agewell_hash = sha256(agewell_bytes).hexdigest()
    agewell = json.loads(agewell_bytes.decode("utf-8"))
    require(agewell["article_id"] == "PMC10001821"
            and agewell["source"]["sha256"] == AGEWELL_SOURCE_SHA256,
            "AgeWell source revision changed")
    summary, projection = _screen(agewell, agewell_hash, "publication:PMC10001821")
    rows.append(summary)
    if projection:
        episode_maps.append(projection)

    active = [row for row in rows if row["episode_count"]]
    distinct_families = sorted({row["support_family"] for row in active})
    binding = {
        "version": "outcome-episode-corpus-screen-4",
        "projector_version": VERSION,
        "projector_sha256": sha256((root / "api/domain/research_outcome_episodes.py").read_bytes()).hexdigest(),
        "screening_tool_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "corpus_manifest_sha256": sha256(manifest_bytes).hexdigest(),
        "agewell_map_sha256": agewell_hash,
        "screened_maps": len(rows),
        "model_calls": 0,
        "network_calls": 0,
        "neo4j_calls": 0,
    }
    require([row["article_id"] for row in active] == [
        "research-pmc5651799-d577fb3b53bb16a1", "research-pmc8294390-73be7ddcb010d1c6",
        "PMC6199791", "PMC10001821",
    ], "Projectable article set changed; inspect before interpreting")
    return {
        "run_id": fingerprint(binding),
        "binding": binding,
        "screening": rows,
        "projectable_publication_families": distinct_families,
        "projectable_publication_count": len(distinct_families),
        "total_episode_count": sum(row["episode_count"] for row in active),
        "projected_episode_maps": episode_maps,
        "comparability": {
            "common_skeleton": "an explicit performed intervention is among the declared bases of an outcome block",
            "same_outcome_pattern_supported_by_multiple_independent_publications": False,
            "independent_publications_with_projected_episodes": 4,
            "human_studies": 2,
            "preclinical_mouse_studies": 1,
            "repeated_sensitivity_or_phase_results_count_as_independent_support": False,
            "why_not_train_one_rule": [
                "The maps cover different outcomes: cognitive frailty, EAE disease scores/onset, and physical activity/well-being/socialization.",
                "Populations and models differ: sedentary older adults, mice with EAE, and self-described healthy adults near retirement.",
                "Designs and comparators differ: randomized control, preclinical intervention arms, and uncontrolled pilot phases.",
                "No common predeclared success threshold spans these studies.",
            ],
        },
        "mapping_gaps": [
            {
                "article_id": "research-pmc5651799-d577fb3b53bb16a1",
                "transition_ids": ["T6"],
                "outcome_knowledge_ids": ["K16"],
                "finding": "The biodistribution result compares human-TNFR1 mice with WT mice, but the transition does not encode the comparison group as a separate comparator; this is a target-engagement observation, not a clinical disease outcome.",
                "interpretation": "Keep it as a pharmacokinetic/target-engagement episode and do not treat it as evidence of therapeutic success.",
            },
            {
                "article_id": "research-pmc5651799-d577fb3b53bb16a1",
                "transition_ids": ["T17", "T19"],
                "outcome_knowledge_ids": ["K31", "K63"],
                "finding": "The outcome texts mention PBS controls, but the declared transition bases contain no comparator knowledge; the projected comparator list is empty.",
                "interpretation": "The map projection cannot recover a structured comparator from the visible result wording alone.",
            },
            {
                "article_id": "research-pmc5651799-d577fb3b53bb16a1",
                "transition_ids": ["T23"],
                "outcome_knowledge_ids": ["K51"],
                "finding": "The transcript result names WT and TNFR1-deficient comparison groups in its text, but neither comparator is represented as a separate parent of the dependency transition.",
                "interpretation": "Retain the reported null findings and their named comparison groups; do not infer a PBS comparison or a treatment effect from this edge.",
            },
            {
                "article_id": "research-pmc8294390-73be7ddcb010d1c6",
                "transition_ids": ["T16"],
                "outcome_knowledge_ids": ["K42"],
                "finding": "The intervention and comparator are included in one protocol action block and repeated as roles on the result statement.",
                "interpretation": "The episode is projectable as a safety comparison, but the same action block represents multiple arms and must not be treated as a single treatment-only operation.",
            },
            {
                "article_id": "PMC10001821",
                "outcome_knowledge_ids": ["K21", "K22", "K23"],
                "finding": "SF-12 threshold, usability, and perceived-usefulness results have no explicit transition from a performed intervention action.",
                "interpretation": "Do not create missing intervention-result transitions from co-occurrence or thematic proximity.",
            },
        ],
        "predictions_made": 0,
        "goal_success_labels_assigned": 0,
        "causal_effects_inferred": 0,
        "expert_validated": False,
    }


def render_report(screen: dict) -> str:
    by_id = {row["article_id"]: row for row in screen["screening"]}
    tros = next(x for x in screen["projected_episode_maps"]
                if x["article_id"] == "research-pmc5651799-d577fb3b53bb16a1")
    life = next(x for x in screen["projected_episode_maps"] if x["article_id"] == "PMC6199791")
    agewell = next(x for x in screen["projected_episode_maps"] if x["article_id"] == "PMC10001821")
    return "\n".join([
        "# Корпусный экран эпизодов «вмешательство → исход»",
        "",
        f"**Запуск:** `{screen['run_id']}`  ",
        f"**Проверено карт:** {len(screen['screening'])}  ",
        f"**Карт с явными эпизодами:** {len(screen['projectable_publication_families'])} публикации  ",
        f"**Извлечено эпизодов:** {screen['total_episode_count']}  ",
        "**Прогнозов, LLM-, сетевых и Neo4j-вызовов:** 0",
        "",
        "## Какие случаи обнаружены",
        "",
        f"- `PMC5651799` — {by_id['research-pmc5651799-d577fb3b53bb16a1']['episode_count']} разных эпизода одного исследования EAE у мышей: фармакокинетика/связывание с мишенью (K16), транскрипционные маркеры без установленного эффекта (K51) и два клинических исхода болезни (K31, K63). Профилактический TROS снизил отдельные показатели тяжести, но задержка начала болезни не была статистически установлена. Локальный TROS задержал начало EAE примерно с 8,1 до 15,4 дня, однако длительная защита и снижение итоговой тяжести не установлены. Это не четыре независимых подтверждения и не один исход. Текст называет группы WT, TNFR1-дефицитных мышей и PBS, но зависимости не кодируют их как отдельные компараторы.",
        f"- `PMC8294390` (Atrosimab) — {by_id['research-pmc8294390-73be7ddcb010d1c6']['episode_count']} эпизод сравнения безопасности в гуманизированных мышах. Блок сообщает, что Atrosimab 30 мг/кг не вызвал значимого изменения веса или повышения IL‑6/CRP, тогда как TNF вызвал; небольшое повышение IL‑6 через шесть часов для Atrosimab/Fc не было значимым. Это не доказывает отсутствие побочных эффектов или безопасность у людей.",
        f"- `PMC6199791` (LIFE) — {by_id['PMC6199791']['episode_count']} эпизода из одного рандомизированного испытания. Физическая активность сравнена с санитарным просвещением по ухудшению когнитивной хрупкости; чувствительный анализ меняет кодировку того же исхода, а не добавляет независимый источник.",
        f"- `PMC10001821` (AgeWell) — {by_id['PMC10001821']['episode_count']} профиля в неконтролируемом пилоте. Физическая активность, психическое благополучие/самоэффективность и социализация менялись неодинаково по фазам; человеческая поддержка совпала с первой фазой, поэтому причинность не установлена.",
        "",
        "## Интерпретация для предсказания",
        "",
        "Обнаружен повторяющийся формальный каркас: выполненное вмешательство участвует в зависимостях, обосновывающих блок измеренного результата. В текущем 20-карточном срезе у четырёх публикаций есть 10 формально проецируемых эпизодов, но это не 10 независимых или сопоставимых подтверждений. LIFE даёт два анализа одного испытания, а четыре эпизода TROS относятся к одной работе и разным уровням результата — от распределения препарата до симптомов EAE. Только два TROS-эпизода описывают клинические показатели болезни; даже они имеют разные режимы введения и временные характеристики.",
        "",
        "Содержательная разметка показывает, почему бинарная метка «успех/неуспех статьи» теряет информацию: одно действие может сопровождаться улучшением одного исхода, отсутствием доказанного эффекта по другому и ограничением эффекта по времени. Статистически неустановленный эффект не означает доказанное отсутствие эффекта; отсутствие контрольной группы не позволяет считать наблюдаемую динамику эффектом вмешательства.",
        "",
        "Старые карты и прежние замороженные эксперименты не менялись. Новый экран не обучает правило, не формирует прогноз и не подтверждает критерий успеха. Он выявляет нижнюю границу данных для обучения: нужны повторяющиеся независимые публикации с сопоставимыми исходами, популяциями и компараторами, а успешность следует задавать для конкретной цели и временного окна.",
        "",
        f"Полный JSON с эпизодами, ссылками на исходные фрагменты и хешами: `screen.json`. SHA-256 binding: `{fingerprint(screen['binding'])}`.",
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    screen = build_screen(root)
    output = root / OUTPUT / screen["run_id"]
    files = {
        "screen.json": json.dumps(screen, ensure_ascii=False, indent=2),
        "report.ru.md": render_report(screen),
    }
    manifest = {
        "run_id": screen["run_id"], "binding": screen["binding"],
        "files": {name: sha256(value.encode("utf-8")).hexdigest() for name, value in files.items()},
        "expert_validated": False, "predictions_made": 0,
        "model_calls": 0, "network_calls": 0, "neo4j_calls": 0,
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)
    for name, value in files.items():
        write_immutable(output / name, value.encode("utf-8"))
    print(output)
    print(json.dumps({"run_id": screen["run_id"], "maps_screened": len(screen["screening"]),
                      "projectable_publications": screen["projectable_publication_count"],
                      "episodes": screen["total_episode_count"], "predictions": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
