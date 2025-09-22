#!/usr/bin/env python3
"""Coordinate-based image extraction: Docling coordinates + PyMuPDF extraction"""

import logging
import asyncio
import uuid
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import fitz  # PyMuPDF for precise extraction
from PIL import Image
import io

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CoordinateBasedExtractor:
    """
    Extract images using Docling coordinates and PyMuPDF precision
    """
    
    def __init__(self):
        pass
    
    async def extract_images_by_coordinates(
        self,
        pdf_path: Path,
        output_dir: Path,
        on_progress: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Extract images using coordinate-based approach
        
        Args:
            pdf_path: Path to PDF file
            output_dir: Output directory
            on_progress: Progress callback
            
        Returns:
            Results with extracted images
        """
        
        try:
            from docling.document_converter import DocumentConverter
            
            logger.info("=== Coordinate-Based Image Extraction ===")
            
            if on_progress:
                on_progress({"percent": 10, "message": "Analyzing coordinates with Docling"})
            
            # Step 1: Get coordinates from Docling
            logger.info("Step 1: Getting coordinates from Docling...")
            converter = DocumentConverter()
            result = converter.convert(str(pdf_path))
            
            coordinates = self._extract_coordinates_from_docling(result)
            logger.info(f"Found {len(coordinates)} image coordinates")
            
            if on_progress:
                on_progress({"percent": 30, "message": f"Found {len(coordinates)} image coordinates"})
            
            # Step 2: Extract images using PyMuPDF with coordinates
            logger.info("Step 2: Extracting images with PyMuPDF...")
            extracted_images = self._extract_images_with_pymupdf_coordinates(
                pdf_path, coordinates, output_dir, on_progress
            )
            
            if on_progress:
                on_progress({"percent": 80, "message": f"Extracted {len(extracted_images)} images"})
            
            # Step 3: Export markdown with proper image references
            logger.info("Step 3: Exporting markdown...")
            markdown_content = ""
            if hasattr(result, 'document') and result.document:
                markdown_content = result.document.export_to_markdown()
                
                # Update image references
                markdown_content = self._update_markdown_image_references(
                    markdown_content, extracted_images
                )
                
                # Save markdown
                markdown_file = output_dir / f"{pdf_path.stem}.md"
                markdown_file.write_text(markdown_content, encoding='utf-8')
                
                logger.info(f"Markdown saved: {markdown_file}")
            
            if on_progress:
                on_progress({"percent": 100, "message": "Coordinate extraction completed"})
            
            return {
                "success": True,
                "method": "coordinate_based",
                "coordinates_found": len(coordinates),
                "images_extracted": len(extracted_images),
                "extracted_images": extracted_images,
                "markdown_length": len(markdown_content),
                "coordinate_details": coordinates
            }
            
        except Exception as e:
            logger.error(f"Coordinate-based extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "method": "coordinate_based"
            }
    
    def _extract_coordinates_from_docling(self, result) -> List[Dict[str, Any]]:
        """Extract coordinate information from Docling result"""
        
        coordinates = []
        
        try:
            if not hasattr(result, 'document') or not result.document:
                logger.warning("No document in result")
                return coordinates
            
            document = result.document
            
            if hasattr(document, 'pictures') and document.pictures:
                logger.info(f"Processing {len(document.pictures)} pictures for coordinates")
                
                for i, picture in enumerate(document.pictures):
                    try:
                        # Extract provenance information
                        if hasattr(picture, 'prov') and picture.prov:
                            for prov_item in picture.prov:
                                if hasattr(prov_item, 'bbox') and hasattr(prov_item, 'page_no'):
                                    bbox = prov_item.bbox
                                    page_no = prov_item.page_no
                                    
                                    # Convert coordinates
                                    coord_info = {
                                        "picture_index": i,
                                        "page_no": page_no,  # 1-based
                                        "page_index": page_no - 1,  # 0-based for PyMuPDF
                                        "bbox": {
                                            "left": bbox.l,
                                            "top": bbox.t,
                                            "right": bbox.r,
                                            "bottom": bbox.b,
                                            "coord_origin": str(bbox.coord_origin)
                                        },
                                        "width": bbox.r - bbox.l,
                                        "height": bbox.t - bbox.b,  # Note: BOTTOMLEFT origin
                                        "self_ref": picture.self_ref if hasattr(picture, 'self_ref') else f"#/pictures/{i}"
                                    }
                                    
                                    coordinates.append(coord_info)
                                    
                                    logger.info(f"Picture {i}: Page {page_no}, "
                                               f"BBox=({bbox.l:.1f}, {bbox.t:.1f}, {bbox.r:.1f}, {bbox.b:.1f}), "
                                               f"Size=({coord_info['width']:.1f}x{coord_info['height']:.1f})")
                    
                    except Exception as e:
                        logger.warning(f"Failed to extract coordinates for picture {i}: {e}")
                        continue
            
            logger.info(f"Extracted {len(coordinates)} coordinate sets")
            return coordinates
            
        except Exception as e:
            logger.error(f"Coordinate extraction from Docling failed: {e}")
            return coordinates
    
    def _extract_images_with_pymupdf_coordinates(
        self,
        pdf_path: Path,
        coordinates: List[Dict],
        output_dir: Path,
        on_progress: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """Extract images using PyMuPDF with precise coordinates"""
        
        extracted_images = []
        
        try:
            # Open PDF with PyMuPDF
            doc = fitz.open(str(pdf_path))
            logger.info(f"Opened PDF with {len(doc)} pages for coordinate extraction")
            
            for coord_info in coordinates:
                try:
                    page_index = coord_info["page_index"]
                    page = doc.load_page(page_index)
                    
                    # Get page dimensions
                    page_rect = page.rect
                    page_height = page_rect.height
                    
                    logger.info(f"\n--- Extracting Picture {coord_info['picture_index']} ---")
                    logger.info(f"Page {coord_info['page_no']} (index {page_index})")
                    logger.info(f"Page dimensions: {page_rect.width} x {page_rect.height}")
                    
                    # Convert Docling coordinates (BOTTOMLEFT) to PyMuPDF coordinates (TOPLEFT)
                    bbox = coord_info["bbox"]
                    
                    # Docling uses BOTTOMLEFT, PyMuPDF uses TOPLEFT
                    # Convert coordinates
                    left = bbox["left"]
                    right = bbox["right"]
                    # For BOTTOMLEFT to TOPLEFT conversion:
                    top = page_height - bbox["top"]
                    bottom = page_height - bbox["bottom"]
                    
                    # Create PyMuPDF rectangle
                    extract_rect = fitz.Rect(left, top, right, bottom)
                    
                    logger.info(f"Original bbox (BOTTOMLEFT): ({bbox['left']:.1f}, {bbox['top']:.1f}, {bbox['right']:.1f}, {bbox['bottom']:.1f})")
                    logger.info(f"Converted rect (TOPLEFT): ({left:.1f}, {top:.1f}, {right:.1f}, {bottom:.1f})")
                    logger.info(f"Extract rect: {extract_rect}")
                    
                    # Extract image from specific area
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=extract_rect)  # 2x scale for better quality
                    
                    if pix.width > 0 and pix.height > 0:
                        # Convert to PIL Image
                        img_data = pix.tobytes("png")
                        pil_image = Image.open(io.BytesIO(img_data))
                        
                        logger.info(f"Extracted image size: {pil_image.size}")
                        logger.info(f"Extracted image mode: {pil_image.mode}")
                        
                        # Generate filename
                        filename = f"coord_page_{coord_info['page_no']}_pic_{coord_info['picture_index']}_{uuid.uuid4().hex[:8]}.png"
                        image_path = output_dir / filename
                        
                        # Save image
                        pil_image.save(image_path)
                        
                        if image_path.exists():
                            size = image_path.stat().st_size
                            logger.info(f"✅ SAVED: {filename} ({size} bytes)")
                            
                            extracted_images.append({
                                "filename": filename,
                                "path": image_path,
                                "picture_index": coord_info["picture_index"],
                                "page_no": coord_info["page_no"],
                                "page_index": page_index,
                                "size_bytes": size,
                                "image_size": pil_image.size,
                                "extraction_method": "coordinate_based",
                                "coordinates": coord_info,
                                "self_ref": coord_info["self_ref"]
                            })
                            
                            if on_progress:
                                on_progress({
                                    "type": "image_extracted",
                                    "filename": filename,
                                    "method": "coordinate_based"
                                })
                    else:
                        logger.warning(f"Empty pixmap for picture {coord_info['picture_index']}")
                    
                    pix = None  # Free memory
                    
                except Exception as e:
                    logger.error(f"Failed to extract image for coordinates {coord_info}: {e}")
                    continue
            
            doc.close()
            
            logger.info(f"✅ Coordinate-based extraction: {len(extracted_images)} images")
            return extracted_images
            
        except Exception as e:
            logger.error(f"PyMuPDF coordinate extraction failed: {e}")
            return extracted_images
    
    def _update_markdown_image_references(self, markdown_content: str, extracted_images: List[Dict]) -> str:
        """Update markdown image references with extracted filenames"""
        
        if not extracted_images:
            return markdown_content
        
        # Sort images by picture_index to maintain order
        sorted_images = sorted(extracted_images, key=lambda x: x["picture_index"])
        
        # Replace <!-- image --> placeholders with actual image references
        lines = markdown_content.split('\n')
        image_count = 0
        
        for i, line in enumerate(lines):
            if '<!-- image -->' in line and image_count < len(sorted_images):
                image_info = sorted_images[image_count]
                filename = image_info['filename']
                
                # Replace with proper markdown image syntax
                lines[i] = f"![Image {image_count + 1}]({filename})"
                image_count += 1
                
                logger.info(f"Updated image reference {image_count}: {filename}")
        
        return '\n'.join(lines)

async def test_coordinate_extraction():
    """Test coordinate-based extraction"""
    
    pdf_path = Path("test_input/parkinson_paper.pdf").resolve()
    if not pdf_path.exists():
        logger.error(f"PDF not found: {pdf_path}")
        return
    
    # Use markdown_output directory
    output_dir = Path("markdown_output")
    output_dir.mkdir(exist_ok=True)
    
    def progress_callback(data):
        logger.info(f"Progress: {data.get('percent', 0)}% - {data.get('message', 'Processing')}")
    
    extractor = CoordinateBasedExtractor()
    
    logger.info("Testing Coordinate-Based Extraction...")
    results = await extractor.extract_images_by_coordinates(
        pdf_path=pdf_path,
        output_dir=output_dir,
        on_progress=progress_callback
    )
    
    logger.info(f"\n=== Coordinate-Based Results ===")
    logger.info(f"Success: {results['success']}")
    if results['success']:
        logger.info(f"Method: {results['method']}")
        logger.info(f"Coordinates found: {results['coordinates_found']}")
        logger.info(f"Images extracted: {results['images_extracted']}")
        logger.info(f"Markdown length: {results['markdown_length']} chars")
        
        if results['extracted_images']:
            logger.info(f"\nExtracted images:")
            for img in results['extracted_images']:
                logger.info(f"  - {img['filename']} (Page {img['page_no']}, {img['size_bytes']} bytes, {img['image_size']})")
    else:
        logger.error(f"Error: {results['error']}")

if __name__ == "__main__":
    asyncio.run(test_coordinate_extraction())
