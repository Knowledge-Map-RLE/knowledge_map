"""File management service"""

import shutil
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from ..core.config import settings
from ..core.logger import get_logger
from ..core.exceptions import PDFConversionError

logger = get_logger(__name__)


class FileService:
    """Service for file operations"""
    
    def __init__(self):
        self.temp_dir = Path(settings.temp_dir)
        self.output_dir = Path(settings.output_dir)
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure required directories exist"""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directories exist: {self.temp_dir}, {self.output_dir}")
    
    def create_temp_directory(self, prefix: str = "pdf_to_md_") -> Path:
        """
        Create temporary directory
        
        Args:
            prefix: Directory name prefix
            
        Returns:
            Path to created directory
        """
        temp_path = Path(tempfile.mkdtemp(prefix=prefix, dir=self.temp_dir))
        logger.debug(f"Created temporary directory: {temp_path}")
        return temp_path
    
    def save_pdf(self, content: bytes, filename: str, temp_dir: Path) -> Path:
        """
        Save PDF content to temporary directory
        
        Args:
            content: PDF content
            filename: Original filename
            temp_dir: Temporary directory
            
        Returns:
            Path to saved PDF file
        """
        pdf_path = temp_dir / filename
        pdf_path.write_bytes(content)
        logger.debug(f"Saved PDF to: {pdf_path}")
        return pdf_path
    
    def save_markdown(
        self,
        content: str,
        doc_id: str,
        output_dir: Optional[Path] = None
    ) -> Path:
        """
        Save markdown content
        
        Args:
            content: Markdown content
            doc_id: Document ID
            output_dir: Output directory (optional)
            
        Returns:
            Path to saved markdown file
        """
        if output_dir is None:
            output_dir = self.output_dir
        
        markdown_path = output_dir / f"{doc_id}.md"
        markdown_path.write_text(content, encoding="utf-8", errors="ignore")
        logger.debug(f"Saved markdown to: {markdown_path}")
        return markdown_path
    
    def save_images(
        self,
        images: Dict[str, bytes],
        doc_id: str,
        output_dir: Optional[Path] = None
    ) -> List[Path]:
        """
        Save images
        
        Args:
            images: Dictionary mapping filename to image data
            doc_id: Document ID
            output_dir: Output directory (optional)
            
        Returns:
            List of paths to saved images
        """
        if output_dir is None:
            output_dir = self.output_dir
        
        saved_paths = []
        for filename, data in images.items():
            image_path = output_dir / filename
            image_path.write_bytes(data)
            saved_paths.append(image_path)
            logger.debug(f"Saved image to: {image_path}")
        
        return saved_paths
    
    def save_metadata(
        self,
        metadata: Dict[str, Any],
        doc_id: str,
        output_dir: Optional[Path] = None
    ) -> Path:
        """
        Save metadata
        
        Args:
            metadata: Metadata dictionary
            doc_id: Document ID
            output_dir: Output directory (optional)
            
        Returns:
            Path to saved metadata file
        """
        if output_dir is None:
            output_dir = self.output_dir
        
        import json
        metadata_path = output_dir / f"{doc_id}_metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        logger.debug(f"Saved metadata to: {metadata_path}")
        return metadata_path
    
    def cleanup_temp_directory(self, temp_dir: Path) -> None:
        """
        Clean up temporary directory
        
        Args:
            temp_dir: Temporary directory to clean up
        """
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> None:
        """
        Clean up old files from output directory
        
        Args:
            max_age_hours: Maximum age of files in hours
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_count = 0
        
        try:
            for file_path in self.output_dir.rglob("*"):
                if file_path.is_file():
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        file_path.unlink()
                        cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} old files")
        
        except Exception as e:
            logger.error(f"Failed to clean up old files: {e}")
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Get file information
        
        Args:
            file_path: Path to file
            
        Returns:
            File information dictionary
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        stat = file_path.stat()
        return {
            "path": str(file_path),
            "size": stat.st_size,
            "size_mb": stat.st_size / (1024 * 1024),
            "created": datetime.fromtimestamp(stat.st_ctime),
            "modified": datetime.fromtimestamp(stat.st_mtime),
            "extension": file_path.suffix,
            "name": file_path.name
        }
    
    def list_output_files(self, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List files in output directory
        
        Args:
            doc_id: Filter by document ID (optional)
            
        Returns:
            List of file information dictionaries
        """
        files = []
        
        try:
            for file_path in self.output_dir.rglob("*"):
                if file_path.is_file():
                    if doc_id is None or doc_id in file_path.name:
                        files.append(self.get_file_info(file_path))
        
        except Exception as e:
            logger.error(f"Failed to list output files: {e}")
        
        return files
