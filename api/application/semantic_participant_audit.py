"""Аудит только явно перечисленных версий карт, без генераторов и исправления источников."""
import logging
import time
from application.ports.article_comparisons import ComparisonMaps
from application.ports.development_prediction import PredictionStore
from application.compare_article_maps import validate_reference
from domain.article_maps import fingerprint, require, ArticleMapNotFound
from domain.semantic_participant_audit import audit_participants, VERSION

log = logging.getLogger(__name__)


class SealParticipantAudit:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, references, owner, metadata, implementation):
        started = time.monotonic()
        require(bool(references) and len({r['article_id'] for r in references}) == len(references), 'Explicit distinct source versions required')
        maps = []
        for ref in references:
            validate_reference(ref)
            result = self.maps.get(ref['article_id'], ref['pipeline_id'], owner, ref['run_id'])
            if result is None:
                raise ArticleMapNotFound('Participant-audit map missing')
            require(result['article_id'] == ref['article_id'] and result['run_id'] == ref['run_id'], 'Participant-audit source differs')
            maps.append(result)
        binding = {'sources': references, 'metadata': metadata, 'implementation': implementation,
                   'map_hashes': [fingerprint(m) for m in maps], 'version': VERSION}
        run_id = fingerprint(binding)
        previous = self.store.read_seal(run_id)
        if previous is not None:
            require(previous['binding'] == binding, 'Participant-audit binding changed')
            return previous
        log.info('semantic_participant_audit start run=%s sources=%d', run_id, len(maps))
        artifact = {'run_id': run_id, 'binding': binding, **audit_participants(maps)}
        self.store.seal(run_id, artifact)
        log.info('semantic_participant_audit sealed run=%s blocks=%d flags=%d duration=%.3f',
                 run_id, artifact['canonical_blocks'], len(artifact['flags']), time.monotonic()-started)
        return self.store.read_seal(run_id)
