"""Восемь фиксированных проверок контекста на прежнем корпусе; только локальные файлы."""
import argparse
import hashlib
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
from application.question_prediction import AuditResearchSemantics
from domain.article_maps import fingerprint, require
from domain.question_context_modifiers import ContextModifierEngine, VARIANTS, variant_id, validate_modifier_policy
from domain.structured_question_context import validate_feature_records
from domain.research_semantics import project_map
from infrastructure.prepared_research_maps import PreparedResearchMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.research_artifacts import FileResearchArtifacts
from infrastructure.immutable_files import write_immutable
from infrastructure.context_modifier_report import save_modifier_review
from tools.run_prepared_question_pilot import read, bundles_from_manifest
from tools.import_codex_article_map import prohibit_generation


def verify_run(store, result):
    require(store.read_seal(result['run_id']) == result and not result['readiness']['target_reading_allowed'],
            'Seal mismatch or independent target gate opened')
    for fold in result['retrospective_folds']:
        sealed = store.read_seal(fold['forecast_run_id'])
        require(fold['plan']['family'] not in sealed['binding']['training_families'], 'Heldout family leaked')
        allowed = set(fold['plan']['training'])
        rows = sealed['outcome_channels']['reported_direction_exploratory']['observations']
        require(all(r['reference'][0] in allowed for r in rows), 'Heldout observation leaked')
        for candidates in sealed['outcome_channels']['reported_direction_exploratory']['modes'].values():
            for candidate in candidates:
                require(all(p['evidence']['article_id'] in allowed for p in candidate.get('premises', [])), 'Heldout premise leaked')
        path = store.root / fold['forecast_run_id'] / 'evaluations' / (fold['evaluation_id'] + '.json')
        require(path.exists() and read(path) == fold['evaluation'], 'Evaluation seal differs')


def main():
    p = argparse.ArgumentParser(description='Аудит MCI, исхода и поправок без моделей')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--corpus-root', type=Path, required=True)
    args = p.parse_args(); prohibit_generation(); logging.basicConfig(level=logging.INFO)
    parent = args.corpus_root
    prior = parent / 'dual-outcome-nineteen-v1'
    structured = parent / 'structured-context-nineteen-v1'
    policy = validate_modifier_policy(read(args.root / 'modifier-policy-v1.json'))
    transport = read(prior / 'transport-v1.json')
    # Снимки и полная сетка фиксируются до первого расчёта, прежние файлы не изменяются.
    preserved = [{'path': path.as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                 for path in sorted(prior.rglob('*')) if path.is_file()]
    write_immutable(args.root / 'preserved-dual-files-v1.json', FilePredictionStore.encode(preserved))
    outputs = {}
    for scope in ('primary', 'sensitivity'):
        folder = args.root / scope
        manifest_path = parent / 'context-audit-nineteen-v1' / scope / 'manifest-v1.json'
        manifest = read(manifest_path); bundles = bundles_from_manifest(manifest, manifest_path.parent)
        maps = PreparedResearchMaps(bundles, manifest['owner'], 'training')
        refs = [{k: b['map'][k] for k in ('article_id', 'pipeline_id', 'run_id')} for b in bundles]
        registry = {b['map']['article_id']: b['registry'] for b in bundles}
        annotations = {b['map']['article_id']: b['annotation'] for b in bundles}
        previous_receipt = read(prior / scope / 'receipt-v2.json')
        previous = FilePredictionStore(prior / scope / 'runs').read_seal(previous_receipt['run_id'])
        expected = [{'article_id': b['map']['article_id'], 'source_sha256': b['map']['source']['sha256'],
                     'graph_sha256': fingerprint(b['map']['graph'])} for b in bundles]
        require(previous['binding']['sources'] == refs and previous['binding']['maps'] == expected
                and previous['binding']['owner'] == manifest['owner'], 'Fixed corpus differs')
        claims = {(c.evidence.article_id, c.claim_id): c for b in bundles for c in project_map(b['map'], b['registry'], b['annotation'])}
        support = [s for b in bundles for s in b['origin'].get('context_revision', {}).get('audit', {}).get('sources', [])]
        features_path = structured / ('features-' + scope + '-v2.json')
        profiles = validate_feature_records(read(features_path), claims, {b['map']['article_id']: b['map'] for b in bundles}, scope, support)
        extraction_policy_path = parent / 'context-audit-nineteen-v1' / 'policy-v2.json'
        for name, path in [('features', features_path), ('manifest', manifest_path), ('extraction-policy', extraction_policy_path),
                           ('transport', prior / 'transport-v1.json'), ('modifier-policy', args.root / 'modifier-policy-v1.json')]:
            write_immutable(folder / (name + '.snapshot.json'), path.read_bytes())
        audit = AuditResearchSemantics(maps, FileResearchArtifacts(folder / 'audits')).execute(
            refs, registry, annotations, manifest['controls'], manifest['owner'])
        require(audit['controls_passed'] == audit['control_count'], 'Semantic controls failed')
        outputs[scope] = {'audit': audit, 'variants': {}, 'old_run_id': previous_receipt['run_id']}
        for selected in VARIANTS:
            name = variant_id(selected); store = FilePredictionStore(folder / name / 'runs')
            engine = ContextModifierEngine(profiles, transport, policy, selected)
            result = SealQualitativeQuestionExperiment(maps, store, engine).execute(
                refs, registry, annotations, manifest['episodes'], manifest['question'], read(extraction_policy_path), manifest['owner'], scope)
            verify_run(store, result)
            outputs[scope]['variants'][name] = result
            write_immutable(folder / name / 'receipt-v1.json', FilePredictionStore.encode({
                'run_id': result['run_id'], 'prediction_sha256': fingerprint(result),
                'fold_count': len(result['retrospective_folds']), 'model_calls': 0, 'future_target_read': False}))
        # Нулевой вариант должен воспроизводить прежнюю проверку, а не менять её задним числом.
        broad = outputs[scope]['variants']['broad']
        for old, new in zip(previous['retrospective_folds'], broad['retrospective_folds']):
            require(old['plan'] == new['plan'], 'Family-time plan changed')
            for mode in ('semantic', 'dependency', 'family_frequency_baseline'):
                a = old['evaluation']['outcome_channels']['reported_direction_exploratory']['modes'][mode]
                b = new['evaluation']['outcome_channels']['reported_direction_exploratory']['modes'][mode]
                require(all(a[k] == b[k] for k in ('issued_answers', 'scorable_comparisons', 'agreements', 'different_signs')),
                        'Broad historical baseline changed')
    for entry in preserved:
        require(hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() == entry['sha256'], 'Previous immutable file changed')
    review = save_modifier_review(args.root / 'review-v2', outputs, policy)
    write_immutable(args.root / 'seal-verification-v2.json', FilePredictionStore.encode({
        'variants_per_scope': 8, 'scopes': 2, 'folds_per_variant': 16, 'preserved_files': len(preserved),
        'broad_baseline_reproduced': True, 'model_calls': 0, 'future_target_read': False,
        'services_changed': False, 'scientific_success': False,
        'report_sha256': hashlib.sha256((args.root / 'review-v2' / 'report.html').read_bytes()).hexdigest()}))
    print(FilePredictionStore.encode(review['summary']).decode('utf-8'))


if __name__ == '__main__':
    main()
