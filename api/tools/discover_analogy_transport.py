"""Офлайн-CLI сохраняет точные входы и реализацию без сети и модельных клиентов."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.analogy_transport import SealAnalogyTransport
from domain.article_maps import fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network
from tools.run_semantic_part_forecast import CODE as PART_CODE

CODE = (*PART_CODE, 'domain/analogy_transport.py', 'application/analogy_transport.py',
        'tools/discover_analogy_transport.py')


def main():
    parser = argparse.ArgumentParser()
    for name in ('sources', 'context-audit', 'origin-audit', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(); disable_network()
    raw = Path(args.sources).read_bytes(); manifest = json.loads(raw)
    audit_bytes = {name: Path(getattr(args, name.replace('-', '_'))).read_bytes()
                   for name in ('context-audit', 'origin-audit')}
    audits = {name: json.loads(value) for name, value in audit_bytes.items()}
    root = Path(__file__).resolve().parents[1]
    code = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    metadata = {**manifest['metadata'], 'model_calls': 0, 'source_manifest_sha256': sha256(raw).hexdigest(),
        'source_dates': {s['reference']['article_id']: s['published_on'] for s in manifest['sources']},
        'input_audit_file_sha256': {name: sha256(value).hexdigest() for name, value in audit_bytes.items()}}
    port = FileForecastMaps(manifest['sources']); store = FilePredictionStore(args.output)
    result = SealAnalogyTransport(port, store).execute([s['reference'] for s in manifest['sources']],
        {s['reference']['article_id']: s['family'] for s in manifest['sources']}, port.owner, metadata, code,
        audits['context-audit'], audits['origin-audit'])
    folder = store.path(result['run_id']); inputs = []
    write_immutable(folder / 'source-manifest.json', raw)
    for name, value in audit_bytes.items(): write_immutable(folder / (name + '.json'), value)
    for source in manifest['sources']:
        content = Path(source['path']).read_bytes()
        require(sha256(content).hexdigest() == source['file_sha256'], 'Analogy input changed after discovery')
        identifier = fingerprint(source['reference']); name = 'inputs/maps/' + identifier + '.json'
        write_immutable(folder / name, content)
        entry = {'reference': source['reference'], 'map_path': name, 'map_file_sha256': source['file_sha256']}
        if 'coverage_artifact' in source:
            artifact = source['coverage_artifact']; content = Path(artifact['path']).read_bytes()
            require(sha256(content).hexdigest() == artifact['sha256'], 'Analogy coverage changed after discovery')
            name = 'inputs/coverage/' + identifier + '.json'; write_immutable(folder / name, content)
            entry.update(coverage_path=name, coverage_sha256=artifact['sha256'])
        inputs.append(entry)
    write_immutable(folder / 'inputs-manifest.json', store.encode({'sources': inputs, 'model_calls': 0, 'target_read': False}))
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    write_immutable(folder / 'reads.json', store.encode({'reads': port.reads, 'model_calls': 0,
        'target_read': False, 'network_disabled': True}))
    print(json.dumps({'run_id': result['run_id'], 'blocks': result['canonical_blocks'],
        'pool_counts': result['pool_counts'], 'steps': result['search_steps'], 'view_decisions': result['view_decisions']}, ensure_ascii=True))


if __name__ == '__main__': main()
