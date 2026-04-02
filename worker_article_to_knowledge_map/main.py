"""
Entry point for the batch article processing worker.

Starts two concurrent tasks:
  1. The worker loop (discovery + pipeline per article)
  2. The status FastAPI server on port 8004
"""
import asyncio
import logging

import uvicorn

from config import load_config
from state_store import StateStore
from status_api import build_app, set_store
from worker import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("worker.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    logger.info(
        f"Starting worker: query='{config.query}', "
        f"target={config.target_count}, batch_size={config.batch_size}"
    )

    store = StateStore(config)
    await store.init()
    await store.resume_or_start(config.query)

    # Wire store into the status API
    set_store(store)
    status_app = build_app()

    # Run status API server
    server_config = uvicorn.Config(
        status_app,
        host=config.status_host,
        port=config.status_port,
        log_level="warning",
    )
    server = uvicorn.Server(server_config)

    async def worker_then_stop():
        try:
            await run_worker(config, store)
        finally:
            logger.info("Worker loop finished, stopping status API...")
            server.should_exit = True

    try:
        await asyncio.gather(
            server.serve(),
            worker_then_stop(),
        )
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await store.close()
        logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
