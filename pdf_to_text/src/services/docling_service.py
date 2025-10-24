"""Docling service for PDF to text conversion"""

import logging
from pathlib import Path
from typing import Optional

from ..core.logger import get_logger
from ..core.exceptions import PDFConversionError

logger = get_logger(__name__)


class DoclingService:
    """Service for converting PDF to text using Docling"""
    
    def __init__(self):
        self.initialized = False
        self._converter = None
    
    def _ensure_initialized(self):
        """Ensure Docling is initialized"""
        if not self.initialized:
            try:
                from docling.document_converter import DocumentConverter
                self._converter = DocumentConverter()
                self.initialized = True
                logger.info("✅ Docling converter initialized")
            except ImportError as e:
                logger.error(f"❌ Docling not available: {e}")
                raise PDFConversionError(f"Docling not available: {e}")
    
    async def convert_pdf_to_text(
        self,
        pdf_path: Path,
        doc_id: Optional[str] = None
    ) -> str:
        """
        Convert PDF to plain text using Docling
        
        Args:
            pdf_path: Path to PDF file
            doc_id: Document ID for logging
            
        Returns:
            Extracted text content
        """
        self._ensure_initialized()
        
        try:
            # Validate input
            if not pdf_path.exists():
                raise PDFConversionError(f"PDF file not found: {pdf_path}")
            
            logger.info(f"🔄 Converting PDF to text: {pdf_path.name} (doc_id={doc_id})")
            
            # Convert with Docling
            result = self._converter.convert(str(pdf_path))
            
            # Extract text
            text = self._extract_text_from_result(result)
            
            if not text or not text.strip():
                raise PDFConversionError("No text extracted from PDF")
            
            logger.info(f"✅ Extracted {len(text)} characters from {pdf_path.name}")
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"❌ PDF conversion failed: {e}")
            raise PDFConversionError(f"Conversion failed: {e}")
    
    def _extract_text_from_result(self, result) -> str:
        """Extract plain text from Docling result"""
        
        try:
            # Try different text extraction methods
            if hasattr(result, 'document') and result.document:
                document = result.document
                
                # Method 1: export_to_text
                if hasattr(document, 'export_to_text'):
                    return document.export_to_text()
                
                # Method 2: export_to_markdown and strip markdown
                if hasattr(document, 'export_to_markdown'):
                    markdown = document.export_to_markdown()
                    # Simple markdown stripping (можно улучшить)
                    text = self._strip_markdown(str(markdown))
                    return text
                
                # Method 3: to_text
                if hasattr(document, 'to_text'):
                    return document.to_text()
                
                # Method 4: Direct string conversion
                return str(document)
            
            # Fallback
            return str(result)
            
        except Exception as e:
            logger.warning(f"Text extraction method failed: {e}")
            # Try simple string conversion
            return str(result)
    
    def _strip_markdown(self, markdown: str) -> str:
        """Simple markdown stripping"""
        import re
        
        # Remove markdown headers
        text = re.sub(r'^#+\s+', '', markdown, flags=re.MULTILINE)
        
        # Remove bold/italic
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        
        # Remove links
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        
        # Remove images
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
        
        # Remove code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'`(.+?)`', r'\1', text)
        
        return text.strip()


# Global instance
docling_service = DoclingService()



