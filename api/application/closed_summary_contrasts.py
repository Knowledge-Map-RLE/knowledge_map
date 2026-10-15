"""Проверка явного корпуса и атомарная публикация закрытых табличных следствий."""
from datetime import date
import logging
from time import perf_counter

from application.compare_article_maps import validate_reference
from application.ports.article_comparisons import ComparisonMaps
from application.ports.development_prediction import PredictionStore
from domain.article_maps import ArticleMapNotFound, fingerprint, require
from domain.evidence_origin_audit import validate_origins
from domain.whole_map_forecast import project
from domain.whole_map_input_audit import audit_corpus
from domain.reported_summary_contrasts import VERSION, project_closed_summaries

log = logging.getLogger(__name__)


class SealClosedSummaryContrasts:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, references, families, owner, metadata, implementation, context_audit, origin_audit):
        start = perf_counter()
        ids = {r['article_id'] for r in references}
        require(len(ids) == len(references) >= 2, 'Distinct explicit summary maps required')
        require(metadata.get('question') is None, 'Summary audit must be question-free')
        cutoff = metadata.get('training_cutoff'); dates = metadata.get('source_dates')
        require(isinstance(cutoff, str) and date.fromisoformat(cutoff).isoformat() == cutoff, 'Exact summary cutoff required')
        require(isinstance(dates, dict) and set(dates) == set(families) == ids, 'Exact summary dates and families required')
        require(all(isinstance(d, str) and date.fromisoformat(d).isoformat() == d and d <= cutoff for d in dates.values()),
                'Future or imprecise summary source date')
        maps = []
        for ref in references:
            validate_reference(ref)
            m = self.maps.get(ref['article_id'], ref['pipeline_id'], owner, ref['run_id'])
            if m is None: raise ArticleMapNotFound('Summary map unavailable')
            require(m['article_id'] == ref['article_id'] and m['run_id'] == ref['run_id'], 'Summary map identity differs')
            maps.append(m)
        require(len({m['source']['sha256'] for m in maps}) == len(maps), 'Repeated summary source text')
        input_audit = audit_corpus(maps, metadata)
        origins = validate_origins(maps, origin_audit)
        require(origins is not None, 'Complete summary origin audit required')
        binding = {'version': VERSION, 'references': references, 'families': families, 'metadata': metadata,
            'implementation': implementation, 'map_hashes': [fingerprint(m) for m in maps],
            'context_audit_sha256': fingerprint(context_audit), 'origin_audit_sha256': fingerprint(origin_audit)}
        run = fingerprint(binding); prior = self.store.read_seal(run)
        if prior is not None:
            require(prior['binding'] == binding, 'Summary binding changed'); return prior
        log.info('closed_summary_start run=%s sources=%d', run, len(maps))
        records, _, _ = project(maps, context_audit)
        results = project_closed_summaries(records, maps)
        for profile in results['profiles']:
            key = tuple(profile['key'])
            profile['proof']['origin'] = origins['knowledge'][key]
            # Происхождение добавляется до окончательного идентификатора, без изменения исходной карты.
            profile['id'] = fingerprint({k: v for k, v in profile.items() if k != 'id'})
        by_key = {tuple(p['key']): p['id'] for p in results['profiles']}
        for row in results['coverage']: row['profile_id'] = by_key.get(tuple(row['key']))
        self.store.seal(run, {'run_id': run, 'binding': binding, 'input_corpus_audit': input_audit, **results})
        log.info('closed_summary_sealed run=%s blocks=%d profiles=%d seconds=%.3f',
            run, len(records), len(results['profiles']), perf_counter() - start)
        return self.store.read_seal(run)
