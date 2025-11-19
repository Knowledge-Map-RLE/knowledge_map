"""Main conversion service for PDF to Markdown"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

try:
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
    from .coordinate_extraction_service import coordinate_extraction_service
except ImportError:
    # Fallback for direct execution
    from core.config import settings
    from core.logger import get_logger
    from core.exceptions import (
        PDFConversionError,
        ModelNotFoundError,
        ModelDisabledError,
        ConversionTimeoutError
    )
    from core.types import (
        ConversionResult,
        ConversionProgress,
        ConversionStatus,
        ProgressCallback
    )
    from core.validators import validate_conversion_request
    from .model_service import ModelService
    from .file_service import FileService
    from .coordinate_extraction_service import coordinate_extraction_service

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
        use_coordinate_extraction: bool = True,
        on_progress: Optional[ProgressCallback] = None
    ) -> ConversionResult:
        """
        Convert PDF to Markdown
        
        Args:
            pdf_content: PDF file content
            doc_id: Document ID (optional)
            model_id: Model ID to use (optional)
            filename: Original filename (optional)
            use_coordinate_extraction: Use coordinate-based image extraction (default: True)
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
                default_model_id = self.model_service.get_default_model()
                logger.info(f"Default model ID from service: {default_model_id}")
                selected_model_id = model_id or default_model_id
                logger.info(f"Selected model ID: {selected_model_id}")
                model = self.model_service.get_model(selected_model_id)
                if not model:
                    raise ModelNotFoundError(f"Model {selected_model_id} not found")
                logger.info(f"Using model: {model.name} ({type(model).__name__})")
                
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
                        use_coordinate_extraction=use_coordinate_extraction,
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
        use_coordinate_extraction: bool = True,
        on_progress: Optional[ProgressCallback] = None
    ) -> ConversionResult:
        """
        Perform the actual conversion
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory
            model: Model to use for conversion
            doc_id: Document ID
            use_coordinate_extraction: Use coordinate-based image extraction
            on_progress: Progress callback
            
        Returns:
            Conversion result
        """
        try:
            markdown_content = ""
            images = {}
            metadata = {}
            s3_images = []
            extraction_method = "standard"
            
            # Try coordinate-based extraction if enabled
            if use_coordinate_extraction:
                try:
                    logger.info(f"Attempting coordinate-based extraction for doc_id={doc_id}")
                    
                    # Progress callback for coordinate extraction
                    def coord_progress(data):
                        if on_progress:
                            # Handle both dict and ConversionProgress objects
                            if hasattr(data, 'get'):
                                # It's a dict
                                on_progress({
                                    "percent": data.get('percent', 0),
                                    "phase": "coordinate_extraction",
                                    "message": data.get('message', 'Извлечение изображений по координатам')
                                })
                            else:
                                # It's a ConversionProgress object - convert to dict
                                on_progress({
                                    "percent": getattr(data, 'percent', 0),
                                    "phase": "coordinate_extraction", 
                                    "message": getattr(data, 'message', 'Извлечение изображений по координатам')
                                })
                    
                    # Perform coordinate extraction
                    coord_result = await coordinate_extraction_service.extract_images_with_s3(
                        pdf_path=pdf_path,
                        document_id=doc_id,
                        on_progress=coord_progress
                    )

                    logger.info(f"[DEBUG] Coordinate extraction result: success={coord_result.get('success')}, keys={list(coord_result.keys())}")

                    if coord_result['success']:
                        logger.info(f"Coordinate extraction successful: {coord_result['images_extracted']} images")
                        docling_raw_markdown = coord_result['markdown_content']
                        s3_images = coord_result['extracted_images']
                        extraction_method = "coordinate_based_s3"

                        # Progress: Save raw Docling markdown to S3
                        if on_progress:
                            on_progress({
                                "percent": 40,
                                "phase": "save_raw_markdown",
                                "message": "Сохранение raw Docling markdown в S3"
                            })

                        # Save raw Docling markdown to S3
                        from .s3_service import s3_service
                        raw_md_filename = f"{doc_id}_docling_raw.md"
                        raw_md_upload = await s3_service.upload_markdown(
                            markdown_content=docling_raw_markdown,
                            filename=raw_md_filename,
                            folder=f"documents/{doc_id}"
                        )

                        if not raw_md_upload['success']:
                            raise Exception(f"Failed to save raw markdown to S3: {raw_md_upload.get('error')}")

                        docling_raw_s3_key = raw_md_upload['object_key']
                        logger.info(f"Saved raw Docling markdown to S3: {docling_raw_s3_key}")

                        # Progress: Conversion complete
                        if on_progress:
                            on_progress({
                                "percent": 90,
                                "phase": "complete",
                                "message": "Конвертация завершена"
                            })

                        # Create result with S3 data (using Docling raw markdown directly, no AI formatting)
                        result = ConversionResult(
                            success=True,
                            doc_id=doc_id,
                            markdown_content=docling_raw_markdown,  # Return raw Docling markdown
                            images=images,
                            metadata=metadata
                        )
                        # Add S3 specific data
                        result.s3_images = s3_images
                        result.extraction_method = extraction_method
                        result.docling_raw_s3_key = docling_raw_s3_key
                        result.formatted_s3_key = None  # No AI formatting

                        return result
                    
                    else:
                        logger.warning(f"Coordinate extraction failed: {coord_result.get('error')}")
                        
                except Exception as e:
                    logger.warning(f"Coordinate extraction error: {e}")
            
            # Fallback to standard model conversion
            logger.info(f"Performing standard model conversion for doc_id={doc_id}")
            
            # Create output directory
            output_dir = temp_dir / "output"
            output_dir.mkdir(exist_ok=True)
            
            # Update progress
            if on_progress:
                on_progress({
                    "percent": 20,
                    "phase": "standard_conversion",
                    "message": "Стандартная конвертация PDF"
                })
            
            # Run model conversion
            result_dir = await model.convert(
                input_path=pdf_path,
                output_dir=output_dir,
                use_coordinate_extraction=False,  # Fallback mode - disable coordinate extraction
                on_progress=lambda data: on_progress({
                    **(data if hasattr(data, 'get') else {'percent': getattr(data, 'percent', 0), 'message': getattr(data, 'message', 'Обработка')}),
                    "phase": "standard_conversion"
                }) if on_progress else None
            )
            
            # Collect results
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
            
            result = ConversionResult(
                success=True,
                doc_id=doc_id,
                markdown_content=markdown_content,
                images=images,
                metadata=metadata
            )
            result.extraction_method = extraction_method
            
            return result
            
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
