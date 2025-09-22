"""Docling model for PDF to Markdown conversion"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from .base_model import BaseModel

logger = logging.getLogger(__name__)


class DoclingModel(BaseModel):
    """Docling model for PDF to Markdown conversion"""
    
    def __init__(self):
        super().__init__()
        self.name = "Docling"
        self.description = "Docling PDF to Markdown conversion with advanced document understanding"
        self.version = "2.0.0"
        self.is_enabled = True
        self.capabilities = ["pdf_to_markdown", "document_structure", "advanced_layout"]
    
    async def convert(
        self,
        input_path: Path,
        output_dir: Path,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Path:
        """
        Convert PDF to Markdown using Docling
        
        Args:
            input_path: Path to PDF file
            output_dir: Output directory
            on_progress: Progress callback
            
        Returns:
            Path to output directory with results
        """
        try:
            from docling.document_converter import DocumentConverter
            from docling.datamodel.document import DocumentConversionInput
            logger.info("✅ Docling imported successfully")
        except ImportError as e:
            logger.error(f"❌ Docling not available: {e}")
            raise RuntimeError(f"Docling not available: {e}")

        # Check if input file exists
        if not input_path.exists():
            raise FileNotFoundError(f"Input PDF file not found: {input_path}")
        
        logger.info(f"✅ Input file exists: {input_path}")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Progress callback
        if on_progress:
            on_progress({
                'percent': 10,
                'phase': 'initialization',
                'message': 'Initializing Docling converter'
            })

        # Initialize converter and convert the document
        converter = DocumentConverter()
        logger.info("✅ DocumentConverter initialized")
        
        if on_progress:
            on_progress({
                'percent': 20,
                'phase': 'preparing',
                'message': 'Preparing document for conversion'
            })
        
        # Create DocumentConversionInput using from_paths method
        input_doc = DocumentConversionInput.from_paths([input_path])
        logger.info("✅ DocumentConversionInput created")
        
        if on_progress:
            on_progress({
                'percent': 30,
                'phase': 'converting',
                'message': 'Converting PDF to Markdown'
            })
        
        # Convert the document
        result = converter.convert(input_doc)
        logger.info("✅ Conversion completed")
        
        if on_progress:
            on_progress({
                'percent': 80,
                'phase': 'processing',
                'message': 'Processing conversion results'
            })
        
        # Get the first result from the generator
        first_result = next(result)
        logger.info("✅ Got conversion result")
        
        # Export to markdown using render_as_markdown method
        md_content = first_result.render_as_markdown()
        if not md_content or not str(md_content).strip():
            raise RuntimeError("Docling did not produce Markdown output")
        
        logger.info("✅ Markdown export successful")
        
        # Save markdown to output directory
        output_file = output_dir / f"{input_path.stem}.md"
        output_file.write_text(str(md_content), encoding="utf-8")
        
        logger.info(f"✅ Markdown saved to: {output_file}")
        logger.info(f"✅ Content length: {len(md_content)} characters")
        
        if on_progress:
            on_progress({
                'percent': 100,
                'phase': 'completed',
                'message': 'Conversion completed successfully'
            })
        
        return output_dir


# Global instance
docling_model = DoclingModel()
