"""Main PDF to text conversion service"""

import logging
import tempfile
import time
import hashlib
from pathlib import Path
from typing import Optional

from ..core.logger import get_logger
from ..core.config import settings
from ..core.types import (
    ConversionResult,
    VectorizationResult,
    QdrantUploadResult,
    ProcessingResult,
    ConversionStatus
)
from ..core.exceptions import PDFConversionError, VectorizationError, QdrantError

from .docling_service import docling_service
from .embedding_service import embedding_service
from .qdrant_service import qdrant_service

logger = get_logger(__name__)


class ConversionService:
    """Main service for PDF to text conversion with Qdrant storage"""
    
    def __init__(self):
        self.docling = docling_service
        self.embedding = embedding_service
        self.qdrant = qdrant_service
    
    async def process_pdf(
        self,
        pdf_content: bytes,
        doc_id: Optional[str] = None,
        filename: Optional[str] = None
    ) -> ProcessingResult:
        """
        Process PDF: convert to text, vectorize, and store in Qdrant
        
        Args:
            pdf_content: PDF file content
            doc_id: Document ID (generated if not provided)
            filename: Original filename
            
        Returns:
            Processing result with all stages
        """
        start_time = time.time()
        
        # Generate doc_id if not provided
        if not doc_id:
            doc_id = hashlib.md5(pdf_content).hexdigest()
        
        logger.info(f"📄 Processing PDF: doc_id={doc_id}, filename={filename}")
        
        try:
            # Stage 1: PDF to Text
            conversion_result = await self._convert_pdf_to_text(
                pdf_content, doc_id, filename
            )
            
            if not conversion_result.success:
                return ProcessingResult(
                    success=False,
                    doc_id=doc_id,
                    conversion=conversion_result,
                    total_time=time.time() - start_time,
                    status=ConversionStatus.FAILED
                )
            
            # Stage 2: Vectorization
            vectorization_result = await self._vectorize_text(
                conversion_result.text, doc_id
            )
            
            if not vectorization_result.success:
                return ProcessingResult(
                    success=False,
                    doc_id=doc_id,
                    conversion=conversion_result,
                    vectorization=vectorization_result,
                    total_time=time.time() - start_time,
                    status=ConversionStatus.FAILED
                )
            
            # Stage 3: Upload to Qdrant
            qdrant_result = await self._upload_to_qdrant(
                doc_id=doc_id,
                text=conversion_result.text,
                filename=filename
            )
            
            total_time = time.time() - start_time
            
            logger.info(f"✅ Processing completed for {doc_id} in {total_time:.2f}s")
            
            return ProcessingResult(
                success=qdrant_result.success,
                doc_id=doc_id,
                conversion=conversion_result,
                vectorization=vectorization_result,
                qdrant_upload=qdrant_result,
                total_time=total_time,
                status=ConversionStatus.COMPLETED if qdrant_result.success else ConversionStatus.FAILED
            )
            
        except Exception as e:
            logger.error(f"❌ Processing failed for {doc_id}: {e}")
            
            return ProcessingResult(
                success=False,
                doc_id=doc_id,
                conversion=ConversionResult(
                    success=False,
                    doc_id=doc_id,
                    text="",
                    text_length=0,
                    error=str(e)
                ),
                total_time=time.time() - start_time,
                status=ConversionStatus.FAILED
            )
    
    async def _convert_pdf_to_text(
        self,
        pdf_content: bytes,
        doc_id: str,
        filename: Optional[str]
    ) -> ConversionResult:
        """Convert PDF to text using Docling"""
        
        start_time = time.time()
        
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                tmp_path = Path(tmp_file.name)
            
            try:
                # Convert with Docling
                text = await self.docling.convert_pdf_to_text(tmp_path, doc_id)
                
                processing_time = time.time() - start_time
                
                return ConversionResult(
                    success=True,
                    doc_id=doc_id,
                    text=text,
                    text_length=len(text),
                    processing_time=processing_time
                )
                
            finally:
                # Cleanup
                if tmp_path.exists():
                    tmp_path.unlink()
                    
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return ConversionResult(
                success=False,
                doc_id=doc_id,
                text="",
                text_length=0,
                error=str(e),
                processing_time=time.time() - start_time
            )
    
    async def _vectorize_text(
        self,
        text: str,
        doc_id: str
    ) -> VectorizationResult:
        """Vectorize text into chunks and embeddings"""
        
        try:
            # Split into chunks
            chunks = self.embedding.chunk_text(text)
            
            # Generate embeddings
            embeddings = await self.embedding.embed_texts(chunks)
            
            # Store for Qdrant upload
            self._cached_chunks = chunks
            self._cached_embeddings = embeddings
            
            return VectorizationResult(
                success=True,
                doc_id=doc_id,
                chunks_count=len(chunks),
                vector_dimension=len(embeddings[0]) if embeddings else 0
            )
            
        except Exception as e:
            logger.error(f"Vectorization failed: {e}")
            return VectorizationResult(
                success=False,
                doc_id=doc_id,
                chunks_count=0,
                vector_dimension=0,
                error=str(e)
            )
    
    async def _upload_to_qdrant(
        self,
        doc_id: str,
        text: str,
        filename: Optional[str]
    ) -> QdrantUploadResult:
        """Upload to Qdrant vector database"""
        
        try:
            # Get cached chunks and embeddings
            chunks = getattr(self, '_cached_chunks', [])
            embeddings = getattr(self, '_cached_embeddings', [])
            
            if not chunks or not embeddings:
                raise QdrantError("No chunks/embeddings available for upload")
            
            # Prepare metadata
            metadata = {
                "filename": filename,
            }
            
            # Upload to Qdrant
            points_uploaded = await self.qdrant.upload_document(
                doc_id=doc_id,
                text=text,
                chunks=chunks,
                embeddings=embeddings,
                metadata=metadata
            )
            
            return QdrantUploadResult(
                success=True,
                doc_id=doc_id,
                points_uploaded=points_uploaded
            )
            
        except Exception as e:
            logger.error(f"Qdrant upload failed: {e}")
            return QdrantUploadResult(
                success=False,
                doc_id=doc_id,
                points_uploaded=0,
                error=str(e)
            )


# Global instance
conversion_service = ConversionService()



