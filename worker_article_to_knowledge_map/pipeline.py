"""
Per-article processing pipeline (state machine).

Each article goes through:
  PENDING → INGESTING → AWAITING_MARKDOWN → ANNOTATING → EXTRACTING → REVIEWING → DONE
                                                                                     ↓
                                                                                  FAILED
"""
import asyncio
import logging
import random
import time
from urllib.parse import unquote

import httpx

from config import Config
from state_store import StateStore

logger = logging.getLogger(__name__)


async def process_article(
    pmcid: str,
    config: Config,
    store: StateStore,
    client: httpx.AsyncClient,
) -> None:
    """Run the full pipeline for a single article. Handles retries internally."""
    retry_count = await store.get_retry_count(pmcid)

    for attempt in range(retry_count, config.max_retries):
        try:
            await _run_pipeline(pmcid, config, store, client)
            return
        except Exception as e:
            error_msg = unquote(f"{type(e).__name__}: {e}")
            store.log(f"[{pmcid}] Attempt {attempt + 1} failed: {error_msg}")
            await store.set_error(pmcid, error_msg)

            if attempt + 1 >= config.max_retries:
                store.log(f"[{pmcid}] Max retries reached, marking as FAILED")
                await store.set_state(pmcid, "failed")
                return

            new_retry = await store.increment_retry(pmcid)
            delay = config.retry_base_delay * new_retry
            store.log(f"[{pmcid}] Retrying in {delay:.0f}s (attempt {new_retry + 1}/{config.max_retries})")
            await asyncio.sleep(delay)


async def _run_pipeline(
    pmcid: str,
    config: Config,
    store: StateStore,
    client: httpx.AsyncClient,
) -> None:
    base = config.api_base_url
    timeout = config.api_timeout

    # ── Step 1: INGESTING ────────────────────────────────────────────────────
    # On retry, reuse existing doc_id if already ingested
    doc_id = await store.get_doc_id(pmcid)
    if doc_id:
        store.log(f"[{pmcid}] Already ingested → doc_id={doc_id}, skipping ingest")
    else:
        store.log(f"[{pmcid}] Ingesting...")
        await store.set_state(pmcid, "ingesting")

        resp = await client.post(
            f"{base}/pubmed/ingest",
            json={"pmcid": pmcid, "source": "pmc"},
            timeout=timeout,
        )
        _check_response(pmcid, "ingest", resp)
        data = resp.json()

        if not data.get("success"):
            raise RuntimeError(f"ingest returned success=false: {data.get('message', '')}")

        doc_id = data["doc_id"]
        processing_status = data.get("processing_status", "")
        await store.set_state(pmcid, "ingesting", doc_id=doc_id)
        store.log(f"[{pmcid}] Ingested → doc_id={doc_id}, status={processing_status}")

        # ── Step 2: AWAITING_MARKDOWN (only if async PDF processing) ─────────
        if processing_status in ("pdf_to_markdown", "uploading", "processing"):
            store.log(f"[{pmcid}] Waiting for markdown conversion...")
            await store.set_state(pmcid, "awaiting_markdown", doc_id=doc_id)
            await _poll_until_markdown_ready(pmcid, doc_id, config, store, client)

    # ── Step 3: ANNOTATING ───────────────────────────────────────────────────
    # Проверяем состояние из StateStore — не делаем лишний HTTP GET /progress.
    # При первом прогоне статья никогда не бывает annotated.
    # При resume — состояние уже сохранено в Neo4j.
    current_state = await store.get_state(pmcid)
    if current_state in ("done", "reviewing", "extracting"):
        store.log(f"[{pmcid}] Already annotated (state={current_state}), skipping annotation")
    else:
        store.log(f"[{pmcid}] Starting auto-annotation...")
        await store.set_state(pmcid, "annotating", doc_id=doc_id)

        resp = await client.post(
            f"{base}/documents/{doc_id}/auto-annotate/batch",
            params={"min_confidence": 0.7},
            timeout=timeout,
        )
        _check_response(pmcid, "auto-annotate", resp)
        store.log(f"[{pmcid}] Annotation started, polling for completion...")
        await _poll_until_annotated(pmcid, doc_id, config, store, client)

    # ── Step 4: EXTRACTING ACTIONS ───────────────────────────────────────────
    store.log(f"[{pmcid}] Extracting actions...")
    await store.set_state(pmcid, "extracting", doc_id=doc_id)

    resp = await client.post(
        f"{base}/documents/{doc_id}/extract-actions",
        timeout=timeout,
    )
    _check_response(pmcid, "extract-actions", resp)
    extract_data = resp.json()
    actions_count = extract_data.get("actions_count", "?")
    edges_count = extract_data.get("edges_count", "?")
    store.log(f"[{pmcid}] Extracted {actions_count} actions, {edges_count} edges")

    # ── Step 5: AUTO-REVIEW ──────────────────────────────────────────────────
    store.log(f"[{pmcid}] Running auto-review...")
    await store.set_state(pmcid, "reviewing", doc_id=doc_id)

    resp = await client.post(
        f"{base}/documents/{doc_id}/auto-review",
        timeout=timeout,
    )
    _check_response(pmcid, "auto-review", resp)
    review_data = resp.json()
    confirmed = review_data.get("confirmed", "?")
    rejected = review_data.get("rejected", "?")
    store.log(f"[{pmcid}] Review done: {confirmed} confirmed, {rejected} rejected")

    # ── DONE ─────────────────────────────────────────────────────────────────
    await store.set_state(pmcid, "done", doc_id=doc_id)
    store.log(f"[{pmcid}] DONE")


