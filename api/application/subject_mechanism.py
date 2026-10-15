"""Фиксация условной гипотезы до чтения диагностических профилей."""
from domain.article_maps import fingerprint, require
from domain.subject_mechanism import VERSION, generate, evaluate_eligibility, mixture_counterexample
from application.ports.subject_mechanism import MechanismInputs, MechanismProfiles
from application.ports.development_prediction import PredictionStore

class SealSubjectMechanism:
    def __init__(self, inputs: MechanismInputs, store: PredictionStore):
        self.inputs, self.store = inputs, store

    def execute(self, implementation):
        inputs = self.inputs.read_inputs()
        binding = {'version':VERSION,'inputs_sha256':fingerprint(inputs),'implementation':implementation}
        run_id = fingerprint(binding)
        previous = self.store.read_seal(run_id)
        if previous: return previous
        result = {'run_id':run_id,'binding':binding,'inputs':inputs,'generation':generate(inputs),
                  'counterexample':mixture_counterexample(),'retrospective':True,'expert_validated':False,
                  'model_calls':0,'new_scientific_predictions':0}
        self.store.seal(run_id,result)
        return self.store.read_seal(run_id)

class AuditSubjectMechanism:
    def __init__(self, profiles: MechanismProfiles, store: PredictionStore):
        self.profiles, self.store = profiles, store

    def execute(self, run_id, implementation):
        seal = self.store.read_seal(run_id)
        require(seal is not None, 'Seal required before profile audit')
        require(seal['binding']['implementation']==implementation, 'Frozen implementation changed')
        profiles = self.profiles.read_profiles()
        require(profiles['inputs_sha256']==seal['binding']['inputs_sha256'], 'Profiles bound to another corpus')
        for profile in profiles['profiles']:
            require(set(profile['provenance']) <= set(seal['inputs']['protocol']['registered_evidence_ids']), 'Unknown profile provenance')
        rows = [{'candidate_id':c['id'],'profiles':evaluate_eligibility(c,profiles['profiles'])} for c in seal['generation']['candidates']]
        binding = {'run_id':run_id,'seal_sha256':fingerprint(seal),'profiles_sha256':fingerprint(profiles),'version':VERSION}
        result = {'evaluation_id':fingerprint(binding),'binding':binding,'rows':rows,
                  'novelty_audit':profiles['novelty_audit'],'scientific_success':False,
                  'empirical_forecasts_released':0,'expert_validated':False,'model_calls':0,
                  'evaluation_kind':'applicability audit of previously read sources, not outcome validation'}
        self.store.save_evaluation(run_id,result['evaluation_id'],result)
        return result
