"""Сервис для поиска и загрузки статей из PubMed и PubMed Central"""
import asyncio
import hashlib
import io
import json
import logging
import os
import re
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import httpx

from src.models import PDFDocument
from src.schemas.api import PubMedSearchResult
from services import settings, get_s3_client

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
OA_API_BASE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
ID_CONV_BASE = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles"

NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")
NCBI_TOOL = os.getenv("NCBI_TOOL_NAME", "KnowledgeMap")
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "user@example.com")


def _ncbi_params(**kwargs) -> Dict[str, str]:
    """Базовые параметры для NCBI запросов"""
    params = {"tool": NCBI_TOOL, "email": NCBI_EMAIL}
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    params.update(kwargs)
    return params


def _text(el: Optional[ET.Element], default: str = "") -> str:
    if el is None:
        return default
    return (el.text or "").strip()


def _parse_pubmed_article(article_el: ET.Element) -> Dict[str, Any]:
    """Парсит один PubMedArticle XML-элемент → словарь с метаданными"""
    medline = article_el.find("MedlineCitation")
    if medline is None:
        return {}

    pmid = _text(medline.find("PMID"))
    article = medline.find("Article")
    if article is None:
        return {}

    title = _text(article.find("ArticleTitle"))

    # Авторы
    authors = []
    for author in article.findall("AuthorList/Author"):
        last = _text(author.find("LastName"))
        first = _text(author.find("ForeName")) or _text(author.find("Initials"))
        if last:
            authors.append(f"{last} {first}".strip())

    # Журнал и дата публикации
    journal = _text(article.find("Journal/Title"))
    pub_date_el = article.find("Journal/JournalIssue/PubDate")
    pub_date = ""
    if pub_date_el is not None:
        year = _text(pub_date_el.find("Year"))
        month = _text(pub_date_el.find("Month"))
        pub_date = f"{year} {month}".strip()

    # Абстракт
    abstract_parts = []
    for ab in article.findall("Abstract/AbstractText"):
        label = ab.get("Label", "")
        text = (ab.text or "").strip()
        if label:
            abstract_parts.append(f"**{label}**: {text}")
        elif text:
            abstract_parts.append(text)
    abstract = "\n\n".join(abstract_parts)

    # DOI
    doi = None
    for eid in article.findall("ELocationID"):
        if eid.get("EIdType") == "doi":
            doi = eid.text

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "pub_date": pub_date,
        "abstract": abstract,
        "doi": doi,
    }


