"""Известные параметры процедуры подставляются из посылки, измеренные ответы не создаются."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re
from domain.article_maps import fingerprint, require
from domain.forecast_attribute_kinds import blocks_unmodelled_numeric_transfer

VERSION = 'source-bound-protocol-parameter-transfer-1'
FIELDS = {'dose': 'dose', 'drug dose': 'dose', 'doses': 'dose', 'tnf dose': 'challenge_dose',
    'duration': 'duration', 'lead time': 'lead_time',
    'days of manifest disease': 'manifest_schedule', 'disease-relative days': 'manifest_schedule'}
UNITS = {'dose': {'mg/kg', 'ug/kg', 'ng/kg', 'mg', 'ug', 'ng', 'mmol/kg', 'nmol/kg'},
    'challenge_dose': {'mg/kg', 'ug/kg', 'ng/kg', 'mg', 'ug', 'ng'},
    'duration': {'day', 'h', 'min', 's', 'week'}, 'lead_time': {'day', 'h', 'min', 's'}, 'manifest_schedule': {'day'}}
NUMBER = re.compile(r'(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d{1,3})?')
CONTEXT_FIELDS = {'route', 'phase'}


def values(value):
    """Только явный конечный положительный список: диапазон и неопределённость не угадываются."""
    if not isinstance(value, str) or len(value) > 512: return None
    items = value.split(';')
    if not 1 <= len(items) <= 32 or any(not NUMBER.fullmatch(v.strip()) for v in items): return None
    try: result = tuple(Decimal(v.strip()) for v in items)
    except InvalidOperation: return None
    return result if all(v.is_finite() and v > 0 for v in result) else None


def specification(attribute):
    kind = FIELDS.get(attribute['name']); parsed = values(attribute['value'])
    if kind is None or parsed is None or attribute['unit'] not in UNITS[kind]: return None
    return {'kind': kind, 'unit': attribute['unit'], 'arity': len(parsed)}


def protocol_frame_identity(frame):
    """Равные записи известных величин не создают ложную новизну; исходные строки сохранены."""
    normalized = deepcopy(frame)
    for s in normalized['statements']:
        for attr in s['attributes']:
            if specification(attr) is None: continue
            numbers = []
            for value in values(attr['value']):
                text = format(value, 'f')
                numbers.append(text.rstrip('0').rstrip('.') if '.' in text else text)
            attr['value'] = '; '.join(numbers)
    return fingerprint(normalized)


def primary_origin(record, expected):
    proof = record.get('projection_proof')
    if proof is None: return False
    native = proof.get('complete_native_knowledge')
    require(native is not None and fingerprint(native) == proof.get('parent_knowledge_sha256'),
            'Protocol transfer requires exact complete native parent')
    require(list(record['native_key']) == proof['parent_key'] and record['run_id'] == proof['run_id'],
            'Protocol transfer native identity changed')
    require(fingerprint(record['frame']) == proof['view_frame_sha256'], 'Protocol view changed after source projection')
    require(native['kind'] == record['frame']['kind'] and native['action_status'] == record['frame']['action_status'],
            'Protocol source action status changed')
    return proof['origin']['origin'] == expected


def roles(statement):
    items = statement['roles']
    if len({r['role'] for r in items}) != len(items): return None
    return {r['role']: (r['value'], r.get('reference_kind')) for r in items}


def manifest_clock(record, statement):
    if any(a['name'] == 'days of manifest disease' for a in statement['attributes']): return True
    text = record['projection_proof']['complete_native_knowledge']['display_text']
    return re.search(r'\b(?:of|during)\s+(?:the\s+)?manifest\s+(?:disease|EAE)\b', text, re.I) is not None


def compatible(body, head, bs, hs, kind):
    if body['frame']['kind'] != 'action' or body['frame']['action_status'] != 'performed': return False
    if not primary_origin(body, 'primary_method'): return False
    if body['native_key'][0] != head['native_key'][0] or body['run_id'] != head['run_id']: return False
    if bs['negated'] or bs['scope']['modality'] is not None or bs['scope'] != hs['scope']: return False
    br, hr = roles(bs), roles(hs)
    if br is None or hr is None: return False
    # Равное число при другом препарате или группе не является источником параметра.
    anchors = ['intervention', 'population'] + (['challenge'] if kind == 'challenge_dose' else [])
    if any(r not in br or r not in hr or br[r] != hr[r] for r in anchors): return False
    if 'comparator' in hr and br.get('comparator') != hr['comparator']: return False
    # Доза не привязывается к другой процедуре с теми же мышами и препаратом.
    for attr in hs['attributes']:
        spec = specification(attr)
        if spec is not None:
            if not any(specification(a) == spec and values(a['value']) == values(attr['value']) for a in bs['attributes']): return False
        elif attr['name'] in CONTEXT_FIELDS:
            if sum(a == attr for a in bs['attributes']) != 1: return False
    if kind == 'manifest_schedule':
        # Отсчёт от индукции и от проявления болезни нельзя объединять по слову «день».
        if not manifest_clock(body, bs) or not manifest_clock(head, hs): return False
    return True


def protocol_copy_plan(body, head):
    numeric = [(si, ai, a) for si, s in enumerate(head['frame']['statements'])
               for ai, a in enumerate(s['attributes']) if blocks_unmodelled_numeric_transfer(a)]
    if not numeric: return None
    frame = head['frame']
    if frame['kind'] != 'state' or frame['action_status'] is not None or not primary_origin(head, 'primary_result'): return None
    if not head['projection_proof'].get('qualitative_result_proof_id'): return None
    copies = []
    for si, ai, attr in numeric:
        hs = frame['statements'][si]; spec = specification(attr)
        if spec is None or hs['negated'] or hs['scope']['modality'] is not None: return None
        if sum(a['name'] == attr['name'] for a in hs['attributes']) != 1: return None
        candidates = []
        for record in body:
            for bi, bs in enumerate(record['frame']['statements']):
                if not compatible(record, head, bs, hs, spec['kind']): continue
                for pi, parameter in enumerate(bs['attributes']):
                    if specification(parameter) != spec or values(parameter['value']) != values(attr['value']): continue
                    if sum(a['name'] == parameter['name'] for a in bs['attributes']) != 1: continue
                    candidates.append({'premise_key': list(record['key']), 'premise_statement': bi, 'premise_attribute': pi,
                        'head_statement': si, 'head_attribute': ai, 'specification': spec,
                        'premise_parameter': deepcopy(parameter), 'head_parameter': deepcopy(attr),
                        'premise_native_key': list(record['native_key']), 'head_native_key': list(head['native_key']),
                        'premise_projection_proof_id': record['projection_proof']['id'],
                        'head_projection_proof_id': head['projection_proof']['id']})
        if not candidates: return None
        copies.append(min(candidates, key=lambda c: (c['premise_key'], c['premise_statement'], c['premise_attribute'])))
    proof = {'version': VERSION, 'copies': copies, 'all_blocking_head_attributes_accounted': True,
        'source_same_procedure_required': True, 'scope_erased': False, 'measured_response_created': False,
        'all_head_protocol_context_fields_matched': True,
        'causal_effect_proven': False, 'numeric_result_prediction': False}
    proof['id'] = fingerprint(proof)
    return proof


def parameterize_frames(ordered, head, plan):
    require(plan == protocol_copy_plan(ordered, head), 'Protocol copy license does not match complete input views')
    premises = [deepcopy(r['frame']) for r in ordered]; conclusion = deepcopy(head['frame']); slots = {}
    for copy in plan['copies']:
        i = next(i for i, r in enumerate(ordered) if list(r['key']) == copy['premise_key'])
        slot = (i, copy['premise_statement'], copy['premise_attribute'])
        if slot not in slots:
            slots[slot] = {'protocol_variable': '$protocol' + str(len(slots)), **copy['specification']}
            parameter = premises[i]['statements'][slot[1]]['attributes'][slot[2]]
            require(parameter == copy['premise_parameter'], 'Protocol parameter changed after licensing')
            parameter['value'] = deepcopy(slots[slot])
        parameter = conclusion['statements'][copy['head_statement']]['attributes'][copy['head_attribute']]
        require(parameter == copy['head_parameter'], 'Protocol head changed after licensing')
        parameter['value'] = deepcopy(slots[slot])
    return premises, conclusion


def bind_parameters(pattern, actual, bindings, source_record=None):
    bindings, transformed = dict(bindings), deepcopy(actual)
    if len(pattern['statements']) != len(actual['statements']): return None
    for ps, actual_s in zip(pattern['statements'], transformed['statements']):
        pa, aa = ps['attributes'], actual_s['attributes']
        if len(pa) != len(aa): return None
        for expected, observed in zip(pa, aa):
            marker = expected['value']
            if not isinstance(marker, dict) or 'protocol_variable' not in marker: continue
            if source_record is None or source_record['frame'] != actual or not primary_origin(source_record, 'primary_method'): return None
            if marker['kind'] == 'manifest_schedule' and not manifest_clock(source_record, actual_s): return None
            if expected['name'] != observed['name'] or expected['unit'] != observed['unit']: return None
            if specification(observed) != {k: marker[k] for k in ['kind', 'unit', 'arity']}: return None
            name, value = marker['protocol_variable'], observed['value']
            if name in bindings and values(bindings[name]) != values(value): return None
            bindings.setdefault(name, value); observed['value'] = deepcopy(marker)
    return transformed, bindings


def instantiate_parameters(frame, bindings):
    frame = deepcopy(frame)
    for s in frame['statements']:
        for attr in s['attributes']:
            marker = attr['value']
            if not isinstance(marker, dict) or 'protocol_variable' not in marker: continue
            require(marker['protocol_variable'] in bindings, 'Unbound protocol parameter')
            attr['value'] = deepcopy(bindings[marker['protocol_variable']])
            require(specification(attr) == {k: marker[k] for k in ['kind', 'unit', 'arity']}, 'Protocol instantiation violates its quantity type')
    return frame
