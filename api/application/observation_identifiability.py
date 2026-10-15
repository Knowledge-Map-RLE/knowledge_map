"""Сценарий аудита доступности измерений без генерации эмпирических прогнозов."""
from domain.article_maps import fingerprint
from domain.observation_identifiability import VERSION,audit_catalog
from application.ports.observation_identifiability import ObservationInputs,ObservationAuditStore

class AuditObservationData:
    def __init__(self,inputs:ObservationInputs,store:ObservationAuditStore):self.inputs,self.store=inputs,store
    def execute(self,implementation):
        data=self.inputs.read_inputs()
        binding={'version':VERSION,'inputs_sha256':fingerprint(data),'implementation':implementation}
        run_id=fingerprint(binding);prior=self.store.read(run_id)
        if prior:return prior
        result={'run_id':run_id,'binding':binding,'inputs':data,'audit':audit_catalog(data['catalog']),
                'model_calls':0,'expert_validated':False,'retrospective':True}
        self.store.save(run_id,result)
        return self.store.read(run_id)
