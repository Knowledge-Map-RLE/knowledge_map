"""Docling model for PDF to Markdown conversion"""

import logging
import io
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List, Tuple
# Coordinate-based approach: Docling OCR + PyMuPDF for precise image extraction
try:
    import fitz  # PyMuPDF - only for coordinate-based extraction
except ImportError:
    fitz = None

from .base_model import BaseModel

try:
    from ..coordinate_extraction_service import coordinate_extraction_service
    from ..s3_client import get_s3_client
    from ...core.config import settings
except ImportError:
    try:
        from ...services.s3_client import get_s3_client
        from ...core.config import settings
    except ImportError:
        # Fallback for testing
        get_s3_client = None
        settings = None

logger = logging.getLogger(__name__)


class DoclingModel(BaseModel):
    """Docling model for PDF to Markdown conversion"""
    
    def __init__(self):
        super().__init__()
        self.name = "Docling"
        self.description = "Docling PDF to Markdown conversion with advanced document understanding and image extraction"
        self.version = "2.1.0"
        self.is_enabled = True
        self.capabilities = ["pdf_to_markdown", "document_structure", "advanced_layout", "image_extraction", "s3_upload"]
        self.s3_client = get_s3_client() if get_s3_client is not None else None
    
    async def convert(
        self,
        input_path: Path,
        output_dir: Path,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        use_coordinate_extraction: bool = True
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

        # Initialize converter with configuration for image extraction
        # This may fail with SSL error if models need to be downloaded from HuggingFace
        converter = None
        try:
            converter = self._create_optimized_converter()
            logger.info("✅ DocumentConverter initialized with optimized image extraction")
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Failed to create optimized converter: {e}")

            # Check if it's an SSL/network error
            if 'SSL' in error_msg or 'huggingface' in error_msg.lower() or 'connection' in error_msg.lower():
                logger.error(f"❌ Failed to download Docling model from HuggingFace: {error_msg}")
                logger.error("Please ensure internet connection is available or download models manually")
                raise RuntimeError(
                    "Docling model download failed (SSL/network error). "
                    "Please check internet connection or download models manually. "
                    f"Error: {error_msg}"
                )

            # For other errors, try default converter
            try:
                converter = DocumentConverter()
                logger.info("✅ DocumentConverter initialized with default settings")
            except Exception as e2:
                error_msg2 = str(e2)
                if 'SSL' in error_msg2 or 'huggingface' in error_msg2.lower() or 'connection' in error_msg2.lower():
                    logger.error(f"❌ Failed to download Docling model with default settings: {error_msg2}")
                    raise RuntimeError(
                        "Docling model download failed (SSL/network error). "
                        "Please check internet connection or download models manually. "
                        f"Error: {error_msg2}"
                    )
                raise
        
        if on_progress:
            on_progress({
                'percent': 20,
                'phase': 'preparing',
                'message': 'Preparing document for conversion'
            })

        # NEW: Try coordinate-based extraction first (ALWAYS enabled by default)
        if use_coordinate_extraction:
            try:
                logger.info(f"🎯 Attempting coordinate-based extraction for: {input_path.name}")
                
                if on_progress:
                    on_progress({
                        'percent': 25,
                        'phase': 'coordinate_extraction',
                        'message': 'Извлечение изображений по координатам'
                    })
                
                # Generate document ID from input path
                document_id = input_path.stem
                
                # Use our coordinate extraction service
                coord_result = await coordinate_extraction_service.extract_images_with_s3(
                    pdf_path=input_path,
                    document_id=document_id,
                    on_progress=lambda data: on_progress({
                        "percent": max(25, min(80, data.get('percent', 25))),
                        "phase": "coordinate_extraction",
                        "message": data.get('message', 'Координатное извлечение')
                    }) if on_progress else None
                )
                
                if coord_result['success']:
                    logger.info(f"✅ Coordinate extraction successful: {coord_result['images_extracted']} images")
                    
                    # Save markdown to output directory
                    markdown_path = output_dir / f"{input_path.stem}.md"
                    markdown_path.write_text(coord_result['markdown_content'], encoding='utf-8')
                    
                    # Create fake images directory for compatibility with old code
                    images_dir = output_dir / "images"
                    images_dir.mkdir(exist_ok=True)
                    
                    # Save S3 image info for compatibility
                    s3_images_info = output_dir / "s3_images.json"
                    import json
                    s3_images_info.write_text(json.dumps(coord_result['extracted_images']), encoding='utf-8')
                    
                    logger.info(f"✅ Coordinate-based conversion completed, saved to: {output_dir}")
                    
                    if on_progress:
                        on_progress({
                            'percent': 100,
                            'phase': 'completed',
                            'message': f'Координатное извлечение завершено ({coord_result["images_extracted"]} изображений)'
                        })
                    
                    # Return ConversionResult with markdown and S3 images
                    from ..core.types import ConversionResult
                    return ConversionResult(
                        success=True,
                        model_name="docling_coordinate_s3",
                        doc_id=document_id,
                        markdown=coord_result['markdown_content'],
                        images={},  # Empty since images are in S3
                        s3_images=coord_result['extracted_images'],
                        extraction_method="coordinate_based_s3",
                        processing_time=None,
                        model_info={"coordinate_extraction": True, "s3_storage": True},
                        output_path=str(output_dir)
                    )
                    
                else:
                    logger.warning(f"⚠️ Coordinate extraction failed: {coord_result.get('error')}")
                    
            except Exception as e:
                logger.warning(f"⚠️ Coordinate extraction error: {e}")
        
        # FALLBACK: Continue with standard Docling conversion
        logger.info("🔄 Falling back to standard Docling conversion")

        if on_progress:
            on_progress({
                'percent': 30,
                'phase': 'converting',
                'message': 'Converting PDF to Markdown'
            })

        # Convert the document using new API (Docling 2.x)
        # Simply pass the file path - no need for DocumentConversionInput
        # Use the already initialized converter (no re-initialization needed)
        if converter is None:
            raise RuntimeError("Converter not initialized. Cannot proceed with fallback conversion.")

        result = converter.convert(str(input_path))
        logger.info("✅ Conversion completed")
        
        if on_progress:
            on_progress({
                'percent': 80,
                'phase': 'processing',
                'message': 'Processing conversion results'
            })
        
        # Result is now a ConversionResult object with document and pages
        first_result = result
        logger.info(f"✅ Got conversion result: {type(result)}")
        
        # Debug the result structure
        if hasattr(result, 'document'):
            logger.info(f"Document type: {type(result.document)}")
        if hasattr(result, 'pages'):
            logger.info(f"Found {len(result.pages)} pages")
        
        if on_progress:
            on_progress({
                'percent': 50,
                'phase': 'extracting_images',
                'message': 'Extracting images from document'
            })
        
        # Coordinate-based image extraction (Docling coordinates + PyMuPDF precision)
        doc_id = input_path.stem
        image_files = await self._coordinate_based_image_extraction(input_path, first_result, output_dir, doc_id, on_progress)
        
        if on_progress:
            on_progress({
                'percent': 70,
                'phase': 'rendering_markdown',
                'message': 'Rendering Markdown content'
            })
        
        # Export to markdown using Docling 2.x API
        try:
            # In Docling 2.x, the document is in result.document
            if hasattr(first_result, 'document') and first_result.document:
                document = first_result.document
                
                # Try different markdown export methods
                if hasattr(document, 'export_to_markdown'):
                    md_content = document.export_to_markdown()
                elif hasattr(document, 'to_markdown'):
                    md_content = document.to_markdown()
                elif hasattr(document, 'markdown'):
                    md_content = document.markdown
                elif hasattr(document, 'render_as_markdown'):
                    md_content = document.render_as_markdown()
                else:
                    # Fallback: convert to string
                    md_content = str(document)
                    
                logger.info(f"✅ Exported markdown: {len(str(md_content))} characters")
                
            else:
                # Direct export from result
                if hasattr(first_result, 'export_to_markdown'):
                    md_content = first_result.export_to_markdown()
                elif hasattr(first_result, 'to_markdown'):
                    md_content = first_result.to_markdown()
                else:
                    md_content = str(first_result)
            
            if not md_content or not str(md_content).strip():
                raise RuntimeError("Docling did not produce Markdown output")
                
        except Exception as e:
            logger.error(f"Failed to export markdown: {e}")
            raise RuntimeError(f"Failed to export markdown: {e}")
        
        logger.info("✅ Markdown export successful")
        
        # Update image references in markdown content
        if image_files:
            md_content = self._update_image_references(str(md_content), image_files, doc_id)
        
        # Save markdown to output directory
        output_file = output_dir / f"{input_path.stem}.md"
        output_file.write_text(str(md_content), encoding="utf-8")
        
        logger.info(f"✅ Markdown saved to: {output_file}")
        logger.info(f"✅ Content length: {len(md_content)} characters")
        logger.info(f"✅ Images extracted: {len(image_files)}")
        
        if on_progress:
            on_progress({
                'percent': 100,
                'phase': 'completed',
                'message': f'Conversion completed successfully with {len(image_files)} images'
            })
        
        return output_dir
    
    def _create_optimized_converter(self):
        """Create DocumentConverter with optimized settings for image extraction"""
        
        # Method 1: Try the best available pipeline - standard_pdf_pipeline
        try:
            from docling.pipeline import standard_pdf_pipeline
            
            # Use the standard PDF pipeline for best results
            converter = DocumentConverter(
                pipeline_configs={
                    ".pdf": standard_pdf_pipeline()
                }
            )
            logger.info("✅ Created DocumentConverter with standard_pdf_pipeline")
            return converter
                
        except Exception as e:
            logger.warning(f"Standard PDF pipeline not available: {e}")
            
        # Method 1.1: Try alternative import
        try:
            from docling import pipeline
            
            if hasattr(pipeline, 'standard_pdf_pipeline'):
                converter = DocumentConverter(
                    pipeline_configs={
                        ".pdf": pipeline.standard_pdf_pipeline()
                    }
                )
                logger.info("✅ Created DocumentConverter with standard_pdf_pipeline (alt)")
                return converter
                
        except Exception as e:
            logger.warning(f"Standard PDF pipeline (alt) not available: {e}")
        
        # Method 2: Try with optimized pipeline options for Docling 2.x
        try:
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat
            
            # Create options with ALL image extraction features enabled for Docling 2.x
            pipeline_options = PdfPipelineOptions(
                # CRITICAL: Enable image generation and extraction
                generate_picture_images=True,
                generate_page_images=True, 
                generate_table_images=True,
                images_scale=1.0,  # Full resolution
                
                # Enable picture processing
                do_picture_classification=True,
                do_picture_description=True,
                
                # Enable all relevant processing
                do_ocr=True,
                do_table_structure=True,
                do_formula_enrichment=True,
                do_code_enrichment=True,
            )
            
            # Create converter with explicit format options
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: pipeline_options,
                }
            )
            
            logger.info("✅ Created DocumentConverter with Docling 2.x optimized pipeline options")
            logger.info(f"Pipeline options: generate_picture_images={pipeline_options.generate_picture_images}")
            return converter
            
        except ImportError as e:
            logger.warning(f"Pipeline options not available: {e}")
            
        except Exception as e:
            logger.warning(f"Failed to create converter with pipeline options: {e}")
        
        # Method 3: Try assemble_options
        try:
            converter = DocumentConverter()
            
            # Check if we can modify assemble_options
            if hasattr(converter, 'assemble_options'):
                options = converter.assemble_options
                logger.info(f"Assemble options available: {dir(options)}")
                
                # Try to enable image-related options
                image_attrs = [attr for attr in dir(options) if 'image' in attr.lower() or 'picture' in attr.lower()]
                for attr in image_attrs:
                    try:
                        if not attr.startswith('_'):
                            setattr(options, attr, True)
                            logger.info(f"Set assemble option {attr} = True")
                    except Exception:
                        pass
            
            logger.info("Created DocumentConverter with modified assemble options")
            return converter
            
        except Exception as e:
            logger.warning(f"Failed to modify assemble options: {e}")
        
        # Method 4: Default converter
        logger.info("Using default DocumentConverter")
        return DocumentConverter()
    
    async def _docling_ocr_image_extraction(
        self,
        document_result,
        output_dir: Path,
        doc_id: str,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> List[Tuple[str, str]]:
        """
        Pure Docling OCR image extraction - primary method
        """
        image_files = []
        
        try:
            logger.info("Using pure Docling OCR for image extraction")
            
            if not hasattr(document_result, 'document') or not document_result.document:
                logger.warning("No document found in conversion result")
                return image_files
            
            document = document_result.document
            
            # Check for pictures in document
            if hasattr(document, 'pictures') and document.pictures:
                logger.info(f"Found {len(document.pictures)} pictures in Docling document")
                
                for i, picture in enumerate(document.pictures):
                    try:
                        logger.info(f"\n=== Processing Docling picture {i} ===")
                        
                        # Try multiple methods to extract image
                        image_obj = None
                        extraction_method = None
                        
                        # Method 1: get_image with document
                        if hasattr(picture, 'get_image'):
                            try:
                                image_obj = picture.get_image(document)
                                if image_obj and hasattr(image_obj, 'save'):
                                    extraction_method = "get_image(document)"
                                    logger.info(f"✅ Got image via {extraction_method}")
                            except Exception as e:
                                logger.debug(f"get_image(document) failed: {e}")
                        
                        # Method 2: get_image with result
                        if not image_obj and hasattr(picture, 'get_image'):
                            try:
                                image_obj = picture.get_image(document_result)
                                if image_obj and hasattr(image_obj, 'save'):
                                    extraction_method = "get_image(result)"
                                    logger.info(f"✅ Got image via {extraction_method}")
                            except Exception as e:
                                logger.debug(f"get_image(result) failed: {e}")
                        
                        # Method 3: Direct image attribute
                        if not image_obj and hasattr(picture, 'image'):
                            image_obj = picture.image
                            if image_obj and hasattr(image_obj, 'save'):
                                extraction_method = "direct_attribute"
                                logger.info(f"✅ Got image via {extraction_method}")
                        
                        # Method 4: Check model_dump for image data
                        if not image_obj:
                            try:
                                picture_data = picture.model_dump()
                                if 'image' in picture_data and picture_data['image'] is not None:
                                    # Try to convert to PIL Image
                                    image_data = picture_data['image']
                                    if isinstance(image_data, bytes):
                                        from PIL import Image
                                        image_obj = Image.open(io.BytesIO(image_data))
                                        extraction_method = "model_dump_bytes"
                                        logger.info(f"✅ Got image via {extraction_method}")
                            except Exception as e:
                                logger.debug(f"model_dump extraction failed: {e}")
                        
                        # Save image if extracted
                        if image_obj and hasattr(image_obj, 'save'):
                            # Generate filename
                            original_ref = f"docling_image_{i}"
                            filename = f"{original_ref}_{uuid.uuid4().hex[:8]}.png"
                            local_path = output_dir / filename
                            
                            # Save locally
                            image_obj.save(local_path)
                            
                            if local_path.exists():
                                size = local_path.stat().st_size
                                logger.info(f"  ✅ Saved locally: {filename} ({size} bytes) via {extraction_method}")
                                
                                # Save to S3 if available
                                try:
                                    s3_client = get_s3_client()
                                    if s3_client and settings:
                                        s3_key = f"documents/{doc_id}/images/{filename}"
                                        
                                        # Convert to bytes for S3
                                        img_bytes = io.BytesIO()
                                        image_obj.save(img_bytes, format='PNG')
                                        img_bytes.seek(0)
                                        
                                        await s3_client.upload_file(
                                            img_bytes,
                                            settings.s3_bucket_name,
                                            s3_key,
                                            content_type="image/png"
                                        )
                                        
                                        logger.info(f"  ✅ Saved to S3: {s3_key}")
                                    else:
                                        logger.info(f"  📁 Saved locally only (S3 not configured)")
                                except Exception as s3_error:
                                    logger.warning(f"  ⚠️ S3 save failed: {s3_error}")
                                
                                image_files.append((original_ref, filename))
                                
                                # Progress callback
                                if on_progress:
                                    on_progress({
                                        "type": "image_extracted",
                                        "filename": filename,
                                        "method": extraction_method,
                                        "size": size
                                    })
                        else:
                            logger.warning(f"Could not extract image {i} - no valid image object found")
                            
                            # Log available attributes for debugging
                            picture_attrs = [attr for attr in dir(picture) if not attr.startswith('_')]
                            logger.debug(f"Picture {i} attributes: {picture_attrs}")
                            
                    except Exception as e:
                        logger.error(f"Error processing Docling picture {i}: {e}")
                        continue
            else:
                logger.info("No pictures found in Docling document")
            
            # Also check pages for additional images
            if hasattr(document_result, 'pages') and document_result.pages:
                logger.info(f"Checking {len(document_result.pages)} pages for additional images")
                
                for page_idx, page in enumerate(document_result.pages):
                    if hasattr(page, 'get_image'):
                        try:
                            page_image = page.get_image()
                            if page_image and hasattr(page_image, 'save'):
                                filename = f"docling_page_{page_idx}_{uuid.uuid4().hex[:8]}.png"
                                local_path = output_dir / filename
                                
                                page_image.save(local_path)
                                
                                if local_path.exists():
                                    size = local_path.stat().st_size
                                    logger.info(f"✅ Page image: {filename} ({size} bytes)")
                                    
                                    image_files.append((f"page_{page_idx}", filename))
                        except Exception as e:
                            logger.debug(f"Page {page_idx} image extraction failed: {e}")
            
            logger.info(f"✅ Docling OCR extracted {len(image_files)} images total")
            return image_files
            
        except Exception as e:
            logger.error(f"Docling OCR image extraction failed: {e}")
            return image_files

    def _analyze_docling_result(self, document_result) -> Dict[str, Any]:
        """
        Analyze Docling result to determine processing strategy
        Pure Docling approach - no external dependencies
        """
        try:
            if not hasattr(document_result, 'document') or not document_result.document:
                logger.warning("No document in result for analysis")
                return {
                    "pdf_type": "unknown",
                    "recommended_strategy": "docling_ocr_primary"
                }
            
            document = document_result.document
            
            # Analyze text content
            try:
                markdown_content = document.export_to_markdown()
                text_length = len(markdown_content.strip())
            except Exception as e:
                logger.debug(f"Markdown export for analysis failed: {e}")
                text_length = 0
            
            # Count pages if available
            total_pages = len(document_result.pages) if hasattr(document_result, 'pages') else 1
            
            # Count images
            total_images = 0
            if hasattr(document, 'pictures') and document.pictures:
                total_images = len(document.pictures)
            
            # Simple heuristic for PDF type
            if text_length > 1000:
                pdf_type = "text_based"
            elif text_length < 200:
                pdf_type = "image_based"
            else:
                pdf_type = "hybrid"
            
            return {
                "pdf_type": pdf_type,
                "total_text_length": text_length,
                "total_images": total_images,
                "total_pages": total_pages,
                "recommended_strategy": "docling_ocr_primary",  # Always use Docling OCR
                "analysis_method": "docling_based"
            }
            
        except Exception as e:
            logger.error(f"Docling result analysis failed: {e}")
            return {
                "pdf_type": "unknown",
                "recommended_strategy": "docling_ocr_primary"
            }
    
    async def _coordinate_based_image_extraction(
        self,
        input_path: Path,
        document_result,
        output_dir: Path,
        doc_id: str,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> List[Tuple[str, str]]:
        """
        Coordinate-based image extraction: Docling coordinates + PyMuPDF precision
        """
        image_files = []
        
        try:
            import fitz  # PyMuPDF for precise extraction
            from PIL import Image
            
            logger.info("Using coordinate-based extraction: Docling + PyMuPDF")
            
            # Step 1: Extract coordinates from Docling result
            coordinates = self._extract_coordinates_from_docling(document_result)
            logger.info(f"Found {len(coordinates)} image coordinates from Docling")
            
            if not coordinates:
                logger.warning("No coordinates found, falling back to pure Docling")
                return await self._docling_ocr_image_extraction(document_result, output_dir, doc_id, on_progress)
            
            # Step 2: Extract images using PyMuPDF with precise coordinates
            doc = fitz.open(str(input_path))
            
            for coord_info in coordinates:
                try:
                    page_index = coord_info["page_index"]
                    page = doc.load_page(page_index)
                    page_rect = page.rect
                    page_height = page_rect.height
                    
                    # Convert Docling coordinates (BOTTOMLEFT) to PyMuPDF coordinates (TOPLEFT)
                    bbox = coord_info["bbox"]
                    left = bbox["left"]
                    right = bbox["right"]
                    top = page_height - bbox["top"]
                    bottom = page_height - bbox["bottom"]
                    
                    # Create extraction rectangle
                    extract_rect = fitz.Rect(left, top, right, bottom)
                    
                    # Extract image with high quality (2x scale)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=extract_rect)
                    
                    if pix.width > 0 and pix.height > 0:
                        # Convert to PIL Image
                        img_data = pix.tobytes("png")
                        pil_image = Image.open(io.BytesIO(img_data))
                        
                        # Generate filename
                        original_ref = f"coord_pic_{coord_info['picture_index']}"
                        filename = f"{original_ref}_{uuid.uuid4().hex[:8]}.png"
                        local_path = output_dir / filename
                        
                        # Save locally
                        pil_image.save(local_path)
                        
                        if local_path.exists():
                            size = local_path.stat().st_size
                            logger.info(f"✅ Coordinate extraction: {filename} ({size} bytes, {pil_image.size})")
                            
                            # Save to S3 if available
                            try:
                                s3_client = get_s3_client()
                                if s3_client and settings:
                                    s3_key = f"documents/{doc_id}/images/{filename}"
                                    
                                    img_bytes = io.BytesIO()
                                    pil_image.save(img_bytes, format='PNG')
                                    img_bytes.seek(0)
                                    
                                    await s3_client.upload_file(
                                        img_bytes,
                                        settings.s3_bucket_name,
                                        s3_key,
                                        content_type="image/png"
                                    )
                                    
                                    logger.info(f"✅ Saved to S3: {s3_key}")
                                else:
                                    logger.info(f"📁 Saved locally only (S3 not configured)")
                            except Exception as s3_error:
                                logger.warning(f"⚠️ S3 save failed: {s3_error}")
                            
                            image_files.append((original_ref, filename))
                            
                            # Progress callback
                            if on_progress:
                                on_progress({
                                    "type": "image_extracted",
                                    "filename": filename,
                                    "method": "coordinate_based",
                                    "size": pil_image.size
                                })
                    
                    pix = None  # Free memory
                    
                except Exception as e:
                    logger.error(f"Failed to extract image for coordinates {coord_info}: {e}")
                    continue
            
            doc.close()
            
            logger.info(f"✅ Coordinate-based extraction: {len(image_files)} images")
            return image_files
            
        except ImportError:
            logger.warning("PyMuPDF not available, falling back to pure Docling")
            return await self._docling_ocr_image_extraction(document_result, output_dir, doc_id, on_progress)
        except Exception as e:
            logger.error(f"Coordinate-based extraction failed: {e}")
            return await self._docling_ocr_image_extraction(document_result, output_dir, doc_id, on_progress)
    
    def _extract_coordinates_from_docling(self, document_result) -> List[Dict[str, Any]]:
        """Extract coordinate information from Docling result"""
        
        coordinates = []
        
        try:
            if not hasattr(document_result, 'document') or not document_result.document:
                return coordinates
            
            document = document_result.document
            
            if hasattr(document, 'pictures') and document.pictures:
                for i, picture in enumerate(document.pictures):
                    try:
                        if hasattr(picture, 'prov') and picture.prov:
                            for prov_item in picture.prov:
                                if hasattr(prov_item, 'bbox') and hasattr(prov_item, 'page_no'):
                                    bbox = prov_item.bbox
                                    page_no = prov_item.page_no
                                    
                                    coord_info = {
                                        "picture_index": i,
                                        "page_no": page_no,
                                        "page_index": page_no - 1,  # 0-based for PyMuPDF
                                        "bbox": {
                                            "left": bbox.l,
                                            "top": bbox.t,
                                            "right": bbox.r,
                                            "bottom": bbox.b,
                                        },
                                        "self_ref": picture.self_ref if hasattr(picture, 'self_ref') else f"#/pictures/{i}"
                                    }
                                    
                                    coordinates.append(coord_info)
                                    
                    except Exception as e:
                        logger.debug(f"Failed to extract coordinates for picture {i}: {e}")
                        continue
            
            return coordinates
            
        except Exception as e:
            logger.error(f"Coordinate extraction failed: {e}")
            return coordinates

    async def _extract_and_save_images(
        self,
        document_result,
        output_dir: Path,
        doc_id: str,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> List[Tuple[str, str]]:
        """
        Extract images from Docling document result and save them locally and to S3
        
        Args:
            document_result: Docling document conversion result
            output_dir: Output directory for local storage
            doc_id: Document ID for S3 path
            on_progress: Progress callback
            
        Returns:
            List of tuples (original_ref, new_filename) for image references
        """
        image_files = []
        
        try:
            # Debug: Log all available attributes of the document result
            available_attrs = [attr for attr in dir(document_result) if not attr.startswith('_')]
            logger.info(f"Document result attributes: {available_attrs}")
            
            # Try multiple ways to find images in Docling 2.x
            pictures = []
            
            # Method 1: Check ConversionResult.document for pictures/images
            if hasattr(document_result, 'document') and document_result.document:
                document = document_result.document
                doc_attrs = [attr for attr in dir(document) if not attr.startswith('_')]
                logger.info(f"Document attributes: {doc_attrs}")
                
                # Check for pictures/images at document level
                for attr_name in ['pictures', 'images', 'figures']:
                    if hasattr(document, attr_name):
                        attr_value = getattr(document, attr_name)
                        if attr_value and hasattr(attr_value, '__len__') and len(attr_value) > 0:
                            pictures.extend(attr_value)
                            logger.info(f"Found {len(attr_value)} images via document.{attr_name}")
                
                # Check document elements
                if hasattr(document, 'elements') and document.elements:
                    for element in document.elements:
                        if hasattr(element, 'label') and 'picture' in str(element.label).lower():
                            pictures.append(element)
                            logger.info(f"Found picture element: {element.label}")
            
            # Method 2: Check pages for images (from ConversionResult.pages)
            if hasattr(document_result, 'pages') and document_result.pages:
                logger.info(f"Checking {len(document_result.pages)} pages for images...")
                
                for page_idx, page in enumerate(document_result.pages):
                    page_attrs = [attr for attr in dir(page) if not attr.startswith('_')]
                    logger.info(f"Page {page_idx} attributes: {page_attrs}")
                    
                    # Check page for images
                    for attr_name in ['images', 'pictures', 'figures']:
                        if hasattr(page, attr_name):
                            attr_value = getattr(page, attr_name)
                            if attr_value and hasattr(attr_value, '__len__') and len(attr_value) > 0:
                                pictures.extend(attr_value)
                                logger.info(f"Found {len(attr_value)} images on page {page_idx} via {attr_name}")
                    
                    # Check page elements for pictures
                    if hasattr(page, 'elements') and page.elements:
                        for element in page.elements:
                            if hasattr(element, 'label') and 'picture' in str(element.label).lower():
                                pictures.append(element)
                                logger.info(f"Found picture element on page {page_idx}: {element.label}")
                            
                    # Check page prediction if available
                    if hasattr(page, 'prediction') and page.prediction:
                        pred_attrs = [attr for attr in dir(page.prediction) if not attr.startswith('_')]
                        logger.info(f"Page {page_idx} prediction attributes: {pred_attrs}")
            
            # Method 3: Direct pictures/images attributes on result
            for attr_name in ['pictures', 'images', 'figures']:
                if hasattr(document_result, attr_name):
                    attr_value = getattr(document_result, attr_name)
                    if attr_value and hasattr(attr_value, '__len__') and len(attr_value) > 0:
                        pictures.extend(attr_value)
                        logger.info(f"Found {len(attr_value)} images via result.{attr_name}")
            
            if pictures:
                logger.info(f"Total found {len(pictures)} images in document")
                
                for i, picture in enumerate(pictures):
                    try:
                        # Debug picture object structure
                        picture_attrs = [attr for attr in dir(picture) if not attr.startswith('_')]
                        logger.info(f"Picture {i} attributes: {picture_attrs}")
                        logger.info(f"Picture {i} type: {type(picture)}")
                        
                        # For Docling 2.x PictureItem, we need to get image data differently
                        image_obj = None
                        image_data = None
                        
                        # Method 1: Try to get PIL image with document reference
                        if hasattr(picture, 'get_image') and callable(picture.get_image):
                            try:
                                # get_image() needs the document as parameter
                                if hasattr(document_result, 'document'):
                                    image_obj = picture.get_image(document_result.document)
                                    logger.info(f"Got image via get_image(doc): {type(image_obj)}")
                                else:
                                    # Try with document_result directly if available
                                    image_obj = picture.get_image(document_result)
                                    logger.info(f"Got image via get_image(result): {type(image_obj)}")
                            except Exception as e:
                                logger.warning(f"get_image() failed: {e}")
                                # Try get_image without parameters as fallback
                                try:
                                    image_obj = picture.get_image()
                                    logger.info(f"Got image via get_image(): {type(image_obj)}")
                                except Exception as e2:
                                    logger.warning(f"get_image() without params also failed: {e2}")
                        
                        # Method 2: Check for direct image attribute
                        if image_obj is None and hasattr(picture, 'image') and picture.image:
                            image_obj = picture.image
                            logger.info(f"Got image via .image: {type(image_obj)}")
                        
                        # Method 3: Check for data/content attributes
                        if image_obj is None:
                            for attr_name in ['data', 'content', 'pil_image', 'raw_data']:
                                if hasattr(picture, attr_name):
                                    attr_value = getattr(picture, attr_name)
                                    if attr_value is not None:
                                        image_obj = attr_value
                                        logger.info(f"Got image via .{attr_name}: {type(image_obj)}")
                                        break
                        
                        # Method 4: Try to serialize picture to get data
                        if image_obj is None and hasattr(picture, 'model_dump'):
                            try:
                                picture_data = picture.model_dump()
                                logger.info(f"Picture data keys: {picture_data.keys()}")
                                # Look for base64 or binary data
                                for key in ['image', 'data', 'content', 'base64']:
                                    if key in picture_data and picture_data[key]:
                                        image_data = picture_data[key]
                                        logger.info(f"Found image data in {key}: type={type(image_data)}, length={len(str(image_data)) if image_data else 0}")
                                        break
                            except Exception as e:
                                logger.warning(f"model_dump failed: {e}")
                        
                        if image_obj is None and image_data is None:
                            logger.warning(f"Could not extract image from picture object {i}")
                            continue
                        
                        # Generate unique filename
                        image_uuid = str(uuid.uuid4())
                        
                        # Try different approaches to save the image
                        image_bytes = None
                        image_extension = "png"  # Default
                        
                        # If we have a PIL image
                        if image_obj is not None:
                            try:
                                image_extension = self._detect_image_format(image_obj)
                                image_bytes = self._image_to_bytes(image_obj, image_extension)
                            except Exception as e:
                                logger.warning(f"Failed to process image object: {e}")
                                # Try to convert string data
                                if isinstance(image_obj, str):
                                    import base64
                                    try:
                                        image_bytes = base64.b64decode(image_obj)
                                        image_extension = "png"
                                    except Exception as e2:
                                        logger.warning(f"Failed to decode base64: {e2}")
                                        continue
                                elif hasattr(image_obj, 'tobytes'):
                                    try:
                                        image_bytes = image_obj.tobytes()
                                    except Exception as e2:
                                        logger.warning(f"Failed tobytes: {e2}")
                                        continue
                                else:
                                    continue
                        
                        # If we have raw data
                        elif image_data is not None:
                            if isinstance(image_data, str):
                                import base64
                                try:
                                    image_bytes = base64.b64decode(image_data)
                                    image_extension = "png"
                                except Exception as e:
                                    logger.warning(f"Failed to decode image data: {e}")
                                    continue
                            elif isinstance(image_data, bytes):
                                image_bytes = image_data
                            else:
                                logger.warning(f"Unknown image data type: {type(image_data)}")
                                continue
                        
                        if not image_bytes:
                            logger.warning(f"No image bytes extracted for picture {i}")
                            continue
                        
                        image_filename = f"{image_uuid}.{image_extension}"
                        local_image_path = output_dir / image_filename
                        
                        # Save locally
                        local_image_path.write_bytes(image_bytes)
                        logger.info(f"Image saved locally: {local_image_path}")
                        
                        # Upload to S3 if client is available
                        if self.s3_client and settings is not None:
                            s3_key = f"documents/{doc_id}/{image_filename}"
                            content_type = f"image/{image_extension}"
                            
                            success = await self.s3_client.upload_bytes(
                                data=image_bytes,
                                bucket_name=settings.s3_bucket_name,
                                object_key=s3_key,
                                content_type=content_type,
                                metadata={
                                    'doc_id': doc_id,
                                    'image_index': str(i),
                                    'extracted_by': 'docling_model'
                                }
                            )
                            
                            if success:
                                logger.info(f"Image uploaded to S3: s3://{settings.s3_bucket_name}/{s3_key}")
                            else:
                                logger.warning(f"Failed to upload image to S3: {image_filename}")
                        
                        # Store reference mapping (for future use if needed)
                        # We'll use the filename as both original and new reference for now
                        image_files.append((image_filename, image_filename))
                        
                    except Exception as e:
                        logger.error(f"Error processing image {i}: {e}")
                        continue
                        
            else:
                logger.info("No images found in document")
                
        except Exception as e:
            logger.error(f"Error during image extraction: {e}")
        
        return image_files
    
    def _detect_image_format(self, pil_image) -> str:
        """Detect image format from PIL Image"""
        if hasattr(pil_image, 'format') and pil_image.format:
            return pil_image.format.lower()
        
        # Default to PNG if format cannot be determined
        return 'png'
    
    def _image_to_bytes(self, pil_image, format_ext: str) -> bytes:
        """Convert PIL Image to bytes"""
        buffer = io.BytesIO()
        
        # Ensure RGB mode for JPEG
        if format_ext.lower() in ['jpg', 'jpeg'] and pil_image.mode in ('RGBA', 'LA', 'P'):
            pil_image = pil_image.convert('RGB')
        
        # Save to buffer
        save_format = 'JPEG' if format_ext.lower() in ['jpg', 'jpeg'] else format_ext.upper()
        pil_image.save(buffer, format=save_format)
        
        return buffer.getvalue()
    
    def _update_image_references(
        self,
        markdown_content: str,
        image_files: List[Tuple[str, str]],
        doc_id: str
    ) -> str:
        """
        Update image references in markdown content to point to S3 URLs or local paths
        
        Args:
            markdown_content: Original markdown content
            image_files: List of (original_ref, new_filename) tuples
            doc_id: Document ID
            
        Returns:
            Updated markdown content
        """
        if not image_files:
            return markdown_content
        
        updated_content = markdown_content
        
        # For now, we'll leave the image references as local filenames
        # The frontend will handle constructing the proper URLs for display
        # When the API serves images, it will use the doc_id and filename
        
        # In the future, we could replace references with API endpoints like:
        # ![image](http://api/documents/{doc_id}/images/{filename})
        
        logger.info(f"Image references maintained in markdown for {len(image_files)} images")
        
        return updated_content


# Global instance
docling_model = DoclingModel()
