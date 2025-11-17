"""
Action Chains Router

Endpoints for building and querying action chains from patterns.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import logging

from services.action_chain_service import ActionChainService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patterns/action-chains", tags=["action-chains"])


class BuildActionChainsRequest(BaseModel):
    clear_existing: Optional[bool] = True


class ActionChainStatistics(BaseModel):
    total_verbs: int
    action_sequences: int
    entity_links: int
    total_sequences: int
    sequence_types: List[Dict[str, Any]]
    avg_confidence: float


@router.post("/build")
async def build_action_chains(request: BuildActionChainsRequest):
    """
    Build action chains from verb patterns.
    Returns a Server-Sent Events (SSE) stream with progress updates.
    """
    action_chain_service = ActionChainService()

    async def event_generator():
        try:
            # Clear existing if requested
            if request.clear_existing:
                action_chain_service.clear_action_chains()
                yield f"data: {json.dumps({'stage': 'cleared', 'message': 'Cleared existing action chains'})}\n\n"

            # Build action chains with progress updates
            for progress in action_chain_service.build_action_chains():
                yield f"data: {json.dumps(progress)}\n\n"

        except Exception as e:
            logger.error(f"Error building action chains: {e}", exc_info=True)
            error_data = {
                "stage": "error",
                "message": str(e)
            }
            yield f"data: {json.dumps(error_data)}\n\n"

        finally:
            action_chain_service.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


@router.get("/statistics", response_model=ActionChainStatistics)
async def get_action_chain_statistics():
    """Get statistics about existing action chains"""
    action_chain_service = ActionChainService()

    try:
        stats = action_chain_service._get_statistics()

        # Get verb count
        verbs = action_chain_service.extract_verb_patterns()

        # Get entity links count
        with action_chain_service.driver.session() as session:
            result = session.run("MATCH ()-[r:SAME_ENTITY]-() RETURN count(r) as count")
            entity_links = result.single()['count']

        return ActionChainStatistics(
            total_verbs=len(verbs),
            action_sequences=stats.get('total_sequences', 0),
            entity_links=entity_links,
            total_sequences=stats.get('total_sequences', 0),
            sequence_types=stats.get('sequence_types', []),
            avg_confidence=stats.get('avg_confidence', 0.0)
        )

    except Exception as e:
        logger.error(f"Error getting action chain statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        action_chain_service.close()


@router.get("/sequences")
async def get_action_sequences(limit: int = 100, skip: int = 0):
    """Get action sequences with pagination"""
    action_chain_service = ActionChainService()

    try:
        with action_chain_service.driver.session() as session:
            query = """
            MATCH (p1:Pattern)-[r:ACTION_SEQUENCE]->(p2:Pattern)
            MATCH (p1)-[:HAS_TEXT]->(t1:PatternProperty {type: 'text'})
            MATCH (p2)-[:HAS_TEXT]->(t2:PatternProperty {type: 'text'})

            RETURN
                p1.pattern_id as from_id,
                p2.pattern_id as to_id,
                t1.value as from_verb,
                t2.value as to_verb,
                r.sequence_type as sequence_type,
                r.confidence as confidence,
                r.evidence as evidence
            ORDER BY r.confidence DESC
            SKIP $skip
            LIMIT $limit
            """

            result = session.run(query, skip=skip, limit=limit)

            sequences = []
            for record in result:
                sequences.append({
                    "from_id": record['from_id'],
                    "to_id": record['to_id'],
                    "from_verb": record['from_verb'],
                    "to_verb": record['to_verb'],
                    "sequence_type": record['sequence_type'],
                    "confidence": record['confidence'],
                    "evidence": record['evidence']
                })

            return {
                "sequences": sequences,
                "total": len(sequences),
                "skip": skip,
                "limit": limit
            }

    except Exception as e:
        logger.error(f"Error getting action sequences: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        action_chain_service.close()


@router.get("/chains")
async def get_action_chains():
    """
    Get complete action chains (paths through the graph) with subjects and objects
    """
    action_chain_service = ActionChainService()

    try:
        with action_chain_service.driver.session() as session:
            # Find all maximal paths (chains that don't have incoming edges)
            query = """
            MATCH path = (start:Pattern)-[:ACTION_SEQUENCE*]->(end:Pattern)
            WHERE NOT ()-[:ACTION_SEQUENCE]->(start)

            WITH path, length(path) as chain_length
            WHERE chain_length >= 2

            WITH path, chain_length, nodes(path) as path_nodes,
                 [r in relationships(path) | {
                     type: r.sequence_type,
                     confidence: r.confidence
                 }] as relations

            // For each node in the path, get verb text, subject, and object
            WITH path, chain_length, relations,
                 [node IN path_nodes |
                    {
                        node: node,
                        verb: [(node)-[:HAS_TEXT]->(t:PatternProperty {type: 'text'}) | t.value][0],
                        subject: [(node)<-[:LINGUISTIC_RELATION {relation_type: 'nsubj'}]-(s:Pattern)-[:HAS_TEXT]->(st:PatternProperty {type: 'text'}) | st.value][0],
                        object: [(node)<-[r:LINGUISTIC_RELATION]-(o:Pattern)-[:HAS_TEXT]->(ot:PatternProperty {type: 'text'}) WHERE r.relation_type IN ['obj', 'dobj'] | ot.value][0]
                    }
                 ] as verb_data

            RETURN
                verb_data,
                relations,
                chain_length,
                reduce(sum = 0.0, r in relations | sum + r.confidence) / size(relations) as avg_confidence
            ORDER BY chain_length DESC, avg_confidence DESC
            LIMIT 50
            """

            result = session.run(query)

            chains = []
            for record in result:
                # Clean verb_data to remove 'node' field
                verb_data_cleaned = [
                    {
                        'verb': vd.get('verb'),
                        'subject': vd.get('subject'),
                        'object': vd.get('object')
                    }
                    for vd in record['verb_data']
                ]

                chains.append({
                    "verb_data": verb_data_cleaned,
                    "relations": record['relations'],
                    "chain_length": record['chain_length'],
                    "avg_confidence": record['avg_confidence']
                })

            return {
                "chains": chains,
                "total": len(chains)
            }

    except Exception as e:
        logger.error(f"Error getting action chains: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        action_chain_service.close()


@router.delete("/clear")
async def clear_action_chains():
    """Clear all action chains and entity links"""
    action_chain_service = ActionChainService()

    try:
        action_chain_service.clear_action_chains()
        return {"message": "Action chains cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing action chains: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        action_chain_service.close()
