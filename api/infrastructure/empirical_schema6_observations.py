"""Адаптер готовой схемы 6 и проверенной разметки; исходные карты не меняются."""
from domain.article_maps import require, fingerprint
from domain.research_semantics import project_map
from domain.structured_question_context import validate_feature_records
from domain.empirical_question_forecast import Observation, eligibility
from domain.statistical_evidence_derivation import number

VERSION = 'empirical-schema6-observations-1'

def findings(claim):
    attributes = {v['name']:v for v in claim.measurements}
    point=None
    if attributes.get('association direction',{}).get('value') == 'more decline with higher exposure':
        point='more_decline'
    for name in ('beta','slope difference','hazard ratio','odds ratio'):
        item=attributes.get(name)
        if item is None: continue
        estimate=number(item['value'])
        if name in ('hazard ratio','odds ratio'):
            require(item['unit']=='dimensionless' and estimate>0,'Positive dimensionless ratio required')
            point='more_decline' if estimate>1 else 'less_decline' if estimate<1 else 'zero_point_estimate'
        else:
            require(item['unit'] in ('mmse points/year','3mse points/visit per sd'),'Unregistered outcome orientation; no automatic unit conversion')
            point='more_decline' if estimate<0 else 'less_decline' if estimate>0 else 'zero_point_estimate'
        break
    detected=None
    if claim.modality=='not statistically detected': detected='not_detected'
    elif claim.modality=='statistically detected' and point in ('more_decline','less_decline'): detected='detected_'+point
    return {'direction':point,'detection':detected}

def profile_context(feature):
    def value(key):
        item=feature[key]
        return item['value'] if item['status']=='known' else None
    age=value('age');dementia=value('dementia_entry'); exposure=value('exposure');outcome=value('outcome');followup=value('followup');mci=value('mci');adjustments=value('adjustments')
    duration=None
    if followup:
        for name in ('protocol','first_to_last_visit','maximum_protocol','nominal'):
            quantity=followup.get(name)
            if isinstance(quantity,dict) and 'value' in quantity and 'unit' in quantity:
                require(quantity['unit'] in ('year','month'),'Explicit followup unit required')
                duration=quantity['value']/12 if quantity['unit']=='month' else quantity['value'];break
    adjustment_class=None if adjustments is None else 'vascular_apoe' if 'apoe_epsilon4' in adjustments else 'basic_baseline' if 'baseline_mmse_category' in adjustments else 'other_declared'
    return {'age_min':age['minimum']['value'] if age else None,'dementia_excluded':dementia['excluded'] if dementia else None,
            'specimen':exposure['specimen'] if exposure else None,'timing':exposure['timing'] if exposure else None,'exposure':'IL6',
            'outcome_scope':'global_change' if outcome else None,'followup_min':duration,
            'instrument':outcome['instrument'].replace('3mse','3ms') if outcome else None,'estimand':outcome['estimand'] if outcome else None,
            'contrast':exposure['contrast'] if exposure else None,'mci':mci['stratum'] if mci else None,'adjustment_class':adjustment_class}

def prepare_observations(bundles, features):
    maps={b['map']['article_id']:b['map'] for b in bundles}
    require(len(maps)==len(bundles),'Repeated article bundle')
    claims={}
    for bundle in bundles:
        for claim in project_map(bundle['map'],bundle['registry'],bundle['annotation']):
            claims[(claim.evidence.article_id,claim.claim_id)]=claim
    support={s['id']:s for b in bundles for s in b['origin'].get('context_revision',{}).get('audit',{}).get('sources',[])}
    profiles=validate_feature_records(features,claims,maps,'primary',support.values())
    observations=[]
    for key,profile in sorted(profiles.items()):
        claim=claims[key];context=profile_context(profile['record']['features'])
        require(claim.evidence.presentation=='own_result' and claim.predicate=='associated with' and
                claim.roles=={'exposure':'elevated baseline il-6','outcome':'subsequent global cognitive decline'}
                and claim.logic=='single' and not claim.negated and not claim.unresolved and claim.action_status is None,'Only explicit own empirical question results accepted')
        require(not eligibility(context),'Primary feature record no longer eligible')
        # В существующих шести наблюдениях нет проверенных переходов использования автора.
        require(not maps[key[0]]['graph'].get('transitions'),'Unexpected transition: a dedicated author-use audit is required')
        observation=Observation('/'.join(key),claim.evidence.family,claim.evidence.available_on,context,findings(claim),
                                {'source_sha256':claim.evidence.source_sha256,'run_id':claim.evidence.run_id,'claim_sha256':fingerprint(claim.to_dict())},False)
        observation.validate();observations.append(observation)
    return observations,claims,profiles
