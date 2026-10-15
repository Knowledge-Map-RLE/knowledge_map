"""Офлайн-CLI фиксирует внешние гипотезы перед отдельной оценкой исходов."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from application.external_operation_transfer import SealExternalOperationTransfer
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.external_operation_inputs import SealedExternalTrainingCorpus, FileExternalReceivers, FileExternalOutcomes
from infrastructure.immutable_files import write_immutable
from tools.run_conditional_operation_transfer import CODE as UPSTREAM_CODE
from tools.run_free_prediction import disable_network

CODE = tuple(sorted(set(UPSTREAM_CODE) | {
    'domain/external_operation_transfer.py', 'application/external_operation_transfer.py',
    'application/ports/development_prediction.py', 'infrastructure/external_operation_inputs.py',
    'tools/run_external_operation_transfer.py', 'tools/prepare_external_operation_receivers.py',
    'tools/acquire_operation_transfer_source.py', 'infrastructure/primary_article_xml.py',
}))


def main():
    parser = argparse.ArgumentParser()
    for field in ('input-run', 'source', 'methods', 'outcomes', 'output'):
        parser.add_argument('--' + field, required=True)
    args = parser.parse_args(); disable_network()
    root = Path(__file__).resolve().parents[1]
    implementation = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    training = SealedExternalTrainingCorpus(args.input_run)
    receivers = FileExternalReceivers(args.methods, args.source)
    outcomes = FileExternalOutcomes(args.outcomes, args.source)
    store = FilePredictionStore(args.output)
    result, evaluation_id, evaluation = SealExternalOperationTransfer(training, receivers, outcomes, store).execute(implementation)
    folder = store.path(result['run_id'])
    for name, path in (('external-source.json', args.source), ('external-methods.json', args.methods),
                       ('external-outcomes.json', args.outcomes)):
        write_immutable(folder / name, Path(path).read_bytes())
    write_immutable(folder / 'input-corpus.json', store.encode({'snapshot': str(training.root),
        'input_sha256': result['binding']['input_sha256'], 'model_calls': 0}))
    for name in CODE:
        write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    print(json.dumps({'run_id': result['run_id'], 'evaluation_id': evaluation_id,
        'hypotheses': {mode: sum(len(f['predictions']) for f in folds) for mode, folds in result['modes'].items()},
        'coarse_direction_matches': {mode: sum(r['coarse_direction_matches'] for r in rows) for mode, rows in evaluation['modes'].items()},
        'scientific_confirmations': 0, 'graph_advantage_demonstrated': False}))


if __name__ == '__main__': main()
