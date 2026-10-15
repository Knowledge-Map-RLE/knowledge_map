"""Административный офлайн-CLI интервальных следствий и полного парного обучения."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
from application.interval_knowledge import SealIntervalKnowledge
from infrastructure.interval_knowledge import FileIntervalInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_typed_participant_forecast import CODE as UPSTREAM_CODE
from tools.run_free_prediction import disable_network

CODE = tuple(sorted(set(UPSTREAM_CODE) | {'domain/interval_knowledge.py', 'application/interval_knowledge.py',
    'infrastructure/interval_knowledge.py', 'tools/run_interval_knowledge.py', 'tools/prepare_interval_knowledge.py'}))


def main():
    parser = argparse.ArgumentParser()
    for f in ('input-run', 'audit', 'output'): parser.add_argument('--' + f, required=True)
    args = parser.parse_args(); disable_network(); logging.basicConfig(level=logging.INFO)
    inputs, store = FileIntervalInputs(args.input_run, args.audit), FilePredictionStore(args.output)
    root = Path(__file__).resolve().parents[1]; implementation = {f: sha256((root / f).read_bytes()).hexdigest() for f in CODE}
    result = SealIntervalKnowledge(inputs, store).execute(implementation)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'audit.json', Path(args.audit).read_bytes())
    write_immutable(folder / 'input-corpus.json', store.encode({'baseline': str(inputs.root)}))
    for f in CODE: write_immutable(folder / 'implementation' / f, (root / f).read_bytes())
    print(json.dumps({'run_id': result['run_id'], 'blocks': result['canonical_blocks'], 'parts': result['licensed_parts'],
        'interval_consequences': len(result['interval_consequences']), 'projected_parts': len(result['projected_views']),
        'policies': {p: {m: {'rules': len(r.get('rules', [])), 'predictions': len(r['predictions']),
            'rejected_numeric': r.get('learning', {}).get('rejected', {}).get('unmodelled_numeric_conclusion', 0)}
            for m, r in modes.items()} for p, modes in result['policies'].items()}}))


if __name__ == '__main__': main()
