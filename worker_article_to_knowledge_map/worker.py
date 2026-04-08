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

_LOG_EVERY = 10  # Log progress every N completed articles (avoids O(N²) get_summary calls)


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
    counter_lock = asyncio.Lock()
    processed = 0
    total = len(pending)

    # httpx connection pool sized to batch_size:
    #   batch_size × 4 — запас под polling (каждая статья делает несколько параллельных GET)
    #   keepalive_expiry=60s — переиспользуем TCP-соединения между poll-ами
    limits = httpx.Limits(
        max_connections=config.batch_size * 4,
        max_keepalive_connections=config.batch_size,
        keepalive_expiry=60.0,
    )

    async def process_with_sem(pmcid: str, client: httpx.AsyncClient) -> None:
        nonlocal processed
        async with semaphore:
            await process_article(pmcid, config, store, client)
            async with counter_lock:
                processed += 1
                if processed % _LOG_EVERY == 0 or processed == total:
                    summary = await store.get_summary()
                    store.log(
                        f"Progress {processed}/{total}: "
                        f"{summary['done']} done, {summary['in_progress']} active, "
                        f"{summary['failed']} failed — {summary['percent']}%"
                    )

    async with httpx.AsyncClient(limits=limits) as api_client:
        # TaskGroup (Python 3.11+): структурированный параллелизм, нет утечек задач
        async with asyncio.TaskGroup() as tg:
            for pmcid in pending:
                tg.create_task(process_with_sem(pmcid, api_client))

    summary = await store.get_summary()
    store.log(
        f"Worker finished: {summary['done']} done, "
        f"{summary['failed']} failed, "
        f"{summary['in_progress']} still in progress"
    )
    await store.mark_run_done()
