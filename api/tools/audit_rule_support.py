"""CLI анализа запечатанного прогноза; сеть и создание модельных клиентов запрещены."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.rule_support_diagnostic import SealRuleSupportDiagnostic
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/rule_support_diagnostic.py', 'domain/operator_frame_routing.py',
        'domain/article_maps.py', 'application/rule_support_diagnostic.py',
        'infrastructure/development_prediction_store.py', 'infrastructure/immutable_files.py',
        'tools/run_free_prediction.py', 'tools/audit_rule_support.py')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--forecast-store', required=True)
    parser.add_argument('--forecast-run', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network()
    root = Path(__file__).resolve().parents[1]
    code = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    store = FilePredictionStore(args.output)
    result = SealRuleSupportDiagnostic(FilePredictionStore(args.forecast_store), store).execute(args.forecast_run, code)
    for name in CODE:
        write_immutable(store.path(result['run_id']) / 'implementation' / name, (root / name).read_bytes())
    write_immutable(store.path(result['run_id']) / 'reads.json', store.encode({
        'forecast_store': str(Path(args.forecast_store).resolve()), 'forecast_run': args.forecast_run,
        'source_maps_read': False, 'target_read': False, 'network_disabled': True, 'model_calls': 0}))
    print(json.dumps({'run_id': result['run_id'], 'blocks': result['canonical_blocks'],
        'exact_rules': result['supported_exact_rules'],
        'diagnostic_shapes': {mode: {key: data[key] for key in ('shape_count', 'multi_publication_shape_count', 'multi_primary_shape_count')}
                              for mode, data in result['modes'].items()},
        'new_predictions': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