async def _poll_until_markdown_ready(
    pmcid: str,
    doc_id: str,
    config: Config,
    store: StateStore,
    client: httpx.AsyncClient,
) -> None:
    """Poll /progress until markdown conversion completes.

    Uses adaptive exponential backoff with full jitter to avoid thundering herd
    when multiple articles poll simultaneously:
      interval grows: poll_interval → poll_interval×1.5 → ... → 20s
      actual sleep = random(0, interval)  ← full jitter
    """
    deadline = time.monotonic() + config.poll_timeout_sec
    interval = config.poll_interval_sec
    max_interval = 20.0

    while time.monotonic() < deadline:
        await asyncio.sleep(interval * random.random())
        try:
            resp = await client.get(
                f"{config.api_base_url}/documents/{doc_id}/progress",
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("processing_status", "")
                if status not in ("pdf_to_markdown", "uploading", "processing"):
                    store.log(f"[{pmcid}] Markdown ready (status={status})")
                    return
                phase = data.get("phase", "")
                pct = data.get("percent", 0)
                store.log(f"[{pmcid}] Waiting... {pct}% {phase}")
        except Exception as e:
            store.log(f"[{pmcid}] Poll error: {unquote(str(e))}")

        interval = min(interval * 1.5, max_interval)

    raise TimeoutError(
        f"Markdown not ready after {config.poll_timeout_sec}s for doc {doc_id}"
    )


async def _poll_until_annotated(
    pmcid: str,
    doc_id: str,
    config: Config,
    store: StateStore,
    client: httpx.AsyncClient,
) -> None:
    """Poll /progress until processing_status == 'annotated' (or timeout).

    Adaptive exponential backoff with full jitter:
      interval grows: poll_interval → poll_interval×1.5 → ... → 20s
      actual sleep = random(0, interval)
    """
    deadline = time.monotonic() + config.annotate_wait_sec
    interval = config.poll_interval_sec
    max_interval = 20.0

    while time.monotonic() < deadline:
        await asyncio.sleep(interval * random.random())
        try:
            resp = await client.get(
                f"{config.api_base_url}/documents/{doc_id}/progress",
                timeout=60.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("processing_status", "")
                store.log(f"[{pmcid}] Poll status={status}")
                if status == "annotated":
                    store.log(f"[{pmcid}] Annotation complete")
                    return
        except Exception as e:
            store.log(f"[{pmcid}] Annotation poll error: {type(e).__name__}: {unquote(repr(e))}")

        interval = min(interval * 1.5, max_interval)

    # Timeout — proceed anyway, annotations may be partially done
    store.log(f"[{pmcid}] Annotation poll timeout ({config.annotate_wait_sec:.0f}s), proceeding")


def _check_response(pmcid: str, step: str, resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        body = unquote(resp.text[:300])
        raise RuntimeError(
            f"[{pmcid}] {step} returned HTTP {resp.status_code}: {body}"
        )
