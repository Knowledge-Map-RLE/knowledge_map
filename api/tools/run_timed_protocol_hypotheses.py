"""Сценарий свободной генерации условных протокольных сочетаний; исходы не загружаются."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
from application.timed_protocol_hypotheses import SealTimedProtocolHypotheses
from infrastructure.timed_protocol_hypotheses import FileTimedHypothesisInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_first_administration_clock import CODE as UPSTREAM_CODE
from tools.run_free_prediction import disable_network

CODE=tuple(sorted(set(UPSTREAM_CODE)|{'domain/timed_protocol_hypotheses.py','application/timed_protocol_hypotheses.py',
    'infrastructure/timed_protocol_hypotheses.py','tools/run_timed_protocol_hypotheses.py',
    'tools/prepare_timed_clinical_review.py'}))


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-review',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();disable_network();logging.basicConfig(level=logging.INFO)
    inputs=FileTimedHypothesisInputs(a.source_review);store=FilePredictionStore(a.output);root=Path(__file__).resolve().parents[1]
    implementation={f:sha256((root/f).read_bytes()).hexdigest()for f in CODE}
    result=SealTimedProtocolHypotheses(inputs,store).execute(implementation);folder=store.path(result['run_id'])
    write_immutable(folder/'input-corpus.json',store.encode({'timed_review':str(inputs.review)}))
    for f in CODE:write_immutable(folder/'implementation'/f,(root/f).read_bytes())
    print(json.dumps({'run_id':result['run_id'],'candidates':{m:len(c)for m,c in result['modes'].items()},
        'qualified_new_scientific_forecasts':0,'model_calls':0}))


if __name__=='__main__':main()
