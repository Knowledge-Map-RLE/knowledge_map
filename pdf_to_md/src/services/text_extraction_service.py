"""Text extraction service using PyMuPDF (fitz) for raw PDF text."""

import logging
from pathlib import Path
from typing import List, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    logger.warning("tiktoken not available. Using character-based token estimation.")
    TIKTOKEN_AVAILABLE = False


class TextChunk:
    """Represents a chunk of text with metadata."""

    def __init__(
        self,
        text: str,
        page_range: Tuple[int, int],
        token_count: int,
        char_count: int,
    ):
        """
        Initialize a text chunk.

        Args:
            text: The text content
            page_range: Tuple of (start_page, end_page) inclusive
            token_count: Number of tokens in this chunk
            char_count: Number of characters in this chunk
        """
        self.text = text
        self.page_range = page_range
        self.token_count = token_count
        self.char_count = char_count

    def __repr__(self):
        return f"TextChunk(pages={self.page_range}, tokens={self.token_count}, chars={self.char_count})"


class TextExtractionService:
    """Service for extracting raw text from PDF files using PyMuPDF."""

    def __init__(self, encoding: str = "cl100k_base"):
        """
        Initialize the text extraction service.

        Args:
            encoding: Tiktoken encoding to use (default: cl100k_base for GPT-4/Llama)
        """
        self.encoding_name = encoding
        self.tokenizer = None

        if TIKTOKEN_AVAILABLE:
            try:
                self.tokenizer = tiktoken.get_encoding(encoding)
                logger.info(f"Initialized tiktoken with encoding: {encoding}")
            except Exception as e:
                logger.warning(f"Failed to initialize tiktoken: {e}. Using character-based estimation.")
                self.tokenizer = None

    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in text.

        Args:
            text: Input text

        Returns:
            Number of tokens
        """
        if self.tokenizer is not None:
            try:
                return len(self.tokenizer.encode(text))
            except Exception as e:
                logger.warning(f"Error counting tokens with tiktoken: {e}. Using character estimation.")

        # Fallback: estimate ~4 characters per token
        return len(text) // 4

    def extract_full_text(self, pdf_path: str | Path) -> str:
        """
        Extract all text from a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Full text content of the PDF

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            Exception: If PDF cannot be opened or read
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(f"Extracting text from PDF: {pdf_path}")

        try:
            doc = fitz.open(str(pdf_path))
            full_text = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")  # Extract as plain text
                full_text.append(text)

            doc.close()

            result = "\n\n".join(full_text)
            token_count = self.count_tokens(result)

            logger.info(
                f"Extracted {len(result)} characters (~{token_count} tokens) "
                f"from {len(doc)} pages"
            )

            return result

        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}", exc_info=True)
            raise

    def extract_page_text(self, pdf_path: str | Path, page_num: int) -> str:
        """
        Extract text from a specific page.

        Args:
            pdf_path: Path to the PDF file
            page_num: Page number (0-indexed)

        Returns:
            Text content of the page

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            IndexError: If page number is out of range
            Exception: If PDF cannot be opened or read
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            doc = fitz.open(str(pdf_path))

            if page_num < 0 or page_num >= len(doc):
                raise IndexError(
                    f"Page number {page_num} out of range (0-{len(doc)-1})"
                )

            page = doc[page_num]
            text = page.get_text("text")
            doc.close()

            return text

        except Exception as e:
            logger.error(f"Error extracting text from page {page_num}: {e}", exc_info=True)
            raise

    def create_chunks(
        self,
        pdf_path: str | Path,
        max_tokens: int = 18000,
        overlap_tokens: int = 1000,
    ) -> List[TextChunk]:
        """
        Create text chunks from a PDF with token-based splitting and overlap.

        Args:
            pdf_path: Path to the PDF file
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Number of tokens to overlap between chunks

        Returns:
            List of TextChunk objects

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            Exception: If PDF cannot be opened or read
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(f"Creating chunks from PDF: {pdf_path} (max_tokens={max_tokens}, overlap={overlap_tokens})")

        try:
            doc = fitz.open(str(pdf_path))
            chunks = []
            current_chunk_text = []
            current_chunk_tokens = 0
            chunk_start_page = 0

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text("text")
                page_tokens = self.count_tokens(page_text)

                # Check if adding this page would exceed max_tokens
                if current_chunk_tokens + page_tokens > max_tokens and current_chunk_text:
                    # Save current chunk
                    chunk_text = "\n\n".join(current_chunk_text)
                    chunks.append(
                        TextChunk(
                            text=chunk_text,
                            page_range=(chunk_start_page, page_num - 1),
                            token_count=current_chunk_tokens,
                            char_count=len(chunk_text),
                        )
                    )

                    # Start new chunk with overlap
                    # Keep last portion of previous chunk for overlap
                    overlap_text = self._get_overlap_text(chunk_text, overlap_tokens)
                    overlap_tokens_actual = self.count_tokens(overlap_text)

                    current_chunk_text = [overlap_text, page_text] if overlap_text else [page_text]
                    current_chunk_tokens = overlap_tokens_actual + page_tokens
                    chunk_start_page = page_num
                else:
                    # Add page to current chunk
                    current_chunk_text.append(page_text)
                    current_chunk_tokens += page_tokens

            # Add the last chunk
            if current_chunk_text:
                chunk_text = "\n\n".join(current_chunk_text)
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        page_range=(chunk_start_page, len(doc) - 1),
                        token_count=current_chunk_tokens,
                        char_count=len(chunk_text),
                    )
                )

            # Store page count before closing
            total_pages = len(doc)
            doc.close()

            logger.info(
                f"Created {len(chunks)} chunks from {total_pages} pages. "
                f"Average: {sum(c.token_count for c in chunks) / len(chunks):.0f} tokens/chunk"
            )

            return chunks

        except Exception as e:
            logger.error(f"Error creating chunks from PDF: {e}", exc_info=True)
            raise

    def _get_overlap_text(self, text: str, overlap_tokens: int) -> str:
        """
        Get the last N tokens worth of text for overlap.

        Args:
            text: Source text
            overlap_tokens: Number of tokens to extract

        Returns:
            Overlap text
        """
        if overlap_tokens <= 0:
            return ""

        if self.tokenizer is not None:
            try:
                tokens = self.tokenizer.encode(text)
                if len(tokens) <= overlap_tokens:
                    return text

                overlap_token_ids = tokens[-overlap_tokens:]
                return self.tokenizer.decode(overlap_token_ids)
            except Exception as e:
                logger.warning(f"Error getting overlap with tokenizer: {e}")

        # Fallback: estimate by characters
        char_overlap = overlap_tokens * 4  # ~4 chars per token
        if len(text) <= char_overlap:
            return text

        # Try to find a good break point (paragraph boundary)
        overlap_text = text[-char_overlap:]

        # Find first paragraph boundary
        paragraph_break = overlap_text.find("\n\n")
        if paragraph_break != -1:
            return overlap_text[paragraph_break + 2:]

        # Find first line break
        line_break = overlap_text.find("\n")
        if line_break != -1:
            return overlap_text[line_break + 1:]

        return overlap_text


# Global service instance
_text_extraction_service = None


def get_text_extraction_service() -> TextExtractionService:
    """
    Get or create the global text extraction service instance.

    Returns:
        TextExtractionService instance
    """
    global _text_extraction_service

    if _text_extraction_service is None:
        _text_extraction_service = TextExtractionService()

    return _text_extraction_service
