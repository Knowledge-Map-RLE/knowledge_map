"""Неизменяемая публикация календарных условий через независимый порт источников."""
import logging
from typing import Protocol
from domain.article_maps import fingerprint,require
from domain.treatment_episode_context import VERSION,compile_episodes
from application.ports.development_prediction import PredictionStore

log=logging.getLogger(__name__)


class EpisodeInputs(Protocol):
    def load(self): ...


class SealTreatmentEpisodes:
    def __init__(self,inputs:EpisodeInputs,store:PredictionStore):self.inputs,self.store=inputs,store

    def execute(self,implementation):
        functional,frozen,maps,cases,audit,assets=self.inputs.load()
        binding={'version':VERSION,'functional_sha256':fingerprint(functional),'source_sha256':fingerprint(frozen),
            'map_hashes':[fingerprint(m)for m in maps],'audit_sha256':fingerprint(audit),'cases_sha256':fingerprint(cases),
            'implementation':implementation};run=fingerprint(binding);old=self.store.read_seal(run)
        if old is not None:require(old['binding']==binding,'Episode binding changed');return old
        result={'run_id':run,'binding':binding,**compile_episodes(functional,frozen,maps,cases,audit,assets)}
        self.store.seal(run,result)
        log.info('treatment_episodes_sealed run=%s cases=%d calendar_consequences=%d conflicts=%d',
            run,len(result['episodes']),len(result['calendar_consequences']),len(result['calendar_conflicts']))
        return self.store.read_seal(run)
