"""Дедуктивная реконструкция интерпретации отдельно от эмпирического прогноза."""
import logging
from domain.article_maps import fingerprint,require
from domain.parameterized_reasoning import interpret,VERSION,RULE_ID
from domain.goal_pattern_experience import Goal,assess,summarize
from application.ports.parameterized_reasoning import ReasoningCorpus,ReasoningStore

log=logging.getLogger(__name__)

class SealInterpretations:
    def __init__(self,corpus:ReasoningCorpus,store:ReasoningStore):self.corpus,self.store=corpus,store

    def execute(self,protocol):
        require(protocol.get('episode')=='post_result_interpretation' and protocol.get('clinical_forecast') is False,'Reported results cannot be presented as pre-outcome forecasting')
        inputs=self.corpus.premises()
        require(inputs['case_ids']==protocol['case_ids'],'Explicit protocol corpus differs')
        require(len({c['case_id'] for c in inputs['cases']})==len(inputs['cases']),'Duplicate interpretation case')
        require(all(c['source_binding']==inputs['binding']['source_binding'] and c['family']==inputs['binding']['family'] for c in inputs['cases']),'Case and corpus source bindings differ')
        predictions=[interpret(case) for case in inputs['cases']]
        payload={'protocol':protocol,'protocol_sha256':fingerprint(protocol),'binding':inputs['binding'],
                 'predictions':predictions,'version':VERSION,'operator_id':RULE_ID,'model_calls':0,
                 'scientific_success':False,'blind_test':False,'clinical_predictions':0}
        run_id=fingerprint(payload);self.store.seal(run_id,{'run_id':run_id,**payload})
        log.info('parameterized_reasoning sealed run=%s cases=%d answered=%d',run_id,len(predictions),sum(p['result_available'] for p in predictions))
        return self.store.read_seal(run_id)

class EvaluateInterpretations:
    def __init__(self,corpus:ReasoningCorpus,store:ReasoningStore):self.corpus,self.store=corpus,store

    def execute(self,run_id):
        sealed=self.store.read_seal(run_id)
        require(sealed and sealed['run_id']==fingerprint({k:v for k,v in sealed.items() if k!='run_id'}),'Verified seal required before controls')
        require(sealed['version']==VERSION,'Compatible interpretation version required')
        controls=self.corpus.controls()
        require(controls['premises_sha256']==sealed['binding']['premises_sha256'],'Evaluator premise revision differs')
        require(controls['source_binding']==sealed['binding']['source_binding'],'Evaluator article/map revision differs')
        answers={c['case_id']:c for c in controls['controls']}
        require(set(answers)==set(sealed['protocol']['case_ids']) and len(answers)==len(controls['controls']),'Exact distinct control set required')
        goal=Goal('reconstruct-author-statistical-interpretation','engineering_interpretation','agreement',1.0,
                  {'episode':'post_result_interpretation','basis':'reported_values'},sealed['protocol_sha256'])
        rows=[];experiences=[]
        for p in sealed['predictions']:
            target=answers[p['case_id']]
            require(target['expected'] in {'below_threshold','not_below_threshold'},'Explicit author label required')
            observed=p['result_available'];matched=p['status']==target['expected'] if observed else None
            rows.append({'case_id':p['case_id'],'status':p['status'],'expected':target['expected'],'match':matched,
                         'author_evidence':target['evidence'],'author':target['author'],'expert_validated':False})
            experiences.append(assess(goal,{'pattern_id':RULE_ID,'family':sealed['binding']['family'],'case_id':p['case_id'],
                'metric':'agreement','value':None if matched is None else int(matched),'context':goal.context,
                'outcome_observed':observed,'binding':{'inference_id':p['inference_id'],'evaluation_control':fingerprint(target)},'prospective':False}))
        payload={'prediction_run_id':run_id,'prediction_sha256':fingerprint(sealed),'rows':rows,
                 'answered':sum(p['result_available'] for p in sealed['predictions']),
                 'matches':sum(r['match'] is True for r in rows),'blocked_or_indeterminate':sum(r['match'] is None for r in rows),
                 'experiences':experiences,'patterns':summarize(experiences),'controls_binding':controls['binding'],
                 'scientific_success':False,'clinical_predictions':0,'blind_test':False,
                 'note':'Reconstruction from reported P-values; not an unknown empirical effect forecast.'}
        evaluation_id=fingerprint(payload);result={'evaluation_id':evaluation_id,**payload}
        self.store.save_evaluation(run_id,evaluation_id,result)
        log.info('parameterized_reasoning evaluated run=%s matches=%d answered=%d',run_id,payload['matches'],payload['answered'])
        return result
