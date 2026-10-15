"""Административный CLI явного корпуса без сети и модельных клиентов."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.semantic_part_forecast import SealSemanticPartForecast
from domain.article_maps import fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network
from tools.run_whole_map_forecast import CODE as FRAME_CODE

CODE = (*FRAME_CODE, 'domain/semantic_part_projection.py', 'domain/compound_part_licenses.py', 'domain/semantic_part_forecast.py',
        'domain/method_clause_projection.py',
        'domain/operation_role_bindings.py',
        'domain/qualitative_result_projection.py',
        'domain/article_maps.py', 'application/semantic_part_forecast.py',
        'infrastructure/immutable_files.py', 'tools/run_free_prediction.py', 'tools/run_semantic_part_forecast.py')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', required=True)
    parser.add_argument('--context-audit', required=True)
    parser.add_argument('--model-audit', required=True)
    parser.add_argument('--origin-audit', required=True)
    parser.add_argument('--compound-licenses')
    parser.add_argument('--method-clauses')
    parser.add_argument('--role-bindings')
    parser.add_argument('--without-protocol-parameters', action='store_true', help='Явный контроль без операции передачи параметров')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(); disable_network()
    raw = Path(args.sources).read_bytes(); manifest = json.loads(raw)
    audit_bytes = {name: Path(getattr(args, name.replace('-', '_'))).read_bytes()
                   for name in ('context-audit', 'model-audit', 'origin-audit')}
    if args.compound_licenses:
        audit_bytes['compound-licenses'] = Path(args.compound_licenses).read_bytes()
    if args.method_clauses:
        audit_bytes['method-clauses'] = Path(args.method_clauses).read_bytes()
    if args.role_bindings:
        audit_bytes['role-bindings'] = Path(args.role_bindings).read_bytes()
    audits = {name: json.loads(value) for name, value in audit_bytes.items()}
    port = FileForecastMaps(manifest['sources']); store = FilePredictionStore(args.output)
    root = Path(__file__).resolve().parents[1]
    code = {name: sha256((root / name).read_bytes()).hexdigest() for name in CODE}
    metadata = {**manifest['metadata'], 'model_calls': 0, 'source_manifest_sha256': sha256(raw).hexdigest(),
                'protocol_parameters_enabled': not args.without_protocol_parameters,
                'input_audit_file_sha256': {name: sha256(value).hexdigest() for name, value in audit_bytes.items()},
                'source_dates': {s['reference']['article_id']: s['published_on'] for s in manifest['sources']}}
    result = SealSemanticPartForecast(port, store).execute([s['reference'] for s in manifest['sources']],
        {s['reference']['article_id']: s['family'] for s in manifest['sources']}, port.owner, metadata, code,
        audits['context-audit'], audits['model-audit'], audits['origin-audit'], audits.get('compound-licenses'), audits.get('method-clauses'), audits.get('role-bindings'))
    folder = store.path(result['run_id'])
    write_immutable(folder / 'source-manifest.json', raw)
    for name, value in audit_bytes.items(): write_immutable(folder / (name + '.json'), value)
    inputs = []
    for source in manifest['sources']:
        # Имена задаются хешем ссылки: article_id не используется как файловый путь.
        identifier = fingerprint(source['reference'])
        content = Path(source['path']).read_bytes()
        require(sha256(content).hexdigest() == source['file_sha256'], 'Input map changed after forecast')
        name = 'inputs/maps/' + identifier + '.json'
        write_immutable(folder / name, content)
        entry = {'reference': source['reference'], 'map_path': name, 'map_file_sha256': source['file_sha256']}
        if 'coverage_artifact' in source:
            coverage = Path(source['coverage_artifact']['path']).read_bytes()
            require(sha256(coverage).hexdigest() == source['coverage_artifact']['sha256'], 'Input coverage changed after forecast')
            cname = 'inputs/coverage/' + identifier + '.json'
            write_immutable(folder / cname, coverage)
            entry.update({'coverage_path': cname, 'coverage_sha256': source['coverage_artifact']['sha256']})
        inputs.append(entry)
    write_immutable(folder / 'inputs-manifest.json', store.encode({'sources': inputs, 'model_calls': 0, 'target_read': False}))
    for name in CODE: write_immutable(folder / 'implementation' / name, (root / name).read_bytes())
    write_immutable(folder / 'reads.json', store.encode({'reads': port.reads, 'target_read': False, 'network_disabled': True, 'model_calls': 0}))
    print(json.dumps({'run_id': result['run_id'], 'blocks': result['canonical_blocks'], 'parts': result['licensed_parts'],
        'projection': result['coverage']['counts'],
        'learned': {m: {'publication_rules': len(v['publication_supported_rules']), 'primary_rules': len(v['primary_supported_rules']),
                        'unsupported_rules': v['learning']['unsupported_templates']} for m, v in result['learning_by_mode'].items()},
        'candidates': {m: len(v) for m, v in result['predictions'].items()},
        'alignment_steps': {m: v['alignment']['steps'] for m, v in result['diagnostics'].items() if 'alignment' in v}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
