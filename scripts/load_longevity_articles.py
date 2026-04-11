"""
Скрипт для загрузки longevity/РПЖ статей через PubMed API.

Загружает статьи по ключевым словам:
- mTOR, rapamycin, senolytics, NAD+, metformin
- autophagy, telomere, sirtuin, AMPK
- caloric restriction, longevity, lifespan, aging

Запуск:
    poetry run python scripts/load_longevity_articles.py --limit 50
    poetry run python scripts/load_longevity_articles.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Ключевые запросы для поиска longevity/РПЖ статей
LONGEVITY_QUERIES = [
    # mTOR pathway
    '"mTOR" AND "aging" AND ("rapamycin" OR "inhibitor")',
    # Senolytics
    '"senolytic" AND ("senescent cell" OR "senescence") AND ("dasatinib" OR "quercetin" OR "fisetin")',
    # NAD+ / sirtuins
    '"NAD+" AND ("aging" OR "longevity") AND ("sirtuin" OR "SIRT1" OR "NR" OR "NMN")',
    # Metformin
    '"metformin" AND ("aging" OR "longevity" OR "lifespan" OR "healthspan")',
    # Autophagy
    '"autophagy" AND ("aging" OR "longevity") AND ("mTOR" OR "AMPK" OR "ULK1")',
    # Telomeres
    '"telomere" AND ("aging" OR "longevity") AND ("telomerase" OR "TERT")',
    # Caloric restriction
    '"caloric restriction" AND ("longevity" OR "lifespan" OR "aging")',
    # AMPK
    '"AMPK" AND ("aging" OR "metabolism") AND ("longevity" OR "lifespan")',
    # Stem cells / regeneration
    '"stem cell" AND ("aging" OR "regeneration" OR "rejuvenation")',
    # Epigenetic reprogramming
    '"epigenetic reprogramming" AND ("aging" OR "rejuvenation" OR "Yamanaka")',
    # Mitochondrial dysfunction
    '"mitochondrial dysfunction" AND ("aging" OR "longevity") AND ("ROS" OR "mitophagy")',
    # Inflammaging
    '"inflammaging" OR "inflamm-ageing" AND ("cytokine" OR "NF-kappaB" OR "IL-6")',
    # Proteostasis
    '"proteostasis" AND ("aging" OR "protein homeostasis") AND ("chaperone" OR "ubiquitin")',
    # Growth hormone / IGF-1
    '"IGF-1" AND ("aging" OR "longevity") AND ("growth hormone" OR "GH")',
    # Comparative longevity studies
    '"longevity" AND ("naked mole rat" OR "bowhead whale" OR "centenarian")',
]


def search_pubmed(query: str, retmax: int = 100) -> List[str]:
    """Ищет PubMed ID по запросу."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pmc",
        "term": query,
        "retmax": str(retmax),
        "retmode": "json",
        "sort": "relevance",
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        ids = data.get("esearchresult", {}).get("idlist", [])
        logger.info(f"  Query: '{query[:60]}...' → {len(ids)} PMC IDs")
        return ids
    except Exception as e:
        logger.warning(f"  PubMed search failed for '{query[:40]}': {e}")
        return []


def fetch_pubmed_summary(pmc_id: str) -> Dict[str, Any]:
    """Получает метаданные статьи по PMC ID."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {
        "db": "pmc",
        "id": pmc_id,
        "retmode": "json",
        "version": "2.0",
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("result", {}).get(pmc_id, {})
        return {
            "pmc_id": pmc_id,
            "title": result.get("title", ""),
            "pubdate": result.get("pubdate", ""),
            "source": result.get("source", ""),
            "authors": result.get("authors", []),
            "doi": result.get("doi", ""),
            "pmid": result.get("articleids", [{}])[0].get("idstr", ""),
        }
    except Exception as e:
        logger.warning(f"  PubMed summary failed for PMC{pmc_id}: {e}")
        return {"pmc_id": pmc_id}


def download_pmc_xml(pmc_id: str, output_dir: Path) -> Path | None:
    """Скачивает PMC XML статьи."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pmc",
        "id": pmc_id,
        "rettype": "xml",
        "retmode": "text",
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"
    out_path = output_dir / f"PMC{pmc_id}.xml"

    if out_path.exists() and out_path.stat().st_size > 1000:
        return out_path

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            xml_content = resp.read().decode("utf-8")

        if len(xml_content) < 500:
            logger.warning(f"  PMC{pmc_id}: слишком маленький ответ ({len(xml_content)} байт)")
            return None

        out_path.write_text(xml_content, encoding="utf-8")
        logger.info(f"  PMC{pmc_id}: сохранено {len(xml_content):,} байт")
        return out_path
    except Exception as e:
        logger.warning(f"  Download failed for PMC{pmc_id}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Загрузка longevity статей из PubMed")
    parser.add_argument("--limit", type=int, default=50, help="Максимум статей")
    parser.add_argument("--dry-run", action="store_true", help="Только поиск без скачивания")
    parser.add_argument("--output", type=str, default="data/longevity_articles", help="Директория вывода")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Собираем все PMC ID
    all_pmc_ids: set[str] = set()
    for query in LONGEVITY_QUERIES:
        ids = search_pubmed(query, retmax=20)
        all_pmc_ids.update(ids)
        time.sleep(0.3)  # Rate limit NCBI

    all_pmc_ids = sorted(all_pmc_ids)[:args.limit]
    logger.info(f"\nВсего уникальных PMC ID: {len(all_pmc_ids)}")

    if args.dry_run:
        logger.info("Dry run — скачивание пропущено")
        for pmc_id in all_pmc_ids[:20]:
            summary = fetch_pubmed_summary(pmc_id)
            logger.info(f"  PMC{pmc_id}: {summary.get('title', 'N/A')[:80]}")
        return

    # Скачиваем XML
    downloaded = 0
    for i, pmc_id in enumerate(all_pmc_ids):
        logger.info(f"[{i+1}/{len(all_pmc_ids)}] PMC{pmc_id}")
        path = download_pmc_xml(pmc_id, output_dir)
        if path:
            downloaded += 1
        time.sleep(0.5)

    logger.info(f"\nЗагружено {downloaded}/{len(all_pmc_ids)} статей в {output_dir}")
    logger.info("Далее: используйте pipeline worker_article_to_knowledge_map для обработки")


if __name__ == "__main__":
    main()
