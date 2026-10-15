"""Фиксация обратимых временных представлений через порт неизменяемых результатов."""
import logging
from typing import Protocol
from domain.article_maps import fingerprint,require
from domain.first_administration_clock import VERSION,analyze_clocks
from application.ports.development_prediction import PredictionStore

log=logging.getLogger(__name__)


class ClockInputs(Protocol):
    def load(self): ...


class SealFirstAdministrationClock:
    def __init__(self,inputs:ClockInputs,store:PredictionStore):self.inputs,self.store=inputs,store

    def execute(self,implementation):
        source=self.inputs.load();binding={'version':VERSION,'episode_sha256':fingerprint(source),'implementation':implementation}
        run=fingerprint(binding);old=self.store.read_seal(run)
        if old is not None:require(old['binding']==binding,'Relative clock binding changed');return old
        result={'run_id':run,'binding':binding,**analyze_clocks(source)};self.store.seal(run,result)
        log.info('first_administration_clock_sealed run=%s episodes=%d',run,len(result['clock_proofs']))
        return self.store.read_seal(run)
