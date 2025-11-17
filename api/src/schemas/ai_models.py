"""Pydantic schemas for AI Models endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class GenerateTextRequest(BaseModel):
    """Request schema for text generation."""

    prompt: str = Field(
        ...,
        description="Input prompt for text generation",
        min_length=1,
    )
    max_tokens: Optional[int] = Field(
        None,
        description="Maximum number of tokens to generate",
        ge=1,
        le=8192,
    )
    temperature: Optional[float] = Field(
        None,
        description="Sampling temperature (0.0 to 2.0)",
        ge=0.0,
        le=2.0,
    )
    top_p: Optional[float] = Field(
        None,
        description="Nucleus sampling parameter (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    top_k: Optional[int] = Field(
        None,
        description="Top-k sampling parameter",
        ge=1,
        le=100,
    )
    repetition_penalty: Optional[float] = Field(
        None,
        description="Repetition penalty (1.0 = no penalty)",
        ge=0.0,
        le=2.0,
    )
    enable_chunking: bool = Field(
        True,
        description="Enable automatic chunking for large prompts",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "prompt": "Explain quantum computing in simple terms.",
                    "max_tokens": 512,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
            ]
        }
    }


class GenerateTextResponse(BaseModel):
    """Response schema for text generation."""

    success: bool = Field(..., description="Whether the generation was successful")
    generated_text: str = Field(..., description="Generated text")
    message: str = Field(..., description="Status message or error description")
    model_used: str = Field(..., description="Model that was used for generation")
    input_tokens: int = Field(..., description="Number of input tokens", ge=0)
    output_tokens: int = Field(..., description="Number of generated tokens", ge=0)
    chunked: bool = Field(..., description="Whether chunking was applied")
    num_chunks: int = Field(..., description="Number of chunks if chunking was applied", ge=0)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "generated_text": "Quantum computing is...",
                    "message": "Text generated successfully",
                    "model_used": "meta-llama/Llama-3.2-1B-Instruct",
                    "input_tokens": 128,
                    "output_tokens": 512,
                    "chunked": False,
                    "num_chunks": 0,
                }
            ]
        }
    }


class ModelInfo(BaseModel):
    """Information about an available model."""

    model_id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Human-readable model name")
    description: str = Field(..., description="Model description")
    is_loaded: bool = Field(..., description="Whether the model is currently loaded")
    max_context_length: int = Field(..., description="Maximum context length in tokens", ge=0)
    device: str = Field(..., description="Device the model is running on (cpu, cuda, etc.)")


class GetModelsResponse(BaseModel):
    """Response schema for getting available models."""

    success: bool = Field(..., description="Whether the request was successful")
    message: str = Field(..., description="Status message")
    models: list[ModelInfo] = Field(..., description="List of available models")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "message": "Found 1 models",
                    "models": [
                        {
                            "model_id": "meta-llama/Llama-3.2-1B-Instruct",
                            "name": "Llama 3.2 1B Instruct",
                            "description": "Meta's Llama 3.2 1B instruction-tuned model",
                            "is_loaded": True,
                            "max_context_length": 128000,
                            "device": "cuda",
                        }
                    ],
                }
            ]
        }
    }
