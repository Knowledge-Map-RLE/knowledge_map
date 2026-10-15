"""Неизменяемая фиксация знаний, операторов и условий до выбора цели."""
from domain.article_maps import fingerprint
from domain.frozen_transfer import VERSION,generate_transfer
from application.ports.frozen_transfer import TransferInputs
from application.ports.development_prediction import PredictionStore

class FreezeTransfer:
    def __init__(self,inputs:TransferInputs,store:PredictionStore):self.inputs,self.store=inputs,store
    def execute(self,implementation):
        data=self.inputs.read_inputs();binding={'version':VERSION,'input_sha256':fingerprint(data),'implementation':implementation}
        run_id=fingerprint(binding);previous=self.store.read_seal(run_id)
        if previous:return previous
        result={'run_id':run_id,'binding':binding,'inputs':data,'generation':generate_transfer(data),
                'expert_validated':False,'model_calls':0,'design':'historical holdout frozen now; not a pre-publication prospective study'}
        self.store.seal(run_id,result);return self.store.read_seal(run_id)
