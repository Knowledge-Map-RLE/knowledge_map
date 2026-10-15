"""Адресный допуск утверждений внутри противопоставления сохраняет его полный смысл."""
from copy import deepcopy
from domain.article_maps import fingerprint, require

VERSION = 'source-bound-contrast-clause-license-1'
FOUNDATION = ('A source-asserted contrast retains each independently asserted clause under that clause\'s '
              'complete scope. The contrast relation remains in the full parent; no argument conclusion, '
              'conditional antecedent, universal law, independent replication or causal inference is added.')


def validate_licenses(originals, origins, audit):
    if audit is None:
        return {}
    require(isinstance(audit, dict) and audit.get('version') == VERSION
            and audit.get('author') == 'Codex' and audit.get('model_calls') == 0
            and audit.get('expert_validated') is False, 'Unsupported compound license provenance')
    require(isinstance(audit.get('entries'), list), 'Compound license entries required')
    result = {}
    for entry in audit['entries']:
        key = entry['article_id'], entry['knowledge_id']
        require(key in originals and key not in result, 'Unknown or repeated compound license')
        raw = originals[key]; native = raw.get('native_knowledge')
        require(native is not None, 'Exact native compound knowledge required')
        source = origins['sources'][key[0]]
        require(entry['run_id'] == raw['run_id'] and entry['source_sha256'] == source['source_sha256']
                and entry['graph_sha256'] == source['graph_sha256']
                and entry['knowledge_sha256'] == fingerprint(native), 'Compound license binding differs')
        frame = native['semantic_frame']
        require(native['kind'] == 'state' and native['grounding'] == 'source_explicit'
                and frame['logic'] == raw['frame']['logic'] == 'contrast'
                and len(frame['statements']) >= 2, 'Only source-explicit state contrasts are licensed')
        require(entry['statement_ids'] == [s['statement_id'] for s in frame['statements']],
                'Compound license must account for every clause in source order')
        require(entry['asserted_under_recorded_scope'] is True and entry['discourse_relation_retained'] is True
                and entry['reason_ru'], 'Explicit scoped clause assertion required')
        units = {uid for s in frame['statements'] for uid in s['provenance']['unit_ids']}
        catalog = {e['unit_id']: e for e in source['evidence']}
        evidence = entry['evidence']
        require(isinstance(evidence, list) and len(evidence) == len(units)
                and {e['unit_id'] for e in evidence} == units, 'Complete compound source evidence required')
        for e in evidence:
            require(e == catalog.get(e['unit_id']), 'Compound source evidence differs from exact origin audit')
        result[key] = deepcopy(entry)
    return result
