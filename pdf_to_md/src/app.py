"""Main FastAPI application for PDF to Markdown service"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router as api_router
from .api.s3_routes import router as s3_router
from .api.middleware import LoggingMiddleware, SecurityMiddleware, RateLimitMiddleware
from .core.config import settings
from .core.logger import setup_logging, get_logger
from .services.conversion_service import ConversionService

# Setup logging
logger = setup_logging(
    log_level=settings.log_level,
    service_name=settings.service_name
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.version}")
    logger.info(f"Debug mode: {settings.debug}")
    
    # Initialize services
    app.state.conversion_service = ConversionService()
    logger.info("Conversion service initialized")
    
    # Cleanup old files
    try:
        app.state.conversion_service.file_service.cleanup_old_files()
    except Exception as e:
        logger.warning(f"Failed to cleanup old files: {e}")
    
    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")
    
    # Cancel active conversions
    try:
        active_conversions = app.state.conversion_service.get_active_conversions()
        for doc_id in active_conversions:
            await app.state.conversion_service.cancel_conversion(doc_id)
        logger.info(f"Cancelled {len(active_conversions)} active conversions")
    except Exception as e:
        logger.error(f"Error cancelling active conversions: {e}")


# Create FastAPI application
app = FastAPI(
    title="PDF to Markdown Service",
    description="Микросервис для преобразования PDF документов в Markdown формат",
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityMiddleware)

if settings.enable_rate_limiting:
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.rate_limit_requests
    )

# Include API routes
app.include_router(api_router)
app.include_router(s3_router)

# Add root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.service_name,
        "version": settings.version,
        "status": "running",
        "docs": "/docs" if settings.debug else "disabled"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "An unexpected error occurred"
        }
    )


# Health check endpoint (separate from API routes)
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.version
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
