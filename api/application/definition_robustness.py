"""Проверка происхождения ручных знаний до анализа устойчивости определений."""
from domain.article_maps import digest, require
from domain.definition_robustness import audit_definition_changes


class AuditDefinitionRobustness:
    def execute(self, spec, evidence, texts):
        require(spec['author']=='Codex' and spec['model_calls']==0 and spec['expert_validated'] is False,
                'Unsupported annotation authorship')
        for p in evidence.values():
            require(p['source_id'] in texts and p['offset_encoding']=='unicode_codepoints', 'Unknown source encoding')
            text=texts[p['source_id']]
            require(p['source_sha256']==digest(text), 'Source hash differs')
            require(type(p['start']) is int and type(p['end']) is int and 0<=p['start']<p['end']<=len(text), 'Invalid fragment bounds')
            require(text[p['start']:p['end']]==p['text'] and digest(p['text'])==p['text_sha256'], 'Fragment differs')
        for s in spec['series']:
            for key in s['provenance']+[c['evidence_id'] for c in s['cells']]:
                require(key in evidence and evidence[key]['source_id']==s['source_id'], 'Unknown provenance')
            for cell in s['cells']:
                fragment=evidence[cell['evidence_id']]['text']
                require(all(value in fragment for value in [cell['value'],*cell['interval'],cell['person_years']]), 'Numeric data absent from row')
        return audit_definition_changes(spec['series'],spec['comparisons'])
