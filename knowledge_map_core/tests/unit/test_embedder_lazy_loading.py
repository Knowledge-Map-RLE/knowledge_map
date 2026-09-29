from __future__ import annotations

import asyncio
import threading

from src.infrastructure.embedder import SentenceTransformerEmbedder


def test_embedding_model_is_loaded_lazily_and_off_event_loop(monkeypatch):
    embedder = SentenceTransformerEmbedder("test-model")
    event_loop_thread = threading.get_ident()
    load_threads: list[int] = []
    model = object()

    def load_model():
        load_threads.append(threading.get_ident())
        return model

    monkeypatch.setattr(embedder, "_load_model", load_model)

    assert embedder._model is None

    async def get_model():
        return await embedder._get_model()

    assert asyncio.run(get_model()) is model
    assert load_threads
    assert load_threads[0] != event_loop_thread
