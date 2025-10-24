"""gRPC server implementation"""

import logging
import asyncio
from concurrent import futures
from datetime import datetime
from typing import Optional

import grpc

from .core.logger import get_logger
from .core.config import settings
from .services.conversion_service import conversion_service
from .services.qdrant_service import qdrant_service
from .services.embedding_service import embedding_service

logger = get_logger(__name__)


class PDFToTextServicer:
    """gRPC servicer for PDF to Text service"""
    
    def __init__(self):
        self.conversion_service = conversion_service
        self.qdrant_service = qdrant_service
        self.embedding_service = embedding_service
    
    async def ConvertPDF(self, request, context):
        """Convert PDF to text and store in Qdrant"""
        
        from .generated import pdf_to_text_pb2
        
        try:
            logger.info(f"📄 gRPC ConvertPDF: doc_id={request.doc_id}, filename={request.filename}")
            
            # Validate PDF content
            if not request.pdf_content:
                return pdf_to_text_pb2.ConvertPDFResponse(
                    success=False,
                    doc_id=request.doc_id or "",
                    message="Empty PDF content",
                    error="PDF content is empty"
                )
            
            # Check file size
            max_size = settings.max_file_size_mb * 1024 * 1024
            if len(request.pdf_content) > max_size:
                return pdf_to_text_pb2.ConvertPDFResponse(
                    success=False,
                    doc_id=request.doc_id or "",
                    message="File too large",
                    error=f"File size exceeds {settings.max_file_size_mb}MB"
                )
            
            # Process PDF
            result = await self.conversion_service.process_pdf(
                pdf_content=request.pdf_content,
                doc_id=request.doc_id or None,
                filename=request.filename or None
            )
            
            # Build response
            if result.success:
                return pdf_to_text_pb2.ConvertPDFResponse(
                    success=True,
                    doc_id=result.doc_id,
                    message="PDF successfully converted and stored in Qdrant",
                    text_length=result.conversion.text_length,
                    chunks_count=result.vectorization.chunks_count if result.vectorization else 0,
                    points_uploaded=result.qdrant_upload.points_uploaded if result.qdrant_upload else 0,
                    processing_time=result.total_time
                )
            else:
                error_msg = "Conversion failed"
                if result.conversion and not result.conversion.success:
                    error_msg = result.conversion.error or error_msg
                elif result.vectorization and not result.vectorization.success:
                    error_msg = result.vectorization.error or error_msg
                elif result.qdrant_upload and not result.qdrant_upload.success:
                    error_msg = result.qdrant_upload.error or error_msg
                
                return pdf_to_text_pb2.ConvertPDFResponse(
                    success=False,
                    doc_id=result.doc_id,
                    message="Conversion failed",
                    processing_time=result.total_time,
                    error=error_msg
                )
            
        except Exception as e:
            logger.error(f"❌ gRPC ConvertPDF error: {e}", exc_info=True)
            return pdf_to_text_pb2.ConvertPDFResponse(
                success=False,
                doc_id=request.doc_id or "",
                message="Internal server error",
                error=str(e)
            )
    
    async def SearchDocuments(self, request, context):
        """Search documents by text query"""
        
        from .generated import pdf_to_text_pb2
        
        try:
            logger.info(f"🔍 gRPC SearchDocuments: query={request.query[:100]}")
            
            # Embed query
            query_vector = await self.embedding_service.embed_single_text(request.query)
            
            # Search in Qdrant
            results = await self.qdrant_service.search(
                query_vector=query_vector,
                limit=request.limit if request.limit > 0 else 10,
                score_threshold=request.score_threshold if request.score_threshold > 0 else None
            )
            
            # Build response
            search_results = []
            for result in results:
                payload = result.get("payload", {})
                search_results.append(
                    pdf_to_text_pb2.SearchResult(
                        id=result.get("id", ""),
                        score=result.get("score", 0.0),
                        doc_id=payload.get("doc_id", ""),
                        text=payload.get("text", ""),
                        chunk_index=payload.get("chunk_index", 0),
                        filename=payload.get("filename", "")
                    )
                )
            
            return pdf_to_text_pb2.SearchResponse(
                results=search_results,
                count=len(search_results)
            )
            
        except Exception as e:
            logger.error(f"❌ gRPC SearchDocuments error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pdf_to_text_pb2.SearchResponse(results=[], count=0)
    
    async def DeleteDocument(self, request, context):
        """Delete document from Qdrant"""
        
        from .generated import pdf_to_text_pb2
        
        try:
            logger.info(f"🗑️ gRPC DeleteDocument: doc_id={request.doc_id}")
            
            await self.qdrant_service.delete_document(request.doc_id)
            
            return pdf_to_text_pb2.DeleteDocumentResponse(
                success=True,
                message=f"Document {request.doc_id} deleted"
            )
            
        except Exception as e:
            logger.error(f"❌ gRPC DeleteDocument error: {e}")
            return pdf_to_text_pb2.DeleteDocumentResponse(
                success=False,
                message=str(e)
            )
    
    async def HealthCheck(self, request, context):
        """Health check"""
        
        from .generated import pdf_to_text_pb2
        
        try:
            qdrant_available = await self.qdrant_service.health_check()
            
            return pdf_to_text_pb2.HealthCheckResponse(
                status="healthy" if qdrant_available else "degraded",
                service=settings.service_name,
                version="0.1.0",
                qdrant_available=qdrant_available,
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"❌ gRPC HealthCheck error: {e}")
            return pdf_to_text_pb2.HealthCheckResponse(
                status="unhealthy",
                service=settings.service_name,
                version="0.1.0",
                qdrant_available=False,
                timestamp=datetime.now().isoformat()
            )


async def serve():
    """Start gRPC server"""
    
    from .generated import pdf_to_text_pb2_grpc
    
    logger.info(f"🚀 Starting gRPC server on {settings.api_host}:{settings.api_port}")
    
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 100 * 1024 * 1024),  # 100MB
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),  # 100MB
        ]
    )
    
    servicer = PDFToTextServicer()
    pdf_to_text_pb2_grpc.add_PDFToTextServiceServicer_to_server(servicer, server)
    
    server.add_insecure_port(f"{settings.api_host}:{settings.api_port}")
    
    await server.start()
    
    logger.info(f"✅ gRPC server listening on {settings.api_host}:{settings.api_port}")
    logger.info(f"🗄️ Qdrant at {settings.qdrant_host}:{settings.qdrant_port}")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("🛑 Stopping gRPC server...")
        await server.stop(grace=5)



