"""
Main worker orchestration loop.

1. Discovers PMCIDs via NCBI eSearch (paginated, rate-limited)
2. Stores them in Neo4j as PENDING
3. Processes up to config.batch_size articles concurrently
"""
import asyncio
import logging

import httpx

from config import Config
from pipeline import process_article
from rate_limiter import NCBIRateLimiter
from searcher import search_pmc_ids
from state_store import StateStore

logger = logging.getLogger(__name__)


async def run_worker(config: Config, store: StateStore) -> None:
    limiter = NCBIRateLimiter(has_api_key=bool(config.ncbi_api_key))

    async with httpx.AsyncClient() as search_client:
        store.log(f"Searching PMC for '{config.query}' (target={config.target_count})...")

        pmcids: list[str] = []
        async for pmcid in search_pmc_ids(config, limiter, search_client):
            pmcids.append(pmcid)

    if not pmcids:
        store.log("No articles found. Exiting.")
        return

    store.log(f"Found {len(pmcids)} articles. Adding to state store...")
    await store.add_articles(pmcids)
    await store.set_total(len(pmcids))

    # Сбрасываем зависшие статьи (annotating/extracting/reviewing) → pending
    stuck = await store.reset_stuck_articles()
    if stuck:
        store.log(f"Reset {stuck} stuck articles back to pending")

    # Get articles that still need processing (resume-friendly)
    pending = await store.get_pending_pmcids()
    store.log(f"Processing {len(pending)} articles (batch_size={config.batch_size})...")

    semaphore = asyncio.Semaphore(config.batch_size)
    processed = 0
    total = len(pending)

    async def process_with_sem(pmcid: str, client: httpx.AsyncClient) -> None:
        nonlocal processed
        async with semaphore:
            store.log(f"[{pmcid}] Starting ({processed + 1}/{total})...")
            await process_article(pmcid, config, store, client)
            processed += 1
            summary = await store.get_summary()
            store.log(
                f"Progress: {summary['done']} done, {summary['in_progress']} active, "
                f"{summary['failed']} failed, {summary['pending']} pending — {summary['percent']}%"
            )

    async with httpx.AsyncClient() as api_client:
        tasks = [process_with_sem(pmcid, api_client) for pmcid in pending]
        await asyncio.gather(*tasks, return_exceptions=True)

    summary = await store.get_summary()
    store.log(
        f"Worker finished: {summary['done']} done, "
        f"{summary['failed']} failed, "
        f"{summary['in_progress']} still in progress"
    )
    await store.mark_run_done()
