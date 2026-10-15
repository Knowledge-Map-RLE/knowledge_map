"""Фиксирует очередь проверки явных логических посылок на всём корпусе."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path

from application.categorical_candidate_discovery import RunCategoricalCandidateDiscovery
from infrastructure.categorical_candidate_inputs import FileCategoricalCandidateInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = (
    "domain/categorical_candidate_discovery.py",
    "application/categorical_candidate_discovery.py",
    "infrastructure/categorical_candidate_inputs.py",
    "tools/audit_full_corpus_categorical_candidates.py",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    disable_network()
    logging.basicConfig(level=logging.INFO)
    api_root = Path(__file__).resolve().parents[1]
    base_run = Path(args.base_run).resolve()
    inputs = FileCategoricalCandidateInputs(base_run)
    implementation = {name: sha256((api_root / name).read_bytes()).hexdigest() for name in CODE}
    store = FilePredictionStore(args.output)
    result = RunCategoricalCandidateDiscovery(inputs, store, implementation).execute()
    folder = store.path(result["run_id"])
    write_immutable(folder / "input-corpus.json", store.encode({"base_run": str(base_run)}))
    write_immutable(folder / "source-manifest.json", (base_run / "source-manifest.json").read_bytes())
    for name, digest in implementation.items():
        data = (api_root / name).read_bytes()
        if sha256(data).hexdigest() != digest:
            raise RuntimeError("Implementation changed while the audit was running")
        write_immutable(folder / "implementation" / name, data)
    report = result["report_ru_md"].encode("utf-8")
    write_immutable(folder / "review-v1" / "report.ru.md", report)
    verification = {
        "version": "full-corpus-categorical-screen-verification-2",
        "run_id": result["run_id"],
        "source_count": result["source_count"],
        "canonical_blocks": result["audit"]["canonical_blocks"],
        "candidate_statements": result["audit"]["candidate_statement_count"],
        "definition_kind_candidate_count": result["audit"]["definition_kind_candidate_count"],
        "unique_candidate_parent_blocks": result["audit"]["unique_candidate_parent_blocks"],
        "categorical_relation_without_quantifier_count": result["audit"]["categorical_relation_without_quantifier_count"],
        "quantifier_without_categorical_relation_count": result["audit"]["quantifier_without_categorical_relation_count"],
        "explicit_relation_and_quantifier": result["audit"]["explicit_relation_and_quantifier_count"],
        "licensed_inferences": result["audit"]["licensed_inferences"],
        "new_empirical_predictions": result["audit"]["new_empirical_predictions"],
        "report_ru_sha256": sha256(report).hexdigest(),
        "implementation": implementation,
        "model_calls": 0,
        "network_calls": 0,
        "target_article_included": False,
    }
    write_immutable(folder / "review-v1" / "verification.json",
                    (json.dumps(verification, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == "__main__":
    main()
