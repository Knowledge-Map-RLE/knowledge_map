"""Загружает только явные обучающие кандидаты и фиксирует причины недоступности."""
import logging
from time import monotonic

from application.ports.primary_cohort_sources import PrimarySourceProvider, PrimarySourceStore
from domain.article_maps import digest
from domain.primary_cohort_sources import VERSION, training_access, xml_identity

log=logging.getLogger(__name__)


class AuditPrimarySources:
    def __init__(self,provider:PrimarySourceProvider,store:PrimarySourceStore,converter):
        self.provider,self.store,self.converter=provider,store,converter

    def execute(self,entries):
        results=[]
        for entry in entries:
            expected=training_access(entry)
            prior=self.store.read(entry)
            if prior is not None:
                results.append(prior);continue
            start=monotonic();record=self.provider.metadata(expected)
            result={"entry":entry,"metadata":record,"version":VERSION,"expert_validated":False,"model_calls":0}
            xml=text=None
            if not record["pmcid"]:
                result.update(status="no_pmc_xml_route",reason="No PMCID in selected provider; availability elsewhere not established")
            elif not record["is_open_access"]:
                result.update(status="not_selected_for_open_access_xml",reason="Selected acquisition policy requests JATS only for records flagged Open Access; public reading or other licensed formats may exist")
            else:
                xml=self.provider.training_xml(entry,record)
                identity=xml_identity(xml,record);text=self.converter(xml)
                result.update(status="training_fulltext_saved",identity=identity,source_sha256=digest(text),
                              table_numbers_complete=not any(t["image_only"] for t in identity["tables"]))
            self.store.save(entry,result,xml,text);results.append(result)
            log.info("primary_source id=%s status=%s duration_s=%.3f",entry["id"],result["status"],monotonic()-start)
        return results
