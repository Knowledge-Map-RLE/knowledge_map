"""Офлайн-CLI сохраняет временные ограничения и вычисления отдельной ревизией."""
import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
from application.treatment_episode_context import SealTreatmentEpisodes
from infrastructure.treatment_episode_context import FileEpisodeInputs
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_functional_target_guard import CODE as UPSTREAM_CODE
from tools.run_free_prediction import disable_network

CODE=tuple(sorted(set(UPSTREAM_CODE)|{'domain/treatment_episode_context.py','application/treatment_episode_context.py',
    'infrastructure/treatment_episode_context.py','tools/prepare_treatment_episodes.py','tools/run_treatment_episodes.py'}))


def main():
    p=argparse.ArgumentParser()
    for name in ('input-run','audit','output'):p.add_argument('--'+name,required=True)
    args=p.parse_args();disable_network();logging.basicConfig(level=logging.INFO)
    inputs=FileEpisodeInputs(args.input_run,args.audit);store=FilePredictionStore(args.output);root=Path(__file__).resolve().parents[1]
    implementation={f:sha256((root/f).read_bytes()).hexdigest()for f in CODE}
    result=SealTreatmentEpisodes(inputs,store).execute(implementation);folder=store.path(result['run_id'])
    write_immutable(folder/'audit.json',Path(args.audit).read_bytes())
    write_immutable(folder/'input-corpus.json',store.encode({'functional':str(inputs.root)}))
    for f in CODE:write_immutable(folder/'implementation'/f,(root/f).read_bytes())
    for e in result['assets'].values():write_immutable(folder/e['path'],(inputs.audit.parent/e['path']).read_bytes())
    print(json.dumps({'run_id':result['run_id'],'calendar_consequences':len(result['calendar_consequences']),
        'calendar_conflicts':len(result['calendar_conflicts']),'protocol_conflicts':len(result['protocol_conflicts']),
        'new_empirical_forecasts':result['new_empirical_forecasts']}))


if __name__=='__main__':main()
