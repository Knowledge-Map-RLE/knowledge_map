"""Запечатывает проверку протоколов без сети, моделей и изменения научных карт."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.analogy_protocol_evidence import SealAnalogyProtocolEvidence
from domain.article_maps import require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ('domain/analogy_protocol_evidence.py', 'application/analogy_protocol_evidence.py',
        'tools/audit_analogy_protocols.py', 'domain/article_maps.py', 'infrastructure/development_prediction_store.py',
        'infrastructure/immutable_files.py', 'tools/run_free_prediction.py')


def main():
    parser = argparse.ArgumentParser()
    for field in ('forecast-root', 'forecast-run', 'sources', 'audit', 'output'): parser.add_argument('--' + field, required=True)
    args = parser.parse_args(); disable_network()
    baseline = FilePredictionStore(args.forecast_root).read_seal(args.forecast_run)
    require(baseline is not None, 'Explicit sealed analogy forecast required')
    raw_manifest = Path(args.sources).read_bytes(); manifest = json.loads(raw_manifest)
    audit_raw = Path(args.audit).read_bytes(); audit = json.loads(audit_raw)
    packets = {}; source_bytes = {}
    for entry in manifest['sources']:
        raw = Path(entry['path']).read_bytes(); require(sha256(raw).hexdigest() == entry['file_sha256'], 'Protocol packet file changed')
        require(entry['id'] not in packets, 'Repeated protocol packet')
        packets[entry['id']] = json.loads(raw); source_bytes[entry['id']] = raw
    root = Path(__file__).resolve().parents[1]; code = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    store = FilePredictionStore(args.output); result = SealAnalogyProtocolEvidence(store).execute(baseline, packets, audit, code)
    folder = store.path(result['run_id'])
    write_immutable(folder / 'audit.json', audit_raw); write_immutable(folder / 'source-manifest.json', raw_manifest)
    write_immutable(folder / 'forecast.json', store.encode(baseline))
    for name, raw in source_bytes.items(): write_immutable(folder / 'sources' / (sha256(name.encode()).hexdigest() + '.json'), raw)
    write_immutable(folder / 'source-index.json', store.encode({name: 'sources/' + sha256(name.encode()).hexdigest() + '.json' for name in packets}))
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    write_immutable(folder / 'reads.json', store.encode({'sources': list(packets), 'forecast_run': args.forecast_run,
        'network_disabled': True, 'model_calls': 0, 'target_read': False}))
    print(json.dumps({'run_id': result['run_id'], 'findings': len(result['findings']), 'reviewed': result['candidate_count'],
        'confirmed_transfers': result['confirmed_transfers'], 'model_calls': 0}))


if __name__ == '__main__': main()
