"""Открытый полный текст будущей цели скачивается лишь после запечатывания источникового прогноза."""
from __future__ import annotations
import argparse
import ctypes
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))
from domain.article_maps import digest, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable


from infrastructure.public_article_text import convert_xml

def run(args):
    require(bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required")
    sealed = FilePredictionStore(args.output).read_seal(args.run_id)
    require(sealed is not None, "Seal predictions before downloading the target")
    # Даже сохранённый пустой прогноз не разрешает читать цель ни из сети, ни из кэша.
    require(sealed.get("readiness", {}).get("target_reading_allowed") is True,
            "Learning readiness failed; do not read target")
    require(bool(re.fullmatch(r"PMC\d+", args.pmcid)), "Invalid target PMCID")
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({"format": "json", "resultType": "core", "query": args.pmcid})
    full_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/" + args.pmcid + "/fullTextXML"
    if args.reuse_xml:
        prior = json.loads(args.reuse_xml.with_name("metadata.json").read_text(encoding="utf-8"))
        xml = args.reuse_xml.read_bytes().decode("utf-8")
        require(prior["pmcid"] == args.pmcid and digest(xml) == prior["xml_sha256"], "Cached XML binding differs")
        row = {"title": prior["title"], "doi": prior["doi"], "firstPublicationDate": prior["available_on"]}
    else:
        with urllib.request.urlopen(url, timeout=60) as response: metadata = json.load(response)
        row = next(r for r in metadata["resultList"]["result"] if r.get("pmcid") == args.pmcid)
        with urllib.request.urlopen(full_url, timeout=60) as response: xml = response.read().decode("utf-8")
    markdown = convert_xml(xml)
    folder = args.output / args.run_id / "evaluation-inputs" / args.pmcid / "source-v2"
    folder.mkdir(parents=True, exist_ok=True)
    for name, value in (("article.xml", xml), ("article.md", markdown),
                        ("metadata.json", json.dumps({"pmcid": args.pmcid, "title": row["title"], "doi": row.get("doi"),
                          "available_on": row["firstPublicationDate"], "source_sha256": digest(markdown),
                          "xml_sha256": digest(xml), "metadata_url": url, "fulltext_url": full_url,
                          "conversion_version": "xml-evaluation-source-2", "expert_validated": False,
                          "untranscribed_image_tables": [e.attrib.get("id") for e in ET.fromstring(xml).findall(".//table-wrap")
                               if not e.findall(".//tr") and e.find(".//graphic") is not None]}, ensure_ascii=False, indent=2))):
        path = folder / name; data = value.encode("utf-8")
        write_immutable(path, data)
    return {"downloaded": args.pmcid, "folder": str(folder), "source_sha256": digest(markdown), "model_calls": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--run-id", required=True)
    parser.add_argument("--pmcid", required=True)
    parser.add_argument("--reuse-xml", type=Path)
    print(json.dumps(run(parser.parse_args())))


if __name__ == "__main__": main()
