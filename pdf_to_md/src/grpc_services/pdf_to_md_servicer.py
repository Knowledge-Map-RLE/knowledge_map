"""gRPC servicer for PDF to Markdown service"""

import json
import tempfile
from pathlib import Path
from typing import Dict, Any

import grpc

from ...core.logger import get_logger
from ...core.exceptions import (
    PDFConversionError, ModelNotFoundError, ModelDisabledError,
    FileSizeExceededError, UnsupportedFileTypeError
)
from ...core.types import ConversionProgress, ConversionStatus

try:
    from ...services.s3_client import get_s3_client
    from ...core.config import settings
except ImportError:
    # Fallback for testing
    get_s3_client = None
    settings = None

logger = get_logger(__name__)

# Import gRPC generated files
try:
    from . import pdf_to_md_pb2
    from . import pdf_to_md_pb2_grpc
except ImportError:
    # Fallback for when proto files are not generated
    logger.warning("gRPC proto files not found, using mock definitions")
    pdf_to_md_pb2 = None
    pdf_to_md_pb2_grpc = None


class PDFToMarkdownServicer:
    """gRPC servicer for PDF to Markdown conversion"""
    
    def __init__(self, conversion_service):
        self.conversion_service = conversion_service
    
    async def ConvertPDF(self, request, context):
        """Convert PDF to Markdown"""
        try:
            logger.info(f"gRPC ConvertPDF request: doc_id={request.doc_id}")
            
            # Validate request
            if not request.pdf_content:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("PDF content is required")
                return self._create_error_response(request.doc_id, "PDF content is required")
            
            # Perform conversion
            result = await self.conversion_service.convert_pdf(
                pdf_content=request.pdf_content,
                doc_id=request.doc_id or None,
                model_id=request.model_id or None
            )
            
            if not result.success:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(result.error_message or "Conversion failed")
                return self._create_error_response(request.doc_id, result.error_message)
            
            # Create success response
            return await self._create_success_response(result)
            
        except (FileSizeExceededError, UnsupportedFileTypeError) as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return self._create_error_response(request.doc_id, str(e))
        except (ModelNotFoundError, ModelDisabledError) as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return self._create_error_response(request.doc_id, str(e))
        except PDFConversionError as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return self._create_error_response(request.doc_id, str(e))
        except Exception as e:
            logger.error(f"Unexpected error in ConvertPDF: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal server error")
            return self._create_error_response(request.doc_id, "Internal server error")
    
    async def GetModels(self, request, context):
        """Get available models"""
        try:
            models_data = self.conversion_service.model_service.get_available_models()
            default_model = self.conversion_service.model_service.get_default_model()
            
            if pdf_to_md_pb2 is None:
                # Mock response if proto files not available
                return {"models": models_data, "default_model": default_model}
            
            # Create models dictionary
            models = {}
            for model_id, model_info in models_data.items():
                models[model_id] = pdf_to_md_pb2.ModelInfo(
                    name=model_info.name,
                    description=model_info.description,
                    enabled=(model_info.status == "enabled"),
                    default=model_info.is_default
                )
            
            return pdf_to_md_pb2.GetModelsResponse(
                models=models,
                default_model=default_model
            )
            
        except Exception as e:
            logger.error(f"Error in GetModels: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pdf_to_md_pb2.GetModelsResponse() if pdf_to_md_pb2 else {}
    
    async def SetDefaultModel(self, request, context):
        """Set default model"""
        try:
            success = self.conversion_service.model_service.set_default_model(request.model_id)
            
            if pdf_to_md_pb2 is None:
                return {"success": success, "message": f"Model {request.model_id} set as default" if success else "Failed to set default model"}
            
            return pdf_to_md_pb2.SetDefaultModelResponse(
                success=success,
                message=f"Model {request.model_id} set as default" if success else "Failed to set default model"
            )
            
        except Exception as e:
            logger.error(f"Error in SetDefaultModel: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pdf_to_md_pb2.SetDefaultModelResponse(success=False, message=str(e)) if pdf_to_md_pb2 else {"success": False, "message": str(e)}
    
    async def EnableModel(self, request, context):
        """Enable or disable model"""
        try:
            if request.enabled:
                success = self.conversion_service.model_service.enable_model(request.model_id)
                action = "enabled"
            else:
                success = self.conversion_service.model_service.disable_model(request.model_id)
                action = "disabled"
            
            if pdf_to_md_pb2 is None:
                return {"success": success, "message": f"Model {request.model_id} {action}" if success else f"Failed to {action} model"}
            
            return pdf_to_md_pb2.EnableModelResponse(
                success=success,
                message=f"Model {request.model_id} {action}" if success else f"Failed to {action} model"
            )
            
        except Exception as e:
            logger.error(f"Error in EnableModel: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pdf_to_md_pb2.EnableModelResponse(success=False, message=str(e)) if pdf_to_md_pb2 else {"success": False, "message": str(e)}
    
    async def ConvertPDFWithProgress(self, request, context):
        """Convert PDF with progress updates (streaming)"""
        try:
            logger.info(f"gRPC ConvertPDFWithProgress request: doc_id={request.doc_id}")
            
            # Validate request
            if not request.pdf_content:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("PDF content is required")
                return
            
            # Progress callback
            def on_progress(progress: ConversionProgress):
                try:
                    if pdf_to_md_pb2 is None:
                        return
                    
                    update = pdf_to_md_pb2.ProgressUpdate(
                        doc_id=progress.doc_id,
                        percent=progress.percent,
                        phase=progress.phase,
                        message=progress.message
                    )
                    context.write(update)
                except Exception as e:
                    logger.warning(f"Error sending progress update: {e}")
            
            # Perform conversion
            result = await self.conversion_service.convert_pdf(
                pdf_content=request.pdf_content,
                doc_id=request.doc_id or None,
                model_id=request.model_id or None,
                on_progress=on_progress
            )
            
            # Send final update
            if pdf_to_md_pb2:
                if result.success:
                    final_update = pdf_to_md_pb2.ProgressUpdate(
                        doc_id=result.doc_id,
                        percent=100,
                        phase="completed",
                        message="Conversion completed successfully"
                    )
                else:
                    final_update = pdf_to_md_pb2.ProgressUpdate(
                        doc_id=result.doc_id,
                        percent=0,
                        phase="failed",
                        message=result.error_message or "Conversion failed"
                    )
                context.write(final_update)
            
        except Exception as e:
            logger.error(f"Error in ConvertPDFWithProgress: {e}")
            if pdf_to_md_pb2:
                error_update = pdf_to_md_pb2.ProgressUpdate(
                    doc_id=request.doc_id or "unknown",
                    percent=0,
                    phase="failed",
                    message=f"Error: {str(e)}"
                )
                context.write(error_update)
    
    async def _create_success_response(self, result):
        """Create success response with image info"""
        # Prepare image info
        image_info_list = []
        if result.images and settings is not None and get_s3_client is not None:
            s3_client = get_s3_client()
            
            for filename, image_data in result.images.items():
                # Create S3 key
                s3_key = f"documents/{result.doc_id}/{filename}"
                
                # Determine content type
                content_type = "image/png"
                if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
                    content_type = "image/jpeg"
                elif filename.lower().endswith('.gif'):
                    content_type = "image/gif"
                elif filename.lower().endswith('.bmp'):
                    content_type = "image/bmp"
                
                # Get presigned URL
                presigned_url = None
                try:
                    presigned_url = await s3_client.get_object_url(
                        bucket_name=settings.s3_bucket_name,
                        object_key=s3_key,
                        expiration=3600
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate presigned URL for {filename}: {e}")
                
                if pdf_to_md_pb2:
                    image_info = pdf_to_md_pb2.ImageInfo(
                        filename=filename,
                        content_type=content_type,
                        s3_key=s3_key,
                        presigned_url=presigned_url or "",
                        size_bytes=len(image_data)
                    )
                    image_info_list.append(image_info)
        
        if pdf_to_md_pb2 is None:
            return {
                "success": True,
                "doc_id": result.doc_id,
                "markdown_content": result.markdown_content,
                "images": result.images,
                "metadata_json": json.dumps(result.metadata) if result.metadata else "",
                "message": "Conversion completed successfully"
            }
        
        return pdf_to_md_pb2.ConvertPDFResponse(
            success=True,
            doc_id=result.doc_id,
            markdown_content=result.markdown_content,
            images=result.images,  # Сохраняем для обратной совместимости
            image_info=image_info_list,  # Новое поле с расширенной информацией
            metadata_json=json.dumps(result.metadata) if result.metadata else "",
            message="Conversion completed successfully"
        )
    
    def _create_error_response(self, doc_id, error_message):
        """Create error response"""
        if pdf_to_md_pb2 is None:
            return {
                "success": False,
                "doc_id": doc_id or "unknown",
                "markdown_content": "",
                "images": {},
                "metadata_json": "",
                "message": error_message
            }
        
        return pdf_to_md_pb2.ConvertPDFResponse(
            success=False,
            doc_id=doc_id or "unknown",
            markdown_content="",
            images={},
            metadata_json="",
            message=error_message
        )
