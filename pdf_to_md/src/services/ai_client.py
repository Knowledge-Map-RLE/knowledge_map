"""gRPC client for AI Model Service."""

import os
import logging
from typing import Optional

import grpc

logger = logging.getLogger(__name__)

# Import generated proto files - will be generated from ai/proto/ai_model.proto
try:
    from src import ai_model_pb2, ai_model_pb2_grpc
except ImportError:
    logger.warning("AI Model proto files not generated yet. Run proto generation script.")
    ai_model_pb2 = None
    ai_model_pb2_grpc = None


class AIModelClient:
    """Client for communicating with AI Model Service via gRPC."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        """
        Initialize the AI Model client.

        Args:
            host: AI service host (default from env or 127.0.0.1)
            port: AI service port (default from env or 50054)
        """
        self.host = host or os.getenv("AI_MODEL_SERVICE_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("AI_MODEL_SERVICE_PORT", "50054"))
        self.channel = None
        self.stub = None

        if ai_model_pb2 is None or ai_model_pb2_grpc is None:
            logger.error("AI Model proto files not available. Cannot initialize client.")
            return

        try:
            self._connect()
        except Exception as e:
            logger.error(f"Failed to connect to AI Model service: {e}")

    def _connect(self):
        """Establish connection to the AI Model service."""
        address = f"{self.host}:{self.port}"
        logger.info(f"Connecting to AI Model service at {address}")

        self.channel = grpc.insecure_channel(
            address,
            options=[
                ("grpc.max_send_message_length", 100 * 1024 * 1024),  # 100 MB
                ("grpc.max_receive_message_length", 100 * 1024 * 1024),  # 100 MB
            ],
        )
        self.stub = ai_model_pb2_grpc.AIModelServiceStub(self.channel)

        logger.info("Connected to AI Model service")

    def format_markdown_chunk(
        self,
        raw_text: str,
        docling_markdown: str,
        model_id: str = "meta-llama/Llama-3.2-1B-Instruct",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        timeout: int = 600,
    ) -> dict:
        """
        Format a markdown chunk using AI.

        Args:
            raw_text: Raw text extracted from PDF (preserves original flow)
            docling_markdown: Structured markdown from Docling
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

        Raises:
            Exception: If the service is not available or request fails
        """
        if self.stub is None:
            raise Exception("AI Model service not connected. Check proto files and service availability.")

        # Construct the prompt
        prompt = self._build_formatting_prompt(raw_text, docling_markdown)

        try:
            # Create request
            request = ai_model_pb2.GenerateTextRequest(
                model_id=model_id,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
                repetition_penalty=1.1,
                enable_chunking=False,  # We handle chunking at a higher level
            )

            logger.info(f"Sending formatting request to AI service (model: {model_id})")

            # Make gRPC call
            response = self.stub.GenerateText(request, timeout=timeout)

            # Convert response to dict
            result = {
                "success": response.success,
                "formatted_text": response.generated_text if response.success else "",
                "message": response.message,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }

            if response.success:
                logger.info(
                    f"Formatting successful: {response.output_tokens} tokens generated "
                    f"({response.input_tokens} input tokens)"
                )
            else:
                logger.warning(f"Formatting failed: {response.message}")

            return result

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            return {
                "success": False,
                "formatted_text": "",
                "message": f"gRPC error: {e.details()}",
                "input_tokens": 0,
                "output_tokens": 0,
            }

        except Exception as e:
            logger.error(f"Error calling AI Model service: {e}", exc_info=True)
            return {
                "success": False,
                "formatted_text": "",
                "message": f"Error: {str(e)}",
                "input_tokens": 0,
                "output_tokens": 0,
            }

    def _build_formatting_prompt(self, raw_text: str, docling_markdown: str) -> str:
        """
        Build the formatting prompt for AI.

        Args:
            raw_text: Raw text from PDF
            docling_markdown: Structured markdown from Docling

        Returns:
            Formatted prompt string
        """
        prompt = f"""You are a scientific document formatter. Your task is to create a canonical, well-formatted Markdown document by combining raw text from PDF and structured markdown from Docling parser.

INPUTS:
1. Raw text extracted from PDF (preserves original text flow)
2. Structured markdown from Docling (has layout information)

REQUIREMENTS:
1. Preserve the EXACT text flow and paragraph order from raw PDF text
2. Use Docling markdown for structure hints (headings, tables, images)
3. Create clean YAML frontmatter with: title, authors, date, keywords, abstract
4. Maintain proper heading hierarchy (# ## ### ####)
5. Fix broken paragraphs and hyphenation artifacts
6. Convert tables to HTML with <caption> tags
7. Convert images to HTML <figure> with <figcaption> tags
8. Format citations as numbered references [1]
9. Preserve LaTeX math in $ or $$ delimiters
10. Ensure proper markdown syntax throughout

OUTPUT: Only the formatted Markdown, no explanations.

---
RAW PDF TEXT:
{raw_text}

---
DOCLING MARKDOWN:
{docling_markdown}

---
FORMATTED MARKDOWN:
"""
        return prompt

    def health_check(self) -> bool:
        """
        Check if the AI Model service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        if self.stub is None:
            return False

        try:
            request = ai_model_pb2.HealthCheckRequest(service="ai_model")
            response = self.stub.HealthCheck(request, timeout=5)
            return response.status == "healthy"

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def close(self):
        """Close the gRPC channel."""
        if self.channel:
            self.channel.close()
            logger.info("AI Model client connection closed")

    def __del__(self):
        """Cleanup on deletion."""
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
