"""Офлайн-CLI смены начала отсчёта сохраняет старые карты и условия."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
from application.first_administration_clock import SealFirstAdministrationClock
from infrastructure.first_administration_clock import FileClockInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_treatment_episodes import CODE as UPSTREAM_CODE
from tools.run_free_prediction import disable_network

CODE=tuple(sorted(set(UPSTREAM_CODE)|{'domain/first_administration_clock.py','application/first_administration_clock.py',
    'infrastructure/first_administration_clock.py','tools/run_first_administration_clock.py'}))


def main():
    p=argparse.ArgumentParser();p.add_argument('--input-run',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();disable_network();logging.basicConfig(level=logging.INFO)
    inputs=FileClockInputs(a.input_run);store=FilePredictionStore(a.output);root=Path(__file__).resolve().parents[1]
    implementation={f:sha256((root/f).read_bytes()).hexdigest()for f in CODE}
    result=SealFirstAdministrationClock(inputs,store).execute(implementation);folder=store.path(result['run_id'])
    write_immutable(folder/'input-corpus.json',store.encode({'episodes':str(inputs.root)}))
    for f in CODE:write_immutable(folder/'implementation'/f,(root/f).read_bytes())
    print(json.dumps({'run_id':result['run_id'],'clock_proofs':len(result['clock_proofs']),
        'new_empirical_forecasts':result['new_empirical_forecasts']}))


if __name__=='__main__':main()
