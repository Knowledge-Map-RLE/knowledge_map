"""Публикация смысловых абстракций отделена от источниковых файлов и генерации моделей."""
import logging
from typing import Protocol
from domain.article_maps import fingerprint,require
from domain.measurement_orientation import VERSION,analyze
from application.ports.development_prediction import PredictionStore

log=logging.getLogger(__name__)


class OrientationInputs(Protocol):
    def load(self): ...


class SealMeasurementOrientation:
    def __init__(self,inputs:OrientationInputs,store:PredictionStore): self.inputs,self.store=inputs,store

    def execute(self,implementation):
        previous,frozen,maps,origins,cases,audit=self.inputs.load()
        binding={'version':VERSION,'previous_sha256':fingerprint(previous),'source_sha256':fingerprint(frozen),
            'map_hashes':[fingerprint(m) for m in maps],'origin_audit_sha256':fingerprint(origins),
            'cases_sha256':fingerprint(cases),'audit_sha256':fingerprint(audit),'implementation':implementation}
        run=fingerprint(binding);old=self.store.read_seal(run)
        if old is not None: require(old['binding']==binding,'Orientation binding changed');return old
        result={'run_id':run,'binding':binding,**analyze(previous,frozen,maps,origins,cases,audit)}
        self.store.seal(run,result);log.info('measurement_orientation_sealed run=%s blocks=%d new_views=%d',run,result['canonical_blocks'],len(result['orientation_views']))
        return self.store.read_seal(run)
