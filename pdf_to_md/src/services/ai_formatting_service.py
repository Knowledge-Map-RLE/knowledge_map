"""AI formatting service for converting Docling MD + raw text to formatted MD."""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

from src.services.ai_client import get_ai_client
from src.services.text_extraction_service import get_text_extraction_service, TextChunk


class FormattingChunk:
    """Represents a chunk of content to be formatted by AI."""

    def __init__(
        self,
        raw_text: str,
        docling_markdown: str,
        chunk_index: int,
        total_chunks: int,
    ):
        """
        Initialize a formatting chunk.

        Args:
            raw_text: Raw text from PDF
            docling_markdown: Corresponding Docling markdown
            chunk_index: Index of this chunk (0-based)
            total_chunks: Total number of chunks
        """
        self.raw_text = raw_text
        self.docling_markdown = docling_markdown
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks

    def __repr__(self):
        return f"FormattingChunk({self.chunk_index + 1}/{self.total_chunks})"


class AIFormattingService:
    """Service for formatting markdown using AI with chunking support."""

    def __init__(
        self,
        ai_host: Optional[str] = None,
        ai_port: Optional[int] = None,
        model_id: str = "Qwen/Qwen2.5-0.5B-Instruct",
        max_chunk_tokens: int = 18000,
        overlap_tokens: int = 1000,
        max_generation_tokens: int = 4096,
        temperature: float = 0.3,
        timeout: int = 600,
    ):
        """
        Initialize the AI formatting service.

        Args:
            ai_host: AI service host
            ai_port: AI service port
            model_id: AI model to use
            max_chunk_tokens: Maximum tokens per chunk (for input)
            overlap_tokens: Overlap between chunks
            max_generation_tokens: Maximum tokens to generate per chunk
            temperature: Sampling temperature
            timeout: Timeout per chunk formatting request
        """
        self.ai_client = get_ai_client(host=ai_host, port=ai_port)
        self.text_service = get_text_extraction_service()
        self.model_id = model_id
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_tokens = overlap_tokens
        self.max_generation_tokens = max_generation_tokens
        self.temperature = temperature
        self.timeout = timeout

    async def format_with_chunks(
        self,
        pdf_path: str | Path,
        raw_markdown: str,
        doc_id: str,
    ) -> str:
        """
        Format markdown using AI with automatic chunking for large documents.

        Args:
            pdf_path: Path to the PDF file
            raw_markdown: Raw markdown from Docling
            doc_id: Document ID for logging

        Returns:
            Formatted markdown content

        Raises:
            Exception: If formatting fails
        """
        logger.info(f"Starting AI formatting for document {doc_id}")

        try:
            # 1. Extract raw text chunks from PDF
            text_chunks = self.text_service.create_chunks(
                pdf_path=pdf_path,
                max_tokens=self.max_chunk_tokens,
                overlap_tokens=self.overlap_tokens,
            )

            logger.info(f"Created {len(text_chunks)} text chunks for document {doc_id}")

            # 2. Split Docling markdown into corresponding chunks
            # For simplicity, we'll use the same chunking approach
            # In practice, you might want to align chunks based on page boundaries
            md_chunks = self._split_markdown_by_chunks(raw_markdown, text_chunks)

            # 3. Create formatting chunks
            formatting_chunks = [
                FormattingChunk(
                    raw_text=text_chunks[i].text,
                    docling_markdown=md_chunks[i],
                    chunk_index=i,
                    total_chunks=len(text_chunks),
                )
                for i in range(len(text_chunks))
            ]

            # 4. Format chunks in parallel
            logger.info(f"Formatting {len(formatting_chunks)} chunks in parallel...")
            formatted_chunks = await self._format_chunks_parallel(formatting_chunks, doc_id)

            # 5. Merge formatted chunks
            logger.info(f"Merging {len(formatted_chunks)} formatted chunks...")
            final_markdown = self._merge_formatted_chunks(formatted_chunks)

            logger.info(
                f"Successfully formatted document {doc_id}: "
                f"{len(final_markdown)} characters, {len(formatted_chunks)} chunks"
            )

            return final_markdown

        except Exception as e:
            logger.error(f"Error formatting document {doc_id}: {e}", exc_info=True)
            raise

    def _split_markdown_by_chunks(
        self,
        markdown: str,
        text_chunks: List[TextChunk],
    ) -> List[str]:
        """
        Split markdown content into chunks aligned with text chunks.

        For simplicity, we'll split markdown proportionally based on character counts.
        A more sophisticated approach would parse the markdown and split by sections.

        Args:
            markdown: Full markdown content
            text_chunks: List of text chunks

        Returns:
            List of markdown chunk strings
        """
        if len(text_chunks) == 1:
            return [markdown]

        # Calculate proportions based on character counts
        total_chars = sum(chunk.char_count for chunk in text_chunks)
        md_chunks = []
        start_pos = 0

        for i, chunk in enumerate(text_chunks):
            # Calculate this chunk's proportion of the markdown
            proportion = chunk.char_count / total_chars
            chunk_size = int(len(markdown) * proportion)

            # For the last chunk, take everything remaining
            if i == len(text_chunks) - 1:
                md_chunks.append(markdown[start_pos:])
            else:
                # Try to find a paragraph boundary near the split point
                end_pos = min(start_pos + chunk_size, len(markdown))

                # Look for paragraph break (\n\n) near the split point
                search_window = 200
                search_start = max(0, end_pos - search_window)
                search_end = min(len(markdown), end_pos + search_window)
                search_text = markdown[search_start:search_end]

                paragraph_break = search_text.rfind("\n\n")
                if paragraph_break != -1:
                    end_pos = search_start + paragraph_break + 2

                md_chunks.append(markdown[start_pos:end_pos])
                start_pos = end_pos

        return md_chunks

    async def _format_chunks_parallel(
        self,
        chunks: List[FormattingChunk],
        doc_id: str,
    ) -> List[str]:
        """
        Format multiple chunks in parallel using AI.

        Args:
            chunks: List of formatting chunks
            doc_id: Document ID for logging

        Returns:
            List of formatted markdown strings (in order)

        Raises:
            Exception: If any chunk fails to format
        """
        # Create tasks for parallel execution
        tasks = [
            self._format_single_chunk(chunk, doc_id)
            for chunk in chunks
        ]

        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=False)

        return results

    async def _format_single_chunk(
        self,
        chunk: FormattingChunk,
        doc_id: str,
    ) -> str:
        """
        Format a single chunk using AI.

        Args:
            chunk: Formatting chunk
            doc_id: Document ID for logging

        Returns:
            Formatted markdown for this chunk

        Raises:
            Exception: If formatting fails
        """
        logger.info(
            f"Formatting chunk {chunk.chunk_index + 1}/{chunk.total_chunks} "
            f"for document {doc_id}"
        )

        # Run the synchronous gRPC call in a thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self.ai_client.format_markdown_chunk,
            chunk.raw_text,
            chunk.docling_markdown,
            self.model_id,
            self.max_generation_tokens,
            self.temperature,
            self.timeout,
        )

        if not result["success"]:
            error_msg = f"Failed to format chunk {chunk.chunk_index + 1}: {result['message']}"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.info(
            f"Successfully formatted chunk {chunk.chunk_index + 1}/{chunk.total_chunks}: "
            f"{result['output_tokens']} tokens generated"
        )

        return result["formatted_text"]

    def _merge_formatted_chunks(self, chunks: List[str]) -> str:
        """
        Merge formatted chunks into a single markdown document.

        Args:
            chunks: List of formatted markdown chunks

        Returns:
            Merged markdown content
        """
        if len(chunks) == 1:
            return chunks[0]

        # For now, simple concatenation with paragraph breaks
        # More sophisticated merging could:
        # 1. Remove duplicate headers from chunk boundaries
        # 2. Merge YAML frontmatter from first chunk only
        # 3. Handle split paragraphs at boundaries

        # Extract frontmatter from first chunk if present
        first_chunk = chunks[0]
        has_frontmatter = first_chunk.strip().startswith("---")

        if has_frontmatter:
            # Split first chunk into frontmatter and content
            parts = first_chunk.split("---", 2)
            if len(parts) >= 3:
                frontmatter = f"---{parts[1]}---\n\n"
                first_content = parts[2].strip()

                # Merge: frontmatter + first content + other chunks
                remaining = [first_content] + [chunk.strip() for chunk in chunks[1:]]
                return frontmatter + "\n\n".join(remaining)

        # No frontmatter, simple merge
        return "\n\n".join(chunk.strip() for chunk in chunks)


