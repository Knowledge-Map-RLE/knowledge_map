"""Аудит границ корпуса: все блоки карты не означают весь смысл статьи."""
from collections import Counter
from domain.article_maps import require

VERSION = 'whole-map-input-audit-2'


def audit_source_coverage(result, coverage, artifact_sha256):
    units = {u['id']: u for u in result['source']['units']}
    knowledge = {k['knowledge_id']: k for k in result['graph']['knowledge']}
    rows = coverage.get('units')
    require(isinstance(rows, list) and len(rows) == len(units), 'Coverage must enumerate every source unit')
    require(len({r['unit_id'] for r in rows}) == len(rows), 'Duplicate coverage unit')
    require({r['unit_id'] for r in rows} == set(units), 'Coverage source units differ')
    represented = set()
    for row in rows:
        unit = units[row['unit_id']]
        require((row['start'], row['end']) == (unit['start'], unit['end']), 'Coverage coordinates differ')
        ids = row['knowledge_ids']
        require(isinstance(ids, list) and len(set(ids)) == len(ids) and all(k in knowledge for k in ids), 'Unknown coverage knowledge')
        require(row['status'] in {'selected_propositions_represented', 'not_formalized_in_this_revision', 'represented', 'excluded'}, 'Unknown coverage status')
        if row['status'] in {'not_formalized_in_this_revision', 'excluded'}:
            require(not ids and bool(row.get('reason_ru')), 'Excluded or unformalized fragment needs an exclusion reason and no knowledge')
        else:
            require(bool(ids) and not row.get('reason_ru'), 'Represented coverage must contain knowledge and no exclusion reason')
        for kid in ids:
            provenance = {u for s in knowledge[kid]['semantic_frame']['statements'] for u in s['provenance']['unit_ids']}
            require(row['unit_id'] in provenance, 'Coverage mapping lacks source provenance')
        represented.update(ids)
    require(represented == set(knowledge), 'Coverage omits canonical knowledge')
    declared = coverage.get('complete_semantic_coverage')
    require(type(declared) is bool, 'Explicit semantic coverage declaration required')
    require(not declared or all(r['status'] in {'represented', 'excluded'} for r in rows), 'Partial coverage cannot claim completeness')
    require(coverage.get('references_excluded') is True and result['source'].get('references_excluded') is True, 'References exclusion must be explicit')
    return {'version': VERSION, 'article_id': result['article_id'], 'run_id': result['run_id'],
            'source_sha256': result['source']['sha256'], 'coverage_artifact_sha256': artifact_sha256,
            'canonical_blocks': len(knowledge), 'source_units': len(units),
            'unit_statuses': dict(Counter(r['status'] for r in rows)),
            'declared_complete_semantic_coverage': declared,
            'expert_verified_complete_semantic_coverage': False,
            'complete_source_reviewed': coverage.get('complete_source_reviewed') is True,
            'table_cells_exhaustively_formalized': coverage.get('table_cells_exhaustively_formalized') is True,
            'source_limitations': coverage.get('source_limitations', []),
            'scope': 'declared_complete_map' if declared else 'selected_propositions_only'}


def audit_corpus(maps, metadata):
    signatures = {(m.get('prompt', {}).get('version'), m.get('dependency_prompt', {}).get('version')) for m in maps}
    if len(signatures) > 1:
        require(metadata.get('formalization_compatibility') == 'schema6_diagnostic_mixed_prompt_versions', 'Mixed prompt versions require an explicit diagnostic policy')
    audits = [m.get('forecast_input_coverage', {'article_id': m['article_id'], 'run_id': m['run_id'],
              'scope': 'source_coverage_not_audited', 'expert_verified_complete_semantic_coverage': False}) for m in maps]
    return {'version': VERSION, 'sources': audits,
            'all_canonical_blocks_processed': True,
            'entire_article_semantics_verified': False,
            'partial_maps': sum(a['scope'] == 'selected_propositions_only' for a in audits),
            'source_coverage_not_audited': sum(a['scope'] == 'source_coverage_not_audited' for a in audits),
            'prompt_versions': [list(s) for s in sorted(signatures, key=str)],
            'mixed_prompt_versions': len(signatures) > 1,
            'confirmatory_corpus': False}
