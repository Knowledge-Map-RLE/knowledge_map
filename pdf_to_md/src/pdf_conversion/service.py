"""PDF Conversion Service"""

import asyncio
import tempfile
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from .models import ConversionResult, ConversionProgress, ConversionStatus
from .schemas import ConvertRequest

try:
    from ..core.config import settings
    from ..core.logger import get_logger
    from ..core.exceptions import (
        PDFConversionError, 
        ModelNotFoundError, 
        ModelDisabledError,
        ConversionTimeoutError
    )
except ImportError:
    from core.config import settings
    from core.logger import get_logger
    from core.exceptions import (
        PDFConversionError, 
        ModelNotFoundError, 
        ModelDisabledError,
        ConversionTimeoutError
    )
try:
    from ..core.types import ProgressCallback
    from ..model_registry.service import ModelRegistryService
    from ..file_management.service import FileManagementService
except ImportError:
    from core.types import ProgressCallback
    from model_registry.service import ModelRegistryService
    from file_management.service import FileManagementService

logger = get_logger(__name__)

class ConversionService:
    """Service for PDF to Markdown conversion"""
    
    def __init__(self):
        self.model_registry = ModelRegistryService()
        self.file_service = FileManagementService()
        self._active_conversions: Dict[str, ConversionProgress] = {}
        self._conversion_results: Dict[str, ConversionResult] = {}
    
    async def convert_pdf(
        self,
        pdf_content: bytes,
        doc_id: Optional[str] = None,
        model_id: Optional[str] = None,
        output_format: str = "markdown",
        use_coordinate_extraction: bool = True,
        options: Optional[Dict[str, Any]] = None
    ) -> ConversionResult:
        """Convert PDF to Markdown"""
        try:
            # Generate doc_id if not provided
            if not doc_id:
                doc_id = hashlib.md5(pdf_content).hexdigest()
            
            # Use default model if not specified
            if not model_id:
                model_id = self.model_registry.get_default_model_id()
            
            # Validate model
            if not self.model_registry.is_model_available(model_id):
                raise ModelNotFoundError(f"Model {model_id} not available")
            
            # Create task ID
            task_id = f"conv_{doc_id}_{datetime.now().timestamp()}"
            
            # Initialize progress tracking
            progress = ConversionProgress(
                task_id=task_id,
                status=ConversionStatus.STARTED,
                progress=0,
                message="Starting conversion..."
            )
            self._active_conversions[task_id] = progress
            
            # Get model
            model = self.model_registry.get_model(model_id)
            
            # Save uploaded file
            temp_dir = self.file_service.create_temp_directory()
            pdf_path = self.file_service.save_pdf(pdf_content, f"{doc_id}.pdf", temp_dir)
            
            try:
                # Update progress
                progress.status = ConversionStatus.PROCESSING
                progress.progress = 25
                progress.message = "Processing PDF..."
                progress.updated_at = datetime.now()
                
                # Convert PDF
                result_content = await model.convert_pdf(pdf_path, output_format)
                
                # Update progress
                progress.progress = 75
                progress.message = "Saving result..."
                progress.updated_at = datetime.now()
                
                # Save result
                output_path = self.file_service.save_result(
                    result_content, 
                    f"{doc_id}.md", 
                    temp_dir
                )
                
                # Update progress
                progress.status = ConversionStatus.COMPLETED
                progress.progress = 100
                progress.message = "Conversion completed"
                progress.updated_at = datetime.now()
                
                # Create result
                result = ConversionResult(
                    task_id=task_id,
                    status=ConversionStatus.COMPLETED,
                    output_path=str(output_path),
                    filename=f"{doc_id}.md",
                    content=result_content,
                    created_at=datetime.now(),
                    metadata={
                        "model_id": model_id,
                        "output_format": output_format,
                        "doc_id": doc_id,
                        "file_size": len(pdf_content)
                    }
                )
                
                # Store result
                self._conversion_results[task_id] = result
                
                return result
                
            finally:
                # Cleanup temp directory
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")
                
        except Exception as e:
            logger.error(f"Conversion failed for doc_id {doc_id}: {e}")
            if task_id in self._active_conversions:
                self._active_conversions[task_id].status = ConversionStatus.FAILED
                self._active_conversions[task_id].message = str(e)
                self._active_conversions[task_id].updated_at = datetime.now()
            raise PDFConversionError(f"Conversion failed: {e}")
    
    def get_conversion_progress(self, task_id: str) -> Optional[ConversionProgress]:
        """Get conversion progress"""
        return self._active_conversions.get(task_id)
    
    def get_conversion_result(self, task_id: str) -> Optional[ConversionResult]:
        """Get conversion result"""
        return self._conversion_results.get(task_id)
    
    def get_active_conversions(self) -> List[str]:
        """Get list of active conversion task IDs"""
        return [
            task_id for task_id, progress in self._active_conversions.items()
            if progress.status in [ConversionStatus.STARTED, ConversionStatus.PROCESSING]
        ]
    
    async def cancel_conversion(self, task_id: str) -> bool:
        """Cancel active conversion"""
        if task_id in self._active_conversions:
            progress = self._active_conversions[task_id]
            if progress.status in [ConversionStatus.STARTED, ConversionStatus.PROCESSING]:
                progress.status = ConversionStatus.CANCELLED
                progress.message = "Conversion cancelled"
                progress.updated_at = datetime.now()
                logger.info(f"Cancelled conversion task {task_id}")
                return True
        return False
    
    def cleanup_old_results(self, max_age_hours: int = 24) -> int:
        """Cleanup old conversion results"""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        cleaned_count = 0
        
        # Cleanup old results
        old_results = [
            task_id for task_id, result in self._conversion_results.items()
            if result.created_at.timestamp() < cutoff_time
        ]
        
        for task_id in old_results:
            del self._conversion_results[task_id]
            cleaned_count += 1
        
        # Cleanup old progress
        old_progress = [
            task_id for task_id, progress in self._active_conversions.items()
            if progress.created_at.timestamp() < cutoff_time
        ]
        
        for task_id in old_progress:
            del self._active_conversions[task_id]
            cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old conversion records")
        
        return cleaned_count
