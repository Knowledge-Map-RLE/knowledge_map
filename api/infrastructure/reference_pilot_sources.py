"""Разрешение библиографии и сохранение полных OA-источников в S3/Neo4j."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from domain.article_maps import digest, require
from domain.reference_prediction import normalize, source_priority

log = logging.getLogger(__name__)
TARGET_PMC = "PMC10000452"
TARGET_DOI = "10.3390/healthcare11050703"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
SOURCE_CONVERSION_VERSION = "2"


def element_text(element) -> str:
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def parse_references(xml: bytes) -> list[dict]:
    root = ET.fromstring(xml)
    references = []
    for reference in root.findall(".//ref-list/ref"):
        label = reference.findtext("label") or reference.attrib.get("id", "")
        number = int(re.search(r"\d+", label).group())
        ids = {el.attrib.get("pub-id-type"): element_text(el) for el in reference.findall(".//pub-id")}
        citation = element_text(reference)
        doi = ids.get("doi")
        if not doi:
            match = re.search(r"10\.\d{4,9}/[^\s<>]+", citation)
            doi = match.group().rstrip(".,;") if match else None
        title = element_text(reference.find(".//article-title")) or element_text(reference.find(".//source"))
        year = reference.findtext(".//year")
        if not year:
            match = re.search(r"\b(19\d{2}|20\d{2})\b", citation)
            year = match.group() if match else None
        publication = reference.find("mixed-citation")
        publication = publication if publication is not None else reference.find("element-citation")
        kind = publication.attrib.get("publication-type", "unknown") if publication is not None else "unknown"
        if "Ph.D. Thesis" in citation:
            kind = "thesis"
        elif number == 1:
            kind = "report"
        references.append({"number": number, "title": title or citation, "citation": citation,
                           "doi": normalize(doi) if doi else None, "pmid": ids.get("pmid"),
                           "pmcid": ids.get("pmcid"), "publication_date": year,
                           "document_type": kind, "status": "unresolved", "open_access": None})
    require([r["number"] for r in references] == list(range(1, 55)), "Original bibliography must contain references 1–54")
    return references


def validate_conversion(xml: bytes, markdown: str) -> dict:
    """Контроль полноты конвертации; не оценка научной точности текста."""
    root = ET.fromstring(xml)
    require(root.find("body") is not None, "Source XML has no full-text body")
    language = root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
    require(language is None or language.lower() in {"en", "eng"}, "Full source must be in English")
    references = root.findall(".//ref-list/ref")
    if references:
        label = references[-1].findtext("label")
        if label:
            number = re.search(r"\d+", label)
            if number:
                require(re.search(r"(?m)^\s*" + number.group() + r"[.)\s]", markdown) is not None,
                        "Conversion lost the end of the bibliography")
    # Между соседними XML-ячейками нет пробелов: itertext без разделителя склеивает числа.
    # Для диагностического словаря сохраняем границы XML-фрагментов.
    original_body = " ".join(root.find("body").itertext())
    represented = set(re.findall(r"\w+", normalize(markdown)))
    original_tokens = set(re.findall(r"\w+", normalize(original_body)))
    coverage = len(original_tokens & represented) / len(original_tokens) if original_tokens else 0
    require(coverage >= 0.90, "Full-text conversion loses source tokens")
    return {"body_token_presence": coverage, "reference_count": len(references),
            "scientific_accuracy": "not_assessed"}


class EuropePmcSourceProvider:
    def __init__(self, store, repository, storage, bucket, owner, xml_converter, pdf_converter=None,
                 *, refresh_registry=False):
        self.store, self.repository, self.storage, self.bucket = store, repository, storage, bucket
        self.owner, self.xml_converter, self.pdf_converter = owner, xml_converter, pdf_converter
        self.refresh_registry = refresh_registry
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15), follow_redirects=True,
                                        headers={"User-Agent": "KnowledgeMap-ReferencePilot/1.0"})

    async def close(self):
        await self.client.aclose()
        await self.xml_converter.disconnect()
        if self.pdf_converter:
            await self.pdf_converter.disconnect()

    async def _get(self, url, params=None):
        # Повторяем только временную сетевую ошибку того же запроса; источник не подменяем.
        for attempt in range(3):
            response = await self.client.get(url, params=params)
            if response.status_code not in {429, 502, 503, 504} or attempt == 2:
                return response
            await asyncio.sleep(min(10, 2 ** (attempt + 1)))
        raise AssertionError("Unreachable request state")

    async def _target_xml(self):
        cached = self.store.path("original/target.xml")
        if cached.is_file():
            return cached.read_bytes()
        response = await self._get(f"{EUROPE_PMC}/{TARGET_PMC}/fullTextXML")
        response.raise_for_status()
        xml = response.content
        root = ET.fromstring(xml)
        require(any(element_text(el) == TARGET_DOI for el in root.findall(".//article-meta/article-id")),
                "Target XML identity differs")
        require(root.find("body") is not None and root.find(".//license") is not None,
                "Target full text or OA license missing")
        parse_references(xml)
        self.store.write_bytes("original/target.xml", xml)
        return xml

    async def _resolve(self, reference):
        result = dict(reference)
        crossref = None
        if reference["doi"]:
            response = await self._get("https://api.crossref.org/works/" + reference["doi"])
            if response.status_code == 200:
                crossref = response.json()["message"]
                result["document_type"] = crossref.get("type", result["document_type"])
                date = crossref.get("published", {}).get("date-parts", [[]])[0]
                if date:
                    result["publication_date"] = "-".join(str(v).zfill(2) if i else str(v)
                                                         for i, v in enumerate(date))
                if crossref.get("title"):
                    result["resolved_title"] = crossref["title"][0]
            elif response.status_code != 404:
                response.raise_for_status()
        if reference["pmid"]:
            query = f"EXT_ID:{reference['pmid']} AND SRC:MED"
        elif reference["doi"]:
            query = f"DOI:\"{reference['doi']}\""
        else:
            query = f"TITLE:\"{reference['title'].replace(chr(34), '')}\""
        response = await self._get(EUROPE_PMC + "/search", {"query": query, "format": "json",
                                                          "resultType": "core", "pageSize": 10})
        response.raise_for_status()
        hits = response.json().get("resultList", {}).get("result", [])
        if reference["doi"]:
            hits = [h for h in hits if normalize(h.get("doi", "")) == reference["doi"]]
        elif not reference["pmid"]:
            hits = [h for h in hits if normalize(h.get("title", "").rstrip(".")) ==
                    normalize(reference["title"].rstrip("."))]
        require(len(hits) <= 1, "Ambiguous bibliographic identity")
        hit = hits[0] if hits else {}
        openalex = {}
        if reference["doi"]:
            response = await self._get("https://api.openalex.org/works/https://doi.org/" + reference["doi"])
            if response.status_code == 200:
                openalex = response.json()
            elif response.status_code != 404:
                response.raise_for_status()
        result.update(pmid=hit.get("id") if hit.get("source") == "MED" else reference["pmid"],
                      pmcid=hit.get("pmcid"), license=hit.get("license"),
                      metadata_source="crossref+europepmc+openalex", resolved_title=hit.get("title") or result.get("resolved_title"))
        result["publication_date"] = hit.get("firstPublicationDate") or result["publication_date"]
        pmc_oa = hit.get("isOpenAccess") == "Y"
        oa_metadata = openalex.get("open_access", {})
        result["open_access"] = True if pmc_oa or oa_metadata.get("is_oa") is True else (
            False if oa_metadata.get("is_oa") is False else None)
        result["oa_status"] = openalex.get("open_access", {}).get("oa_status")
        if pmc_oa and result["pmcid"]:
            result.update(status="open_access", fulltext_format="jats",
                          fulltext_url=f"{EUROPE_PMC}/{result['pmcid']}/fullTextXML")
        else:
            links = hit.get("fullTextUrlList", {}).get("fullTextUrl", [])
            pdf_links = [link["url"] for link in links if link.get("documentStyle") == "pdf"
                         and link.get("availability") == "Open access"]
            locations = sorted((l for l in openalex.get("locations", []) if l.get("is_oa") and l.get("pdf_url")),
                               key=lambda l: (l.get("version") != "publishedVersion", l["pdf_url"]))
            pdf_links += [location["pdf_url"] for location in locations]
            if result["open_access"] and pdf_links:
                result.update(status="open_access", fulltext_format="pdf", fulltext_url=pdf_links[0],
                              license=locations[0].get("license") if locations else result["license"],
                              fulltext_version=locations[0].get("version") if locations else "unknown")
            else:
                result["status"] = "fulltext_unavailable" if result["open_access"] else (
                    "not_open_access" if result["open_access"] is False else "access_unverified")
                result["reason"] = "No verified OA full-text endpoint; abstract is not accepted"
        if result["pmcid"] == TARGET_PMC or result["doi"] == TARGET_DOI:
            result.update(status="excluded_target", reason="Target cannot enter the source corpus")
        publication = result.get("publication_date") or ""
        if result["status"] == "open_access" and (not publication or publication > "2023-02-27"
                                                  or publication in {"2023", "2023-02"}):
            result.update(status="date_unverified_or_future", reason="Historical publication cutoff is not satisfied")
        return result

    async def registry(self):
        cached = self.store.read("registry.json")
        if cached is not None and not self.refresh_registry:
            require(len(cached["references"]) == 54 and cached["target_pmc_id"] == TARGET_PMC,
                    "Bibliographic registry identity differs")
            require(cached.get("version") == 2, "Registry requires explicit prepare --refresh-registry")
            # Исправление раннего реестра: отсутствие DOI/метаданных OA не означает закрытый доступ.
            corrected = [r for r in cached["references"] if r.get("doi") is None
                         and r.get("oa_status") is None and r.get("status") == "not_open_access"
                         and r.get("metadata_source") == "crossref+europepmc+openalex"]
            if corrected:
                from domain.article_maps import fingerprint
                self.store.write(f"registry/revisions/{fingerprint(cached)}.json", cached)
                for reference in corrected:
                    reference.update(open_access=None, status="access_unverified",
                                     reason="No explicit OA availability metadata for this bibliographic source")
                cached["created_at"] = datetime.now(timezone.utc).isoformat()
                self.store.write(f"registry/revisions/{fingerprint(cached)}.json", cached)
                self.store.write("registry.json", cached, immutable=False)
            return cached
        xml = await self._target_xml()
        references, seen = [], set()
        for reference in parse_references(xml):
            try:
                resolved = await self._resolve(reference)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                resolved = reference | {"status": "lookup_failed", "reason": type(exc).__name__}
            identity = resolved.get("doi") or resolved.get("pmcid")
            if identity and identity in seen:
                resolved.update(status="duplicate_reference", reason="Same scientific source is already registered")
            if identity:
                seen.add(identity)
            if resolved["status"] == "open_access":
                try:
                    download = await self._get(resolved["fulltext_url"])
                    download.raise_for_status()
                    if resolved["fulltext_format"] == "jats":
                        require(ET.fromstring(download.content).find("body") is not None, "Missing full-text body")
                    else:
                        require(download.content.startswith(b"%PDF"), "Full-text endpoint is not a PDF")
                    original_sha = hashlib.sha256(download.content).hexdigest()
                    self.store.write_bytes(f"downloads/{original_sha}.bin", download.content)
                    resolved["download_sha256"] = original_sha
                except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
                    resolved.update(status="download_unavailable", reason=type(exc).__name__)
            references.append(resolved)
            log.info("reference_pilot reference=%s status=%s pmcid=%s", reference["number"],
                     resolved["status"], resolved.get("pmcid"))
            await asyncio.sleep(0.15)
        registry = {"version": 2, "target_pmc_id": TARGET_PMC, "target_doi": TARGET_DOI,
                    "original_xml_sha256": hashlib.sha256(xml).hexdigest(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "order": [r["number"] for r in sorted(references, key=source_priority)], "references": references}
        from domain.article_maps import fingerprint
        if cached:
            self.store.write(f"registry/revisions/{fingerprint(cached)}.json", cached)
        self.store.write(f"registry/revisions/{fingerprint(registry)}.json", registry)
        self.store.write("registry.json", registry, immutable=False)
        self.refresh_registry = False
        return registry

    async def _publish(self, source, markdown, original, original_format):
        require(bool(markdown.strip()) and len(markdown) > 1000, "Full text is empty or implausibly short")
        sha = digest(markdown)
        safe_id = re.sub(r"[^a-z0-9_-]", "-", source["source_id"].casefold())
        article_id = f"pilot-pmc10000452-{safe_id}-{sha[:16]}"
        prefix = f"reference_pilots/pmc10000452/sources/{safe_id}/{sha}/"
        source = source | {"article_id": article_id, "source_sha256": sha,
                           "conversion_version": SOURCE_CONVERSION_VERSION,
                           "article_sha256": sha, "document_uid": article_id, "article_title": source["title"],
                           "needs_expert_review": True, "annotation_scope": "automatic_full_text",
                           "s3_bucket": self.bucket, "s3_key": prefix + "article.md",
                           "source": {"system": "neo4j+s3", "bucket": self.bucket, "key": prefix + "article.md"}}
        relative = f"sources/{safe_id}/revisions/{sha}"
        self.store.write_bytes(relative + "/article.md", markdown.encode("utf-8"))
        self.store.write_bytes(relative + f"/article.{original_format}", original)
        self.store.write(relative + "/meta.json", source)
        require(await self.storage.upload_bytes(markdown.encode("utf-8"), self.bucket,
                                                source["s3_key"], content_type="text/markdown; charset=utf-8"),
                "Failed to save full text in S3")
        require(await self.storage.upload_bytes(original, self.bucket, prefix + f"article.{original_format}",
                                                content_type="application/xml" if original_format == "xml" else "application/pdf"),
                "Failed to save original OA source in S3")
        with self.repository.driver.session() as session:
            date_parts = [int(v) for v in (source.get("publication_date") or "").split("-") if v]
            publication = (datetime(*(date_parts + [1, 1])[:3], tzinfo=timezone.utc) if date_parts else None)
            def create(tx):
                existing = tx.run("MATCH (d:Document {uid:$id}) RETURN d.created_by_uid AS owner,d.pilot_source_sha256 AS sha",
                                  id=article_id).single()
                require(existing is None or (existing["owner"] == self.owner and existing["sha"] == sha),
                        "Experiment source owner or revision differs")
                tx.run("""MERGE (d:Document {uid:$id}) ON CREATE SET
                  d.created_by_uid=$owner,d.title=$title,d.original_filename=$filename,
                  d.md5_hash=$md5,d.s3_bucket=$bucket,d.s3_key=$key,d.file_size=$bytes,
                  d.docling_raw_md_s3_key=$key,d.source='pmc',d.pmc_id=$pmc,d.doi=$doi,
                  d.is_open_access=true,d.is_processed=true,d.processing_status='completed',
                  d.is_gold_standard=true,d.gold_standard_source_pmc_id=$pmc,
                  d.pilot_source_sha256=$sha,d.needs_expert_review=true,
                  d.source_md5_hash=$source_md5,
                  d.pilot_experiment_id='pmc10000452',d.upload_date=datetime(),
                  d.publication_date=$publication""", id=article_id, owner=self.owner, title=source["title"],
                       filename=safe_id + ".md",
                       # Отдельная GOLD-копия имеет отдельный ключ; исходный хеш не теряется.
                       md5=hashlib.md5((article_id + "\0" + markdown).encode("utf-8")).hexdigest(),
                       source_md5=hashlib.md5(markdown.encode("utf-8")).hexdigest(),
                       bucket=self.bucket, key=source["s3_key"], bytes=len(markdown.encode("utf-8")),
                       pmc=source.get("pmcid"), doi=source.get("doi"), sha=sha,
                       publication=publication).consume()
            session.execute_write(create)
        self.store.write(f"source_index/{safe_id}.json", source, immutable=False)
        return source

    async def materialize(self, reference):
        require(reference["status"] == "open_access", "Source is not verified Open Access")
        identity = reference.get("pmcid") or reference["doi"]
        safe_id = re.sub(r"[^a-z0-9_-]", "-", identity.casefold())
        cached = self.store.read(f"source_index/{safe_id}.json")
        if cached is not None and cached.get("conversion_version") == SOURCE_CONVERSION_VERSION:
            return cached
        original = self.store.path(f"downloads/{reference['download_sha256']}.bin").read_bytes()
        require(hashlib.sha256(original).hexdigest() == reference["download_sha256"], "Downloaded source changed")
        source = {"source_id": identity, "pmcid": reference.get("pmcid"), "doi": reference.get("doi"),
                  "title": reference.get("resolved_title") or reference["title"],
                  "reference_number": reference["number"], "publication_date": reference["publication_date"],
                  "document_type": reference["document_type"], "license": reference.get("license"),
                  "download_url": reference["fulltext_url"], "original_sha256": hashlib.sha256(original).hexdigest()}
        if reference["fulltext_format"] == "jats":
            root = ET.fromstring(original)
            require(root.find("body") is not None, "OA XML does not contain the article body")
            identifiers = {element_text(el) for el in root.findall(".//article-meta/article-id")}
            require(reference.get("doi") in identifiers or str(reference["pmcid"]).removeprefix("PMC") in identifiers,
                    "Downloaded full-text identity differs")
            converted = await self.xml_converter.convert_pmc_xml(original, timeout=120)
            original_format = "xml"
        else:
            require(original.startswith(b"%PDF"), "OA endpoint did not return a PDF")
            require(self.pdf_converter is not None, "PDF converter is not configured")
            converted = await self.pdf_converter.convert_pdf(original, doc_id=f"pilot-{safe_id}")
            original_format = "pdf"
        require(converted.get("success"), "Full-text conversion failed")
        if original_format == "xml":
            source["conversion_validation"] = validate_conversion(original, converted["markdown_content"])
        return await self._publish(source, converted["markdown_content"], original, original_format)

    async def target(self):
        cached = self.store.read("source_index/target.json")
        if cached is not None and cached.get("conversion_version") == SOURCE_CONVERSION_VERSION:
            return cached
        xml = await self._target_xml()
        converted = await self.xml_converter.convert_pmc_xml(xml, timeout=120)
        require(converted.get("success"), "Target full-text conversion failed")
        markdown = converted["markdown_content"]
        validation = validate_conversion(xml, markdown)
        require("54." in markdown[markdown.lower().rfind("references"):],
                "Converted target bibliography is incomplete")
        source = {"source_id": TARGET_PMC, "pmcid": TARGET_PMC, "doi": TARGET_DOI,
                  "title": element_text(ET.fromstring(xml).find(".//article-title")),
                  "reference_number": None, "publication_date": "2023-02-27", "document_type": "journal-article",
                  "license": "CC BY 4.0", "download_url": f"{EUROPE_PMC}/{TARGET_PMC}/fullTextXML",
                  "original_sha256": hashlib.sha256(xml).hexdigest()}
        source["conversion_validation"] = validation
        source = await self._publish(source, markdown, xml, "xml")
        self.store.write("source_index/target.json", source, immutable=False)
        return source
