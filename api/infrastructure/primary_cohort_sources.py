"""Один явный HTTP-провайдер и неизменяемые файлы первичного материала."""
import json
import logging
import re
import copy
from hashlib import sha256
from xml.etree import ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from domain.article_maps import digest, fingerprint, require
from domain.primary_cohort_sources import VERSION, CONTROL_QUERY, TRAINING_QUERY, doi, metadata_record, training_access
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.public_article_text import convert_xml

log=logging.getLogger(__name__)
BASE="https://www.ebi.ac.uk/europepmc/webservices/rest/"
CONVERSION_VERSION="primary-jats-detached-objects-2"


def convert_primary_xml(xml):
    # В JATS таблицы и рисунки могут находиться в floats-group вне основного текста.
    root=ET.fromstring(xml);body=root.find("body")
    require(body is not None,"Complete primary body required")
    in_body={id(e) for e in body.iter()}
    detached=[e for e in root.iter() if e.tag in {"table-wrap","fig"} and id(e) not in in_body]
    if detached:
        section=ET.SubElement(body,"sec");ET.SubElement(section,"title").text="Tables and figures stored outside the article body"
        for element in detached:section.append(copy.deepcopy(element))
    return convert_xml(ET.tostring(root,encoding="unicode"))


class CachedPrimarySources:
    """Явно проверенный старый аудит используется только как кэш исходного XML."""
    def __init__(self,root):
        self.root=Path(root).resolve();self.requests=[]
        self.audit=json.loads((self.root/"audit.json").read_text(encoding="utf-8"))
        self.registry=json.loads((self.root/"registry.json").read_text(encoding="utf-8"))
        require(fingerprint(self.registry)==self.audit["registry_sha256"],"Cached registry changed")
        self.records={r["metadata"]["doi"]:r for r in self.audit["sources"]+self.audit["additional_sources"]}
        for r in self.records.values():
            folder=self.root/"sources"/r["entry"]["id"]
            require(json.loads((folder/"metadata.json").read_text(encoding="utf-8"))==r,"Cached metadata changed")
            if r["status"]=="training_fulltext_saved":
                require(digest((folder/"article.xml").read_text(encoding="utf-8"))==r["identity"]["xml_sha256"],"Cached original XML changed")
                require(digest((folder/"article.md").read_text(encoding="utf-8"))==r["source_sha256"],"Cached original conversion changed")

    def metadata(self,expected):
        require(expected in self.records,"Source not in explicitly verified cache")
        return copy.deepcopy(self.records[expected]["metadata"])

    def training_xml(self,entry,record):
        expected=training_access(entry);require(expected==record["doi"],"Cached fulltext identity differs")
        old=self.records[expected];require(old["status"]=="training_fulltext_saved","No verified original fulltext")
        return (self.root/"sources"/old["entry"]["id"]/"article.xml").read_text(encoding="utf-8")

    def _candidates(self,name,key):
        value=json.loads((self.root/name).read_text(encoding="utf-8"))
        require(fingerprint(value)==self.audit[key],"Cached metadata candidates changed")
        return value["candidates"]

    def training_candidates(self):return self._candidates("additional-training-metadata.json","additional_metadata_sha256")
    def control_candidates(self):return self._candidates("control-metadata.json","control_metadata_sha256")


class EuropePmcPrimarySources:
    def __init__(self):self.requests=[]

    def _get(self,url,stage):
        request=Request(url,headers={"User-Agent":"KnowledgeMap-PrimarySourceAudit/1.0"})
        with urlopen(request,timeout=25) as response:
            raw=response.read(20_000_001)
        require(len(raw)<=20_000_000,"Primary response exceeds explicit limit")
        self.requests.append({"stage":stage,"url":url,"bytes":len(raw),"sha256":sha256(raw).hexdigest()})
        log.info("primary_http stage=%s bytes=%d",stage,len(raw))
        return raw.decode("utf-8")

    def metadata(self,expected):
        url=BASE+"search?"+urlencode({"query":'DOI:"'+doi(expected)+'"',"format":"json","resultType":"lite","pageSize":10})
        response=json.loads(self._get(url,"training_metadata"))
        rows=[metadata_record(r) for r in response["resultList"]["result"] if r.get("source")=="MED" and r.get("doi") and doi(r["doi"])==doi(expected)]
        require(len(rows)==1,"Exact primary DOI has no unique MED record")
        return rows[0]

    def training_xml(self,entry,record):
        expected=training_access(entry)
        require(expected==record["doi"] and bool(re.fullmatch(r"PMC\d+",record["pmcid"] or "")),"Primary fulltext identity differs")
        return self._get(BASE+record["pmcid"]+"/fullTextXML","training_fulltext")

    def _candidates(self,query,stage):
        url=BASE+"search?"+urlencode({"query":query,"format":"json","resultType":"lite","pageSize":100})
        data=json.loads(self._get(url,stage))
        require(data["hitCount"]<=100,"Control metadata search requires an explicitly expanded scope")
        return sorted([metadata_record(r) for r in data["resultList"]["result"] if r.get("doi")],key=lambda r:(r["published_on"] or "",r["doi"]))

    def control_candidates(self):return self._candidates(CONTROL_QUERY,"control_metadata_only")

    def training_candidates(self):return self._candidates(TRAINING_QUERY,"additional_training_metadata")


class FilePrimarySourceStore:
    def __init__(self,root):self.root=Path(root).resolve()

    def read(self,entry):
        training_access(entry);folder=self.root/entry["id"];path=folder/"metadata.json"
        if not path.exists():return None
        result=json.loads(path.read_text(encoding="utf-8"))
        require(result["entry"]==entry and result["version"]==VERSION,"Cached primary binding differs")
        if result["status"]=="training_fulltext_saved":
            require(digest((folder/"article.xml").read_text(encoding="utf-8"))==result["identity"]["xml_sha256"],"Cached primary XML changed")
            require(digest((folder/"article.md").read_text(encoding="utf-8"))==result["source_sha256"],"Cached primary text changed")
        return result

    def save(self,entry,result,xml,text):
        training_access(entry);folder=self.root/entry["id"]
        if xml is not None:write_immutable(folder/"article.xml",xml.encode("utf-8"))
        if text is not None:write_immutable(folder/"article.md",text.encode("utf-8"))
        write_immutable(folder/"metadata.json",FilePredictionStore.encode(result))
