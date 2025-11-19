"""Model registry for managing available AI models."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ModelConfig:
    """Configuration for a specific model."""

    def __init__(
        self,
        model_id: str,
        name: str,
        description: str,
        max_context_length: int,
        model_class: str,
        default_params: Optional[Dict] = None,
    ):
        """
        Initialize model configuration.

        Args:
            model_id: Hugging Face model identifier
            name: Human-readable model name
            description: Model description
            max_context_length: Maximum context length in tokens
            model_class: Python class that implements this model
            default_params: Default generation parameters
        """
        self.model_id = model_id
        self.name = name
        self.description = description
        self.max_context_length = max_context_length
        self.model_class = model_class
        self.default_params = default_params or {}


class ModelRegistry:
    """Registry for managing available AI models."""

    def __init__(self):
        """Initialize the model registry."""
        self._models: Dict[str, ModelConfig] = {}
        self._loaded_models: Dict[str, any] = {}

        # Register default models
        self._register_default_models()

    def _register_default_models(self):
        """Register the default set of models."""
        # Llama 3.2 1B Instruct
        self.register_model(
            ModelConfig(
                model_id="meta-llama/Llama-3.2-1B-Instruct",
                name="Llama 3.2 1B Instruct",
                description="Meta's Llama 3.2 1B instruction-tuned model for text generation",
                max_context_length=128000,
                model_class="instruct_model.InstructModel",
                default_params={
                    "max_tokens": 2048,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 50,
                },
            )
        )

        # Qwen 2.5 0.5B Instruct
        self.register_model(
            ModelConfig(
                model_id="Qwen/Qwen2.5-0.5B-Instruct",
                name="Qwen 2.5 0.5B Instruct",
                description="Alibaba's Qwen 2.5 0.5B instruction-tuned model - fast and lightweight",
                max_context_length=32000,  # Qwen 2.5 supports 32k context
                model_class="instruct_model.InstructModel",
                default_params={
                    "max_tokens": 2048,
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 50,
                },
            )
        )

        # Add more models here as needed
        # Example for future expansion:
        # self.register_model(
        #     ModelConfig(
        #         model_id="meta-llama/Llama-3.2-3B-Instruct",
        #         name="Llama 3.2 3B Instruct",
        #         description="Larger variant of Llama 3.2",
        #         max_context_length=128000,
        #         model_class="instruct_model.InstructModel",
        #     )
        # )

    def register_model(self, config: ModelConfig):
        """
        Register a model in the registry.

        Args:
            config: Model configuration
        """
        self._models[config.model_id] = config
        logger.info(f"Registered model: {config.model_id}")

    def get_model_config(self, model_id: str) -> Optional[ModelConfig]:
        """
        Get configuration for a specific model.

        Args:
            model_id: Model identifier

        Returns:
            Model configuration or None if not found
        """
        return self._models.get(model_id)

    def list_models(self, filter_text: Optional[str] = None) -> List[ModelConfig]:
        """
        List all registered models.

        Args:
            filter_text: Optional filter string to match model ID or name

        Returns:
            List of model configurations
        """
        models = list(self._models.values())

        if filter_text:
            filter_lower = filter_text.lower()
            models = [
                m for m in models
                if filter_lower in m.model_id.lower() or filter_lower in m.name.lower()
            ]

        return models

    def is_model_available(self, model_id: str) -> bool:
        """
        Check if a model is available in the registry.

        Args:
            model_id: Model identifier

        Returns:
            True if model is registered
        """
        return model_id in self._models

    def is_model_loaded(self, model_id: str) -> bool:
        """
        Check if a model is currently loaded in memory.

        Args:
            model_id: Model identifier

        Returns:
            True if model is loaded
        """
        return model_id in self._loaded_models

    def get_loaded_model(self, model_id: str) -> Optional[any]:
        """
        Get a loaded model instance.

        Args:
            model_id: Model identifier

        Returns:
            Model instance or None if not loaded
        """
        return self._loaded_models.get(model_id)

    def set_loaded_model(self, model_id: str, model_instance: any):
        """
        Store a loaded model instance.

        Args:
            model_id: Model identifier
            model_instance: The loaded model instance
        """
        self._loaded_models[model_id] = model_instance
        logger.info(f"Cached loaded model: {model_id}")

    def unload_model(self, model_id: str):
        """
        Unload a model from memory.

        Args:
            model_id: Model identifier
        """
        if model_id in self._loaded_models:
            del self._loaded_models[model_id]
            logger.info(f"Unloaded model: {model_id}")

    def unload_all_models(self):
        """Unload all models from memory."""
        count = len(self._loaded_models)
        self._loaded_models.clear()
        logger.info(f"Unloaded all {count} models")


# Global registry instance
registry = ModelRegistry()
