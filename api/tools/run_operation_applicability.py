"""CLI контракта применимости читает только явный запечатанный корпус."""
import argparse
from hashlib import sha256
from pathlib import Path
import json

from application.operation_applicability import SealOperationApplicability
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus
from tools.run_free_prediction import disable_network

CODE = ('domain/operation_applicability.py','application/operation_applicability.py',
        'infrastructure/sealed_forecast_corpus.py','tools/run_operation_applicability.py',
        'domain/article_maps.py','domain/evidence_origin_audit.py','domain/comparison_normalization.py',
        'infrastructure/development_prediction_store.py','infrastructure/free_prediction_snapshots.py',
        'infrastructure/immutable_files.py','tools/run_free_prediction.py')


def main():
    p=argparse.ArgumentParser()
    for flag in ('input-run','audit','output'):p.add_argument('--'+flag,required=True)
    a=p.parse_args();disable_network();corpus=SealedForecastCorpus(a.input_run);store=FilePredictionStore(a.output)
    raw=Path(a.audit).read_bytes();audit=json.loads(raw);root=Path(__file__).resolve().parents[1]
    code={name:sha256((root/name).read_bytes()).hexdigest() for name in CODE}
    result=SealOperationApplicability(corpus,store).execute(audit,code);folder=store.path(result['run_id'])
    write_immutable(folder/'audit.json',raw)
    write_immutable(folder/'input-predictions.json',corpus.read('predictions.json'))
    write_immutable(folder/'input-corpus.json',store.encode({'snapshot':str(corpus.root),'input_run_id':result['input_run_id'],
        'input_sha256':result['binding']['input_sha256'],'target_read':False,'model_calls':0}))
    for name in CODE:write_immutable(folder/'implementation'/name,(root/name).read_bytes())
    print(json.dumps({'run_id':result['run_id'],'sources':len(result['binding']['map_hashes']),
        'cases':len(result['cases']),'supported_schemata':sum(s['minimum_primary_support'] for s in result['schemata']),
        'new_predictions':0}))


if __name__ == '__main__':main()
