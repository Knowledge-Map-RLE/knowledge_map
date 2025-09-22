#!/usr/bin/env python3
"""
Minimal standalone PDF→Markdown converter using Docling.

This script converts a PDF file to Markdown format using Docling library
and saves the result to the markdown_output/ directory.

Requirements:
- Docling library must be installed (pip install docling)
- Input PDF file must exist at the specified path

Usage:
    python convert_docling_min.py

The script will:
1. Convert the hardcoded PDF file to Markdown
2. Save the result as parkinson_hallmarks.md in markdown_output/ folder
3. Display conversion progress and results

Based on official Docling documentation:
- https://github.com/docling-project/docling
- https://docling-project.github.io/docling/
"""
import os
from pathlib import Path
import sys

def convert_with_docling(input_pdf: Path) -> str:
    """Convert PDF to Markdown using Docling according to official documentation."""
    try:
        from docling.document_converter import DocumentConverter
        from docling.datamodel.document import DocumentConversionInput
    except ImportError as e:
        raise RuntimeError(f"Docling not available: {e}")

    # Check if input file exists
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF file not found: {input_pdf}")

    # Initialize converter and convert the document
    converter = DocumentConverter()
    
    # Create DocumentConversionInput using from_paths method
    input_doc = DocumentConversionInput.from_paths([input_pdf])
    
    # Convert the document
    result = converter.convert(input_doc)
    
    # Get the first result from the generator
    first_result = next(result)
    
    # Export to markdown using render_as_markdown method
    md = first_result.render_as_markdown()
    if not md or not str(md).strip():
        raise RuntimeError("Docling did not produce Markdown output")
    
    return str(md)


def main() -> None:
    """Main function to convert PDF to Markdown using Docling."""
    # Input PDF file path
    input_pdf = Path(r"D:\Knowledge_Map\knowledge_map\personal_folder\The FEBS Journal - 2013 - Antony - The hallmarks of Parkinson s disease.pdf")
    
    # Output directory and file path
    output_dir = Path(__file__).resolve().parent / "markdown_output"
    output_file = output_dir / "parkinson_hallmarks.md"
    
    try:
        print(f"Converting PDF: {input_pdf}")
        print(f"Output will be saved to: {output_file}")
        
        # Convert PDF to Markdown
        md_text = convert_with_docling(input_pdf)
        
        # Create output directory if it doesn't exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save the markdown content
        output_file.write_text(md_text, encoding="utf-8")
        
        print(f"✅ Successfully converted PDF to Markdown!")
        print(f"📁 Output file: {output_file}")
        print(f"📄 Content length: {len(md_text)} characters")
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"❌ Conversion error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


