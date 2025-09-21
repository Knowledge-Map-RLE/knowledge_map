"""Main conversion service for PDF to Markdown"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from ..core.config import settings
from ..core.logger import get_logger
from ..core.exceptions import (
    PDFConversionError,
    ModelNotFoundError,
    ModelDisabledError,
    ConversionTimeoutError
)
from ..core.types import (
    ConversionResult,
    ConversionProgress,
    ConversionStatus,
    ProgressCallback
)
from ..core.validators import validate_conversion_request
from .model_service import ModelService
from .file_service import FileService

logger = get_logger(__name__)


class ConversionService:
    """Main service for PDF to Markdown conversion"""
    
    def __init__(self):
        self.model_service = ModelService()
        self.file_service = FileService()
        self._active_conversions: Dict[str, asyncio.Task] = {}
    
    async def convert_pdf(
        self,
        pdf_content: bytes,
        doc_id: Optional[str] = None,
        model_id: Optional[str] = None,
        filename: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None
    ) -> ConversionResult:
        """
        Convert PDF to Markdown
        
        Args:
            pdf_content: PDF file content
            doc_id: Document ID (optional)
            model_id: Model ID to use (optional)
            filename: Original filename (optional)
            on_progress: Progress callback (optional)
            
        Returns:
            Conversion result
            
        Raises:
            PDFConversionError: If conversion fails
            ModelNotFoundError: If model is not found
            ModelDisabledError: If model is disabled
        """
        start_time = datetime.now()
        
        try:
            # Validate request
            request = validate_conversion_request(
                pdf_content=pdf_content,
                doc_id=doc_id,
                model_id=model_id,
                filename=filename
            )
            
            # Generate doc_id if not provided
            if not request.doc_id:
                request.doc_id = request.generate_doc_id()
            
            doc_id = request.doc_id
            logger.info(f"Starting conversion for doc_id={doc_id}")
            
            # Check if conversion is already in progress
            if doc_id in self._active_conversions:
                raise PDFConversionError(f"Conversion for {doc_id} is already in progress")
            
            # Create temporary directory
            temp_dir = Path(tempfile.mkdtemp(prefix=f"pdf_to_md_{doc_id}_"))
            
            try:
                # Save PDF to temporary directory
                pdf_path = temp_dir / f"{doc_id}.pdf"
                pdf_path.write_bytes(pdf_content)
                
                # Get model
                model = self.model_service.get_model(model_id or settings.default_model)
                if not model:
                    raise ModelNotFoundError(f"Model {model_id} not found")
                
                if not model.is_enabled:
                    raise ModelDisabledError(f"Model {model_id} is disabled")
                
                # Create progress callback wrapper
                def progress_wrapper(progress_data: Dict[str, Any]) -> None:
                    if on_progress:
                        progress = ConversionProgress(
                            doc_id=doc_id,
                            status=ConversionStatus.PROCESSING,
                            percent=progress_data.get('percent', 0),
                            phase=progress_data.get('phase', 'processing'),
                            message=progress_data.get('message', ''),
                            pages_processed=progress_data.get('pages_processed'),
                            total_pages=progress_data.get('total_pages'),
                            processing_time=progress_data.get('processing_time'),
                            throughput=progress_data.get('throughput')
                        )
                        on_progress(progress)
                
                # Start conversion task
                conversion_task = asyncio.create_task(
                    self._perform_conversion(
                        pdf_path=pdf_path,
                        temp_dir=temp_dir,
                        model=model,
                        doc_id=doc_id,
                        on_progress=progress_wrapper
                    )
                )
                
                # Track active conversion
                self._active_conversions[doc_id] = conversion_task
                
                try:
                    # Wait for conversion with timeout
                    result = await asyncio.wait_for(
                        conversion_task,
                        timeout=settings.conversion_timeout_seconds
                    )
                    
                    # Calculate processing time
                    processing_time = (datetime.now() - start_time).total_seconds()
                    result.processing_time = processing_time
                    
                    logger.info(f"Conversion completed for doc_id={doc_id} in {processing_time:.2f}s")
                    return result
                    
                except asyncio.TimeoutError:
                    conversion_task.cancel()
                    raise ConversionTimeoutError(
                        f"Conversion timeout after {settings.conversion_timeout_seconds} seconds"
                    )
                finally:
                    # Remove from active conversions
                    self._active_conversions.pop(doc_id, None)
                
            finally:
                # Clean up temporary directory
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")
        
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Conversion failed for doc_id={doc_id}: {e}")
            
            return ConversionResult(
                success=False,
                doc_id=doc_id or "unknown",
                error_message=str(e),
                processing_time=processing_time
            )
    
    async def _perform_conversion(
        self,
        pdf_path: Path,
        temp_dir: Path,
        model: Any,
        doc_id: str,
        on_progress: Optional[ProgressCallback] = None
    ) -> ConversionResult:
        """
        Perform the actual conversion
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory
            model: Model to use for conversion
            doc_id: Document ID
            on_progress: Progress callback
            
        Returns:
            Conversion result
        """
        try:
            # Create output directory
            output_dir = temp_dir / "output"
            output_dir.mkdir(exist_ok=True)
            
            # Run model conversion
            result_dir = await model.convert(
                input_path=pdf_path,
                output_dir=output_dir,
                on_progress=on_progress
            )
            
            # Collect results
            markdown_content = ""
            images = {}
            metadata = {}
            
            # Read markdown file
            markdown_files = list(result_dir.glob("*.md"))
            if markdown_files:
                markdown_content = markdown_files[0].read_text(encoding="utf-8", errors="ignore")
            
            # Collect images
            image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp"]
            for ext in image_extensions:
                for img_file in result_dir.glob(ext):
                    images[img_file.name] = img_file.read_bytes()
            
            # Read metadata if available
            metadata_files = list(result_dir.glob("*.json"))
            if metadata_files:
                import json
                try:
                    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"Failed to read metadata: {e}")
            
            return ConversionResult(
                success=True,
                doc_id=doc_id,
                markdown_content=markdown_content,
                images=images,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Model conversion failed for doc_id={doc_id}: {e}")
            return ConversionResult(
                success=False,
                doc_id=doc_id,
                error_message=str(e)
            )
    
    async def cancel_conversion(self, doc_id: str) -> bool:
        """
        Cancel active conversion
        
        Args:
            doc_id: Document ID to cancel
            
        Returns:
            True if conversion was cancelled, False if not found
        """
        if doc_id in self._active_conversions:
            task = self._active_conversions[doc_id]
            task.cancel()
            del self._active_conversions[doc_id]
            logger.info(f"Cancelled conversion for doc_id={doc_id}")
            return True
        
        return False
    
    def get_active_conversions(self) -> Dict[str, str]:
        """
        Get list of active conversions
        
        Returns:
            Dictionary mapping doc_id to status
        """
        return {
            doc_id: "processing" for doc_id in self._active_conversions.keys()
        }
    
    async def get_conversion_status(self, doc_id: str) -> Optional[str]:
        """
        Get conversion status for a document
        
        Args:
            doc_id: Document ID
            
        Returns:
            Status string or None if not found
        """
        if doc_id in self._active_conversions:
            task = self._active_conversions[doc_id]
            if task.done():
                if task.cancelled():
                    return "cancelled"
                elif task.exception():
                    return "failed"
                else:
                    return "completed"
            else:
                return "processing"
        
        return None
