"""Main entry point"""

import asyncio

from .core.config import settings
from .core.logger import get_logger
from .grpc_server import serve

logger = get_logger(__name__)


def main():
    """Run the gRPC server"""
    
    logger.info(f"Starting {settings.service_name}...")
    
    asyncio.run(serve())


if __name__ == "__main__":
    main()

