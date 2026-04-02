"""
NCBI eSearch-based PMC article discoverer.

Searches PubMed Central for articles matching a query term,
with pagination and rate limiting.

Strategy:
  Primary:  db=pmc  (returns PMC IDs directly)
  Fallback: db=pubmed with pmc open access filter (returns PMIDs, then converted)
            Used when db=pmc returns a backend error (known intermittent NCBI issue).
"""
import logging
from typing import AsyncIterator

import httpx

from config import Config
from rate_limiter import NCBIRateLimiter

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PAGE_SIZE = 200  # max retmax per request


async def search_pmc_ids(
    config: Config,
    limiter: NCBIRateLimiter,
    client: httpx.AsyncClient,
) -> AsyncIterator[str]:
    """
    Yields PMCIDs (e.g. 'PMC1234567') for up to config.target_count articles.

    Tries db=pmc first. If NCBI returns a backend error, falls back to
    db=pubmed with 'pmc open access[filter]', which is more reliable.
    """
    # Try primary strategy: db=pmc
    found_any = False
    async for pmcid in _search_db_pmc(config, limiter, client):
        found_any = True
        yield pmcid

    if found_any:
        return

    # Fallback: db=pubmed with PMC open access filter → get PMCIDs via elink
    logger.warning("db=pmc returned no results, falling back to db=pubmed + pmc filter")
    async for pmcid in _search_pubmed_pmc_filter(config, limiter, client):
        yield pmcid


async def _search_db_pmc(
    config: Config,
    limiter: NCBIRateLimiter,
    client: httpx.AsyncClient,
) -> AsyncIterator[str]:
    total_fetched = 0
    retstart = 0

    while total_fetched < config.target_count:
        retmax = min(PAGE_SIZE, config.target_count - total_fetched)

        params = {
            "db": "pmc",
            "term": config.query,
            "retmax": retmax,
            "retstart": retstart,
            "retmode": "json",
            "tool": config.ncbi_tool,
            "email": config.ncbi_email,
        }
        if config.ncbi_api_key:
            params["api_key"] = config.ncbi_api_key

        await limiter.acquire()

        try:
            resp = await client.get(ESEARCH_URL, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"eSearch (pmc) failed at retstart={retstart}: {e}")
            return

        esearch_result = data.get("esearchresult", {})

        # NCBI sometimes returns ERROR for db=pmc
        if "ERROR" in esearch_result:
            logger.warning(
                f"NCBI db=pmc returned ERROR: {esearch_result['ERROR']!r}. "
                "Will fall back to db=pubmed."
            )
            return

        ids = esearch_result.get("idlist", [])

        if not ids:
            logger.warning(
                f"db=pmc: empty idlist at retstart={retstart} "
                f"(found so far: {total_fetched}), "
                f"count={esearch_result.get('count')!r}"
            )
            return

        count = esearch_result.get("count", "?")
        logger.info(
            f"db=pmc: got {len(ids)} IDs (retstart={retstart}, "
            f"total available={count})"
        )

        for pmc_numeric_id in ids:
            yield f"PMC{pmc_numeric_id}"
            total_fetched += 1
            if total_fetched >= config.target_count:
                return

        retstart += len(ids)

        if len(ids) < retmax:
            return

    logger.info(f"db=pmc discovery done: {total_fetched} PMCIDs for '{config.query}'")


async def _search_pubmed_pmc_filter(
    config: Config,
    limiter: NCBIRateLimiter,
    client: httpx.AsyncClient,
) -> AsyncIterator[str]:
    """
    Search db=pubmed with 'pmc open access[filter]', then convert PMIDs → PMCIDs
    via elink in batches.
    """
    total_fetched = 0
    retstart = 0
    term = f"{config.query} AND free full text[filter]"

    while total_fetched < config.target_count:
        retmax = min(PAGE_SIZE, config.target_count - total_fetched)

        params = {
            "db": "pubmed",
            "term": term,
            "retmax": retmax,
            "retstart": retstart,
            "retmode": "json",
            "tool": config.ncbi_tool,
            "email": config.ncbi_email,
        }
        if config.ncbi_api_key:
            params["api_key"] = config.ncbi_api_key

        await limiter.acquire()

        try:
            resp = await client.get(ESEARCH_URL, params=params, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"eSearch (pubmed fallback) failed at retstart={retstart}: {e}")
            return

        esearch_result = data.get("esearchresult", {})
        pmids = esearch_result.get("idlist", [])

        if not pmids:
            logger.warning(
                f"pubmed fallback: empty idlist at retstart={retstart}, "
                f"count={esearch_result.get('count')!r}, "
                f"ERROR={esearch_result.get('ERROR')!r}"
            )
            return

        count = esearch_result.get("count", "?")
        logger.info(
            f"pubmed fallback: got {len(pmids)} PMIDs (retstart={retstart}, "
            f"total available={count}), converting to PMCIDs..."
        )

        # Convert PMIDs → PMCIDs via elink
        pmcids = await _pmids_to_pmcids(pmids, config, limiter, client)
        logger.info(f"pubmed fallback: {len(pmcids)} PMCIDs obtained from {len(pmids)} PMIDs")

        for pmcid in pmcids:
            yield pmcid
            total_fetched += 1
            if total_fetched >= config.target_count:
                return

        retstart += len(pmids)

        if len(pmids) < retmax:
            return

    logger.info(
        f"pubmed fallback discovery done: {total_fetched} PMCIDs for '{config.query}'"
    )


ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


async def _pmids_to_pmcids(
    pmids: list[str],
    config: Config,
    limiter: NCBIRateLimiter,
    client: httpx.AsyncClient,
) -> list[str]:
    """Convert PubMed IDs to PMC IDs using esummary (reads articleids field)."""
    await limiter.acquire()

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "tool": config.ncbi_tool,
        "email": config.ncbi_email,
    }
    if config.ncbi_api_key:
        params["api_key"] = config.ncbi_api_key

    try:
        resp = await client.get(ESUMMARY_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"esummary failed: {e}")
        return []

    pmcids = []
    result = data.get("result", {})
    for uid, article in result.items():
        if uid == "uids" or not isinstance(article, dict):
            continue
        for id_entry in article.get("articleids", []):
            if id_entry.get("idtype") == "pmc":
                val = id_entry.get("value", "")
                if val:
                    # value может быть "PMC1234567" или просто "1234567"
                    pmcid = val if val.startswith("PMC") else f"PMC{val}"
                    pmcids.append(pmcid)
                break

    return pmcids
