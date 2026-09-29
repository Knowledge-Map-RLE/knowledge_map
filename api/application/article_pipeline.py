"""Versioned extraction use case, independent of HTTP and database drivers."""
from __future__ import annotations
import asyncio
import logging
from knowledge_pipeline import ArticlePipeline
from knowledge_pipeline.pipeline import uid
log = logging.getLogger(__name__)

class ExtractArticle:
    def __init__(self, repository, nlp, llm):
        self.repository = repository
        self.pipeline = ArticlePipeline(nlp, llm)
    async def execute(self, doc_id, text, user_uid, emit, save=True):
        latest = {}
        async def checkpoint(result):
            nonlocal latest
            latest = result
            if save:
                await asyncio.to_thread(self.repository.save,result,user_uid)
            await emit({"type":"progress","run_id":result["run_id"],"version_id":result["version_id"],
                        "stage":result["stage"],"processed":result.get("processed",0),"total":result.get("total",1)})
        try:
            result = await self.pipeline.run(doc_id,text,checkpoint)
            log.info("article_pipeline completed article=%s run=%s",doc_id,result["run_id"])
            return result
        except (Exception, asyncio.CancelledError) as exc:
            if latest and save:
                latest.update(status="cancelled" if isinstance(exc,asyncio.CancelledError) else "failed",
                              error=str(exc) or "Cancelled",success=False)
                await asyncio.to_thread(self.repository.save,latest,user_uid)
            log.exception("article_pipeline stopped article=%s run=%s",doc_id,latest.get("run_id"))
            raise
