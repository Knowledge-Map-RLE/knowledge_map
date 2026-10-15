"""Адресный запуск по запечатанным прошлым данным, без сети и AI-клиентов."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.analogy_hypothesis_plan import SealAnalogyHypothesisPlan
from domain.article_maps import require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/analogy_hypothesis_plan.py', 'application/analogy_hypothesis_plan.py',
        'tools/seal_analogy_hypotheses.py', 'domain/article_maps.py',
        'infrastructure/development_prediction_store.py', 'infrastructure/immutable_files.py', 'tools/run_free_prediction.py')


def main():
    parser = argparse.ArgumentParser()
    for field in ('forecast-root', 'forecast-run', 'audit-root', 'audit-run', 'plan', 'output'):
        parser.add_argument('--' + field, required=True)
    args = parser.parse_args(); disable_network()
    forecast = FilePredictionStore(args.forecast_root).read_seal(args.forecast_run)
    audit = FilePredictionStore(args.audit_root).read_seal(args.audit_run)
    require(forecast is not None and audit is not None, 'Explicit sealed inputs required')
    raw = Path(args.plan).read_bytes(); plan = json.loads(raw)
    root = Path(__file__).resolve().parents[1]
    code = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    store = FilePredictionStore(args.output)
    result = SealAnalogyHypothesisPlan(store).execute(forecast, audit, plan, code)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'plan.json', raw)
    write_immutable(folder / 'forecast.json', store.encode(forecast))
    write_immutable(folder / 'protocol-audit.json', store.encode(audit))
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    write_immutable(folder / 'reads.json', store.encode({'forecast_run': args.forecast_run, 'audit_run': args.audit_run,
        'network_disabled': True, 'model_calls': 0, 'target_read': False}))
    print(json.dumps({'run_id': result['run_id'], 'hypotheses': result['hypothesis_count'],
                      'scored': result['future_results_scored'], 'model_calls': 0}))


if __name__ == '__main__': main()
