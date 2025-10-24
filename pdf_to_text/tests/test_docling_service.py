"""Tests for Docling service"""

import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_docling_service_import():
    """Test that docling service can be imported"""
    from src.services.docling_service import docling_service
    assert docling_service is not None


@pytest.mark.asyncio
async def test_chunk_text():
    """Test text chunking"""
    from src.services.embedding_service import embedding_service
    
    text = "This is a test. " * 100
    chunks = embedding_service.chunk_text(text)
    
    assert len(chunks) > 0
    assert all(isinstance(chunk, str) for chunk in chunks)


@pytest.mark.asyncio
async def test_health_check():
    """Test health check endpoint"""
    from src.api.routes import health_check
    
    result = await health_check()
    
    assert result.service == "pdf-to-text-service"
    assert result.version == "0.1.0"



