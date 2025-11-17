"""Text chunking utilities for handling large prompts."""

from typing import List

from loguru import logger


class TextChunker:
    """Handles chunking of large text into smaller parts for model processing."""

    def __init__(
        self,
        max_tokens: int = 100000,
        overlap: int = 200,
        tokenizer=None,
    ):
        """
        Initialize the text chunker.

        Args:
            max_tokens: Maximum number of tokens per chunk
            overlap: Number of tokens to overlap between chunks
            tokenizer: Tokenizer to use for counting tokens
        """
        self.max_tokens = max_tokens
        self.overlap = overlap
        self.tokenizer = tokenizer

    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in text.

        Args:
            text: Input text

        Returns:
            Number of tokens
        """
        if self.tokenizer is None:
            # Rough estimation: ~4 characters per token for English text
            return len(text) // 4

        try:
            tokens = self.tokenizer.encode(text, add_special_tokens=False)
            return len(tokens)
        except Exception as e:
            logger.warning(f"Error counting tokens: {e}. Using character-based estimation.")
            return len(text) // 4

    def needs_chunking(self, text: str) -> bool:
        """
        Check if text needs to be chunked.

        Args:
            text: Input text

        Returns:
            True if text exceeds max_tokens
        """
        token_count = self.count_tokens(text)
        return token_count > self.max_tokens

    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks with overlap.

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks
        """
        if not self.needs_chunking(text):
            return [text]

        chunks = []

        # Split by paragraphs first to avoid breaking mid-sentence
        paragraphs = text.split("\n\n")

        current_chunk = ""
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            # If single paragraph is too large, split by sentences
            if para_tokens > self.max_tokens:
                sentences = self._split_into_sentences(para)
                for sentence in sentences:
                    sentence_tokens = self.count_tokens(sentence)

                    if current_tokens + sentence_tokens > self.max_tokens:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            # Keep overlap from previous chunk
                            overlap_text = self._get_overlap_text(current_chunk)
                            current_chunk = overlap_text + "\n" + sentence
                            current_tokens = self.count_tokens(current_chunk)
                        else:
                            # Single sentence is too large, force split
                            current_chunk = sentence
                            current_tokens = sentence_tokens
                    else:
                        current_chunk += "\n" + sentence
                        current_tokens += sentence_tokens
            else:
                # Add paragraph to current chunk if it fits
                if current_tokens + para_tokens > self.max_tokens:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        # Keep overlap from previous chunk
                        overlap_text = self._get_overlap_text(current_chunk)
                        current_chunk = overlap_text + "\n\n" + para
                        current_tokens = self.count_tokens(current_chunk)
                    else:
                        current_chunk = para
                        current_tokens = para_tokens
                else:
                    if current_chunk:
                        current_chunk += "\n\n" + para
                    else:
                        current_chunk = para
                    current_tokens += para_tokens

        # Add the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        logger.info(f"Split text into {len(chunks)} chunks")
        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.

        Args:
            text: Input text

        Returns:
            List of sentences
        """
        # Simple sentence splitting by common punctuation
        import re

        # Split on sentence-ending punctuation followed by whitespace
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _get_overlap_text(self, text: str) -> str:
        """
        Get the overlap portion from the end of text.

        Args:
            text: Input text

        Returns:
            Overlap text
        """
        if self.overlap <= 0:
            return ""

        # Try to get last N tokens worth of text
        if self.tokenizer is not None:
            try:
                tokens = self.tokenizer.encode(text, add_special_tokens=False)
                if len(tokens) <= self.overlap:
                    return text
                overlap_tokens = tokens[-self.overlap:]
                return self.tokenizer.decode(overlap_tokens, skip_special_tokens=True)
            except Exception as e:
                logger.warning(f"Error getting overlap with tokenizer: {e}")

        # Fallback: estimate by characters
        char_overlap = self.overlap * 4  # ~4 chars per token
        if len(text) <= char_overlap:
            return text

        # Try to find a good break point (end of sentence)
        overlap_text = text[-char_overlap:]

        # Find the first sentence boundary
        import re
        match = re.search(r'[.!?]\s+', overlap_text)
        if match:
            return overlap_text[match.end():]

        return overlap_text

    def merge_chunks(self, chunk_results: List[str]) -> str:
        """
        Merge results from multiple chunks.

        Args:
            chunk_results: List of generated text from each chunk

        Returns:
            Merged text
        """
        if not chunk_results:
            return ""

        if len(chunk_results) == 1:
            return chunk_results[0]

        # Simple concatenation with paragraph breaks
        # More sophisticated merging could be implemented here
        merged = "\n\n".join(chunk_results)

        logger.info(f"Merged {len(chunk_results)} chunk results")
        return merged
