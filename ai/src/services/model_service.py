"""Service for managing and executing AI models."""

from typing import Dict, Optional

from loguru import logger

from src.config import settings
from src.services.model_registry import registry
from src.utils.chunking import TextChunker


class ModelService:
    """Service for loading and running AI models."""

    def __init__(self):
        """Initialize the model service."""
        self.registry = registry
        self.chunker = None

    def _get_model_instance(self, model_id: str):
        """
        Get or load a model instance.

        Args:
            model_id: Model identifier

        Returns:
            Model instance

        Raises:
            ValueError: If model is not registered
            RuntimeError: If model cannot be loaded
        """
        # Check if model is registered
        config = self.registry.get_model_config(model_id)
        if config is None:
            raise ValueError(f"Model not registered: {model_id}")

        # Check if model is already loaded
        model = self.registry.get_loaded_model(model_id)
        if model is not None:
            logger.debug(f"Using cached model: {model_id}")
            return model

        # Load the model
        logger.info(f"Loading model: {model_id}")

        try:
            # Dynamically import the model class
            module_name, class_name = config.model_class.rsplit(".", 1)
            module = __import__(f"src.models.{module_name}", fromlist=[class_name])
            model_class = getattr(module, class_name)

            # Instantiate the model
            model = model_class(model_id=model_id, device=settings.device)

            # Cache the loaded model
            self.registry.set_loaded_model(model_id, model)

            logger.info(f"Successfully loaded model: {model_id}")
            return model

        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            raise RuntimeError(f"Failed to load model: {e}") from e

    def _get_chunker(self, model_id: str):
        """
        Get or create a text chunker for the model.

        Args:
            model_id: Model identifier

        Returns:
            TextChunker instance
        """
        model = self._get_model_instance(model_id)
        tokenizer = getattr(model, "tokenizer", None)

        return TextChunker(
            max_tokens=settings.max_context_length,
            overlap=settings.chunk_overlap,
            tokenizer=tokenizer,
        )

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
    ) -> Dict:
        """
        Generate text using the specified model.

        Args:
            model_id: Model identifier
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            repetition_penalty: Repetition penalty
            enable_chunking: Whether to enable chunking for large prompts

        Returns:
            Dictionary with generation results
        """
        try:
            # Get model instance
            model = self._get_model_instance(model_id)

            # Get model config for defaults
            config = self.registry.get_model_config(model_id)

            # Use defaults if not specified
            max_tokens = max_tokens or config.default_params.get("max_tokens", settings.default_max_tokens)
            temperature = temperature if temperature is not None else config.default_params.get("temperature", settings.default_temperature)
            top_p = top_p if top_p is not None else config.default_params.get("top_p", settings.default_top_p)
            top_k = top_k if top_k is not None else config.default_params.get("top_k", settings.default_top_k)
            repetition_penalty = repetition_penalty if repetition_penalty is not None else settings.default_repetition_penalty

            # Check if chunking is needed
            chunked = False
            num_chunks = 0
            input_tokens = 0

            if enable_chunking:
                chunker = self._get_chunker(model_id)

                if chunker.needs_chunking(prompt):
                    logger.info("Prompt requires chunking")
                    chunks = chunker.chunk_text(prompt)
                    num_chunks = len(chunks)
                    chunked = True

                    # Process each chunk
                    chunk_results = []
                    total_input_tokens = 0
                    total_output_tokens = 0

                    for i, chunk in enumerate(chunks):
                        logger.info(f"Processing chunk {i + 1}/{num_chunks}")

                        result = model.generate(
                            prompt=chunk,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            top_p=top_p,
                            top_k=top_k,
                            repetition_penalty=repetition_penalty,
                        )

                        chunk_results.append(result["generated_text"])
                        total_input_tokens += result.get("input_tokens", 0)
                        total_output_tokens += result.get("output_tokens", 0)

                    # Merge chunk results
                    generated_text = chunker.merge_chunks(chunk_results)
                    input_tokens = total_input_tokens
                    output_tokens = total_output_tokens

                else:
                    # No chunking needed, process directly
                    result = model.generate(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        top_k=top_k,
                        repetition_penalty=repetition_penalty,
                    )
                    generated_text = result["generated_text"]
                    input_tokens = result.get("input_tokens", 0)
                    output_tokens = result.get("output_tokens", 0)
            else:
                # Chunking disabled, process directly
                result = model.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    repetition_penalty=repetition_penalty,
                )
                generated_text = result["generated_text"]
                input_tokens = result.get("input_tokens", 0)
                output_tokens = result.get("output_tokens", 0)

            return {
                "success": True,
                "generated_text": generated_text,
                "message": "Text generated successfully",
                "model_used": model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "chunked": chunked,
                "num_chunks": num_chunks,
            }

        except ValueError as e:
            logger.error(f"Validation error: {e}")
            return {
                "success": False,
                "generated_text": "",
                "message": str(e),
                "model_used": model_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "chunked": False,
                "num_chunks": 0,
            }

        except Exception as e:
            logger.error(f"Error generating text: {e}", exc_info=True)
            return {
                "success": False,
                "generated_text": "",
                "message": f"Error generating text: {str(e)}",
                "model_used": model_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "chunked": False,
                "num_chunks": 0,
            }

    def get_available_models(self, filter_text: Optional[str] = None):
        """
        Get list of available models.

        Args:
            filter_text: Optional filter string

        Returns:
            List of model information dictionaries
        """
        models = self.registry.list_models(filter_text)

        return [
            {
                "model_id": m.model_id,
                "name": m.name,
                "description": m.description,
                "is_loaded": self.registry.is_model_loaded(m.model_id),
                "max_context_length": m.max_context_length,
                "device": settings.device,
            }
            for m in models
        ]


# Global service instance
model_service = ModelService()
