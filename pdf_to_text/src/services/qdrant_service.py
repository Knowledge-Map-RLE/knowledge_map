"""Qdrant vector storage service"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..core.logger import get_logger
from ..core.config import settings
from ..core.exceptions import QdrantError

logger = get_logger(__name__)


class QdrantService:
    """Service for interacting with Qdrant vector database"""
    
    def __init__(self):
        self._client = None
        self._collection_name = settings.qdrant_collection_name
    
    def _ensure_client(self):
        """Ensure Qdrant client is initialized"""
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams
                
                logger.info(f"🔄 Connecting to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}")
                
                # Initialize client
                self._client = QdrantClient(
                    host=settings.qdrant_host,
                    port=settings.qdrant_port,
                    api_key=settings.qdrant_api_key
                )
                
                # Ensure collection exists
                self._ensure_collection()
                
                logger.info(f"✅ Connected to Qdrant, collection: {self._collection_name}")
                
            except ImportError as e:
                raise QdrantError(f"qdrant-client not available: {e}")
            except Exception as e:
                raise QdrantError(f"Failed to connect to Qdrant: {e}")
    
    def _ensure_collection(self):
        """Ensure collection exists, create if not"""
        from qdrant_client.models import Distance, VectorParams
        
        try:
            # Check if collection exists
            collections = self._client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            if self._collection_name not in collection_names:
                logger.info(f"📦 Creating collection: {self._collection_name}")
                
                self._client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(
                        size=settings.embedding_dimension,
                        distance=Distance.COSINE
                    )
                )
                
                logger.info(f"✅ Collection created: {self._collection_name}")
            else:
                logger.info(f"✅ Collection exists: {self._collection_name}")
                
        except Exception as e:
            raise QdrantError(f"Failed to ensure collection: {e}")
    
    async def upload_document(
        self,
        doc_id: str,
        text: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Upload document chunks with embeddings to Qdrant
        
        Args:
            doc_id: Document ID
            text: Full document text
            chunks: List of text chunks
            embeddings: List of embedding vectors
            metadata: Additional metadata
            
        Returns:
            Number of points uploaded
        """
        self._ensure_client()
        
        try:
            from qdrant_client.models import PointStruct
            
            logger.info(f"🔄 Uploading document {doc_id} to Qdrant ({len(chunks)} chunks)")
            
            # Prepare points
            points = []
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                point_id = f"{doc_id}_chunk_{idx}"
                
                payload = {
                    "doc_id": doc_id,
                    "chunk_index": idx,
                    "text": chunk,
                    "full_text": text if idx == 0 else None,  # Store full text only in first chunk
                    "chunk_count": len(chunks),
                    "created_at": datetime.now().isoformat(),
                }
                
                # Add custom metadata
                if metadata:
                    payload.update(metadata)
                
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
                points.append(point)
            
            # Upload to Qdrant
            self._client.upsert(
                collection_name=self._collection_name,
                points=points
            )
            
            logger.info(f"✅ Uploaded {len(points)} points for document {doc_id}")
            
            return len(points)
            
        except Exception as e:
            logger.error(f"❌ Failed to upload to Qdrant: {e}")
            raise QdrantError(f"Upload failed: {e}")
    
    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents
        
        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            
        Returns:
            List of search results
        """
        self._ensure_client()
        
        try:
            results = self._client.search(
                collection_name=self._collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold
            )
            
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                }
                for hit in results
            ]
            
        except Exception as e:
            logger.error(f"❌ Search failed: {e}")
            raise QdrantError(f"Search failed: {e}")
    
    async def delete_document(self, doc_id: str) -> int:
        """
        Delete all chunks of a document
        
        Args:
            doc_id: Document ID
            
        Returns:
            Number of points deleted
        """
        self._ensure_client()
        
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            # Delete by doc_id filter
            result = self._client.delete(
                collection_name=self._collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id)
                        )
                    ]
                )
            )
            
            logger.info(f"✅ Deleted document {doc_id} from Qdrant")
            return result
            
        except Exception as e:
            logger.error(f"❌ Delete failed: {e}")
            raise QdrantError(f"Delete failed: {e}")
    
    async def health_check(self) -> bool:
        """Check if Qdrant is available"""
        try:
            self._ensure_client()
            self._client.get_collections()
            return True
        except Exception as e:
            logger.warning(f"Qdrant health check failed: {e}")
            return False


# Global instance
qdrant_service = QdrantService()



