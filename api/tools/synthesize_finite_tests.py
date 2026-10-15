"""Синтез конечных наборов через административный CLI, без сети и AI-клиентов."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.finite_test_synthesis import SynthesizeSealedFiniteTests
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.reason_quantified_evidence import CODE as QUANTITATIVE_CODE
from tools.run_free_prediction import disable_network

CODE = (*QUANTITATIVE_CODE, 'domain/finite_test_synthesis.py', 'application/finite_test_synthesis.py',
        'tools/synthesize_finite_tests.py')


def main():
    parser = argparse.ArgumentParser()
    for name in ('source-runs', 'source-run-id', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network()
    sources, output = FilePredictionStore(args.source_runs), FilePredictionStore(args.output)
    root = Path(__file__).resolve().parents[1]
    implementation = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    result = SynthesizeSealedFiniteTests(sources, output).execute(args.source_run_id, implementation)
    folder = output.path(result['run_id']); source = sources.path(args.source_run_id)
    for name in ('predictions.json', 'seal.json'):
        write_immutable(folder / 'inputs' / name, (source / name).read_bytes())
    for name in CODE:
        write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    write_immutable(folder / 'reads.json', output.encode({'source_run_id': args.source_run_id,
                    'network_disabled': True, 'model_calls': 0, 'target_read': False, 'other_maps_read': False}))
    print(json.dumps({'run_id': result['run_id'], 'groups': len(result['author_groups']),
                      'counts': result['counts'], 'baseline_sets': len(result['semantic_sets_without_author_groups']),
                      'new_predictions': 0, 'scientific_success': False}, ensure_ascii=True))


if __name__ == '__main__':
    main()
