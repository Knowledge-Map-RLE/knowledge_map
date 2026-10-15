"""Сначала фиксируется прогноз; удержанные результаты доступны только оценщику."""
from domain.article_maps import fingerprint, require
from domain.empirical_question_forecast import ForecastRequest, forecast, score_prediction, VERSION
from application.ports.empirical_question_forecast import ExplicitEmpiricalCorpus, EmpiricalForecastArtifacts

class SealEmpiricalForecast:
    def __init__(self, corpus: ExplicitEmpiricalCorpus, artifacts: EmpiricalForecastArtifacts):
        self.corpus=corpus; self.artifacts=artifacts

    def execute(self, references, raw_request, plan_sha256):
        request=ForecastRequest.parse(raw_request)
        require(len(references)==len(set(references)),'Repeated explicit source reference')
        observations=self.corpus.read(references)
        require({o.reference for o in observations}==set(references),'Corpus expanded or omitted explicit sources')
        require(all(o.family not in request.excluded_families and o.available_on<request.as_of for o in observations),'Training corpus leaks target family or chronology')
        binding={'version':VERSION,'plan_sha256':plan_sha256,'request':raw_request,
                 'sources':sorted([{'reference':o.reference,'binding':o.binding,'family':o.family,'available_on':o.available_on,'context':o.context,'findings':o.findings,'dependency_grounded':o.dependency_grounded} for o in observations],key=lambda r:r['reference'])}
        run_id=fingerprint(binding)
        artifact={'run_id':run_id,'binding':binding,'modes':{m:forecast(observations,request,m) for m in ('known_union','frequency','semantic','dependency')},
                  'model_calls':0,'future_target_reading_allowed':False,'blind_test':False,'expert_validated':False}
        self.artifacts.seal(run_id,artifact)
        return artifact

class EvaluateEmpiricalForecast:
    def __init__(self, evaluator: ExplicitEmpiricalCorpus, artifacts: EmpiricalForecastArtifacts):
        self.evaluator=evaluator; self.artifacts=artifacts

    def execute(self, run_id, targets):
        sealed=self.artifacts.read_seal(run_id)
        require(sealed['run_id']==run_id and fingerprint(sealed['binding'])==run_id,'Sealed forecast binding differs')
        # Повторное вычисление на запечатанном обучении выявляет подмену вероятностей.
        from domain.empirical_question_forecast import Observation
        observations=[Observation(**r) for r in sealed['binding']['sources']]
        request=ForecastRequest.parse(sealed['binding']['request'])
        require(sealed['modes']=={m:forecast(observations,request,m) for m in ('known_union','frequency','semantic','dependency')},'Sealed forecast has been changed')
        heldout=self.evaluator.read(targets)
        require(len(heldout)==len(set(targets)) and {o.reference for o in heldout}==set(targets),'Evaluator corpus differs')
        result={'run_id':run_id,'targets':[{'reference':o.reference,'binding':o.binding} for o in heldout],
                'scores':{m:score_prediction(v,heldout) for m,v in sealed['modes'].items()},
                'scientific_success':False,'future_target_reading_allowed':False,'blind_test':False,'expert_validated':False}
        evaluation_id=fingerprint(result);result['evaluation_id']=evaluation_id
        self.artifacts.evaluate(run_id,evaluation_id,result)
        return result
