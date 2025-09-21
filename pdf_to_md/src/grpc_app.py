"""gRPC application for PDF to Markdown service"""

import asyncio
import logging
import grpc
from concurrent import futures
from pathlib import Path

from .core.config import settings
from .core.logger import setup_logging, get_logger
from .services.conversion_service import ConversionService
from .grpc_services.pdf_to_md_servicer import PDFToMarkdownServicer

# Setup logging
logger = setup_logging(
    log_level=settings.log_level,
    service_name=f"{settings.service_name}-grpc"
)


class GRPCApplication:
    """gRPC application class"""
    
    def __init__(self):
        self.conversion_service = ConversionService()
        self.server = None
    
    async def start(self):
        """Start gRPC server"""
        logger.info(f"Starting gRPC server on port {settings.grpc_port}")
        
        # Create server
        self.server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=10)
        )
        
        # Add servicer
        servicer = PDFToMarkdownServicer(self.conversion_service)
        
        # Import and add service
        try:
            from .grpc_services import pdf_to_md_pb2_grpc
            pdf_to_md_pb2_grpc.add_PDFToMarkdownServiceServicer_to_server(
                servicer, self.server
            )
        except ImportError as e:
            logger.error(f"Failed to import gRPC service definitions: {e}")
            raise
        
        # Add port
        listen_addr = f'0.0.0.0:{settings.grpc_port}'
        self.server.add_insecure_port(listen_addr)
        
        # Start server
        await self.server.start()
        logger.info(f"gRPC server started on {listen_addr}")
        
        # Wait for termination
        await self.server.wait_for_termination()
    
    async def stop(self):
        """Stop gRPC server"""
        if self.server:
            logger.info("Stopping gRPC server")
            await self.server.stop(grace=5.0)
            logger.info("gRPC server stopped")


async def main():
    """Main function for gRPC server"""
    app = GRPCApplication()
    
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
