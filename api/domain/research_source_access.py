"""Полный текст и конфликтующие описания проверяются до формализации обучающего источника."""
from copy import deepcopy
import re
from domain.article_maps import digest, fingerprint, require

VERSION = 'research-source-access-1'
KINDS = {'journal_abstract', 'author_summary', 'bibliographic_metadata',
         'full_primary_article', 'full_primary_author_chapter'}
MATRICES = {'plasma', 'serum', 'whole_blood', 'whole_blood_supernatant'}


def audit_source_access(candidate, documents):
    require(set(candidate) == {'doi', 'pmid', 'publication_year', 'cutoff_year'}
            and isinstance(candidate['doi'], str) and re.fullmatch(r'10\.\d{4,9}/\S+', candidate['doi'])
            and isinstance(candidate['pmid'], str) and candidate['pmid'].isdigit()
            and type(candidate['publication_year']) is int and type(candidate['cutoff_year']) is int
            and 1900 <= candidate['publication_year'] <= candidate['cutoff_year'] == 2022,
            'Explicit historical article identity required')
    require(bool(documents) and len({d['id'] for d in documents}) == len(documents), 'Explicit unique documents required')
    grouped = {}; verified_full = []
    for document in documents:
        require(set(document) == {'id', 'doi', 'pmid', 'kind', 'language', 'text', 'sha256',
                                  'full_text_verified', 'sections', 'assertions'}, 'Source descriptor fields differ')
        require(document['doi'] == candidate['doi'] and document['pmid'] == candidate['pmid'],
                'Unmatched article identity cannot supply evidence')
        require(document['kind'] in KINDS and document['language'] in {'en', 'ja'}
                and isinstance(document['text'], str) and bool(document['text'].strip())
                and document['sha256'] == digest(document['text']) and type(document['full_text_verified']) is bool,
                'Source type, language or provenance differs')
        def validate_span(span):
            require(set(span) == {'start', 'end', 'text', 'offset_encoding'}
                    and span['offset_encoding'] == 'unicode_code_points'
                    and type(span['start']) is int and type(span['end']) is int
                    and 0 <= span['start'] < span['end'] <= len(document['text'])
                    and document['text'][span['start']:span['end']] == span['text'], 'Source fragment differs')
        if document['full_text_verified']:
            require(document['kind'] in {'full_primary_article', 'full_primary_author_chapter'}
                    and document['language'] == 'en' and set(document['sections']) == {'methods', 'results', 'references'},
                    'An abstract, summary or unreviewed text cannot substitute for a full English primary text')
            for section in document['sections'].values(): validate_span(section)
            methods, results, references = (document['sections'][key] for key in ('methods', 'results', 'references'))
            require(methods['end'] <= results['start'] and results['end'] <= references['start'],
                    'Primary methods, results and references must be distinct ordered fragments')
            verified_full.append(document['id'])
        else:
            require(document['sections'] == {}, 'Unverified completeness cannot establish primary sections')
        for assertion in document['assertions']:
            require(set(assertion) == {'scope', 'field', 'value', 'evidence'}
                    and isinstance(assertion['scope'], str) and bool(assertion['scope'].strip())
                    and assertion['field'] == 'matrix' and assertion['value'] in MATRICES
                    and bool(assertion['evidence']), 'Explicit comparable specimen assertion required')
            require(document['kind'] != 'bibliographic_metadata', 'Bibliographic metadata cannot establish methods')
            for span in assertion['evidence']: validate_span(span)
            if document['full_text_verified']:
                require(all(methods['start'] <= span['start'] < span['end'] <= methods['end']
                            for span in assertion['evidence']), 'Specimen evidence must come from own primary methods')
            key = assertion['scope'], assertion['field']
            grouped.setdefault(key, []).append({'document_id': document['id'], 'value': assertion['value'],
                                                'kind': document['kind'], 'evidence': deepcopy(assertion['evidence'])})
    conflicts = []
    for (scope, field), assertions in sorted(grouped.items()):
        if len({a['value'] for a in assertions}) > 1:
            conflicts.append({'scope': scope, 'field': field, 'assertions': assertions,
                              'resolution': 'unresolved', 'resolved_value': None})
    blockers = []
    if not verified_full: blockers.append('full_primary_text_not_acquired_and_verified')
    if conflicts: blockers.append('source_descriptions_conflict')
    # Полнота документа ещё не доказывает пригодность по исследовательскому вопросу.
    return {'version': VERSION, 'candidate': deepcopy(candidate), 'full_text_document_ids': verified_full,
            'conflicts': conflicts, 'blockers': blockers, 'ready_for_fulltext_formalization': not blockers,
            'question_eligibility_confirmed': False, 'training_support_added': False,
            'model_calls': 0, 'expert_validated': False,
            'input_sha256': fingerprint({'candidate': candidate, 'documents': documents})}
