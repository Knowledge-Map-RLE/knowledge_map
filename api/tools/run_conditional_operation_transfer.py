"""Офлайн-CLI фиксирует перенос до открытия исходов оценщику."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from application.conditional_operation_transfer import SealConditionalOperationTransfer
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.sealed_operation_transfer_corpus import SealedOperationTransferCorpus
from tools.run_free_prediction import disable_network

CODE = ('domain/conditional_operation_transfer.py', 'application/conditional_operation_transfer.py',
        'infrastructure/sealed_operation_transfer_corpus.py', 'tools/run_conditional_operation_transfer.py',
        'domain/operation_applicability.py', 'domain/article_maps.py', 'domain/comparison_normalization.py',
        'domain/evidence_origin_audit.py', 'infrastructure/sealed_forecast_corpus.py',
        'infrastructure/development_prediction_store.py', 'infrastructure/immutable_files.py',
        'infrastructure/free_prediction_snapshots.py', 'tools/run_free_prediction.py')


def main():
    parser = argparse.ArgumentParser()
    for name in ('input-run', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    disable_network()
    corpus = SealedOperationTransferCorpus(args.input_run)
    store = FilePredictionStore(args.output)
    root = Path(__file__).resolve().parents[1]
    implementation = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    result, evaluation_id, evaluation = SealConditionalOperationTransfer(corpus, store).execute(implementation)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'input-applicability.json', (corpus.root / 'predictions.json').read_bytes())
    write_immutable(folder / 'receiver-inputs.json', store.encode(result['receivers']))
    write_immutable(folder / 'input-corpus.json', store.encode({'snapshot': str(corpus.root),
                    'input_sha256': result['binding']['input_sha256'], 'model_calls': 0}))
    for name in CODE:
        write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    print(json.dumps({'run_id': result['run_id'], 'evaluation_id': evaluation_id,
        'hypotheses': {mode: sum(len(f['predictions']) for f in folds) for mode, folds in result['modes'].items()},
        'resubstitution_candidates': len(evaluation['resubstitution_diagnostic']['candidates']),
        'graph_advantage_demonstrated': False}))


if __name__ == '__main__':
    main()
