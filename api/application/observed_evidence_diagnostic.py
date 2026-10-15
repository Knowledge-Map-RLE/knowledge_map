"""Диагностирует известные результаты и не открывает сценарий научного прогноза."""
from application.ports.question_prediction import ResearchArtifacts
from domain.article_maps import digest, fingerprint, require
from domain.research_semantics import compare_claims, validate_context, valid_date
from domain.statistical_evidence_derivation import derive_evidence_label

VERSION = 'observed-study-evidence-diagnostic-1'


class CompareObservedStudyEvidence:
    def __init__(self, artifacts: ResearchArtifacts):
        self.artifacts = artifacts

    def execute(self, studies, cutoff):
        valid_date(cutoff)
        require(len(studies) == 2, 'This diagnostic requires exactly two explicit study results')
        ids = [s['claim'].evidence.article_id for s in studies]
        require(len(set(ids)) == 2, 'Distinct study results required')
        labels = []
        for study in studies:
            claim, source = study['claim'], study['source']
            require(claim.evidence.presentation == 'own_result' and claim.evidence.available_on <= cutoff
                    and claim.evidence.source_sha256 == source['sha256'] == digest(source['text']),
                    'Historical own-result provenance required')
            valid_date(claim.evidence.available_on); validate_context(claim.context)
            require(claim.evidence.spans and 0 < source['content_end'] <= len(source['text']), 'Primary source body required')
            for span in claim.evidence.spans:
                require(span['offset_encoding'] == 'unicode_code_points'
                        and 0 <= span['start'] < span['end'] <= source['content_end']
                        and source['text'][span['start']:span['end']] == span['text'], 'Evidence fragment differs')
            evidence = study['statistical_evidence']
            require(evidence.effect in {'odds_ratio','linear_coefficient'}, 'Unsupported statistical effect')
            # Числовые входы должны уже присутствовать в наблюдённом семантическом утверждении.
            measurements = {m['name']:m for m in claim.measurements}
            name = 'odds ratio' if evidence.effect == 'odds_ratio' else 'beta'
            require(name in measurements and measurements[name]['value'] == evidence.estimate
                    and measurements[name]['unit'] == evidence.unit
                    and measurements.get('p',{}).get('value') == evidence.p
                    and measurements.get(name+' ci',{}).get('value') == (None if evidence.ci95 is None else list(evidence.ci95)),
                    'Statistical evidence differs from source claim semantics')
            labels.append({'article_id':claim.evidence.article_id,'claim_id':claim.claim_id,
                           'derivation':derive_evidence_label(evidence)})
        comparison = compare_claims(studies[0]['claim'],studies[1]['claim'])
        binding = {'version':VERSION,'cutoff':cutoff,'claims':[s['claim'].to_dict() for s in studies],
                   'statistical_evidence':[{**vars(s['statistical_evidence']),
                                            'ci95':None if s['statistical_evidence'].ci95 is None else list(s['statistical_evidence'].ci95)} for s in studies]}
        result = {'run_id':fingerprint(binding),'binding':binding,'comparison':comparison,'derived_labels':labels,
                  'forecast_issued':False,'future_target_selected':False,'new_training_sources':0,
                  'model_calls':0,'expert_validated':False,
                  'scope':'retrospective_reconstruction_of_observed_evidence_not_prediction'}
        self.artifacts.audit(result['run_id'],result)
        return result
