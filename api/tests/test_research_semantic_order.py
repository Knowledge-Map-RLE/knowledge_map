"""Стабильный порядок сравнения для неизменяемых исследовательских артефактов."""
from dataclasses import replace

from domain.research_semantics import Evidence, SemanticClaim, compare_claims, context_value


def claim_with_measurements(values):
    return SemanticClaim('K1S1', 'K1', 'associated with', {'exposure': 'IL-6', 'outcome': 'cognitive decline'},
        False, None, 'not statistically detected',
        {'species': context_value('human'), 'time': context_value('followup')},
        tuple({'name': name, 'value': value, 'unit': 'dimensionless'} for name, value in values),
        None, 'single', 'Claim', Evidence('article', 'run', 'source', '2020-01-01', 'family', 'own_result', ()))


def test_matching_measurement_diagnostics_have_canonical_order():
    names=['z score', 'p', 'hazard ratio', 'beta', 'confidence interval', 'sample size']
    left=claim_with_measurements([(name,index) for index,name in enumerate(names)])
    right=replace(left, measurements=tuple(reversed(left.measurements)))
    result=compare_claims(left,right)
    assert result['relation']=='equivalent'
    assert result['matched']==['predicate','exposure','outcome']+['measurement:'+name for name in sorted(names)]
    assert compare_claims(right,left)==result


def test_different_measurement_diagnostics_have_canonical_order():
    names=['z score', 'p', 'hazard ratio', 'beta', 'confidence interval', 'sample size']
    left=claim_with_measurements([(name,index) for index,name in enumerate(names)])
    right=claim_with_measurements([(name,index+10) for index,name in enumerate(names)])
    result=compare_claims(left,right)
    assert result['relation']=='partial'
    assert result['differences']==['value:'+name for name in sorted(names)]
    assert compare_claims(right,left)==result
