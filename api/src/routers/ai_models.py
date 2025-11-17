"""Router for AI Models endpoints."""

from fastapi import APIRouter, HTTPException, Path, status
from loguru import logger

from services.ai_model_client import get_ai_model_client
from src.schemas.ai_models import (
    GenerateTextRequest,
    GenerateTextResponse,
    GetModelsResponse,
)

router = APIRouter(prefix="/ai", tags=["AI Models"])


@router.post(
    "/{model_id:path}/",
    response_model=GenerateTextResponse,
    summary="Generate text using AI model",
    description="""
    Generate text using the specified AI model.

    The model_id should be a valid Hugging Face model identifier (e.g., "meta-llama/Llama-3.2-1B-Instruct").

    Large prompts are automatically chunked and processed in parts if enable_chunking is True.

    Example usage:
    - POST /api/ai/meta-llama/Llama-3.2-1B-Instruct/
    """,
)
async def generate_text(
    model_id: str = Path(
        ...,
        description="Model identifier (e.g., 'meta-llama/Llama-3.2-1B-Instruct')",
        example="meta-llama/Llama-3.2-1B-Instruct",
    ),
    request: GenerateTextRequest = ...,
) -> GenerateTextResponse:
    """
    Generate text using the specified AI model.

    Args:
        model_id: Model identifier (from path)
        request: Generation request with prompt and parameters

    Returns:
        Generation response with generated text and metadata

    Raises:
        HTTPException: If the AI service is unavailable or generation fails
    """
    try:
        logger.info(f"Received generation request for model: {model_id}")

        # Get AI model client
        client = get_ai_model_client()

        # Generate text
        result = client.generate_text(
            model_id=model_id,
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            repetition_penalty=request.repetition_penalty,
            enable_chunking=request.enable_chunking,
        )

        # Check if generation was successful
        if not result["success"]:
            logger.error(f"Generation failed: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"],
            )

        logger.info(
            f"Generation successful: {result['output_tokens']} tokens, "
            f"chunked: {result['chunked']}"
        )

        return GenerateTextResponse(**result)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error in generate_text endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get(
    "/models",
    response_model=GetModelsResponse,
    summary="Get available models",
    description="Get a list of all available AI models with their information.",
)
async def get_models(
    filter: str = None,
) -> GetModelsResponse:
    """
    Get list of available AI models.

    Args:
        filter: Optional filter string to match model ID or name

    Returns:
        Response with list of available models

    Raises:
        HTTPException: If the AI service is unavailable
    """
    try:
        logger.info("Received request to get available models")

        # Get AI model client
        client = get_ai_model_client()

        # Get models
        result = client.get_models(filter_text=filter)

        if not result["success"]:
            logger.error(f"Failed to get models: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"],
            )

        logger.info(f"Found {len(result['models'])} models")

        return GetModelsResponse(**result)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error in get_models endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get(
    "/health",
    summary="Check AI service health",
    description="Check if the AI Model service is healthy and available.",
)
async def health_check():
    """
    Check AI Model service health.

    Returns:
        Health status

    Raises:
        HTTPException: If the AI service is unavailable
    """
    try:
        client = get_ai_model_client()
        is_healthy = client.health_check()

        if not is_healthy:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI Model service is not healthy",
            )

        return {
            "status": "healthy",
            "service": "ai_model",
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error in health check: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI Model service unavailable: {str(e)}",
        )
