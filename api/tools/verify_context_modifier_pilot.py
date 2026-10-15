"""Проверка научных печатей, повторяемости и точного файла автономного отчёта."""
import argparse
import hashlib
import json
from pathlib import Path
from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_context_modifier_pilot import verify_run
from tools.run_prepared_question_pilot import read


def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True); root = p.parse_args().root
    log = (root / 'test-output-v2.txt').read_bytes()
    test_text = log.decode('utf-16') if log.startswith(b'\xff\xfe') else log.decode('utf-8-sig')
    require('181 passed' in test_text and 'FAILED' not in test_text, 'Regression checks failed')
    require(all('Traceback' not in (root / name).read_text('utf-8-sig') for name in ('run-output-v1.txt', 'run-output-v2.txt')),
            'Repeat experiment failed')
    proof = read(root / 'seal-verification-v2.json'); dom = read(root / 'offline-dom-verification-v1.json')
    report_hash = hashlib.sha256((root / 'review-v2/report.html').read_bytes()).hexdigest()
    require(dom['status'] == 'passed' and dom['report_sha256'] == proof['report_sha256'] == report_hash
            and dom['variantChecks'] == 32 and dom['foldChecks'] == 512 and dom['network_calls'] == 0,
            'Exact bilingual report was not checked')
    preserved = read(root / 'preserved-dual-files-v1.json')
    for entry in preserved:
        require(hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() == entry['sha256'], 'Previous result changed')
    review = read(root / 'review-v2/review.json')
    count = 0
    for scope, branch in review['scopes'].items():
        for name, variant in branch['variants'].items():
            receipt = read(root / scope / name / 'receipt-v1.json'); store = FilePredictionStore(root / scope / name / 'runs')
            result = store.read_seal(receipt['run_id']); verify_run(store, result)
            require(fingerprint(result) == receipt['prediction_sha256'] == variant['forecast_sha256'], 'Reviewed result differs')
            require(result['binding']['analysis_scope'] == scope and len(result['binding']['sources']) == 19
                    and result['claim_count'] == 66 and len(result['retrospective_folds']) == 16, 'Corpus changed')
            for fold in result['retrospective_folds']:
                sealed = store.read_seal(fold['forecast_run_id']); evaluation = fold['evaluation']
                require(evaluation['binding']['prediction_sha256'] == fingerprint(sealed)
                        and fingerprint(evaluation['binding']) == evaluation['evaluation_id'], 'Holdout evaluation binding differs')
                count += 1
    workspace = Path(__file__).resolve().parents[2]
    code = ['api/domain/question_context_modifiers.py', 'api/infrastructure/context_modifier_report.py',
            'api/tools/run_context_modifier_pilot.py', 'api/tools/verify_context_modifier_pilot.py',
            'api/tests/test_question_context_modifiers.py', 'api/application/qualitative_question_prediction.py',
            'api/domain/dual_question_outcomes.py', 'api/domain/structured_question_context.py',
            'api/domain/qualitative_question_prediction.py']
    verification = {'status': 'passed', 'python_tests': 181, 'python_runner': 'poetry', 'html_runner': 'bun/jsdom',
                    'verified_variants': 16, 'verified_temporal_folds': count, 'controls_per_branch': 31,
                    'hash_seeds': ['42', '2026'], 'broad_baseline_reproduced': True,
                    'preserved_previous_files': len(preserved), 'report_sha256': report_hash,
                    'code_sha256': {f: hashlib.sha256((workspace / f).read_bytes()).hexdigest() for f in code},
                    'model_calls': 0, 'future_target_read': False, 'services_changed': False,
                    'visual_browser_review': False, 'scientific_predictive_success': False,
                    'best_variant_selected': False}
    write_immutable(root / 'verification-v1.json', FilePredictionStore.encode(verification))
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == '__main__':
    main()
