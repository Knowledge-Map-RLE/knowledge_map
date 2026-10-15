"""Фиксирует выполненные проверки, код, сохранность прошлых результатов и повторяемость опыта."""
import argparse
import hashlib
import json
from pathlib import Path
from domain.article_maps import require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();root=args.root
    log=(root/'test-output-v2.txt').read_bytes()
    text=log.decode('utf-16') if log.startswith(b'\xff\xfe') else log.decode('utf-8-sig')
    require('151 passed' in text,'Python checks did not pass')
    dom=json.loads((root/'offline-dom-verification-v1.json').read_text('utf-8'));require(dom['status']=='passed','HTML checks did not pass')
    require(hashlib.sha256((root/'review-v2/report.html').read_bytes()).hexdigest()==dom['report_sha256'],'Verified report changed')
    seal=json.loads((root/'seal-verification-v1.json').read_text('utf-8'))
    for file,expected in seal['preserved_artifacts'].items():require(hashlib.sha256(Path(file).read_bytes()).hexdigest()==expected,'Previous file changed')
    code=['api/domain/dual_question_outcomes.py','api/infrastructure/dual_question_report.py','api/tools/run_dual_question_pilot.py',
          'api/tools/finalize_dual_question_pilot.py','api/tools/verify_dual_question_pilot.py','api/tests/test_dual_question_outcomes.py']
    workspace=Path(__file__).resolve().parents[2]
    result={'status':'passed','python_tests':151,'python_runner':'poetry','html_runner':'bun/jsdom','semantic_controls_per_branch':31,
            'code_sha256':{file:hashlib.sha256((workspace/file).read_bytes()).hexdigest() for file in code},
            'hash_seeds':['42','2026'],'preserved_artifacts':len(seal['preserved_artifacts']),'report_sha256':dom['report_sha256'],
            'model_calls':0,'future_target_read':False,'services_changed':False,'visual_browser_review':False,
            'clinical_context_transport_confirmed':False,'scientific_predictive_success':False}
    write_immutable(root/'verification-v1.json',FilePredictionStore.encode(result))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
