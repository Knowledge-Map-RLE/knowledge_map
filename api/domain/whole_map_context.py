"""Адресный аудит контекста и типов величин без изменения исходной карты."""
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize, normalize_attribute, contains_unresolved_cycle

VERSION = 'whole-map-context-audit-1'
TYPE_NAMES = {
    'dimensionless_statistic': {'p', 'cohens d', 'z threshold', 'minimum incremental r2', 'incremental r2'},
    'category_code': {'long code', 'normal code', 'absence code', 'presence code'},
}


def audit_index(maps, audit):
    if audit is None:
        return {}
    require(audit['version'] == VERSION and audit['author'] == 'Codex' and audit['expert_validated'] is False
            and audit['model_calls'] == 0, 'Unsupported context audit provenance')
    sources = {m['article_id']: m for m in maps}
    index = {}
    for entry in audit['entries']:
        article, kid = entry['article_id'], entry['knowledge_id']
        require(article in sources, 'Audit references an unlisted source')
        source = sources[article]
        require(entry['run_id'] == source['run_id'] and entry['source_sha256'] == source['source']['sha256']
                and entry['graph_sha256'] == fingerprint(source['graph']), 'Context audit binding differs')
        knowledge = next((k for k in source['graph']['knowledge'] if k['knowledge_id'] == kid), None)
        require(knowledge is not None and entry['knowledge_sha256'] == fingerprint(knowledge), 'Audited knowledge changed')
        key = (article, kid)
        require(key not in index, 'Duplicate context audit entry')
        require(entry['decision'] in {'resolve_for_pattern_analysis', 'retain_unknown'}, 'Invalid audit decision')
        require(entry['context_resolution'] in {'source_local_report', 'existing_scope', 'retain_unknown'}, 'Invalid context resolution')
        require(entry['reason_ru'] and entry['reason_en'] and entry['evidence'], 'Audit reason or evidence missing')
        units = {u['id']: u for u in source['source']['units']}
        parent_units = {u for s in knowledge['semantic_frame']['statements'] for u in s['provenance']['unit_ids']}
        for evidence in entry['evidence']:
            require(evidence['unit_id'] in parent_units, 'Audit evidence is unrelated to knowledge')
            unit = units[evidence['unit_id']]
            require(evidence['start'] == unit['start'] and evidence['end'] == unit['end'] <= source['source']['content_end']
                    and evidence['text'] == source['source']['text'][unit['start']:unit['end']]
                    and evidence['sha256'] == sha256(evidence['text'].encode('utf8')).hexdigest(), 'Context evidence differs')
        statements = {s['statement_id']: s for s in knowledge['semantic_frame']['statements']}
        seen = set()
        for annotation in entry['attribute_types']:
            sid, name, kind = annotation['statement_id'], normalize(annotation['attribute_name']), annotation['type']
            require((sid, name) not in seen, 'Duplicate measurement type')
            seen.add((sid, name))
            require(sid in statements and kind in TYPE_NAMES and name in TYPE_NAMES[kind], 'Unestablished measurement type')
            attributes = [a for a in statements[sid]['qualifiers']['attributes'] if normalize(a['name']) == name]
            require(len(attributes) == 1 and attributes[0]['unit'] is None, 'Typed attribute differs')
            if kind == 'category_code':
                require(type(attributes[0]['value']) is int and attributes[0]['value'] in (0, 1), 'Invalid binary category code')
        index[key] = entry
    return index


def apply_context_audit(knowledge, original, entry):
    """Восстанавливает только явно проверенные типы; числа и логика сохраняются."""
    result = deepcopy(knowledge)
    if entry is None or entry['decision'] == 'retain_unknown':
        return result
    require(entry['context_resolution'] != 'retain_unknown', 'Unresolved context cannot be admitted')
    raw = {s['statement_id']: s for s in original['semantic_frame']['statements']}
    for statement in result['statements']:
        if entry['context_resolution'] == 'source_local_report':
            # Источник задаёт область локального отчёта, но не неизвестный календарный период.
            condition = 'source-local report: ' + knowledge['article_id']
            statement['scope']['conditions'] = sorted(set(statement['scope']['conditions']) | {condition})
            statement['scope']['study_group'] = knowledge['article_id']
        types = {normalize(a['attribute_name']): a['type'] for a in entry['attribute_types']
                 if a['statement_id'] == statement['id']}
        if types:
            statement['attribute_types'] = types
        unknown = (original['knowledge_kind'] != 'definition' and not statement['scope']['time']
                   and not statement['scope']['conditions'])
        unknown = unknown or any(type(a['value']) in (int, float) and normalize_attribute(a)['unit'] is None
                                 and normalize(a['name']) not in types
                                 for a in raw[statement['id']]['qualifiers']['attributes']
                                 if normalize(a['name']) != 'source grounded description')
        unknown = unknown or any(contains_unresolved_cycle(r['value']) for r in statement['roles'])
        statement['unknown_context'] = unknown
    return result
