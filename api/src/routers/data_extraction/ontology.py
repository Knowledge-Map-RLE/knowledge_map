"""
Ontology Generation API Routes

Endpoints for generating and managing ontologies from NLP annotations.
Ontologies are semantic networks combining syntactic dependencies and semantic relations.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from services.ontology_service import OntologyService
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ontology", tags=["ontology"])


class GenerateOntologiesRequest:
    """Request model for ontology generation"""
    batch_size: int = 100
    clear_existing: bool = True


@router.post("/generate")
async def generate_ontologies(request: dict = None):
    """
    Generate ontologies from multilevel NLP annotations.

    Streams progress updates via Server-Sent Events (SSE).

    Query Parameters:
    - batch_size: Number of tokens to process in each batch (default: 100)
    - clear_existing: Whether to clear existing ontologies (default: true)

    Returns:
    - Stream of SSE events with progress updates
    - Each event contains: total, processed, percentage, stage, message
    - Final event includes statistics (ontologies, properties, relationships)

    Example stages:
    - clearing: Removing existing ontologies
    - creating_ontologies: Creating ontology nodes from tokens
    - creating_relationships: Creating syntactic relationships
    - complete: Finished successfully
    """

    if request is None:
        request = {}

    batch_size = request.get("batch_size", 100)
    clear_existing = request.get("clear_existing", True)

    ontology_service = OntologyService()

    async def event_generator():
        try:
            for progress in ontology_service.generate_ontologies(
                batch_size=batch_size,
                clear_existing=clear_existing
            ):
                # SSE format: "data: {json}\n\n"
                yield f"data: {json.dumps(progress)}\n\n"
        except Exception as e:
            logger.error(f"Error generating ontologies: {e}")
            error_data = {
                "stage": "error",
                "message": str(e),
                "error": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
        finally:
            ontology_service.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/statistics")
async def get_ontology_statistics():
    """
    Get statistics about existing ontologies.

    Returns:
    - ontologies: Number of ontology nodes
    - properties: Number of ontology property nodes
    - relationships: Number of syntactic relationships
    """
    ontology_service = OntologyService()

    try:
        stats = ontology_service._get_statistics()
        return {
            "success": True,
            "data": {
                "ontologies": stats["ontologies"],
                "properties": stats["properties"],
                "relationships": stats["relationships"]
            }
        }
    except Exception as e:
        logger.error(f"Error getting ontology statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ontology_service.close()


@router.delete("/clear")
async def clear_ontologies():
    """
    Clear all existing ontologies and their properties.

    WARNING: This operation cannot be undone.
    Make sure you have backups if needed.

    Returns:
    - success: Boolean indicating if operation succeeded
    - message: Human-readable status message
    """
    ontology_service = OntologyService()

    try:
        ontology_service.clear_ontologies()
        return {
            "success": True,
            "message": "All ontologies have been cleared"
        }
    except Exception as e:
        logger.error(f"Error clearing ontologies: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ontology_service.close()


@router.get("/count")
async def get_ontology_count():
    """
    Get the count of tokens available for ontology generation.

    Returns:
    - count: Number of tokens with multilevel_nlp annotations
    """
    ontology_service = OntologyService()

    try:
        count = ontology_service.get_token_count()
        return {
            "success": True,
            "count": count,
            "message": f"Found {count} tokens for ontology generation"
        }
    except Exception as e:
        logger.error(f"Error getting token count: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ontology_service.close()


@router.get("/{ontology_id}")
async def get_ontology(ontology_id: str):
    """
    Get a specific ontology with all its properties.

    Path Parameters:
    - ontology_id: UUID of the ontology node

    Returns:
    - Ontology object with all properties and relationships
    """
    ontology_service = OntologyService()

    try:
        ontology = ontology_service.get_ontology_with_properties(ontology_id)
        if not ontology:
            raise HTTPException(status_code=404, detail=f"Ontology {ontology_id} not found")

        return {
            "success": True,
            "data": ontology
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ontology {ontology_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ontology_service.close()
