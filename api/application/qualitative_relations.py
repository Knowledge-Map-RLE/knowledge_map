"""Фиксирует качественные гипотезы до программного чтения контроля."""
from collections import Counter
from domain.article_maps import fingerprint,require
from domain.qualitative_relations import VERSION,POLICY,forecast_fold,evaluate_fold
from application.ports.qualitative_relations import QualitativeInputs,QualitativeControls
from application.ports.development_prediction import PredictionStore

class SealQualitativeRelations:
    def __init__(self,inputs:QualitativeInputs,store:PredictionStore):self.inputs,self.store=inputs,store
    def execute(self,implementation):
        data=self.inputs.read_inputs()
        binding={'manifest_sha256':fingerprint(data['manifest']),'folds_sha256':[fingerprint(f) for f in data['folds']],
                 'implementation':implementation,'version':VERSION,'policy':POLICY}
        run_id=fingerprint(binding);prior=self.store.read_seal(run_id)
        if prior:return prior
        result={'run_id':run_id,'binding':binding,'folds':[forecast_fold(f) for f in data['folds']],
                'model_calls':0,'expert_validated':False,'new_scientific_predictions':0,'retrospective':True}
        self.store.seal(run_id,result);return self.store.read_seal(run_id)

class EvaluateQualitativeRelations:
    def __init__(self,controls:QualitativeControls,store:PredictionStore):self.controls,self.store=controls,store
    def execute(self,run_id,implementation):
        seal=self.store.read_seal(run_id);require(seal is not None,'Seal required before controls')
        require(seal['binding']['implementation']==implementation,'Implementation changed')
        controls=self.controls.read_controls();require(controls['manifest_sha256']==seal['binding']['manifest_sha256'],'Wrong control corpus')
        require(set(controls['controls'])=={f['fold_id'] for f in seal['folds']},'Missing or extra control fold')
        folds=[evaluate_fold(f,controls['controls'][f['fold_id']]) for f in seal['folds']]
        totals={mode:dict(sum((Counter(f['modes'][mode]['counts']) for f in folds),Counter())) for mode in ('semantic','known_union','frequency')}
        binding={'run_id':run_id,'controls_sha256':fingerprint(controls),'seal_sha256':fingerprint(seal),'version':VERSION}
        result={'evaluation_id':fingerprint(binding),'binding':binding,'folds':folds,'totals':totals,
                'new_scientific_predictions':0,'independent_success':False,'retrospective':True}
        self.store.save_evaluation(run_id,result['evaluation_id'],result);return result
