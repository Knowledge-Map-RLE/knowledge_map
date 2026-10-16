"""HTTP client for the AI Agent microservice (OpenAI-compatible gateway).

The microservice (``ai/``) exposes an OpenAI-compatible ``/v1/chat/completions``
endpoint. This client keeps the previous gRPC interface so callers
(``src/services/ai_formatting_service.py``) stay unchanged.
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class AIModelClient:
    """Client for communicating with the AI Agent microservice via HTTP."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        """
        Initialize the AI Model client.

        Args:
            host: AI service host (default from env or 127.0.0.1)
            port: AI service port (default from env or 50059)
        """
        self.host = host or os.getenv("AI_MODEL_SERVICE_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("AI_MODEL_SERVICE_PORT", "50059"))
        self.root_url = f"http://{self.host}:{self.port}"
        self.base_url = f"{self.root_url}/v1"

    def format_markdown_chunk(
        self,
        raw_text: str,
        structured_markdown: str,
        model_id: str = "openai_gpt6_luna",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        timeout: int = 600,
    ) -> dict:
        """
        Format a markdown chunk using AI.

        Args:
            raw_text: Raw text extracted from PDF (preserves original flow)
            structured_markdown: Structured markdown from OCR
            model_id: AI model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            timeout: Request timeout in seconds

        Returns:
            Dictionary with formatting results:
            {
                "success": bool,
                "formatted_text": str,
                "message": str,
                "input_tokens": int,
                "output_tokens": int
            }
        """
        prompt = self._build_formatting_prompt(raw_text, structured_markdown)
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
            "repetition_penalty": 1.1,
        }

        try:
            logger.info(f"Sending formatting request to AI service (model: {model_id})")
            response = httpx.post(
                f"{self.base_url}/chat/completions", json=payload, timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            formatted_text = data["choices"][0]["message"].get("content", "")
            usage = data.get("usage") or {}
            result = {
                "success": True,
                "formatted_text": formatted_text,
                "message": "Formatting successful",
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            }
            logger.info(
                f"Formatting successful: {result['output_tokens']} tokens generated "
                f"({result['input_tokens']} input tokens)"
            )
            return result
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            logger.error("AI Agent service error: HTTP %s - %s", exc.response.status_code, detail)
            return {
                "success": False,
                "formatted_text": "",
                "message": f"AI Agent service error: {detail}",
                "input_tokens": 0,
                "output_tokens": 0,
            }
        except httpx.HTTPError as exc:
            logger.error(f"AI Agent service unavailable: {exc}")
            return {
                "success": False,
                "formatted_text": "",
                "message": f"AI Agent service unavailable: {exc}",
                "input_tokens": 0,
                "output_tokens": 0,
            }
        except Exception as exc:
            logger.error(f"Error calling AI Agent service: {exc}", exc_info=True)
            return {
                "success": False,
                "formatted_text": "",
                "message": f"Error: {str(exc)}",
                "input_tokens": 0,
                "output_tokens": 0,
            }

    def _build_formatting_prompt(self, raw_text: str, structured_markdown: str) -> str:
        """
        Build the formatting prompt for AI.

        Args:
            raw_text: Raw text from PDF
            structured_markdown: Structured markdown from OCR

        Returns:
            Formatted prompt string
        """
        prompt = f"""You are a scientific document formatter. Your task is to create a canonical, well-formatted Markdown document by combining raw text from PDF and structured markdown from OCR parser.

INPUTS:
1. Raw text extracted from PDF (preserves original text flow)
2. Structured markdown from OCR (has layout information)

REQUIREMENTS:
1. Preserve the exact text flow and paragraph order from the source
2. Use structured OCR Markdown for headings, tables, figures, and reading order
3. Create clean YAML frontmatter with: title, authors, date, keywords, abstract
4. Maintain proper heading hierarchy (# ## ### ####)
5. Fix broken paragraphs and hyphenation artifacts
6. Preserve HTML tables and their captions as HTML; do not flatten or rebuild their cells
7. Preserve existing <figure>, <img src>, and <figcaption> markup and image URLs
8. Format citations as numbered references [1]
9. Preserve all LaTeX formulas in $ or $$ delimiters exactly
10. Do not invent, translate, or omit document content
11. Ensure proper markdown syntax throughout

OUTPUT: Only the formatted Markdown, no explanations.

---
RAW PDF TEXT:
{raw_text}

---
STRUCTURED MARKDOWN:
{structured_markdown}

---
FORMATTED MARKDOWN:
"""
        return prompt

    def health_check(self) -> bool:
        """
        Check if the AI Agent service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = httpx.get(f"{self.root_url}/health", timeout=5)
            return response.status_code == 200 and response.json().get("status") == "ok"
        except Exception as exc:
            logger.error(f"Health check failed: {exc}")
            return False

    def close(self):
        """Kept for interface compatibility (per-call HTTP client)."""

    def __del__(self):
        self.close()


# Global client instance
_ai_client_instance = None


def get_ai_client(host: Optional[str] = None, port: Optional[int] = None) -> AIModelClient:
    """
    Get or create the global AI Model client instance.

    Args:
        host: AI service host (optional)
        port: AI service port (optional)

    Returns:
        AIModelClient instance
    """
    global _ai_client_instance

    if _ai_client_instance is None:
        _ai_client_instance = AIModelClient(host=host, port=port)

    return _ai_client_instance
