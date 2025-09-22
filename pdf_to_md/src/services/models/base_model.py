"""Base model interface for PDF to Markdown conversion"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List


class BaseModel(ABC):
    """Base class for PDF to Markdown conversion models"""
    
    def __init__(self):
        self.name: str = ""
        self.description: str = ""
        self.version: str = "1.0.0"
        self.is_enabled: bool = True
        self.capabilities: List[str] = []
    
    @abstractmethod
    async def convert(
        self,
        input_path: Path,
        output_dir: Path,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Path:
        """
        Convert PDF to Markdown
        
        Args:
            input_path: Path to PDF file
            output_dir: Output directory
            on_progress: Progress callback
            
        Returns:
            Path to output directory with results
        """
        pass
