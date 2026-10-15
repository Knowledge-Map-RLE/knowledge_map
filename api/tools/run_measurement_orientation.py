"""Полный парный опыт использует прежний корпус и отдельные неизменяемые абстракции."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
from application.measurement_orientation import SealMeasurementOrientation
from infrastructure.measurement_orientation import FileOrientationInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_interval_knowledge import CODE as UPSTREAM_CODE
from tools.run_free_prediction import disable_network

CODE=tuple(sorted(set(UPSTREAM_CODE)|{'domain/measurement_orientation.py','application/measurement_orientation.py',
    'infrastructure/measurement_orientation.py','tools/prepare_measurement_orientation.py','tools/run_measurement_orientation.py',
    'domain/operation_applicability.py'}))


def main():
    parser=argparse.ArgumentParser()
    for f in ('input-run','applicability','audit','output'):parser.add_argument('--'+f,required=True)
    args=parser.parse_args();disable_network();logging.basicConfig(level=logging.INFO)
    inputs=FileOrientationInputs(args.input_run,args.applicability,args.audit);store=FilePredictionStore(args.output)
    root=Path(__file__).resolve().parents[1];code={f:sha256((root/f).read_bytes()).hexdigest() for f in CODE}
    result=SealMeasurementOrientation(inputs,store).execute(code);folder=store.path(result['run_id'])
    write_immutable(folder/'audit.json',Path(args.audit).read_bytes())
    write_immutable(folder/'input-corpus.json',store.encode({'previous':str(inputs.root),'applicability':str(inputs.applicability)}))
    for f in CODE:write_immutable(folder/'implementation'/f,(root/f).read_bytes())
    print(json.dumps({'run_id':result['run_id'],'blocks':result['canonical_blocks'],'parts':result['oriented_parts'],
        'views_added':len(result['orientation_views']),'policies':{p:{m:{'rules':len(r.get('rules',[])),
        'predictions':len(r['predictions']),'structural_groups':len(r.get('guard_barriers',[]))}
        for m,r in modes.items()} for p,modes in result['policies'].items()}}))


if __name__=='__main__':main()
