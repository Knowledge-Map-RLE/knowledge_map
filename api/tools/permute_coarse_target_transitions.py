"""Проверяет единственный грубый структурный hit перестановкой рёбер."""
from __future__ import annotations

import json
import random
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools import run_training21_operator_transition_lopo as baseline
from tools.operator_route_experiment import shape_id, types_for_map

TRAINING = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
MANIFEST = TRAINING / "training-corpus-manifest.json"
TARGET_META = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "heldout-target.json"
TARGET_MAP = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "runs" / "86f921d6-7bb9-5cd3-a84a-befdc0e83854" / "map.json"
EXPERIMENT = ROOT / "eval" / "whole_map_forecast" / "curated-operator-route-v1" / "pmc10002471"
RUN_ID = "5424c1da25628b4d64117970bac19c99fde27949e26b24c0851d79254ff134d5"
PERMUTATIONS = 1000
SEED = 20261015
BUDGETS = (20, 50)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    sealed_dir = EXPERIMENT / "sealed" / RUN_ID
    seal = load_json(sealed_dir / "seal-receipt.json")
    raw_predictions = (sealed_dir / "predictions.json").read_bytes()
    predictions = json.loads(raw_predictions)
    require(seal["sealed"] and seal["prediction_sha256"] == sha256(raw_predictions).hexdigest()
            and predictions["target_map_read"] is False,
            "Прогноз не прошёл проверку seal")

    target_meta = load_json(TARGET_META)
    raw_target = TARGET_MAP.read_bytes()
    require(sha256(raw_target).hexdigest() == target_meta["file_sha256"], "Карта цели изменилась")
    target_snapshot = json.loads(raw_target)
    target_entry = {"reference": target_meta["reference"], "path": str(TARGET_MAP),
                    "file_sha256": target_meta["file_sha256"],
                    "graph_sha256": fingerprint(target_snapshot["graph"]),
                    "source_sha256": target_snapshot["source"]["sha256"]}
    target_repo = FileForecastMaps([target_entry])
    target = target_repo.get("PMC10002471", "text_reified", target_repo.owner,
                            target_meta["reference"]["run_id"])
    require(target is not None, "Оценщик не смог загрузить удержанную цель")
    truth = types_for_map(target)["transitions"]["coarse"]
    truth_ids = {shape_id(row) for row in truth}

    manifest = load_json(MANIFEST)
    repository = FileForecastMaps(manifest["sources"])
    rows = []
    for entry in manifest["sources"]:
        reference = entry["reference"]
        snapshot = repository.get(reference["article_id"], reference["pipeline_id"],
                                  repository.owner, reference["run_id"])
        require(snapshot is not None, "Карта обучения отсутствует")
        rows.append({"article_id": snapshot["article_id"],
                     "transitions": types_for_map(snapshot)["transitions"]["coarse"]})
    allowed = set(predictions["training_article_ids"])
    require(allowed == {row["article_id"] for row in rows}, "Набор обучения после seal изменился")
    allowed_mask = (1 << len(rows)) - 1
    observed = {}
    for budget in BUDGETS:
        selected = predictions["modes"]["coarse"]["graph"][str(budget)]
        observed[str(budget)] = len({shape_id(row["shape"]) for row in selected} & truth_ids)

    random_hits = {str(budget): [] for budget in BUDGETS}
    for permutation in range(PERMUTATIONS):
        support: dict[str, int] = {}
        for index, row in enumerate(rows):
            original = row["transitions"]
            targets = [item["target_type"] for item in original]
            random.Random(SEED + permutation * len(rows) + index * 7919).shuffle(targets)
            bit = 1 << index
            for transition, target_type in zip(original, targets):
                changed = {"arity": transition["arity"],
                           "source_types": transition["source_types"],
                           "target_type": target_type}
                key = baseline.shape_id(changed)
                support[key] = support.get(key, 0) | bit
        candidate_support = baseline.candidate_support(support, allowed_mask)
        order = sorted(candidate_support, key=lambda key: (-candidate_support[key], key))
        for budget in BUDGETS:
            random_hits[str(budget)].append(len(set(order[:budget]) & truth_ids))

    results = {}
    for budget in BUDGETS:
        values = sorted(random_hits[str(budget)])
        obs = observed[str(budget)]
        exceed = sum(value >= obs for value in values)
        results[str(budget)] = {
            "observed_matches": obs,
            "null_mean": sum(values) / len(values),
            "null_95th_percentile": values[round(.95 * (len(values) - 1))],
            "null_maximum": values[-1],
            "empirical_one_sided_p": (1 + exceed) / (PERMUTATIONS + 1),
            "permutation_histogram": {str(value): values.count(value) for value in sorted(set(values))},
        }
    data = {
        "version": "coarse-target-shape-permutation-1",
        "forecast_run_id": RUN_ID,
        "forecast_sha256": seal["prediction_sha256"],
        "target_article_id": target["article_id"],
        "target_map_sha256": target_entry["file_sha256"],
        "target_was_previously_read_by_codex": True,
        "permutation_count": PERMUTATIONS,
        "seed": SEED,
        "method_ru": "Внутри каждой обучающей статьи случайно перемешиваются типы заключения у сохранённых переходов; исходные типы предпосылок и распределение заключений в статье остаются неизменными.",
        "results": results,
        "model_calls": 0,
        "network_calls": 0,
    }
    output = EXPERIMENT / "evaluation" / RUN_ID / "coarse-permutation-control"
    require(not output.exists(), "Перестановочный контроль уже создан")
    output.mkdir(parents=True)
    data_raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    report = [
        "# Перестановочный контроль грубой формы перехода",
        "",
        "Проверен единственный грубый hit при @50: ограничение и два результата → заключение. В каждом обучающем источнике 1 000 раз перемешивались типы заключений между переходами, сохраняя набор предпосылок и распределение типов заключений внутри этой статьи. Для каждого перемешивания заново строились поддержанные минимум двумя источниками графовые шаблоны.",
        "",
        "| Бюджет | Реальный граф | Среднее перестановок | 95-й процентиль | Максимум | `p` |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for budget in BUDGETS:
        item = results[str(budget)]
        report.append(f"| @{budget} | {item['observed_matches']} | {item['null_mean']:.3f} | {item['null_95th_percentile']} | {item['null_maximum']} | {item['empirical_one_sided_p']:.4f} |")
    report += [
        "",
        "Этот контроль показывает, насколько часто столь же общий типовой переход возникает после разрушения конкретных направлений между узлами. Он не проверяет семантическое содержание и не доказывает причинную или научную закономерность. Целевая карта была создана Codex после чтения статьи, поэтому проверка не слепая для автора карты.",
        "",
        "Модельных и сетевых вызовов — 0.",
        "",
    ]
    report_raw = "\n".join(report).encode("utf-8")
    (output / "data.json").write_bytes(data_raw)
    (output / "report.ru.md").write_bytes(report_raw)
    verification = {
        "forecast_seal_valid": True,
        "target_map_hash_valid": True,
        "training_maps_hash_valid": True,
        "permutation_count": PERMUTATIONS,
        "model_calls": 0,
        "network_calls": 0,
        "files": {"data.json": sha256(data_raw).hexdigest(),
                  "report.ru.md": sha256(report_raw).hexdigest()},
    }
    (output / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"@20 observed={results['20']['observed_matches']}; null mean={results['20']['null_mean']:.3f}; p={results['20']['empirical_one_sided_p']:.4f}")
    print(f"@50 observed={results['50']['observed_matches']}; null mean={results['50']['null_mean']:.3f}; max={results['50']['null_maximum']}; p={results['50']['empirical_one_sided_p']:.4f}")
    print(f"report={output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
