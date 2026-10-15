"""Идентичность первичных источников и запрет преждевременного чтения контроля."""
import re
from xml.etree import ElementTree as ET

from domain.article_maps import digest, require

VERSION = "primary-cohort-source-audit-2"
CONTROL_QUERY = 'TITLE:"mild cognitive impairment" AND TITLE:incidence AND FIRST_PDATE:[2024-01-01 TO 2025-12-31] AND HAS_FT:Y AND SRC:MED'
TRAINING_QUERY = 'TITLE:"mild cognitive impairment" AND TITLE:incidence AND FIRST_PDATE:[2013-01-01 TO 2023-12-31] AND OPEN_ACCESS:Y AND SRC:MED'


def doi(value):
    value = value.strip().lower()
    require(bool(re.fullmatch(r"10\.\d{4,9}/\S+",value)),"Invalid DOI")
    return value


def metadata_record(row):
    require("abstractText" not in row,"Metadata-only response unexpectedly contains an abstract")
    require(row.get("source")=="MED" and row.get("doi") and row.get("title"),"Incomplete primary metadata")
    return {"pmid":str(row["id"]),"pmcid":row.get("pmcid"),"doi":doi(row["doi"]),"title":row["title"],
            "authors":row.get("authorString"),"published_on":row.get("firstPublicationDate"),
            "is_open_access":row.get("isOpenAccess")=="Y","has_fulltext":row.get("inPMC")=="Y" or row.get("inEPMC")=="Y",
            "metadata_only":True}


def training_access(entry):
    require(entry.get("role")=="training_candidate","Control full text is prohibited before a prediction seal")
    require(bool(re.fullmatch(r"[a-z][a-z0-9-]+",entry["id"])),"Invalid source identifier")
    return doi(entry["doi"])


def xml_identity(xml, record):
    root=ET.fromstring(xml)
    require(root.tag=="article" and root.find("body") is not None,"Complete JATS article required")
    ids=[doi(e.text or "") for e in root.findall(".//article-meta/article-id[@pub-id-type='doi']")]
    require(record["doi"] in ids,"JATS DOI differs from primary metadata")
    title=root.find(".//article-meta/title-group/article-title")
    require(title is not None,"JATS title missing")
    return {"title":" ".join("".join(title.itertext()).split()),"xml_sha256":digest(xml),
            "tables":[{"id":t.get("id"),"label":" ".join(t.findtext("label",default="").split()),
                       "xml_rows":len(t.findall(".//tr")),"image_only":not t.findall(".//tr") and t.find(".//graphic") is not None}
                      for t in root.findall(".//table-wrap")],
            "figures":len(root.findall(".//fig")),"references":len(root.findall(".//ref-list/ref"))}
