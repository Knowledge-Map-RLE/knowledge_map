"""Офлайн-CLI проверяет протоколы только из снимка исходного корпуса."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.analogy_protocol_reconciliation import ReconcileSealedAnalogyProtocols
from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.discover_licensed_part_analogy import CODE as ANALOGY_CODE
from tools.run_free_prediction import disable_network

CODE = (*ANALOGY_CODE, 'domain/analogy_protocol_reconciliation.py',
    'application/analogy_protocol_reconciliation.py', 'tools/reconcile_part_analogy_protocols.py')


def main():
    parser = argparse.ArgumentParser()
    for name in ('forecasts', 'run-id', 'annotation', 'output'): parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network(); source = FilePredictionStore(args.forecasts)
    forecast = source.read_seal(args.run_id); require(forecast is not None, 'Explicit analogy source missing')
    folder = source.path(args.run_id); raw = (folder / 'inputs/arguments/predictions.json').read_bytes()
    arguments = json.loads(raw)
    require(fingerprint(arguments) == forecast['binding']['arguments_artifact_sha256'], 'Argument source changed')
    seal = json.loads((folder / 'inputs/arguments/seal.json').read_bytes())
    require(seal['prediction_sha256'] == fingerprint(arguments), 'Argument seal changed')
    annotation_bytes = Path(args.annotation).read_bytes(); annotation = json.loads(annotation_bytes)
    root = Path(__file__).resolve().parents[1]; output = FilePredictionStore(args.output)
    code = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    result = ReconcileSealedAnalogyProtocols(source, output).execute(args.run_id, arguments, annotation, code)
    out = output.path(result['run_id'])
    for name in ('predictions.json', 'seal.json'): write_immutable(out / 'inputs/forecast' / name, (folder / name).read_bytes())
    write_immutable(out / 'inputs/arguments.json', raw); write_immutable(out / 'inputs/annotation.json', annotation_bytes)
    for name in CODE: write_immutable(out / 'implementation' / name, (root / name).read_bytes())
    write_immutable(out / 'reads.json', output.encode({'forecast_run_id': args.run_id, 'network_disabled': True,
        'other_sources_read': False, 'model_calls': 0, 'target_read': False}))
    print(json.dumps({'run_id': result['run_id'], 'candidates': result['all_candidates_reviewed'], 'counts': result['counts'],
        'budget': len(result['original_budget_slots']), 'confirmed': 0}, ensure_ascii=True))


if __name__ == '__main__': main()
