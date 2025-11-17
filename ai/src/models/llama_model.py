"""Llama model implementation using Hugging Face transformers."""

import torch
from loguru import logger
from transformers import AutoModelForCausalLM, AutoTokenizer

from src.config import settings


class LlamaModel:
    """Llama model implementation for text generation."""

    def __init__(self, model_id: str, device: str = "auto"):
        """
        Initialize the Llama model.

        Args:
            model_id: Hugging Face model identifier
            device: Device to run the model on (auto, cpu, cuda)
        """
        self.model_id = model_id
        self.device = self._setup_device(device)
        self.model = None
        self.tokenizer = None

        # Load model and tokenizer
        self._load_model()

    def _setup_device(self, device: str) -> str:
        """
        Setup the computation device.

        Args:
            device: Requested device (auto, cpu, cuda)

        Returns:
            Actual device to use
        """
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
                logger.info(f"CUDA available. Using GPU: {torch.cuda.get_device_name(0)}")
            else:
                device = "cpu"
                logger.info("CUDA not available. Using CPU")
        elif device == "cuda":
            if not torch.cuda.is_available():
                logger.warning("CUDA requested but not available. Falling back to CPU")
                device = "cpu"
            else:
                logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            logger.info("Using CPU")

        return device

    def _load_model(self):
        """Load the model and tokenizer from Hugging Face."""
        try:
            logger.info(f"Loading tokenizer for {self.model_id}")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                cache_dir=str(settings.model_cache_dir),
                trust_remote_code=True,
            )

            # Set pad token if not set
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            logger.info(f"Loading model {self.model_id}")

            # Load model with appropriate settings
            load_kwargs = {
                "cache_dir": str(settings.model_cache_dir),
                "trust_remote_code": True,
                "torch_dtype": torch.float16 if self.device == "cuda" else torch.float32,
            }

            if self.device == "cuda":
                # Use device_map for automatic GPU placement
                load_kwargs["device_map"] = "auto"
            else:
                load_kwargs["low_cpu_mem_usage"] = True

            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                **load_kwargs,
            )

            # Move to device if not using device_map
            if self.device == "cpu":
                self.model = self.model.to(self.device)

            self.model.eval()  # Set to evaluation mode

            logger.info(f"Successfully loaded {self.model_id} on {self.device}")

        except Exception as e:
            logger.error(f"Failed to load model {self.model_id}: {e}")
            raise

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 50,
        repetition_penalty: float = 1.1,
    ) -> dict:
        """
        Generate text based on the prompt.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            repetition_penalty: Repetition penalty

        Returns:
            Dictionary with generated text and metadata
        """
        try:
            # Tokenize input
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                padding=True,
                truncation=True,
            )

            # Move inputs to device
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

            input_length = inputs["input_ids"].shape[1]
            logger.debug(f"Input tokens: {input_length}")

            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    repetition_penalty=repetition_penalty,
                    do_sample=True,
                    pad_token_id=self.tokenizer.pad_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                )

            # Decode output
            generated_tokens = outputs[0][input_length:]  # Remove input tokens
            generated_text = self.tokenizer.decode(
                generated_tokens,
                skip_special_tokens=True,
            )

            output_length = len(generated_tokens)
            logger.debug(f"Generated tokens: {output_length}")

            return {
                "generated_text": generated_text,
                "input_tokens": input_length,
                "output_tokens": output_length,
            }

        except Exception as e:
            logger.error(f"Error during generation: {e}", exc_info=True)
            raise

    def get_max_length(self) -> int:
        """
        Get the maximum context length for this model.

        Returns:
            Maximum context length in tokens
        """
        if hasattr(self.model.config, "max_position_embeddings"):
            return self.model.config.max_position_embeddings
        elif hasattr(self.model.config, "n_positions"):
            return self.model.config.n_positions
        else:
            # Default conservative estimate
            return 2048

    def __del__(self):
        """Cleanup when model is deleted."""
        if self.model is not None:
            del self.model
        if self.tokenizer is not None:
            del self.tokenizer
        if self.device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
