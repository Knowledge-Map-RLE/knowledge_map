"""Номер источника и версия программы не подменяют измеряемую величину."""
import re
from collections import Counter
from copy import deepcopy
from domain.article_maps import fingerprint, require

VERSION = 'source-bound-forecast-attribute-kinds-1'
LOCATOR_FIELDS = {'table', 'source table', 'figure', 'source figure', 'source section', 'source appendix', 'source page'}
LOCATOR = re.compile(r'(?:table|figure|fig\.?|appendix|section|page)\s+(?:s?\d+(?:\.\d+)*[a-z]?|[ivx]+)', re.I)
SOFTWARE = re.compile(r'(?:stata|spss|sas|r|graphpad prism|prism)\s+(?:version\s+)?\d+(?:\.\d+){0,3}', re.I)


def classify_attribute(attribute):
    name, value, unit = attribute['name'], attribute['value'], attribute['unit']
    if not isinstance(value, str):
        return 'numeric_or_untyped' if isinstance(value, (int, float)) else 'untyped'
    if name in LOCATOR_FIELDS and unit is None and LOCATOR.fullmatch(value):
        return 'source_locator'
    if name == 'software' and unit is None and SOFTWARE.fullmatch(value):
        return 'method_software_version'
    return 'numeric_or_untyped' if re.search(r'\d', value) else 'nonnumeric_descriptor'


def blocks_unmodelled_numeric_transfer(attribute):
    # Локатор должен сначала пройти адресную проверку и отделение от научного утверждения.
    return classify_attribute(attribute) in {'numeric_or_untyped', 'source_locator', 'untyped'}


def project_source_locators(records, origins):
    output, proofs, coverage = deepcopy(records), [], []
    counts = Counter()
    require(origins is not None and set(origins['knowledge']) == set(records), 'Exact source registry required for locator projection')
    for key, parent in records.items():
        source = origins['sources'][key[0]]
        candidates = []
        for index, statement in enumerate(parent['frame']['statements']):
            for position, attribute in enumerate(statement['attributes']):
                if classify_attribute(attribute) != 'source_locator': continue
                # Номер переносится в доказательство только если найден в точном исходном фрагменте.
                evidence = [e for e in source['evidence'] if e['unit_id'] in parent['provenance'][index]['unit_ids']]
                pattern = re.compile(r'(?<!\w)' + re.escape(attribute['value']).replace(r'\ ', r'\s+') + r'(?!\w)', re.I)
                matched = [deepcopy(e) for e in evidence if pattern.search(e['text'])]
                reason = None
                if not parent['eligible']: reason = 'unknown_parent_context'
                elif not matched: reason = 'locator_not_found_in_bound_evidence'
                elif sum(a['name'] == attribute['name'] for a in statement['attributes']) != 1:
                    reason = 'ambiguous_locator_attribute'
                elif statement.get('attribute_types'):
                    reason = 'typed_attribute_contract_requires_separate_operator'
                if reason:
                    counts[reason] += 1
                    coverage.append({'key': key, 'statement_position': index, 'attribute_position': position, 'status': reason})
                else:
                    candidates.append({'statement_position': index, 'attribute_position': position,
                                       'attribute': deepcopy(attribute), 'evidence': matched})
        if not candidates: continue
        removed = {(c['statement_position'], c['attribute_position']) for c in candidates}
        for index, statement in enumerate(output[key]['frame']['statements']):
            statement['attributes'] = [a for position, a in enumerate(statement['attributes']) if (index, position) not in removed]
        proof = {'version': VERSION, 'key': key, 'run_id': parent['run_id'],
            'source_sha256': source['source_sha256'], 'graph_sha256': source['graph_sha256'],
            'parent_frame': deepcopy(parent['frame']), 'parent_frame_sha256': fingerprint(parent['frame']),
            'projected_frame': deepcopy(output[key]['frame']), 'locators': candidates,
            'scientific_attributes_removed': False, 'scope_changed': False, 'new_measurement': False,
            'reason_ru': 'Проверенный номер исходной таблицы или рисунка хранится в происхождении; '
                         'он не является числом научного результата и не предсказывает номер в другой статье.'}
        proof['id'] = fingerprint(proof)
        output[key]['source_locator_proof_id'] = proof['id']; proofs.append(proof)
        counts['source_locators_relocated'] += len(candidates)
    return output, {'version': VERSION, 'proofs': proofs, 'coverage': coverage, 'counts': dict(counts),
                    'model_calls': 0, 'new_measurements': 0}
