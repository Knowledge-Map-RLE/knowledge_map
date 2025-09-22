"""Marker model for PDF to Markdown conversion (placeholder)"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from .base_model import BaseModel

logger = logging.getLogger(__name__)


class MarkerModel(BaseModel):
    """Marker model for PDF to Markdown conversion (placeholder)"""
    
    def __init__(self):
        super().__init__()
        self.name = "Marker"
        self.description = "Marker PDF to Markdown conversion (placeholder implementation)"
        self.version = "1.0.0"
        self.is_enabled = False  # Disabled by default
        self.capabilities = ["pdf_to_markdown"]
    
    async def convert(
        self,
        input_path: Path,
        output_dir: Path,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Path:
        """
        Convert PDF to Markdown using Marker (placeholder)
        
        Args:
            input_path: Path to PDF file
            output_dir: Output directory
            on_progress: Progress callback
            
        Returns:
            Path to output directory with results
        """
        raise NotImplementedError("Marker model is not implemented yet. Use Docling model instead.")


# Global instance
marker_model = MarkerModel()
