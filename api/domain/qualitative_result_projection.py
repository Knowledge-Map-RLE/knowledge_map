"""Явный качественный результат отделяется от величины и точности, сохраняя источник."""
import re
from collections import Counter
from copy import deepcopy
from decimal import Decimal

from domain.article_maps import fingerprint, require
from domain.statistical_primitives import number

VERSION = 'source-bound-qualitative-result-projection-2'
PREDICATES = frozenset({'expression increased', 'reduced after intervention', 'induction attenuated',
    'downregulation prevented', 'cell count reduced after intervention', 'induction abrogated',
    'memory performance improved', 'morphology preserved after intervention',
    'exacerbated after intervention', 'improved after intervention', 'onset delayed after intervention',
    'concentration reduced after intervention', 'apical localization preserved',
    'plaque burden reduced after intervention', 'plaque count reduced after intervention'})
SAMPLE_FIELDS = frozenset({'n per group', 'animals per group', 'pbs n', 'tros n', 'app n',
    'tnfr1 deficient app n', 'control n', 'ko app n', 'ko n', 'wt n', 'normal n', 'n'})
INTERPRETATION = {'name': 'qualitative projection interpretation',
    'value': 'reported direction only; magnitude, significance and causality not transferred', 'unit': None}


def summary_kind(attribute, predicate):
    name, value, unit = attribute['name'], attribute['value'], attribute['unit']
    if not isinstance(value, str): return None
    if name == 'n' and unit is None: return None
    if name in SAMPLE_FIELDS and unit in {None, 'mouse', 'animals', 'participants', 'mice per group', 'mouse per group'}:
        match = re.fullmatch(r'(\d+)(?:-(\d+))?', value)
        if match and 0 < int(match[1]) <= int(match[2] or match[1]): return 'sample_size'
    if name in {'p', 'p upper bound'} and unit in {None, 'dimensionless'}:
        point = number(value)
        if point is not None and Decimal(0) <= point <= Decimal(1): return 'reported_test_summary'
    if name == 'approximate fold change' and unit == 'fold' and predicate == 'expression increased':
        point = number(value)
        if point is not None and point > 1: return 'reported_magnitude'
    if name in {'significance', 'statistical status'} and unit is None and value in {
            'significant increase', 'significant decrease', 'significant improvement'}:
        return 'reported_significance_descriptor'
    return None


def project_qualitative_results(records, origins):
    require(origins is not None and set(origins['knowledge']) == set(records),
            'Exact source registry required for qualitative projection')
    output, proofs, coverage, counts = deepcopy(records), [], [], Counter()
    for key, parent in records.items():
        source = origins['sources'][key[0]]
        annotation = origins['knowledge'][key]['statements']
        require(len(annotation) == len(parent['frame']['statements']) == len(parent['provenance']),
                'Complete ordered qualitative statement origins required')
        projected = []
        for index, statement in enumerate(parent['frame']['statements']):
            if statement['predicate'] not in PREDICATES: continue
            reason = None
            origin = annotation[index]
            evidence = [e for e in source['evidence'] if e['unit_id'] in origin['evidence_unit_ids']]
            if not parent['eligible']: reason = 'unknown_parent_context'
            elif source['document_kind'] != 'primary_study' or origin['origin'] != 'primary_result':
                reason = 'no_primary_result_origin'
            elif parent['frame']['kind'] != 'state' or parent['frame']['action_status'] is not None:
                reason = 'not_observed_state'
            elif statement['negated'] or statement['scope']['modality'] is not None:
                reason = 'negated_or_modal_result'
            elif statement.get('attribute_types'): reason = 'typed_attribute_requires_separate_operator'
            elif len({a['name'] for a in statement['attributes']}) != len(statement['attributes']):
                reason = 'ambiguous_attributes'
            elif any(a['name'] == INTERPRETATION['name'] for a in statement['attributes']):
                reason = 'already_projected_or_unknown_interpretation'
            elif not origin['evidence_unit_ids'] or set(origin['evidence_unit_ids']) != set(parent['provenance'][index]['unit_ids']) or {e['unit_id'] for e in evidence} != set(origin['evidence_unit_ids']):
                reason = 'incomplete_source_evidence'
            if reason:
                counts[reason] += 1; coverage.append({'key': key, 'position': index, 'status': reason}); continue
            removed = [{'position': position, 'attribute': deepcopy(a), 'summary_kind': kind}
                for position, a in enumerate(statement['attributes'])
                if (kind := summary_kind(a, statement['predicate'])) is not None]
            positions = {r['position'] for r in removed}
            target = output[key]['frame']['statements'][index]
            target['attributes'] = [a for pos, a in enumerate(target['attributes']) if pos not in positions] + [deepcopy(INTERPRETATION)]
            projected.append({'position': index, 'statement_id': origin['statement_id'],
                'origin': deepcopy(origin), 'evidence': deepcopy(evidence), 'summaries': removed})
            counts['qualitative_statements'] += 1
            counts['summaries_in_evidence'] += len(removed)
        if not projected: continue
        proof = {'version': VERSION, 'key': key, 'run_id': parent['run_id'],
            'source_sha256': source['source_sha256'], 'graph_sha256': source['graph_sha256'],
            'parent_frame': deepcopy(parent['frame']), 'parent_frame_sha256': fingerprint(parent['frame']),
            'projected_frame': deepcopy(output[key]['frame']), 'statements': projected,
            'origin_registry_sha256': origins.get('audit_sha256'),
            'scope_changed': False, 'participants_changed': False, 'direction_inferred_from_numbers': False,
            'new_measurement': False, 'significance_predicted': False, 'causality_asserted': False,
            'expert_validated': False,
            'reason_ru': 'Направление уже явно записано в привязанной к источнику семантике. '
                'Численная величина, точность и размер выборки остаются в обосновании. '
                'Сравнение происходит только на уровне качественного результата; дозы, сроки '
                'и прочие условия не удаляются. Значимость и причинность не переносятся.'}
        proof['id'] = fingerprint(proof)
        output[key]['qualitative_result_proof_id'] = proof['id']; proofs.append(proof)
    return output, {'version': VERSION, 'proofs': proofs, 'coverage': coverage, 'counts': dict(counts),
        'model_calls': 0, 'new_measurements': 0, 'rule_discovery': False}
