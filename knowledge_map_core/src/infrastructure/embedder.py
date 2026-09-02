from __future__ import annotations

import logging
from functools import lru_cache

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

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            logger.info("Loaded SentenceTransformer model: %s", self._model_name)
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            raise
        except Exception as e:
            logger.error("Failed to load model %s: %s", self._model_name, e)
            raise

    def ensure_loaded(self) -> bool:
        """Load model if not yet loaded. Returns True on success, False on failure."""
        try:
            self._load_model()
            return True
        except Exception:
            return False

    async def embed(self, text: str) -> list[float]:
        self._load_model()
        assert self._model is not None

        import asyncio

        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                text,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
        )
        return embedding.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        self._load_model()
        assert self._model is not None

        import asyncio

        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
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
