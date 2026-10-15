"""Запечатывание условных кандидатов до обращения к независимым исходам."""
import logging
from typing import Protocol
from datetime import datetime,timezone
from domain.article_maps import fingerprint,require
from domain.timed_protocol_hypotheses import VERSION,forecast
from application.ports.development_prediction import PredictionStore

log=logging.getLogger(__name__)


class TimedHypothesisInputs(Protocol):
    def load(self): ...


class SealTimedProtocolHypotheses:
    def __init__(self,inputs:TimedHypothesisInputs,store:PredictionStore):self.inputs,self.store=inputs,store

    def execute(self,implementation):
        review,clock,functional,frozen,maps=self.inputs.load()
        binding={'version':VERSION,'review_sha256':fingerprint(review),'clock_sha256':fingerprint(clock),
            'functional_sha256':fingerprint(functional),'frozen_sha256':fingerprint(frozen),
            'map_hashes':[fingerprint(m)for m in maps],'implementation':implementation}
        run=fingerprint(binding);old=self.store.read_seal(run)
        if old is not None:require(old['binding']==binding,'Timed hypothesis binding changed');return old
        result={'run_id':run,'binding':binding,'sealed_at_utc':datetime.now(timezone.utc).isoformat(),
            **forecast(review,clock,functional,frozen,maps)}
        self.store.seal(run,result);log.info('timed_protocol_hypotheses_sealed run=%s candidates=%d',run,result['candidate_count'])
        return self.store.read_seal(run)