# Global service instance
_ai_formatting_service = None


def get_ai_formatting_service(
    ai_host: Optional[str] = None,
    ai_port: Optional[int] = None,
    model_id: Optional[str] = None,
    max_chunk_tokens: Optional[int] = None,
    overlap_tokens: Optional[int] = None,
) -> AIFormattingService:
    """
    Get or create the global AI formatting service instance.

    Args:
        ai_host: AI service host (optional, from config if not provided)
        ai_port: AI service port (optional, from config if not provided)
        model_id: AI model ID (optional, from config if not provided)
        max_chunk_tokens: Max tokens per chunk (optional, from config if not provided)
        overlap_tokens: Overlap tokens (optional, from config if not provided)

    Returns:
        AIFormattingService instance
    """
    global _ai_formatting_service

    # Allow parameters to override defaults, but preserve existing instance if no params
    if _ai_formatting_service is None or any([ai_host, ai_port, model_id, max_chunk_tokens, overlap_tokens]):
        # Import settings
        try:
            from ..core.config import settings
        except ImportError:
            from core.config import settings

        kwargs = {}
        kwargs["ai_host"] = ai_host if ai_host is not None else settings.ai_model_service_host
        kwargs["ai_port"] = ai_port if ai_port is not None else settings.ai_model_service_port
        kwargs["model_id"] = model_id if model_id is not None else settings.ai_model_id
        kwargs["max_chunk_tokens"] = max_chunk_tokens if max_chunk_tokens is not None else settings.ai_max_chunk_tokens
        kwargs["overlap_tokens"] = overlap_tokens if overlap_tokens is not None else settings.ai_overlap_tokens
        kwargs["max_generation_tokens"] = settings.ai_max_generation_tokens
        kwargs["temperature"] = settings.ai_temperature
        kwargs["timeout"] = settings.ai_formatting_timeout

        _ai_formatting_service = AIFormattingService(**kwargs)

    return _ai_formatting_service
