from __future__ import annotations

import logging
import asyncio
from threading import Lock

logger = logging.getLogger(__name__)


class SentenceTransformerEmbedder:
    """
    SentenceTransformer embedder для семантического сравнения утверждений.

    Использует sentence-transformers (Hugging Face) с кэшированием модели.
    Default model: all-MiniLM-L6-v2 (384 dim, fast, good quality).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None
        self._load_lock = Lock()

    def _load_model(self):
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self._model_name)
                logger.info("Loaded SentenceTransformer model: %s", self._model_name)
                return self._model
            except ImportError:
                logger.error(
                    "sentence-transformers not installed. "
                    "Install it in the Poetry environment."
                )
                raise
            except Exception as e:
                logger.error("Failed to load model %s: %s", self._model_name, e)
                raise

    async def _get_model(self):
        """Load the optional embedding model off the event loop on first use."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._load_model)

    def ensure_loaded(self) -> bool:
        """Load model if not yet loaded. Returns True on success, False on failure."""
        try:
            self._load_model()
            return True
        except Exception:
            return False

    async def embed(self, text: str) -> list[float]:
        model = await self._get_model()
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: model.encode(
                text,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
        )
        return embedding.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = await self._get_model()
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=32,
            ),
        )
        return [e.tolist() for e in embeddings]

    @property
    def dimension(self) -> int:
        self._load_model()
        assert self._model is not None
        return self._model.get_sentence_embedding_dimension()
