"""Проекция числовой семантики готового блока; текст не используется как классификатор."""
from math import isfinite
from domain.article_maps import require

def structured_findings(knowledge, alpha):
    frame = knowledge['semantic_frame']
    require(frame['logic'] == 'single' and len(frame['statements']) == 1, 'Explicit single empirical statement required')
    statement = frame['statements'][0]
    require(not statement['negated'] and statement['predicate'] in {'associated with', 'estimated association', 'estimated hazard ratio'}, 'Unsupported empirical statement')
    attrs = statement['qualifiers']['attributes']
    require(len({a['name'] for a in attrs}) == len(attrs), 'Ambiguous numerical attributes')
    attrs = {a['name']: a for a in attrs}
    require(attrs.get('evidence_presentation', {}).get('value') == 'own_result', 'Citation is not an own empirical result')
    def number(item):
        value = item['value']
        require(type(value) in {int, float} and isfinite(value), 'Finite numeric semantic measurement required')
        return value
    direction = None
    if 'estimate' in attrs:
        require(attrs['estimate']['unit'] in {'MMSE points/year', '3MSE points/6-month visit per SD'}, 'Unregistered outcome orientation')
        value = number(attrs['estimate'])
        direction = 'more_decline' if value < 0 else 'less_decline' if value > 0 else 'zero_point_estimate'
    elif 'HR' in attrs:
        value = number(attrs['HR'])
        require(attrs['HR']['unit'] == 'dimensionless' and value > 0 and statement['predicate'] == 'estimated hazard ratio', 'Explicit positive decline-event hazard ratio required')
        direction = 'more_decline' if value > 1 else 'less_decline' if value < 1 else 'zero_point_estimate'
    detection = None
    if 'p' in attrs:
        p = number(attrs['p'])
        require(attrs['p']['unit'] == 'dimensionless' and 0 <= p <= 1, 'Probability outside range')
        require(type(alpha) in {int, float} and isfinite(alpha) and 0 < alpha < 1, 'Exact source detection threshold required')
        detection = 'detected' if p < alpha else 'not_detected'
    elif attrs.get('detection', {}).get('value') == 'statistically significant':
        detection = 'detected'
    return {'reported_detection': detection, 'point_direction': direction}
