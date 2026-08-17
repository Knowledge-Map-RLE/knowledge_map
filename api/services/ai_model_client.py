"""HTTP client for the AI Agent microservice (OpenAI-compatible gateway).

The microservice (``ai/``) exposes an OpenAI-compatible ``/v1/chat/completions``
endpoint and forwards requests to configured providers (LM Studio, DeepSeek, ...).
This client keeps the previous gRPC interface so callers (``src/routers/ai_models.py``)
stay unchanged.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class AIModelClient:
    """Client for communicating with the AI Agent microservice via HTTP."""

    def __init__(self):
        """Initialize the AI Agent client."""
        self.host = os.getenv("AI_MODEL_SERVICE_HOST", "127.0.0.1")
        self.port = os.getenv("AI_MODEL_SERVICE_PORT", "50059")
        self.root_url = f"http://{self.host}:{self.port}"
        self.base_url = f"{self.root_url}/v1"

    def generate_text(
        self,
        model_id: str,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        repetition_penalty: Optional[float] = None,
        enable_chunking: bool = True,
        timeout: int = 300,
    ) -> dict:
        """
        Generate text using the AI model.

        Args:
            model_id: Model identifier (e.g., "qwen/qwen3-4b")
            prompt: Input prompt for text generation
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (0.0 to 2.0)
            top_p: Nucleus sampling parameter (0.0 to 1.0)
            top_k: Top-k sampling parameter
            repetition_penalty: Repetition penalty (default 1.0)
            enable_chunking: Kept for interface compatibility (no-op; the gateway
                does not chunk prompts)
            timeout: Request timeout in seconds

        Returns:
            Dictionary with generation results:
            {
                "success": bool,
                "generated_text": str,
                "message": str,
                "model_used": str,
                "input_tokens": int,
                "output_tokens": int,
                "chunked": bool,
                "num_chunks": int
            }

        Raises:
            Exception: If the service is not available
        """
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if top_k is not None:
            payload["top_k"] = top_k
        if repetition_penalty is not None:
            payload["repetition_penalty"] = repetition_penalty

        try:
            logger.info(f"Sending generation request for model: {model_id}")
            response = httpx.post(
                f"{self.base_url}/chat/completions", json=payload, timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"].get("content", "")
            usage = data.get("usage") or {}
            return {
                "success": True,
                "generated_text": content,
                "message": "Text generated successfully",
                "model_used": data.get("model", model_id),
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "chunked": False,
                "num_chunks": 0,
            }
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            logger.error(
                "AI Agent service error: HTTP %s - %s", exc.response.status_code, detail
            )
            return self._failure(model_id, f"AI Agent service error: {detail}")
        except httpx.HTTPError as exc:
            logger.error(f"AI Agent service unavailable: {exc}")
            return self._failure(model_id, f"AI Agent service unavailable: {exc}")
        except Exception as exc:
            logger.error(f"Error calling AI Agent service: {exc}", exc_info=True)
            return self._failure(model_id, f"Error: {str(exc)}")

    def get_models(self, filter_text: Optional[str] = None) -> dict:
        """
        Get list of available models.

        Returns:
            Dictionary with models list:
            {
                "success": bool,
                "message": str,
                "models": [
                    {
                        "model_id": str,
                        "name": str,
                        "description": str,
                        "is_loaded": bool,
                        "max_context_length": int,
                        "device": str
                    }
                ]
            }
        """
        try:
            response = httpx.get(f"{self.base_url}/models", timeout=10)
            response.raise_for_status()
            data = response.json().get("data", [])

            models = []
            for model in data:
                model_id = model.get("id", "")
                if filter_text and filter_text.lower() not in model_id.lower():
                    continue
                models.append({
                    "model_id": model_id,
                    "name": model_id,
                    "description": f"Provider: {model.get('provider', 'unknown')}",
                    "is_loaded": True,
                    "max_context_length": 0,
                    "device": model.get("provider", "remote"),
                })

            return {
                "success": True,
                "message": f"Found {len(models)} models",
                "models": models,
            }
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            logger.error("Failed to get models: HTTP %s - %s", exc.response.status_code, detail)
            return {"success": False, "message": f"AI Agent service error: {detail}", "models": []}
        except httpx.HTTPError as exc:
            logger.error(f"AI Agent service unavailable: {exc}")
            return {"success": False, "message": f"AI Agent service unavailable: {exc}", "models": []}
        except Exception as exc:
            logger.error(f"Error calling AI Agent service: {exc}", exc_info=True)
            return {"success": False, "message": f"Error: {str(exc)}", "models": []}

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

    @staticmethod
    def _failure(model_id: str, message: str) -> dict:
        return {
            "success": False,
            "generated_text": "",
            "message": message,
            "model_used": model_id,
            "input_tokens": 0,
            "output_tokens": 0,
            "chunked": False,
            "num_chunks": 0,
        }

    def __del__(self):
        self.close()


# Global client instance
_ai_model_client = None


def get_ai_model_client() -> AIModelClient:
    """
    Get or create the global AI Model client instance.

    Returns:
        AIModelClient instance
    """
    global _ai_model_client

    if _ai_model_client is None:
        _ai_model_client = AIModelClient()

    return _ai_model_client
