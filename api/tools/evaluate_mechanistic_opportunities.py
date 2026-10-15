"""Оценка фиксированного прогона без сети, AI-клиентов и доступа к обучающим картам."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.mechanistic_evaluation import EvaluateMechanisticOpportunities
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.mechanistic_controls import FileMechanisticControls
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/mechanistic_evaluation.py', 'application/mechanistic_evaluation.py',
        'application/ports/mechanistic_evaluation.py', 'application/ports/development_prediction.py',
        'infrastructure/mechanistic_controls.py', 'infrastructure/development_prediction_store.py',
        'infrastructure/immutable_files.py', 'domain/article_maps.py', 'tools/run_free_prediction.py',
        'tools/evaluate_mechanistic_opportunities.py')


def main():
    parser = argparse.ArgumentParser()
    for flag in ('forecast-store', 'run-id', 'plan', 'controls', 'control-id'): parser.add_argument('--' + flag, required=True)
    args = parser.parse_args(); disable_network()
    plan = json.loads(Path(args.plan).read_text(encoding='utf8'))
    controls = FileMechanisticControls(json.loads(Path(args.controls).read_text(encoding='utf8')))
    store = FilePredictionStore(args.forecast_store); api = Path(__file__).resolve().parents[1]
    implementation = {name: sha256((api / name).read_bytes()).hexdigest() for name in CODE}
    result = EvaluateMechanisticOpportunities(store, controls).execute(args.run_id, plan, args.control_id, implementation)
    folder = store.path(args.run_id) / 'evaluation-artifacts' / result['evaluation_id']
    for name in CODE: write_immutable(folder / 'implementation' / name, (api / name).read_bytes())
    write_immutable(folder / 'plan.json', Path(args.plan).read_bytes())
    write_immutable(folder / 'reads.json', store.encode({'reads': controls.reads, 'network_disabled': True, 'model_calls': 0}))
    print(json.dumps({'evaluation_id': result['evaluation_id'], 'modes': {k: v['counts'] for k, v in result['modes'].items()},
                      'scientific_success': False, 'graph_advantage_demonstrated': False}))


if __name__ == '__main__': main()
