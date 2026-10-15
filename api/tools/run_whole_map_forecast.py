"""CLI читает только заданные карты; сеть и модельные вызовы запрещены."""
import argparse
import json
from pathlib import Path
from hashlib import sha256
from application.whole_map_forecast import SealWholeMapForecast
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/categorical_licenses.py', 'domain/categorical_logic.py', 'domain/whole_map_categorical.py', 'domain/evidence_origin_audit.py', 'domain/whole_map_provenance.py', 'domain/whole_map_input_audit.py', 'domain/whole_map_forecast.py', 'domain/forecast_attribute_kinds.py', 'domain/whole_map_context.py', 'domain/whole_map_ablation.py', 'domain/whole_map_numeric.py', 'domain/statistical_primitives.py', 'domain/statistical_model_views.py', 'domain/statistical_context_audit.py', 'domain/statistical_context_views.py', 'application/whole_map_forecast.py',
        'domain/comparison_normalization.py', 'domain/development_prediction.py',
        'infrastructure/free_prediction_snapshots.py', 'infrastructure/development_prediction_store.py',
        'tools/run_whole_map_forecast.py')
CODE += ('domain/protocol_parameter_transfer.py',)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--context-audit')
    parser.add_argument('--model-audit')
    parser.add_argument('--origin-audit')
    parser.add_argument('--categorical-licenses')
    args = parser.parse_args()
    disable_network()
    manifest_raw = Path(args.sources).read_bytes()
    manifest = json.loads(manifest_raw)
    context_audit = json.loads(Path(args.context_audit).read_text(encoding='utf8')) if args.context_audit else None
    model_audit = json.loads(Path(args.model_audit).read_text(encoding='utf8')) if args.model_audit else None
    origin_audit = json.loads(Path(args.origin_audit).read_text(encoding='utf8')) if args.origin_audit else None
    categorical_licenses = json.loads(Path(args.categorical_licenses).read_text(encoding='utf8')) if args.categorical_licenses else None
    maps = FileForecastMaps(manifest['sources'])
    api = Path(__file__).resolve().parents[1]
    implementation = {name: sha256((api / name).read_bytes()).hexdigest() for name in CODE}
    store = FilePredictionStore(args.output)
    result = SealWholeMapForecast(maps, store).execute([s['reference'] for s in manifest['sources']],
        {s['reference']['article_id']: s['family'] for s in manifest['sources']}, maps.owner,
        {**manifest['metadata'], 'source_manifest_sha256': sha256(manifest_raw).hexdigest(), 'source_dates': {s['reference']['article_id']: s['published_on'] for s in manifest['sources']}}, implementation, context_audit, model_audit, origin_audit, categorical_licenses)
    write_immutable(store.path(result['run_id']) / 'source-manifest.json', manifest_raw)
    for entry in manifest['sources']:
        if 'coverage_artifact' in entry:
            write_immutable(store.path(result['run_id']) / 'source-coverage' / (entry['reference']['article_id'] + '.json'), Path(entry['coverage_artifact']['path']).read_bytes())
    if context_audit:
        write_immutable(store.path(result['run_id']) / 'context-audit.json', store.encode(context_audit))
    if model_audit:
        write_immutable(store.path(result['run_id']) / 'model-audit.json', store.encode(model_audit))
    if origin_audit:
        write_immutable(store.path(result['run_id']) / 'origin-audit.json', store.encode(origin_audit))
    if categorical_licenses:
        write_immutable(store.path(result['run_id']) / 'categorical-licenses.json', store.encode(categorical_licenses))
    for name in CODE:
        write_immutable(store.path(result['run_id']) / 'implementation' / name, (api / name).read_bytes())
    write_immutable(store.path(result['run_id']) / 'reads.json', store.encode({'reads': maps.reads,
        'network_disabled': True, 'model_calls': 0, 'target_read': False}))
    print(json.dumps({'run_id': result['run_id'], 'blocks': result['canonical_blocks'],
        'eligible': sum(c['eligible'] for c in result['coverage']), 'rules': len(result['rules']),
        'candidates': {k: len(v) for k, v in result['predictions'].items()},
        'numeric_consequences': len(result['numeric_consequences']['proofs']),
        'categorical_admitted': result['categorical_inference']['admitted_blocks'],
        'categorical_consequences': {k: len(v) for k, v in result['categorical_inference']['consequences'].items()},
        'licensed_categorical_status': result['licensed_categorical_inference']['status'],
        'licensed_categorical_consequences': ({k: len(v) for k, v in result['licensed_categorical_inference']['consequences'].items()}
            if result['licensed_categorical_inference']['status'] == 'source_definitions_licensed' else None),
        'diagnostics': {k: result['learning'][k] for k in ('rejected', 'unsupported_templates')}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
