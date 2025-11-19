"""Generic instruction-tuned model implementation using Hugging Face transformers.

This module provides a universal wrapper for instruction-tuned causal language models
from Hugging Face, including but not limited to:
- Llama models (meta-llama/Llama-*)
- Qwen models (Qwen/Qwen*)
- Mistral models
- Any other AutoModelForCausalLM compatible model
"""

import logging
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)

from src.config import settings


class InstructModel:
    """Universal instruction-tuned model implementation for text generation.

    This class provides a generic wrapper around HuggingFace's transformers library
    that can load and run any instruction-tuned causal language model.
    """

    def __init__(self, model_id: str, device: str = "auto"):
        """
        Initialize the instruction-tuned model.

        Args:
            model_id: Hugging Face model identifier (e.g., "Qwen/Qwen2.5-0.5B-Instruct")
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
            # Prepare authentication token if available
            token = settings.hugging_face_token
            if token:
                logger.info(f"Using Hugging Face token for authentication")

            logger.info(f"Loading tokenizer for {self.model_id}")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                cache_dir=str(settings.model_cache_dir),
                trust_remote_code=True,
                token=token,
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
                "token": token,
                "low_cpu_mem_usage": True,  # Always use low CPU mem mode
            }

            if self.device == "cuda":
                # Use device_map for automatic GPU placement with memory limits
                load_kwargs["device_map"] = "auto"
                # Set max memory per device (7GB for GPU, rest for CPU)
                load_kwargs["max_memory"] = {0: "7GiB", "cpu": "8GiB"}
            else:
                # CPU-only mode
                load_kwargs["max_memory"] = {"cpu": "8GiB"}

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
            # Tokenize input with max_length limit to prevent OOM
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=18000,  # Hard limit on input tokens
            )

            # Move inputs to device
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

            input_length = inputs["input_ids"].shape[1]
            logger.info(f"Input tokens: {input_length}")

            # Warn if input is very large
            if input_length > 16000:
                logger.warning(f"Large input ({input_length} tokens) may cause memory issues")

            # Generate with memory-efficient settings
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
                    use_cache=True,  # Use KV cache for efficiency
                    num_beams=1,  # Disable beam search to save memory
                )

            # Decode output
            generated_tokens = outputs[0][input_length:]  # Remove input tokens
            generated_text = self.tokenizer.decode(
                generated_tokens,
                skip_special_tokens=True,
            )

            output_length = len(generated_tokens)
            logger.info(f"Generated tokens: {output_length}")

            # Clear GPU cache after generation
            if self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()

            return {
                "generated_text": generated_text,
                "input_tokens": input_length,
                "output_tokens": output_length,
            }

        except Exception as e:
            logger.error(f"Error during generation: {e}", exc_info=True)
            # Clear cache on error too
            if self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
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
