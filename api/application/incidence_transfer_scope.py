"""Разделяет фиксацию типизированного прогноза и чтение контрольных значений."""
import logging

from application.ports.incidence_transfer_scope import IncidenceScopeInputs
from application.ports.development_prediction import PredictionStore
from application.ports.empirical_inference import EmpiricalControls
from domain.article_maps import fingerprint,require
from domain.incidence_transfer_scope import VERSION,POLICY,forecast_scoped_fold,evaluate_scoped

log=logging.getLogger(__name__)


class SealIncidenceScope:
    def __init__(self,inputs:IncidenceScopeInputs,store:PredictionStore):self.inputs,self.store=inputs,store

    def execute(self,implementation):
        data=self.inputs.read_inputs()
        binding={'manifest_sha256':fingerprint(data['manifest']),'scope_manifest_sha256':fingerprint(data['scope_manifest']),
                 'folds_sha256':[fingerprint(f) for f in data['folds']],
                 'registry_sha256':fingerprint(data['registry']),'policy':POLICY,'version':VERSION,'implementation':implementation}
        run_id=fingerprint(binding);prior=self.store.read_seal(run_id)
        if prior is not None:
            require(prior['binding']==binding,'Scope seal changed');return prior
        folds=[forecast_scoped_fold(f,data['registry']['scopes']) for f in data['folds']]
        result={'run_id':run_id,'binding':binding,'folds':folds,'model_calls':0,'expert_validated':False,
                'new_scientific_predictions':0,'known_results_retrospective':True}
        self.store.seal(run_id,result)
        log.info('incidence_scope sealed run=%s queries=%d',run_id,sum(len(f['predictions']) for f in folds))
        return self.store.read_seal(run_id)


class EvaluateIncidenceScope:
    def __init__(self,controls:EmpiricalControls,store:PredictionStore):self.controls,self.store=controls,store

    def execute(self,run_id,implementation):
        sealed=self.store.read_seal(run_id);require(sealed is not None,'Seal required before controls')
        require(sealed['binding']['implementation']==implementation,'Scope implementation changed')
        controls=self.controls.read_controls()
        require(controls['manifest_sha256']==sealed['binding']['manifest_sha256'],'Controls belong to another corpus')
        binding={'run_id':run_id,'sealed_sha256':fingerprint(sealed),'controls_sha256':fingerprint(controls),
                 'evaluator_version':VERSION}
        evaluation={'evaluation_id':fingerprint(binding),'binding':binding,**evaluate_scoped(sealed['folds'],controls['controls'])}
        self.store.save_evaluation(run_id,evaluation['evaluation_id'],evaluation)
        return evaluation
