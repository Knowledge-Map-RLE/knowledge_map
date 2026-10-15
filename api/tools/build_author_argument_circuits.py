"""Автономный CLI полных авторских цепочек: только явные источники, без сети и AI."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.author_argument_circuits import SealAuthorArgumentCircuits
from domain.article_maps import require, fingerprint
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network
from tools.build_semantic_operator_graph import CODE as GRAPH_CODE

CODE = (*GRAPH_CODE, 'domain/author_argument_circuits.py', 'domain/knowledge_development.py', 'domain/evidence_origin_audit.py',
    'domain/whole_map_input_audit.py', 'application/author_argument_circuits.py',
    'application/ports/article_comparisons.py', 'application/ports/development_prediction.py',
    'tools/build_author_argument_circuits.py')


def main():
    parser = argparse.ArgumentParser()
    for name in ('sources', 'context-audit', 'origin-audit', 'output'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--exclude-source-sha256', action='append', required=True)
    args = parser.parse_args(); disable_network()
    raw = Path(args.sources).read_bytes(); manifest = json.loads(raw)
    audit_bytes = {n: Path(getattr(args, n.replace('-', '_'))).read_bytes() for n in ('context-audit', 'origin-audit')}
    audits = {n: json.loads(data) for n, data in audit_bytes.items()}
    maps = FileForecastMaps(manifest['sources']); store = FilePredictionStore(args.output)
    api = Path(__file__).resolve().parents[1]
    implementation = {name: sha256((api / name).read_bytes()).hexdigest() for name in CODE}
    metadata = {**manifest['metadata'], 'model_calls': 0, 'target_read': False,
        'source_manifest_sha256': sha256(raw).hexdigest(), 'excluded_source_sha256': args.exclude_source_sha256,
        'source_dates': {r['reference']['article_id']: r['published_on'] for r in manifest['sources']},
        'input_audit_file_sha256': {name: sha256(data).hexdigest() for name, data in audit_bytes.items()}}
    result = SealAuthorArgumentCircuits(maps, store).execute([r['reference'] for r in manifest['sources']],
        maps.owner, metadata, implementation, audits['context-audit'], audits['origin-audit'])
    folder = store.path(result['run_id'])
    write_immutable(folder / 'source-manifest.json', raw)
    for name, data in audit_bytes.items(): write_immutable(folder / (name + '.json'), data)
    inputs = []
    for entry in manifest['sources']:
        content = Path(entry['path']).read_bytes()
        require(sha256(content).hexdigest() == entry['file_sha256'], 'Input map changed after circuit construction')
        name = 'inputs/maps/' + fingerprint(entry['reference']) + '.json'
        write_immutable(folder / name, content)
        item = {'reference': entry['reference'], 'map_path': name, 'map_file_sha256': entry['file_sha256']}
        if 'coverage_artifact' in entry:
            data = Path(entry['coverage_artifact']['path']).read_bytes()
            require(sha256(data).hexdigest() == entry['coverage_artifact']['sha256'], 'Input coverage changed')
            path = 'inputs/coverage/' + fingerprint(entry['reference']) + '.json'
            write_immutable(folder / path, data)
            item.update({'coverage_path': path, 'coverage_sha256': entry['coverage_artifact']['sha256']})
        inputs.append(item)
    write_immutable(folder / 'inputs-manifest.json', store.encode({'sources': inputs, 'target_read': False, 'model_calls': 0}))
    write_immutable(folder / 'reads.json', store.encode({'reads': maps.reads, 'network_disabled': True, 'model_calls': 0, 'target_read': False}))
    for name in CODE: write_immutable(folder / 'implementation' / name, (api / name).read_bytes())
    circuits = result['argument_circuits']
    print(json.dumps({'run_id': result['run_id'], 'blocks': circuits['canonical_blocks'], 'occurrences': circuits['visible_occurrences'],
        'groups': len(circuits['groups']), 'depth': circuits['maximum_depth'], 'counts': circuits['counts'],
        'forms': circuits['transition_forms'], 'incomplete_evidence': circuits['transition_evidence_incomplete'],
        'new_predictions': 0, 'scientific_success': False}, ensure_ascii=False))


if __name__ == '__main__': main()
