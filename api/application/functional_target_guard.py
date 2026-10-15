"""Функциональные предпосылки фиксируются отдельно от чтения источников."""
import logging
from typing import Protocol
from domain.article_maps import fingerprint,require
from domain.functional_target_guard import VERSION,compile_guards
from application.ports.development_prediction import PredictionStore

log=logging.getLogger(__name__)


class FunctionalInputs(Protocol):
    def load(self): ...


class SealFunctionalTargetGuard:
    def __init__(self,inputs:FunctionalInputs,store:PredictionStore):self.inputs,self.store=inputs,store

    def execute(self,implementation):
        orientation,frozen,maps,cases,audit=self.inputs.load()
        binding={'version':VERSION,'orientation_sha256':fingerprint(orientation),'source_sha256':fingerprint(frozen),
            'map_hashes':[fingerprint(m) for m in maps],'cases_sha256':fingerprint(cases),'audit_sha256':fingerprint(audit),
            'implementation':implementation};run=fingerprint(binding)
        old=self.store.read_seal(run)
        if old is not None:require(old['binding']==binding,'Functional guard binding changed');return old
        result={'run_id':run,'binding':binding,**compile_guards(orientation,frozen,maps,cases,audit)}
        self.store.seal(run,result);log.info('functional_target_guard_sealed run=%s certificates=%d',run,len(result['functional_certificates']))
        return self.store.read_seal(run)
