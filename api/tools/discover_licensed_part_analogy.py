"""Офлайн-CLI аналогии читает только два явных запечатанных среза и аудит происхождения."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.licensed_part_analogy import DiscoverSealedPartAnalogies
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network
from tools.run_semantic_part_forecast import CODE as PART_CODE
from tools.build_author_argument_circuits import CODE as ARGUMENT_CODE

CODE = tuple(dict.fromkeys((*PART_CODE, *ARGUMENT_CODE, 'domain/analogy_transport.py',
    'domain/licensed_part_analogy.py', 'application/licensed_part_analogy.py', 'tools/discover_licensed_part_analogy.py')))


def main():
    parser = argparse.ArgumentParser()
    for name in ('parts-runs', 'parts-run-id', 'arguments-runs', 'arguments-run-id', 'origin-audit', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network()
    parts = FilePredictionStore(args.parts_runs); arguments = FilePredictionStore(args.arguments_runs)
    output = FilePredictionStore(args.output); origin_bytes = Path(args.origin_audit).read_bytes()
    origin = json.loads(origin_bytes); root = Path(__file__).resolve().parents[1]
    implementation = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    result = DiscoverSealedPartAnalogies(parts, arguments, output).execute(
        args.parts_run_id, args.arguments_run_id, origin, implementation)
    folder = output.path(result['run_id'])
    for label, source, run in (('parts', parts, args.parts_run_id), ('arguments', arguments, args.arguments_run_id)):
        for name in ('predictions.json', 'seal.json'):
            write_immutable(folder / 'inputs' / label / name, (source.path(run) / name).read_bytes())
    write_immutable(folder / 'inputs' / 'origin-audit.json', origin_bytes)
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    write_immutable(folder / 'reads.json', output.encode({'parts_run_id': args.parts_run_id,
        'arguments_run_id': args.arguments_run_id, 'network_disabled': True, 'model_calls': 0,
        'target_read': False, 'other_maps_read': False}))
    print(json.dumps({'run_id': result['run_id'], 'blocks': result['canonical_blocks'],
        'native_statements': result['native_statements'], 'admitted_parts': result['admitted_parts'],
        'all_hypotheses': len(result['all_candidates']), 'ranked_hypotheses': len(result['ranked_candidates']),
        'rejections': result['rejection_counts'], 'confirmed_predictions': 0,
        'graph_advantage_demonstrated': False}, ensure_ascii=True))


if __name__ == '__main__': main()
