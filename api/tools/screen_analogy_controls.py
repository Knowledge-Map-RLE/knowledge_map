"""Проверка локально сохранённых контролей без сети и AI-клиентов."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.analogy_control_screen import SealAnalogyControlScreen
from domain.article_maps import require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/analogy_control_screen.py', 'application/analogy_control_screen.py', 'tools/screen_analogy_controls.py',
        'domain/article_maps.py', 'infrastructure/development_prediction_store.py', 'infrastructure/immutable_files.py',
        'tools/run_free_prediction.py')


def main():
    parser = argparse.ArgumentParser()
    for field in ('forecast-root', 'forecast-run', 'registry', 'sources', 'annotation', 'output'):
        parser.add_argument('--' + field, required=True)
    args = parser.parse_args(); disable_network()
    forecast = FilePredictionStore(args.forecast_root).read_seal(args.forecast_run)
    require(forecast is not None, 'Explicit sealed forecast required')
    training_forecast = json.loads((FilePredictionStore(args.forecast_root).path(args.forecast_run) / 'forecast.json').read_bytes())
    raw_registry = Path(args.registry).read_bytes(); registry = json.loads(raw_registry)
    raw_annotation = Path(args.annotation).read_bytes(); annotation = json.loads(raw_annotation)
    raw_manifest = Path(args.sources).read_bytes(); manifest = json.loads(raw_manifest)
    packets = {}; raws = {}
    for item in manifest['sources']:
        raw = Path(item['path']).read_bytes(); require(sha256(raw).hexdigest() == item['file_sha256'], 'Full control file changed')
        require(item['id'] not in packets, 'Repeated full control source')
        packets[item['id']] = json.loads(raw); raws[item['id']] = raw
    root = Path(__file__).resolve().parents[1]; code = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    store = FilePredictionStore(args.output)
    result = SealAnalogyControlScreen(store).execute(forecast, registry, packets, annotation, training_forecast, code)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'forecast.json', store.encode(forecast))
    write_immutable(folder / 'training-forecast.json', store.encode(training_forecast))
    write_immutable(folder / 'registry.json', raw_registry); write_immutable(folder / 'annotation.json', raw_annotation)
    write_immutable(folder / 'source-manifest.json', raw_manifest)
    for sid, raw in raws.items(): write_immutable(folder / 'controls' / (sid + '.json'), raw)
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    print(json.dumps({'run_id': result['run_id'], 'records': result['specific_later_records'],
        'controls_read': len(packets), 'eligible': result['eligible_protocol_comparisons'], 'confirmed': 0}))


if __name__ == '__main__': main()
