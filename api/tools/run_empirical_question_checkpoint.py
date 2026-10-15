"""Изолированный локальный CLI: подготовка, запечатывание, затем оценка."""
import argparse
import hashlib
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from domain.article_maps import require, fingerprint
from domain.empirical_question_forecast import VERSION
from infrastructure.empirical_schema6_observations import prepare_observations, VERSION as ADAPTER_VERSION
from infrastructure.empirical_forecast_store import FileEmpiricalForecastStore, PreparedEmpiricalCorpus
from infrastructure.immutable_files import write_immutable
from application.empirical_question_forecast import SealEmpiricalForecast, EvaluateEmpiricalForecast

def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value): write_immutable(path,FileEmpiricalForecastStore.encode(value))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def prohibit_network(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):
        raise RuntimeError('All network/model calls are prohibited in the empirical checkpoint')

def run(root,command):
    sys.addaudithook(prohibit_network)
    plan=read(root/'plan.json');prior=root.parent
    require(plan['minimum_training_families']==2 and plan['prior_per_label']==1 and plan['similarity_weights']==[1]*5,'Plan differs from fixed empirical method')
    if command=='prepare':
        manifest_path=prior/'context-audit-nineteen-v1/primary/manifest-v1.json'
        feature_path=prior/'structured-context-nineteen-v1/features-primary-v2.json'
        manifest=read(manifest_path);bundles=[read(p) for p in manifest['bundles']]
        observations,claims,profiles=prepare_observations(bundles,read(feature_path))
        screening=read(prior/'continuation-batch4-v1/screening-v2.json')
        screened={row['pmcid']:row for row in screening['rows']}
        audit=[]
        for bundle in bundles:
            pmc=bundle['registry']['article_id'].split('-')[1].upper()
            selected=[o.reference for o in observations if o.reference.startswith(bundle['registry']['article_id']+'/')]
            row=screened[pmc]
            audit.append({'pmcid':pmc,'family':bundle['registry']['family'],'eligible_references':selected,
                          'screening_before_context_revision':row,'context_revision':bundle['origin'].get('context_revision'),
                          'source_sha256':bundle['registry']['source_sha256'],'run_id':bundle['registry']['run_id'],
                          'status':'eligible_results' if selected else 'no_verified_primary_observation',
                          'claims':[{'claim_id':c.claim_id,'text':c.text,'context':c.context,'source_spans':list(c.evidence.spans)} for (article,_),c in claims.items() if article==bundle['registry']['article_id']]})
        preservation=[{'path':str(manifest_path),'sha256':sha(manifest_path)},{'path':str(feature_path),'sha256':sha(feature_path)}]+[{'path':p,'sha256':sha(p)} for p in manifest['bundles']]
        save(root/'prepared/preservation.json',preservation)
        save(root/'prepared/audit.json',audit)
        save(root/'prepared/observations.json',[asdict(o) for o in observations])
        save(root/'prepared/binding.json',{'manifest_sha256':sha(manifest_path),'features_sha256':sha(feature_path),'plan_sha256':sha(root/'plan.json'),
                                         'adapter_version':ADAPTER_VERSION,'engine_version':VERSION,
                                         'code':{str(p):sha(p) for p in (Path(__file__),Path(__file__).resolve().parents[1]/'domain/empirical_question_forecast.py',Path(__file__).resolve().parents[1]/'infrastructure/empirical_schema6_observations.py',Path(__file__).resolve().parents[1]/'application/empirical_question_forecast.py',Path(__file__).resolve().parents[1]/'infrastructure/empirical_forecast_store.py')}})
        logging.info('corpus articles=%s families=%s eligible_results=%s eligible_families=%s',len(bundles),len({b['registry']['family'] for b in bundles}),len(observations),len({o.family for o in observations}))
        return
    from domain.empirical_question_forecast import Observation
    observations=[Observation(**r) for r in read(root/'prepared/observations.json')]
    binding=read(root/'prepared/binding.json')
    require(binding['plan_sha256']==sha(root/'plan.json') and all(sha(p)==h for p,h in binding['code'].items()),'Prepared dependencies changed; create a new checkpoint')
    for p in read(root/'prepared/preservation.json'): require(sha(p['path'])==p['sha256'],'Previous source changed')
    store=FileEmpiricalForecastStore(root/'runs')
    if command=='seal':
        folds=[]
        for target in observations:
            earlier=[o for o in observations if o.family!=target.family and o.available_on<target.available_on]
            corpus=PreparedEmpiricalCorpus(earlier)
            request={'question_id':plan.get('question_id','baseline-plasma-il6-global-decline-2y-1'),
                     'as_of':target.available_on,'excluded_families':[target.family],'context':target.context}
            sealed=SealEmpiricalForecast(corpus,store).execute([o.reference for o in earlier],request,sha(root/'plan.json'))
            folds.append({'target_reference':target.reference,'family':target.family,'run_id':sealed['run_id'],'training_families':len({o.family for o in earlier})})
        save(root/'sealed-folds.json',folds)
        logging.info('sealed folds=%s',len(folds));return
    results=[]
    for fold in read(root/'sealed-folds.json'):
        target=next(o for o in observations if o.reference==fold['target_reference'])
        evaluation=EvaluateEmpiricalForecast(PreparedEmpiricalCorpus([target]),store).execute(fold['run_id'],[target.reference])
        results.append({'fold':fold,'evaluation':evaluation,'sealed':store.read_seal(fold['run_id'])})
    metrics={}
    for mode in ('frequency','semantic','dependency'):
        metrics[mode]={}
        for channel in ('direction','detection'):
            rows=[r for result in results for r in result['evaluation']['scores'][mode] if r['channel']==channel]
            evaluated=[r for r in rows if 'brier' in r]
            families={family:[r for r in evaluated if r['family']==family] for family in {r['family'] for r in evaluated}}
            averages=[sum(r['brier'] for r in rs)/len(rs) for rs in families.values()]
            metrics[mode][channel]={'targets':len(rows),'scored_results':len(evaluated),'scored_families':len(families),
                                    'categorical_matches':sum(r.get('categorical_match') is True for r in rows),
                                    'ties':sum('brier' in r and r.get('categorical_match') is None for r in rows),
                                    'family_mean_brier':sum(averages)/len(averages) if averages else None}
    result={'version':VERSION,'plan_sha256':sha(root/'plan.json'),'metrics':metrics,'results':results,
            'retrospective':True,'blind_test':False,'expert_validated':False,'scientific_success':False,
            'future_target_reading_allowed':False,'model_calls':0,'network_calls':0,'embeddings':0,'translator_calls':0,'token_usage':None}
    save(root/'result.json',result)
    print(json.dumps(metrics,ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser(description='Эмпирический прогноз IL-6: без LLM и сети')
    parser.add_argument('command',choices=('prepare','seal','evaluate'))
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    run(args.root.resolve(),args.command)

if __name__=='__main__':main()
