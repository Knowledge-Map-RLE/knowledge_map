"""Text embedding service"""

import logging
from typing import List, Optional
import numpy as np

from ..core.logger import get_logger
from ..core.config import settings
from ..core.exceptions import VectorizationError

logger = get_logger(__name__)


class EmbeddingService:
    """Service for text vectorization using sentence-transformers"""
    
    def __init__(self):
        self._model = None
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
    
    def _ensure_model_loaded(self):
        """Ensure embedding model is loaded"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                
                logger.info(f"🔄 Loading embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"✅ Embedding model loaded: {self.model_name}")
                
            except ImportError as e:
                raise VectorizationError(f"sentence-transformers not available: {e}")
            except Exception as e:
                raise VectorizationError(f"Failed to load model: {e}")
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks
        
        Args:
            text: Input text
            
        Returns:
            List of text chunks
        """
        chunk_size = settings.chunk_size
        overlap = settings.chunk_overlap
        
        # Simple chunking by characters with overlap
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            
            # Try to break at sentence boundary
            if end < text_length:
                # Look for last period, question mark, or exclamation
                for delimiter in ['. ', '? ', '! ', '\n\n']:
                    last_delim = chunk.rfind(delimiter)
                    if last_delim > chunk_size // 2:  # Don't break too early
                        chunk = chunk[:last_delim + len(delimiter)]
                        end = start + len(chunk)
                        break
            
            if chunk.strip():
                chunks.append(chunk.strip())
            
            # Move start position with overlap
            start = end - overlap
            
            # Safety check
            if start <= 0:
                start = end
        
        logger.info(f"📄 Text split into {len(chunks)} chunks")
        return chunks
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        self._ensure_model_loaded()
        
        try:
            logger.info(f"🔄 Embedding {len(texts)} text chunks")
            
            # Generate embeddings
            embeddings = self._model.encode(
                texts,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            
            # Convert to list of lists
            embeddings_list = embeddings.tolist()
            
            logger.info(f"✅ Generated {len(embeddings_list)} embeddings "
                       f"with dimension {len(embeddings_list[0])}")
            
            return embeddings_list
            
        except Exception as e:
            logger.error(f"❌ Embedding generation failed: {e}")
            raise VectorizationError(f"Embedding failed: {e}")
    
    async def embed_single_text(self, text: str) -> List[float]:
        """
        Embed single text
        
        Args:
            text: Input text
            
        Returns:
            Embedding vector
        """
        embeddings = await self.embed_texts([text])
        return embeddings[0]


# Global instance
embedding_service = EmbeddingService()



