"""Парсер PubMed XML метаданных.

Извлечено из api/services/pubmed_service.py.
"""
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET


def get_text(el: Optional[ET.Element], default: str = "") -> str:
    """Безопасно извлекает текст из XML элемента."""
    if el is None:
        return default
    return (el.text or "").strip()


def parse_pubmed_article(article_el: ET.Element) -> Dict[str, Any]:
    """Парсит один PubMedArticle XML-элемент → словарь с метаданными."""
    medline = article_el.find("MedlineCitation")
    if medline is None:
        return {}

    pmid = get_text(medline.find("PMID"))
    article = medline.find("Article")
    if article is None:
        return {}

    title = get_text(article.find("ArticleTitle"))

    # Авторы
    authors = []
    for author in article.findall("AuthorList/Author"):
        last = get_text(author.find("LastName"))
        first = get_text(author.find("ForeName")) or get_text(author.find("Initials"))
        if last:
            authors.append(f"{last} {first}".strip())

    # Журнал и дата публикации
    journal = get_text(article.find("Journal/Title"))
    pub_date_el = article.find("Journal/JournalIssue/PubDate")
    pub_date = ""
    if pub_date_el is not None:
        year = get_text(pub_date_el.find("Year"))
        month = get_text(pub_date_el.find("Month"))
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


def metadata_to_markdown(meta: Dict[str, Any]) -> str:
    """Создаёт Markdown из метаданных статьи (для не-OA статей)."""
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
