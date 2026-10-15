"""Офлайн-CLI фиксирует предпосылки трёхчастного прототипа; прогноз не подменяется компиляцией."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
from application.functional_target_guard import SealFunctionalTargetGuard
from infrastructure.functional_target_guard import FileFunctionalInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_measurement_orientation import CODE as UPSTREAM_CODE
from tools.run_free_prediction import disable_network

CODE=tuple(sorted(set(UPSTREAM_CODE)|{'domain/functional_target_guard.py','application/functional_target_guard.py',
    'infrastructure/functional_target_guard.py','tools/prepare_functional_target_guard.py','tools/run_functional_target_guard.py'}))


def main():
    p=argparse.ArgumentParser()
    for f in ('input-run','audit','output'):p.add_argument('--'+f,required=True)
    args=p.parse_args();disable_network();logging.basicConfig(level=logging.INFO)
    inputs=FileFunctionalInputs(args.input_run,args.audit);store=FilePredictionStore(args.output);root=Path(__file__).resolve().parents[1]
    code={f:sha256((root/f).read_bytes()).hexdigest()for f in CODE};result=SealFunctionalTargetGuard(inputs,store).execute(code)
    folder=store.path(result['run_id']);write_immutable(folder/'audit.json',Path(args.audit).read_bytes())
    write_immutable(folder/'input-corpus.json',store.encode({'orientation':str(inputs.root)}))
    for f in CODE:write_immutable(folder/'implementation'/f,(root/f).read_bytes())
    print(json.dumps({'run_id':result['run_id'],'certificates':len(result['functional_certificates']),
        'prototype_premises':len(result['guarded_prototype']['body']),'new_empirical_forecasts':0}))


if __name__=='__main__':main()
