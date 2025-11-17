"""gRPC client for AI Model Service."""

import os
from typing import Optional

import grpc
from loguru import logger

# Import generated proto files
try:
    from utils.generated import ai_model_pb2, ai_model_pb2_grpc
except ImportError:
    logger.warning("AI Model proto files not generated. Run proto generation script.")
    ai_model_pb2 = None
    ai_model_pb2_grpc = None


class AIModelClient:
    """Client for communicating with AI Model Service via gRPC."""

    def __init__(self):
        """Initialize the AI Model client."""
        self.host = os.getenv("AI_MODEL_SERVICE_HOST", "127.0.0.1")
        self.port = os.getenv("AI_MODEL_SERVICE_PORT", "50054")
        self.channel = None
        self.stub = None

        if ai_model_pb2 is None or ai_model_pb2_grpc is None:
            logger.error("AI Model proto files not available")
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
            model_id: Model identifier (e.g., "meta-llama/Llama-3.2-1B-Instruct")
            prompt: Input prompt for text generation
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (0.0 to 2.0)
            top_p: Nucleus sampling parameter (0.0 to 1.0)
            top_k: Top-k sampling parameter
            repetition_penalty: Repetition penalty (default 1.0)
            enable_chunking: Whether to enable chunking for large prompts
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
            Exception: If the service is not available or request fails
        """
        if self.stub is None:
            raise Exception("AI Model service not connected")

        try:
            # Create request
            request = ai_model_pb2.GenerateTextRequest(
                model_id=model_id,
                prompt=prompt,
                enable_chunking=enable_chunking,
            )

            # Add optional parameters if provided
            if max_tokens is not None:
                request.max_tokens = max_tokens
            if temperature is not None:
                request.temperature = temperature
            if top_p is not None:
                request.top_p = top_p
            if top_k is not None:
                request.top_k = top_k
            if repetition_penalty is not None:
                request.repetition_penalty = repetition_penalty

            logger.info(f"Sending generation request for model: {model_id}")

            # Make gRPC call
            response = self.stub.GenerateText(request, timeout=timeout)

            # Convert response to dict
            result = {
                "success": response.success,
                "generated_text": response.generated_text,
                "message": response.message,
                "model_used": response.model_used,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "chunked": response.chunked,
                "num_chunks": response.num_chunks,
            }

            if response.success:
                logger.info(
                    f"Generation successful: {response.output_tokens} tokens generated"
                )
            else:
                logger.warning(f"Generation failed: {response.message}")

            return result

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            return {
                "success": False,
                "generated_text": "",
                "message": f"gRPC error: {e.details()}",
                "model_used": model_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "chunked": False,
                "num_chunks": 0,
            }

        except Exception as e:
            logger.error(f"Error calling AI Model service: {e}", exc_info=True)
            return {
                "success": False,
                "generated_text": "",
                "message": f"Error: {str(e)}",
                "model_used": model_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "chunked": False,
                "num_chunks": 0,
            }

    def get_models(self, filter_text: Optional[str] = None) -> dict:
        """
        Get list of available models.

        Args:
            filter_text: Optional filter string

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
        if self.stub is None:
            raise Exception("AI Model service not connected")

        try:
            request = ai_model_pb2.GetModelsRequest()
            if filter_text:
                request.filter = filter_text

            response = self.stub.GetModels(request, timeout=10)

            models = []
            for model in response.models:
                models.append({
                    "model_id": model.model_id,
                    "name": model.name,
                    "description": model.description,
                    "is_loaded": model.is_loaded,
                    "max_context_length": model.max_context_length,
                    "device": model.device,
                })

            return {
                "success": response.success,
                "message": response.message,
                "models": models,
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            return {
                "success": False,
                "message": f"gRPC error: {e.details()}",
                "models": [],
            }

        except Exception as e:
            logger.error(f"Error calling AI Model service: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "models": [],
            }

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
