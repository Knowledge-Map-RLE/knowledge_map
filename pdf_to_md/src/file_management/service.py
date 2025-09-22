"""File Management Service"""

import shutil
import tempfile
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from .models import FileInfo, FileOperation, FileOperationResult

try:
    from ..core.config import settings
    from ..core.logger import get_logger
    from ..core.exceptions import PDFConversionError
except ImportError:
    from core.config import settings
    from core.logger import get_logger
    from core.exceptions import PDFConversionError

logger = get_logger(__name__)

class FileManagementService:
    """Service for file operations"""
    
    def __init__(self):
        self.temp_dir = Path(settings.temp_dir)
        self.output_dir = Path(settings.output_dir)
        self._ensure_directories()
        self._file_registry: Dict[str, FileInfo] = {}
    
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
            content: PDF file content
            filename: Original filename
            temp_dir: Temporary directory path
            
        Returns:
            Path to saved PDF file
        """
        pdf_path = temp_dir / filename
        with open(pdf_path, "wb") as f:
            f.write(content)
        
        logger.debug(f"Saved PDF: {pdf_path}")
        return pdf_path
    
    def save_result(self, content: str, filename: str, temp_dir: Path) -> Path:
        """
        Save conversion result to temporary directory
        
        Args:
            content: Result content
            filename: Output filename
            temp_dir: Temporary directory path
            
        Returns:
            Path to saved result file
        """
        result_path = temp_dir / filename
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.debug(f"Saved result: {result_path}")
        return result_path
    
    def save_to_output(self, content: str, filename: str, subdir: Optional[str] = None) -> Path:
        """
        Save file to output directory
        
        Args:
            content: File content
            filename: Output filename
            subdir: Optional subdirectory
            
        Returns:
            Path to saved file
        """
        if subdir:
            output_path = self.output_dir / subdir
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            output_path = self.output_dir
        
        file_path = output_path / filename
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Register file
        file_id = hashlib.md5(content.encode()).hexdigest()
        file_info = FileInfo(
            file_id=file_id,
            filename=filename,
            file_path=str(file_path),
            file_size=len(content.encode()),
            content_type="text/markdown",
            created_at=datetime.now(),
            metadata={"subdir": subdir}
        )
        self._file_registry[file_id] = file_info
        
        logger.info(f"Saved to output: {file_path}")
        return file_path
    
    def get_file_info(self, file_id: str) -> Optional[FileInfo]:
        """Get file information by ID"""
        return self._file_registry.get(file_id)
    
    def list_files(self, subdir: Optional[str] = None) -> List[FileInfo]:
        """List all files in registry"""
        if subdir:
            return [
                file_info for file_info in self._file_registry.values()
                if file_info.metadata and file_info.metadata.get("subdir") == subdir
            ]
        return list(self._file_registry.values())
    
    def delete_file(self, file_id: str) -> FileOperationResult:
        """Delete file by ID"""
        file_info = self._file_registry.get(file_id)
        if not file_info:
            return FileOperationResult(
                operation=FileOperation.DELETE,
                file_id=file_id,
                success=False,
                message="File not found"
            )
        
        try:
            file_path = Path(file_info.file_path)
            if file_path.exists():
                file_path.unlink()
            
            del self._file_registry[file_id]
            
            return FileOperationResult(
                operation=FileOperation.DELETE,
                file_id=file_id,
                success=True,
                message="File deleted successfully",
                details={"filename": file_info.filename, "file_size": file_info.file_size}
            )
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return FileOperationResult(
                operation=FileOperation.DELETE,
                file_id=file_id,
                success=False,
                message=f"Failed to delete file: {e}"
            )
    
    def cleanup_old_files(self, max_age_hours: int = 24, dry_run: bool = False) -> FileOperationResult:
        """Cleanup old files"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        deleted_count = 0
        freed_space = 0
        deleted_files = []
        
        old_files = [
            (file_id, file_info) for file_id, file_info in self._file_registry.items()
            if file_info.created_at < cutoff_time
        ]
        
        for file_id, file_info in old_files:
            if not dry_run:
                result = self.delete_file(file_id)
                if result.success:
                    deleted_count += 1
                    freed_space += file_info.file_size
                    deleted_files.append(file_info.filename)
            else:
                deleted_count += 1
                freed_space += file_info.file_size
                deleted_files.append(file_info.filename)
        
        return FileOperationResult(
            operation=FileOperation.CLEANUP,
            file_id="",
            success=True,
            message=f"Cleanup completed: {deleted_count} files processed",
            details={
                "deleted_count": deleted_count,
                "freed_space": freed_space,
                "deleted_files": deleted_files,
                "dry_run": dry_run
            }
        )
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        total_files = len(self._file_registry)
        total_size = sum(file_info.file_size for file_info in self._file_registry.values())
        
        # Count files by type
        file_types: Dict[str, int] = {}
        for file_info in self._file_registry.values():
            ext = Path(file_info.filename).suffix.lower()
            file_types[ext] = file_types.get(ext, 0) + 1
        
        return {
            "total_files": total_files,
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_types": file_types,
            "temp_dir": str(self.temp_dir),
            "output_dir": str(self.output_dir)
        }
