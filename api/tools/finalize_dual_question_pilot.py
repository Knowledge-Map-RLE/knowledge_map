"""Сверка нового опыта с прежними файлами и объединение автономных просмотров."""
import argparse
import hashlib
import json
from pathlib import Path
from domain.article_maps import require,fingerprint
from infrastructure.dual_question_report import combine_reviews
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();root=args.root
    combined={}
    for scope in ('primary','sensitivity'):
        receipt=json.loads((root/scope/'receipt-v2.json').read_text('utf-8'));store=FilePredictionStore(root/scope/'runs');forecast=store.read_seal(receipt['run_id'])
        require(not forecast['readiness']['target_reading_allowed'],'Exploratory transport cannot open future target')
        for fold in forecast['retrospective_folds']:
            prediction=store.read_seal(fold['forecast_run_id'])
            require(fold['plan']['family'] not in prediction['binding']['training_families'],'Heldout family leaked')
            allowed=set(fold['plan']['training'])
            require(all(p['reference'][0] in allowed for p in prediction['structured_context']['profiles']),'Heldout profiles used by fit')
            direction=prediction['outcome_channels']['reported_direction_exploratory']
            require(all(o['reference'][0] in allowed for o in direction['observations']),'Heldout directions used by fit')
        report=json.loads((Path(receipt['report_folder'])/'review.json').read_text('utf-8'))[scope]
        require(report['forecast_sha256']==fingerprint(forecast),'Report differs from exact forecast')
        combined[scope]={'run_id':receipt['run_id'],'forecast_sha256':fingerprint(forecast),'summary':receipt['summary']}
    previous=root.parent/'structured-context-nineteen-v1'
    preserved=json.loads((previous/'seal-verification-v1.json').read_text('utf-8'))['preserved_artifacts']
    for file,expected in preserved.items():require(hashlib.sha256(Path(file).read_bytes()).hexdigest()==expected,'Previous artifact changed')
    previous_files=[previous/'review-v1/report.html',previous/'verification-v1.json']
    for scope in ('primary','sensitivity'):
        receipt=json.loads((previous/scope/'receipt-v2.json').read_text('utf-8'))
        previous_files.extend([previous/scope/'runs'/receipt['run_id']/'predictions.json',previous/scope/'runs'/receipt['run_id']/'seal.json'])
    preserved={**preserved,**{p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in previous_files}}
    write_immutable(root/'seal-verification-v1.json',FilePredictionStore.encode({'status':'passed','branches':combined,'preserved_artifacts':preserved,'model_calls':0,'future_target_read':False}))
    combine_reviews(root)
    print(json.dumps({'branches':combined,'preserved_artifacts':len(preserved)},ensure_ascii=False))


if __name__=='__main__':main()
