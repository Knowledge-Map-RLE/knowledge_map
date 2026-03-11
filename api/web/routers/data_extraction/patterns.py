"""
Pattern Generation Router

Endpoints for generating and managing patterns from linguistic annotations.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import logging

from services.pattern_service import PatternService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patterns", tags=["patterns"])


class GeneratePatternsRequest(BaseModel):
    batch_size: Optional[int] = 100
    clear_existing: Optional[bool] = True


class PatternStatistics(BaseModel):
    patterns: int
    properties: int
    relationships: int


@router.post("/generate")
async def generate_patterns(request: GeneratePatternsRequest):
    """
    Generate patterns from multilevel NLP annotations.
    Returns a Server-Sent Events (SSE) stream with progress updates.
    """
    pattern_service = PatternService()

    async def event_generator():
        try:
            for progress in pattern_service.generate_patterns(
                batch_size=request.batch_size,
                clear_existing=request.clear_existing
            ):
                # Send progress update as SSE
                yield f"data: {json.dumps(progress)}\n\n"

        except Exception as e:
            logger.error(f"Error generating patterns: {e}", exc_info=True)
            error_data = {
                "stage": "error",
                "message": str(e)
            }
            yield f"data: {json.dumps(error_data)}\n\n"

        finally:
            pattern_service.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@router.get("/statistics", response_model=PatternStatistics)
async def get_pattern_statistics():
    """Get statistics about existing patterns"""
    pattern_service = PatternService()

    try:
        stats = pattern_service._get_statistics()
        return PatternStatistics(**stats)

    except Exception as e:
        logger.error(f"Error getting pattern statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        pattern_service.close()


@router.delete("/clear")
async def clear_patterns():
    """Clear all existing patterns"""
    pattern_service = PatternService()

    try:
        pattern_service.clear_patterns()
        return {"message": "Patterns cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing patterns: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        pattern_service.close()
