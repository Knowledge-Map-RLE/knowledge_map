"""Офлайн-аудит всех авторских групп перед обучением типов научных операций."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from application.author_operator_eligibility import AuditSealedAuthorOperators
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from domain.semantic_part_forecast import LIMITS
from tools.run_free_prediction import disable_network

CODE = ('domain/author_operator_eligibility.py', 'application/author_operator_eligibility.py',
        'tools/audit_author_operators.py', 'domain/semantic_part_forecast.py')


def main():
    parser = argparse.ArgumentParser()
    for name in ('sources', 'source-run', 'output'): parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network(); source = FilePredictionStore(args.sources)
    output = FilePredictionStore(args.output); api = Path(__file__).resolve().parents[1]
    code = {name: sha256((api / name).read_bytes()).hexdigest() for name in CODE}
    result = AuditSealedAuthorOperators(source, output).execute(args.source_run, LIMITS['max_premise_parents'], code)
    folder = output.path(result['run_id']); original = source.path(args.source_run)
    for name in ('predictions.json', 'seal.json'): write_immutable(folder / 'inputs/source' / name, (original / name).read_bytes())
    for name in CODE: write_immutable(folder / 'implementation' / name, (api / name).read_bytes())
    write_immutable(folder / 'reads.json', output.encode({'model_calls': 0, 'network_disabled': True,
        'source_run_id': args.source_run, 'other_maps_read': False, 'future_outcomes_read': False}))
    print(json.dumps({'run_id': result['run_id'], 'groups': len(result['rows']), 'counts': result['counts'],
                      'arity_counts': result['arity_counts'], 'oversized': result['groups_above_previous_arity']}, ensure_ascii=True))


if __name__ == '__main__': main()