def _pmc_xml_to_markdown(
    xml_bytes: bytes,
    image_urls: Optional[Dict[str, str]] = None,
) -> str:
    """Конвертирует PMC XML (NLM DTD) в Markdown.

    Args:
        xml_bytes: XML байты статьи
        image_urls: словарь {basename_без_расширения: url} для подстановки в <fig>
                    Ключи — имена файлов изображений (e.g. "pone.0123456.g001"),
                    значения — полные URL или относительные пути.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.error(f"[pmc_xml_to_md] Ошибка парсинга XML: {e}")
        return ""

    if image_urls is None:
        image_urls = {}

    lines = []

    # Заголовок
    title_el = root.find(".//article-title")
    if title_el is not None:
        title_text = "".join(title_el.itertext()).strip()
        lines.append(f"# {title_text}\n")

    # Авторы
    authors = []
    for contrib in root.findall(".//contrib[@contrib-type='author']"):
        surname = contrib.findtext(".//surname", "")
        given = contrib.findtext(".//given-names", "")
        if surname:
            authors.append(f"{surname} {given}".strip())
    if authors:
        lines.append(f"**Авторы:** {', '.join(authors)}\n")

    # Журнал и дата
    journal = root.findtext(".//journal-title", "")
    year = root.findtext(".//pub-date/year", "")
    if journal:
        lines.append(f"**Журнал:** {journal}" + (f" ({year})" if year else "") + "\n")

    # DOI
    for article_id in root.findall(".//article-id"):
        if article_id.get("pub-id-type") == "doi":
            lines.append(f"**DOI:** {article_id.text}\n")
            break

    lines.append("")

    # Абстракт
    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        lines.append("## Abstract\n")
        for p in abstract_el.findall(".//p"):
            text = "".join(p.itertext()).strip()
            if text:
                title_tag = p.get("content-type") or ""
                if title_tag:
                    lines.append(f"**{title_tag}:** {text}\n")
                else:
                    lines.append(f"{text}\n")
        lines.append("")

    # Собираем фигуры из <floats-group> по id (floating layout)
    # Они будут вставляться после первого параграфа, который на них ссылается
    figs_by_id: Dict[str, ET.Element] = {}
    floats = root.find(".//floats-group")
    if floats is not None:
        for fig in floats.findall("fig"):
            fig_id = fig.get("id", "")
            if fig_id:
                figs_by_id[fig_id] = fig

    # Также собираем фигуры прямо из body/sec (inline layout)
    for fig in root.findall(".//body//fig"):
        fig_id = fig.get("id", "")
        if fig_id and fig_id not in figs_by_id:
            figs_by_id[fig_id] = fig

    rendered_figs: set = set()  # track which figs already rendered

    # Основные секции
    for sec in root.findall(".//body/sec"):
        _render_section(sec, lines, level=2, image_urls=image_urls,
                        figs_by_id=figs_by_id, rendered_figs=rendered_figs)

    # Фигуры из <floats-group>, которые так и не встретились в тексте — добавляем в конец
    remaining = [figs_by_id[fid] for fid in figs_by_id if fid not in rendered_figs]
    if remaining:
        lines.append("## Figures\n")
        for fig in remaining:
            _render_fig(fig, lines, image_urls)

    # Список литературы (краткий)
    refs = root.findall(".//ref-list/ref")
    if refs:
        lines.append("## References\n")
        for i, ref in enumerate(refs[:50], 1):
            mixed_citation = ref.find(".//mixed-citation")
            element_citation = ref.find(".//element-citation")
            if mixed_citation is not None:
                ref_text = "".join(mixed_citation.itertext()).strip()
            elif element_citation is not None:
                ref_text = "".join(element_citation.itertext()).strip()
            else:
                ref_text = "".join(ref.itertext()).strip()
            if ref_text:
                lines.append(f"{i}. {ref_text}\n")

    return "\n".join(lines)


def _render_fig(fig: ET.Element, lines: List[str], image_urls: Dict[str, str]):
    """Рендерит одну фигуру в markdown: изображение + подпись."""
    fig_id = fig.get("id", "")
    label_el = fig.find("label")
    label = "".join(label_el.itertext()).strip() if label_el is not None else ""
    caption_el = fig.find(".//caption/p")
    cap = "".join(caption_el.itertext()).strip() if caption_el is not None else ""

    img_url = _resolve_fig_image(fig, image_urls)
    if img_url:
        alt = label or fig_id or "Figure"
        lines.append(f"![{alt}]({img_url})\n")
    if label or cap:
        full_cap = f"**{label}**" if label else ""
        if cap:
            full_cap = f"{full_cap} {cap}".strip()
        lines.append(f"*{full_cap}*\n")
    lines.append("")


def _resolve_fig_image(fig_el: ET.Element, image_urls: Dict[str, str]) -> Optional[str]:
    """Находит URL изображения для элемента <fig>.

    Ищет атрибут xlink:href у <graphic> внутри фигуры и ищет совпадение в image_urls.
    """
    ns = {"xlink": "http://www.w3.org/1999/xlink"}
    graphic = fig_el.find(".//graphic")
    if graphic is None:
        return None

    href = graphic.get("{http://www.w3.org/1999/xlink}href") or graphic.get("href") or ""
    if not href:
        return None

    # Убираем расширение для поиска
    base = href.rsplit(".", 1)[0] if "." in href else href
    basename = base.rsplit("/", 1)[-1]

    # Ищем совпадение: полное имя, или basename без расширения
    for key, url in image_urls.items():
        key_base = key.rsplit(".", 1)[0] if "." in key else key
        key_base_short = key_base.rsplit("/", 1)[-1]
        if key == href or key_base == base or key_base_short == basename:
            return url

    return None


def _render_section(
    sec: ET.Element,
    lines: List[str],
    level: int = 2,
    image_urls: Optional[Dict[str, str]] = None,
    figs_by_id: Optional[Dict[str, ET.Element]] = None,
    rendered_figs: Optional[set] = None,
):
    """Рекурсивно рендерит раздел статьи в Markdown.

    При наличии figs_by_id вставляет фигуру из <floats-group>
    сразу после первого параграфа, где на неё ссылаются через <xref ref-type="fig">.
    """
    if image_urls is None:
        image_urls = {}
    if figs_by_id is None:
        figs_by_id = {}
    if rendered_figs is None:
        rendered_figs = set()

    title_el = sec.find("title")
    if title_el is not None:
        sec_title = "".join(title_el.itertext()).strip()
        if sec_title:
            lines.append(f"{'#' * level} {sec_title}\n")

    for child in sec:
        tag = child.tag
        if tag == "title":
            continue
        elif tag == "p":
            text = "".join(child.itertext()).strip()
            if text:
                lines.append(f"{text}\n")
            # После параграфа вставляем фигуры, на которые он ссылается (floating layout)
            if figs_by_id:
                for xref in child.findall('.//xref[@ref-type="fig"]'):
                    rid = xref.get("rid", "")
                    if rid and rid in figs_by_id and rid not in rendered_figs:
                        rendered_figs.add(rid)
                        _render_fig(figs_by_id[rid], lines, image_urls)
        elif tag == "sec":
            _render_section(child, lines, level + 1, image_urls=image_urls,
                            figs_by_id=figs_by_id, rendered_figs=rendered_figs)
        elif tag == "fig":
            # Inline фигура (не floating layout) — рендерим на месте
            fig_id = child.get("id", "")
            if fig_id and rendered_figs is not None:
                rendered_figs.add(fig_id)
            _render_fig(child, lines, image_urls)
        elif tag == "table-wrap":
            caption_el = child.find(".//caption/p")
            if caption_el is not None:
                cap = "".join(caption_el.itertext()).strip()
                lines.append(f"*{cap}*\n")
        elif tag == "list":
            for item in child.findall("list-item"):
                item_text = "".join(item.itertext()).strip()
                if item_text:
                    lines.append(f"- {item_text}\n")

    lines.append("")


def _metadata_to_markdown(meta: Dict[str, Any]) -> str:
    """Создаёт Markdown из метаданных статьи (для не-OA статей)"""
    lines = []

    title = meta.get("title", "Без заголовка")
    lines.append(f"# {title}\n")

    if meta.get("authors"):
        lines.append(f"**Авторы:** {', '.join(meta['authors'])}\n")

    if meta.get("journal"):
        date_part = f" ({meta['pub_date']})" if meta.get("pub_date") else ""
        lines.append(f"**Журнал:** {meta['journal']}{date_part}\n")

    if meta.get("doi"):
        lines.append(f"**DOI:** {meta['doi']}\n")

    pmid = meta.get("pmid")
    pmcid = meta.get("pmcid")
    if pmid:
        lines.append(f"**PubMed ID:** [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)\n")
    if pmcid:
        lines.append(f"**PMC ID:** [{pmcid}](https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/)\n")

    lines.append("")
    lines.append("> **Примечание:** Полный текст статьи недоступен (не Open Access).\n")
    lines.append("")

    if meta.get("abstract"):
        lines.append("## Abstract\n")
        lines.append(f"{meta['abstract']}\n")

    return "\n".join(lines)


class PubMedService:
    """Сервис для поиска и загрузки статей PubMed/PMC"""

    def __init__(self):
        self.s3_client = get_s3_client()
        self.bucket = settings.S3_BUCKET_NAME

    async def _search_in_db(self, db: str, query: str, retmax: int) -> List[PubMedSearchResult]:
        """Поиск в одной базе (pubmed или pmc). Возвращает пустой список при ошибке."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                search_params = _ncbi_params(
                    db=db,
                    term=query,
                    retmax=str(retmax),
                    retmode="json",
                    sort="relevance",
                )
                resp = await client.get(f"{EUTILS_BASE}/esearch.fcgi", params=search_params)
                resp.raise_for_status()
                id_list = resp.json().get("esearchresult", {}).get("idlist", [])
                if not id_list:
                    return []
                if db == "pubmed":
                    return await self._fetch_pubmed_metadata(client, id_list)
                else:
                    return await self._fetch_pmc_metadata(client, id_list)
        except Exception as e:
            logger.warning(f"[pubmed] Ошибка поиска в {db}: {e}")
            return []

    async def search(self, query: str, retmax: int = 10) -> List[PubMedSearchResult]:
        """Единый поиск в PubMed и PMC одновременно.

        Параллельно запрашивает оба источника, дедуплицирует по PMID,
        обогащает PubMed-результаты данными PMC (PMCID + OA-статус).
        OA-статьи с полным текстом идут первыми.
        """
        # Параллельный поиск в обоих источниках
        pubmed_res, pmc_res = await asyncio.gather(
            self._search_in_db("pubmed", query, retmax),
            self._search_in_db("pmc", query, retmax),
            return_exceptions=True,
        )
        if isinstance(pubmed_res, Exception):
            pubmed_res = []
        if isinstance(pmc_res, Exception):
            pmc_res = []

        # Слияние с дедупликацией по PMID
        # pubmed_results хранят позицию релевантности → используем как основу
        merged: Dict[str, PubMedSearchResult] = {}
        for r in pubmed_res:
            key = r.pmid or r.pmcid or r.title
            merged[key] = r

        for r in pmc_res:
            # Сначала пробуем найти по PMID
            existing = merged.get(r.pmid) if r.pmid else None
            # Если не нашли по PMID — ищем по PMCID среди уже добавленных
            # (PMC не всегда возвращает PMID, что приводит к дублям в поиске)
            if existing is None and r.pmcid:
                existing = next(
                    (v for v in merged.values()
                     if v.pmcid and (v.pmcid == r.pmcid or v.pmcid.lstrip("PMC") == r.pmcid.lstrip("PMC"))),
                    None
                )
            if existing:
                # Обогащаем PubMed-запись данными PMC
                existing.pmcid = r.pmcid or existing.pmcid
                existing.is_open_access = True
                # Берём более длинный абстракт
                if len(r.abstract) > len(existing.abstract):
                    existing.abstract = r.abstract
            else:
                # Статья есть только в PMC
                key = r.pmcid or r.title
                merged[key] = r

        # Сортировка: OA-статьи (с полным текстом) первыми, остальное — как есть
        results = sorted(merged.values(), key=lambda r: (not r.is_open_access,))
        return results[:retmax]

    async def _fetch_pubmed_metadata(self, client: httpx.AsyncClient, pmids: List[str]) -> List[PubMedSearchResult]:
        """Получает метаданные PubMed статей по PMID списку, сохраняя порядок релевантности."""
        fetch_params = _ncbi_params(
            db="pubmed",
            id=",".join(pmids),
            retmode="xml",
        )
        resp = await client.get(f"{EUTILS_BASE}/efetch.fcgi", params=fetch_params)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        # Сначала собираем результаты в словарь по PMID
        results_by_pmid: Dict[str, PubMedSearchResult] = {}

        for article_el in root.findall("PubmedArticle"):
            meta = _parse_pubmed_article(article_el)
            if not meta.get("pmid"):
                continue

            pmc_data = article_el.find("PubmedData/ArticleIdList/ArticleId[@IdType='pmc']")
            pmcid = pmc_data.text if pmc_data is not None else None
            is_oa = pmcid is not None

            results_by_pmid[meta["pmid"]] = PubMedSearchResult(
                pmid=meta.get("pmid"),
                pmcid=pmcid,
                title=meta.get("title", "Без заголовка"),
                authors=meta.get("authors", []),
                journal=meta.get("journal", ""),
                pub_date=meta.get("pub_date", ""),
                abstract=meta.get("abstract", ""),
                doi=meta.get("doi"),
                is_open_access=is_oa,
                source="pubmed",
            )

        # Восстанавливаем порядок релевантности из esearch
        return [results_by_pmid[pmid] for pmid in pmids if pmid in results_by_pmid]

    async def _fetch_pmc_metadata(self, client: httpx.AsyncClient, pmcids: List[str]) -> List[PubMedSearchResult]:
        """Получает метаданные PMC статей по PMCID списку"""
        # PMC esearch возвращает PMC IDs без префикса "PMC"
        fetch_params = _ncbi_params(
            db="pmc",
            id=",".join(pmcids),
            retmode="xml",
        )
        resp = await client.get(f"{EUTILS_BASE}/efetch.fcgi", params=fetch_params)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        # Сначала собираем результаты в словарь по числовому PMC ID (без префикса)
        results_by_id: Dict[str, PubMedSearchResult] = {}

        for article_el in root.findall(".//article"):
            title_el = article_el.find(".//article-title")
            title = "".join(title_el.itertext()).strip() if title_el is not None else "Без заголовка"

            pmcid = None
            pmid = None
            raw_pmcid = None  # числовой ID без "PMC" — для сопоставления с id_list
            for aid in article_el.findall(".//article-id"):
                if aid.get("pub-id-type") in ("pmcid", "pmc"):
                    raw_pmcid = (aid.text or "").lstrip("PMC")
                    pmcid = f"PMC{raw_pmcid}"
                elif aid.get("pub-id-type") == "pmid":
                    pmid = aid.text

            doi = None
            for aid in article_el.findall(".//article-id"):
                if aid.get("pub-id-type") == "doi":
                    doi = aid.text

            authors = []
            for contrib in article_el.findall(".//contrib[@contrib-type='author']"):
                surname = contrib.findtext(".//surname", "")
                given = contrib.findtext(".//given-names", "")
                if surname:
                    authors.append(f"{surname} {given}".strip())

            journal = article_el.findtext(".//journal-title", "")
            year = article_el.findtext(".//pub-date/year", "")

            abstract_parts = []
            for p in article_el.findall(".//abstract//p"):
                text = "".join(p.itertext()).strip()
                if text:
                    abstract_parts.append(text)
            abstract = "\n\n".join(abstract_parts)

            result = PubMedSearchResult(
                pmid=pmid,
                pmcid=pmcid,
                title=title,
                authors=authors,
                journal=journal,
                pub_date=year,
                abstract=abstract,
                doi=doi,
                is_open_access=True,
                source="pmc",
            )
            if raw_pmcid:
                results_by_id[raw_pmcid] = result

        # Восстанавливаем порядок релевантности из esearch
        return [results_by_id[pid] for pid in pmcids if pid in results_by_id]

    async def fetch_by_id(self, article_id: str) -> Optional[PubMedSearchResult]:
        """Получает одну статью напрямую по PMID или PMCID.

        Автоматически определяет тип ID:
        - Начинается с 'PMC' → запрос в PMC
        - Иначе → запрос в PubMed как PMID, затем обогащение PMCID через ID Converter
        """
        async with httpx.AsyncClient(timeout=30) as client:
            if article_id.upper().startswith("PMC"):
                # Прямой запрос в PMC по PMCID
                raw_id = article_id.lstrip("PMCpmc")
                results = await self._fetch_pmc_metadata(client, [raw_id])
                return results[0] if results else None
            else:
                # Прямой запрос в PubMed по PMID
                results = await self._fetch_pubmed_metadata(client, [article_id])
                if not results:
                    return None
                result = results[0]
                # Обогащаем: если PMCID не нашёлся в PubMed XML — проверяем через ID Converter
                # (некоторые OA-статьи не имеют ArticleId[@IdType='pmc'] в PubMed API)
                if not result.is_open_access and not result.pmcid:
                    pmcid = await self._get_pmcid_for_pmid(client, article_id)
                    if pmcid:
                        result.pmcid = pmcid
                        result.is_open_access = True
                        logger.info(f"[pubmed] fetch_by_id: обогащён PMCID={pmcid} для PMID={article_id} через ID Converter")
                return result

    async def _get_pmcid_for_pmid(self, client: httpx.AsyncClient, pmid: str) -> Optional[str]:
        """Конвертирует PMID в PMCID через ID Converter API"""
        try:
            params = {
                "ids": pmid,
                "idtype": "pmid",
                "format": "json",
                "tool": NCBI_TOOL,
                "email": NCBI_EMAIL,
            }
            resp = await client.get(f"{ID_CONV_BASE}/", params=params, timeout=15)
            if resp.status_code != 200:
                return None
            data = resp.json()
            records = data.get("records", [])
            if records:
                return records[0].get("pmcid")
        except Exception as e:
            logger.warning(f"[pubmed] Ошибка конвертации PMID→PMCID для {pmid}: {e}")
        return None

    async def _find_pmcid_via_esearch(self, client: httpx.AsyncClient, pmid: str) -> Optional[str]:
        """Запасной вариант: найти PMCID через поиск в базе PMC по PMID.

        Используется когда ID Converter не вернул PMCID, но статья реально есть в PMC.
        """
        try:
            params = _ncbi_params(db="pmc", term=f"{pmid}[PMID]", retmax="1", retmode="json")
            resp = await client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params, timeout=15)
            resp.raise_for_status()
            id_list = resp.json().get("esearchresult", {}).get("idlist", [])
            if id_list:
                return f"PMC{id_list[0]}"
        except Exception as e:
            logger.warning(f"[pubmed] Ошибка PMC esearch для PMID {pmid}: {e}")
        return None

    async def _check_oa(self, client: httpx.AsyncClient, pmcid: str) -> Optional[Dict[str, str]]:
        """Проверяет OA статус и получает ссылки на файлы через OA API.

        Returns:
            dict с ключами 'pdf' и/или 'tgz' если OA, иначе None
        """
        try:
            resp = await client.get(OA_API_BASE, params={"id": pmcid}, timeout=15)
            if resp.status_code != 200:
                return None

            root = ET.fromstring(resp.content)
            error_el = root.find("error")
            if error_el is not None:
                return None

            links: Dict[str, str] = {}
            for link_el in root.findall(".//link"):
                fmt = link_el.get("format", "")
                href = link_el.get("href", "")
                if href.startswith("ftp://"):
                    # NCBI поддерживает HTTPS для тех же путей
                    href = "https://" + href[len("ftp://"):]
                if fmt == "pdf" and href:
                    links["pdf"] = href
                elif fmt == "tgz" and href:
                    links["tgz"] = href

            return links if links else None
        except Exception as e:
            logger.warning(f"[pubmed] Ошибка OA API для {pmcid}: {e}")
            return None

    async def _build_pmc_image_urls_from_xml(self, xml_bytes: bytes, pmcid: str) -> Dict[str, str]:
        """Строит словарь image_urls из XML, используя публичные URL Europe PMC.

        Europe PMC хранит изображения по адресу:
        https://europepmc.org/articles/{pmcid}/bin/{filename}
        (доступно для большинства PMC-статей, включая не-OA)

        Returns:
            dict {filename: public_url}
        """
        image_urls: Dict[str, str] = {}
        try:
            root = ET.fromstring(xml_bytes)
            for graphic in root.findall(".//graphic"):
                href = graphic.get("{http://www.w3.org/1999/xlink}href") or graphic.get("href") or ""
                if not href:
                    continue
                basename = href.rsplit("/", 1)[-1]
                # Если расширение уже есть — используем как есть
                fname = basename if "." in basename else f"{basename}.jpg"
                url = f"https://europepmc.org/articles/{pmcid}/bin/{fname}"
                image_urls[basename] = url
                image_urls[fname] = url
        except Exception as e:
            logger.warning(f"[pubmed] Ошибка построения image_urls для {pmcid}: {e}")
        return image_urls

    async def _fetch_pmc_fulltext_xml(self, client: httpx.AsyncClient, pmcid: str) -> Optional[bytes]:
        """Получает полный текст статьи из PMC через efetch (XML формат).

        Работает для статей в PMC даже если они не в OA subset.
        Возвращает XML байты или None если текст недоступен.
        """
        try:
            # Убираем префикс PMC для числового ID
            pmc_num = pmcid.lstrip("PMCpmc")
            params = _ncbi_params(db="pmc", id=pmc_num, retmode="xml")
            resp = await client.get(f"{EUTILS_BASE}/efetch.fcgi", params=params, timeout=30)
            resp.raise_for_status()

            # Проверяем что вернулся полноценный XML с телом статьи, а не ошибка
            content = resp.content
            if not content or b"<article" not in content:
                logger.info(f"[pubmed] efetch PMC не вернул статью для {pmcid}")
                return None

            return content
        except Exception as e:
            logger.warning(f"[pubmed] Ошибка efetch PMC для {pmcid}: {e}")
            return None

    async def _get_pubmed_metadata(self, client: httpx.AsyncClient, pmid: str) -> Optional[Dict[str, Any]]:
        """Получает полные метаданные одной статьи по PMID, включая PMCID если есть"""
        params = _ncbi_params(db="pubmed", id=pmid, retmode="xml")
        resp = await client.get(f"{EUTILS_BASE}/efetch.fcgi", params=params)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        article_el = root.find("PubmedArticle")
        if article_el is None:
            return None
        meta = _parse_pubmed_article(article_el)
        # Извлекаем PMCID только из PubmedData/ArticleIdList статьи (не из ReferenceList)
        pmc_el = article_el.find("PubmedData/ArticleIdList/ArticleId[@IdType='pmc']")
        if pmc_el is not None and pmc_el.text:
            pmcid = pmc_el.text
            if not pmcid.startswith("PMC"):
                pmcid = f"PMC{pmcid}"
            meta["pmcid_from_pubmed"] = pmcid
        return meta

    async def ingest_article(
        self,
        pmid: Optional[str] = None,
        pmcid: Optional[str] = None,
        source: str = "pubmed",
        background_tasks=None,
    ) -> Dict[str, Any]:
        """Главная функция: получить статью и сохранить в систему.

        Логика:
        1. Получить метаданные через efetch
        2. Попробовать конвертировать PMID → PMCID
        3. Проверить OA статус
        4. PMC OA: скачать tar.gz → XML → Markdown (без Docling)
        5. PubMed OA с PDF: скачать PDF → Docling pipeline
        6. Не-OA: создать Markdown из абстракта + метаданных

        Returns:
            dict с doc_id, success, message, processing_status
        """
        if not pmid and not pmcid:
            return {"success": False, "message": "Необходимо указать PMID или PMCID", "processing_status": "error"}

        logger.info(f"[pubmed] ingest_article: pmid={pmid}, pmcid={pmcid}, source={source}")

        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                # 1. Получаем метаданные из PubMed
                meta: Dict[str, Any] = {}
                if pmid:
                    meta = await self._get_pubmed_metadata(client, pmid) or {}
                    meta["pmid"] = pmid
                    logger.info(f"[pubmed] Получены метаданные для PMID={pmid}: title={meta.get('title', 'N/A')[:60]}")
                    # PMCID уже может быть в метаданных
                    if not pmcid and meta.get("pmcid_from_pubmed"):
                        pmcid = meta["pmcid_from_pubmed"]
                        logger.info(f"[pubmed] Найден PMCID={pmcid} из efetch для PMID={pmid}")
                elif pmcid:
                    meta["pmcid"] = pmcid

                # 2. Если PMCID всё ещё не найден — пробуем ID Converter
                if pmid and not pmcid:
                    pmcid = await self._get_pmcid_for_pmid(client, pmid)
                    logger.info(f"[pubmed] PMCID из ID Converter: {pmcid}")

                # 2b. Запасной вариант: PMC esearch по PMID (если ID Converter не нашёл)
                if pmid and not pmcid:
                    pmcid = await self._find_pmcid_via_esearch(client, pmid)
                    logger.info(f"[pubmed] PMCID из PMC esearch: {pmcid}")

                meta["pmcid"] = pmcid
                # Устанавливаем source: если есть PMCID → pmc, иначе → pubmed
                meta["source"] = "pmc" if pmcid else source

                # 3. Генерируем doc_id
                id_str = pmid or pmcid or ""
                doc_id = hashlib.md5(id_str.encode()).hexdigest()
                logger.info(f"[pubmed] doc_id={doc_id} для id_str={id_str}")

                # 4. Проверяем, не загружена ли уже статья
                existing = PDFDocument.nodes.get_or_none(uid=doc_id)
                if existing:
                    # Проверяем, реально ли файл существует в S3
                    bucket = self.bucket
                    prefix = f"documents/{doc_id}/"
                    md_key = (
                        existing.user_md_s3_key or
                        existing.formatted_md_s3_key or
                        existing.docling_raw_md_s3_key or
                        f"{prefix}{doc_id}.md"
                    )
                    pdf_key = f"{prefix}{doc_id}.pdf"
                    md_exists = await self.s3_client.object_exists(bucket, md_key)
                    pdf_exists = await self.s3_client.object_exists(bucket, pdf_key)

                    if md_exists or pdf_exists:
                        # Если статья была загружена без полного текста (не-OA), но теперь у нас есть
                        # PMCID — удаляем старую запись и перезагружаем с полным текстом
                        if not existing.is_open_access and pmcid:
                            logger.info(f"[pubmed] Статья {id_str} была загружена без полного текста, перезагружаем с PMCID={pmcid}")
                            try:
                                existing.delete()
                            except Exception as del_err:
                                logger.error(f"[pubmed] Ошибка удаления старой записи: {del_err}")
                        else:
                            logger.info(f"[pubmed] Статья {id_str} уже загружена и файлы в S3 есть, doc_id={doc_id}")
                            return {
                                "success": True,
                                "doc_id": doc_id,
                                "message": "Статья уже загружена",
                                "processing_status": existing.processing_status or "annotated",
                            }
                    else:
                        logger.warning(f"[pubmed] Запись в Neo4j есть, но файлов в S3 нет для doc_id={doc_id} — повторяем загрузку")
                        # Удаляем неполную запись из Neo4j и перезагружаем
                        try:
                            existing.delete()
                        except Exception as del_err:
                            logger.error(f"[pubmed] Ошибка удаления неполной записи: {del_err}")

                # 5. Определяем стратегию получения контента
                #
                # Приоритет:
                # A. Есть PMCID + OA API вернул ссылки → tar.gz (полный XML) или PDF → Docling
                # B. Есть PMCID + нет OA ссылок → пробуем efetch?db=pmc (полный текст через API)
                # C. Нет PMCID или efetch вернул пусто → metadata-only (абстракт)

                oa_links: Optional[Dict[str, str]] = None
                if pmcid:
                    oa_links = await self._check_oa(client, pmcid)
                    logger.info(f"[pubmed] OA links для {pmcid}: {oa_links}")

                if oa_links and (oa_links.get("tgz") or oa_links.get("pdf")):
                    # Сценарий A: PMC OA — скачиваем tar.gz и конвертируем XML → Markdown
                    if oa_links.get("tgz"):
                        logger.info(f"[pubmed] Сценарий A: PMC OA tar.gz")
                        result = await self._ingest_from_tgz(
                            client, oa_links["tgz"], doc_id, meta, background_tasks
                        )
                    else:
                        logger.info(f"[pubmed] Сценарий A: PMC OA PDF → Docling")
                        result = await self._ingest_pdf_via_docling(
                            client, oa_links["pdf"], doc_id, meta, background_tasks
                        )
                elif pmcid:
                    # Сценарий B: есть PMCID но нет OA ссылок — пробуем efetch полный текст
                    logger.info(f"[pubmed] Сценарий B: efetch полный текст из PMC для {pmcid}")
                    pmc_xml = await self._fetch_pmc_fulltext_xml(client, pmcid)
                    if pmc_xml:
                        # Для Сценария B изображения не скачиваются (нет tar.gz),
                        # но XML содержит xlink:href на имена файлов.
                        # Строим image_urls через публичный PMC URL
                        # (работает для статей с открытыми изображениями)
                        image_urls = await self._build_pmc_image_urls_from_xml(pmc_xml, pmcid)
                        markdown = _pmc_xml_to_markdown(pmc_xml, image_urls=image_urls)
                        if markdown:
                            logger.info(f"[pubmed] Сценарий B: получен полный текст через efetch ({len(markdown)} символов), images={len(image_urls)}")
                            result = await self._save_document(
                                doc_id=doc_id, meta=meta, markdown=markdown,
                                pdf_bytes=None, is_oa=True,
                            )
                        else:
                            logger.warning(f"[pubmed] Сценарий B: XML получен, но конвертация пуста → metadata-only")
                            result = await self._ingest_metadata_only(doc_id, meta)
                    else:
                        logger.info(f"[pubmed] Сценарий B: efetch вернул пусто → metadata-only")
                        result = await self._ingest_metadata_only(doc_id, meta)
                else:
                    logger.info(f"[pubmed] Сценарий C: metadata-only (нет PMCID)")
                    result = await self._ingest_metadata_only(doc_id, meta)

                logger.info(f"[pubmed] ingest_article result: {result}")
                return result

        except Exception as e:
            import traceback
            logger.error(f"[pubmed] Необработанная ошибка в ingest_article: {e}\n{traceback.format_exc()}")
            return {
                "success": False,
                "message": f"Ошибка загрузки: {e}",
                "processing_status": "error",
            }

    async def _ingest_from_tgz(
        self,
        client: httpx.AsyncClient,
        tgz_url: str,
        doc_id: str,
        meta: Dict[str, Any],
        background_tasks=None,
    ) -> Dict[str, Any]:
        """Скачивает tar.gz из PMC, извлекает XML и конвертирует в Markdown"""
        logger.info(f"[pubmed] Скачивание tar.gz: {tgz_url}")
        pmcid = meta.get("pmcid")
        try:
            resp = await client.get(tgz_url, timeout=120)
            resp.raise_for_status()
            tgz_bytes = resp.content
        except Exception as e:
            logger.error(f"[pubmed] Ошибка скачивания tar.gz: {e}")
            # Fallback: пробуем получить полный текст через efetch
            if pmcid:
                logger.info(f"[pubmed] Fallback на efetch для {pmcid}")
                pmc_xml = await self._fetch_pmc_fulltext_xml(client, pmcid)
                if pmc_xml:
                    image_urls = await self._build_pmc_image_urls_from_xml(pmc_xml, pmcid)
                    markdown = _pmc_xml_to_markdown(pmc_xml, image_urls=image_urls)
                    if markdown:
                        return await self._save_document(
                            doc_id=doc_id, meta=meta, markdown=markdown,
                            pdf_bytes=None, is_oa=True,
                        )
            return await self._ingest_metadata_only(doc_id, meta)

        # Извлекаем XML, PDF и изображения из tar.gz
        IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".svg")
        xml_bytes = None
        pdf_bytes = None
        images: Dict[str, bytes] = {}  # {filename: bytes}

        try:
            with tarfile.open(fileobj=io.BytesIO(tgz_bytes), mode="r:gz") as tar:
                for member in tar.getmembers():
                    name_lower = member.name.lower()
                    basename = member.name.rsplit("/", 1)[-1]
                    if member.name.endswith(".nxml") or (member.name.endswith(".xml") and not member.name.endswith("_meta.xml")):
                        f = tar.extractfile(member)
                        if f:
                            xml_bytes = f.read()
                    elif name_lower.endswith(".pdf") and pdf_bytes is None:
                        f = tar.extractfile(member)
                        if f:
                            pdf_bytes = f.read()
                    elif any(name_lower.endswith(ext) for ext in IMAGE_EXTS):
                        f = tar.extractfile(member)
                        if f:
                            images[basename] = f.read()
        except Exception as e:
            logger.error(f"[pubmed] Ошибка распаковки tar.gz: {e}")
            return await self._ingest_metadata_only(doc_id, meta)

        if xml_bytes is None:
            logger.warning(f"[pubmed] XML не найден в tar.gz для doc_id={doc_id}")
            return await self._ingest_metadata_only(doc_id, meta)

        logger.info(f"[pubmed] Извлечено из tar.gz: XML={xml_bytes is not None}, PDF={pdf_bytes is not None}, images={list(images.keys())}")

        # Загружаем изображения в S3 и строим словарь URL для markdown
        import mimetypes as _mimetypes
        image_urls: Dict[str, str] = {}
        bucket = self.bucket
        prefix = f"documents/{doc_id}/"
        base_url = getattr(settings, "API_BASE_URL", None) or os.getenv("API_BASE_URL", "http://localhost:8000")

        for img_name, img_data in images.items():
            s3_key = f"{prefix}{img_name}"
            content_type = _mimetypes.guess_type(img_name)[0] or "image/jpeg"
            ok = await self.s3_client.upload_bytes(img_data, bucket, s3_key, content_type=content_type)
            if ok:
                # Формируем URL через API image proxy (такой же как у Docling-изображений)
                img_url = f"{base_url}/api/v1/s3/image/documents/{doc_id}/{img_name}"
                # Ключ без расширения для поиска в XML href
                image_urls[img_name] = img_url
                logger.info(f"[pubmed] Изображение загружено: {s3_key} → {img_url}")
            else:
                logger.warning(f"[pubmed] Не удалось загрузить изображение: {img_name}")

        # Конвертируем PMC XML → Markdown (с подстановкой URL изображений)
        markdown = _pmc_xml_to_markdown(xml_bytes, image_urls=image_urls)
        if not markdown:
            return await self._ingest_metadata_only(doc_id, meta)

        # Сохраняем
        return await self._save_document(
            doc_id=doc_id,
            meta=meta,
            markdown=markdown,
            pdf_bytes=pdf_bytes,
            is_oa=True,
        )

    async def _ingest_pdf_via_docling(
        self,
        client: httpx.AsyncClient,
        pdf_url: str,
        doc_id: str,
        meta: Dict[str, Any],
        background_tasks=None,
    ) -> Dict[str, Any]:
        """Скачивает PDF и отправляет на конвертацию через Docling"""
        logger.info(f"[pubmed] Скачивание PDF: {pdf_url}")
        try:
            resp = await client.get(pdf_url, timeout=120)
            resp.raise_for_status()
            pdf_bytes = resp.content
        except Exception as e:
            logger.error(f"[pubmed] Ошибка скачивания PDF: {e}")
            return await self._ingest_metadata_only(doc_id, meta)

        if background_tasks:
            # Запускаем Docling асинхронно
            from services.pdf_to_md_grpc_client import get_pdf_to_md_grpc_client_instance
            background_tasks.add_task(
                self._run_docling_pipeline, pdf_bytes, doc_id, meta
            )
            # Сначала сохраняем запись в Neo4j со статусом processing
            await self._save_document(
                doc_id=doc_id,
                meta=meta,
                markdown=None,
                pdf_bytes=pdf_bytes,
                is_oa=True,
                processing_status="pdf_to_markdown",
            )
            return {
                "success": True,
                "doc_id": doc_id,
                "message": "PDF загружен, конвертация запущена",
                "processing_status": "pdf_to_markdown",
            }
        else:
            # Синхронная конвертация (для тестов)
            await self._run_docling_pipeline(pdf_bytes, doc_id, meta)
            return {
                "success": True,
                "doc_id": doc_id,
                "message": "PDF успешно обработан",
                "processing_status": "annotated",
            }

    async def _run_docling_pipeline(self, pdf_bytes: bytes, doc_id: str, meta: Dict[str, Any]):
        """Фоновая задача: конвертация PDF через Docling gRPC"""
        from services.pdf_to_md_grpc_client import get_pdf_to_md_grpc_client_instance
        from services.data_extraction_service import extract_title_from_markdown
        import mimetypes

        logger.info(f"[pubmed] Запуск Docling для doc_id={doc_id}")
        try:
            grpc_client = get_pdf_to_md_grpc_client_instance()
            result = await grpc_client.convert_pdf(
                pdf_content=pdf_bytes,
                doc_id=doc_id,
                timeout=3600,
            )

            if not result["success"]:
                raise RuntimeError(result.get("message", "Docling error"))

            markdown = result.get("markdown_content", "")
            images = result.get("images", {})
            docling_raw_key = result.get("docling_raw_s3_key")
            formatted_key = result.get("formatted_s3_key")

            bucket = self.bucket
            prefix = f"documents/{doc_id}/"

            # Сохраняем изображения
            for img_name, img_data in (images or {}).items():
                await self.s3_client.upload_bytes(
                    img_data, bucket, f"{prefix}{img_name}",
                    content_type=mimetypes.guess_type(img_name)[0] or "image/jpeg"
                )

            # Обновляем документ
            doc = PDFDocument.nodes.get_or_none(uid=doc_id)
            if doc:
                if markdown:
                    extracted_title = extract_title_from_markdown(markdown)
                    if extracted_title:
                        doc.title = extracted_title
                if docling_raw_key:
                    doc.docling_raw_md_s3_key = docling_raw_key
                if formatted_key:
                    doc.formatted_md_s3_key = formatted_key
                doc.processing_status = "annotated"
                doc.is_processed = True
                doc.save()

            logger.info(f"[pubmed] Docling pipeline завершен для doc_id={doc_id}")
        except Exception as e:
            logger.error(f"[pubmed] Ошибка Docling pipeline для {doc_id}: {e}")
            doc = PDFDocument.nodes.get_or_none(uid=doc_id)
            if doc:
                doc.processing_status = "error"
                doc.error_message = str(e)
                doc.save()

    async def _ingest_metadata_only(self, doc_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """Сохраняет только метаданные и абстракт (для не-OA статей)"""
        markdown = _metadata_to_markdown(meta)
        return await self._save_document(
            doc_id=doc_id,
            meta=meta,
            markdown=markdown,
            pdf_bytes=None,
            is_oa=False,
        )

    async def _save_document(
        self,
        doc_id: str,
        meta: Dict[str, Any],
        markdown: Optional[str],
        pdf_bytes: Optional[bytes],
        is_oa: bool,
        processing_status: str = "annotated",
    ) -> Dict[str, Any]:
        """Сохраняет документ в S3 и Neo4j"""
        bucket = self.bucket
        prefix = f"documents/{doc_id}/"

        # Сохраняем PDF если есть
        pdf_key = None
        if pdf_bytes:
            pdf_key = f"{prefix}{doc_id}.pdf"
            ok = await self.s3_client.upload_bytes(
                pdf_bytes, bucket, pdf_key, content_type="application/pdf"
            )
            if not ok:
                logger.error(f"[pubmed] Не удалось загрузить PDF в S3: {pdf_key}")
            else:
                logger.info(f"[pubmed] PDF сохранён: s3://{bucket}/{pdf_key}")

        # Сохраняем Markdown
        md_key = None
        if markdown:
            md_key = f"{prefix}{doc_id}.md"
            ok = await self.s3_client.upload_bytes(
                markdown.encode("utf-8"), bucket, md_key, content_type="text/markdown; charset=utf-8"
            )
            if not ok:
                logger.error(f"[pubmed] Не удалось загрузить Markdown в S3: {md_key}")
                md_key = None  # не ставим ключ если файл не загружен
            else:
                logger.info(f"[pubmed] Markdown сохранён: s3://{bucket}/{md_key}")

        # Извлекаем заголовок из Markdown или метаданных
        title = meta.get("title") or "Без заголовка"
        if markdown:
            from services.data_extraction_service import extract_title_from_markdown
            extracted = extract_title_from_markdown(markdown)
            if extracted:
                title = extracted

        # Определяем original_filename
        pmid = meta.get("pmid")
        pmcid = meta.get("pmcid")
        if pmcid:
            filename = f"{pmcid}.pdf" if pdf_key else f"{pmcid}.md"
        elif pmid:
            filename = f"PMID{pmid}.pdf" if pdf_key else f"PMID{pmid}.md"
        else:
            filename = f"{doc_id}.md"

        source = meta.get("source", "pubmed")

        # Проверяем что хотя бы один файл сохранён
        if not pdf_key and not md_key:
            logger.error(f"[pubmed] Нет ни PDF ни Markdown для doc_id={doc_id}, отмена сохранения")
            return {
                "success": False,
                "doc_id": doc_id,
                "message": "Не удалось сохранить файлы в S3",
                "processing_status": "error",
            }

        # Сохраняем в Neo4j
        try:
            existing = PDFDocument.nodes.get_or_none(uid=doc_id)
            if existing:
                if markdown and md_key:
                    existing.docling_raw_md_s3_key = md_key
                existing.processing_status = processing_status
                existing.is_processed = processing_status == "annotated"
                existing.title = title
                existing.original_filename = filename
                if pmid:
                    existing.pubmed_id = pmid
                if pmcid:
                    existing.pmc_id = pmcid
                existing.save()
                logger.info(f"[pubmed] Neo4j запись обновлена: doc_id={doc_id}")
            else:
                doc = PDFDocument(
                    uid=doc_id,
                    original_filename=filename,
                    md5_hash=doc_id,
                    s3_key=pdf_key or md_key or f"{prefix}{doc_id}",
                    title=title,
                    authors=meta.get("authors", []),
                    abstract=meta.get("abstract", ""),
                    journal=meta.get("journal", ""),
                    doi=meta.get("doi"),
                    source=source,
                    pubmed_id=pmid,
                    pmc_id=pmcid,
                    is_open_access=is_oa,
                    is_processed=processing_status == "annotated",
                    processing_status=processing_status,
                    docling_raw_md_s3_key=md_key,
                )
                doc.save()
                logger.info(f"[pubmed] Neo4j запись создана: doc_id={doc_id}, title={title}, md_key={md_key}")
        except Exception as e:
            import traceback
            logger.error(f"[pubmed] Ошибка сохранения в Neo4j для doc_id={doc_id}: {e}\n{traceback.format_exc()}")
            return {
                "success": False,
                "doc_id": doc_id,
                "message": f"Ошибка сохранения в базу данных: {e}",
                "processing_status": "error",
            }

        return {
            "success": True,
            "doc_id": doc_id,
            "message": "Статья успешно загружена",
            "processing_status": processing_status,
        }
