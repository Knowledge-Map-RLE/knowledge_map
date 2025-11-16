"""Роутер для NLP анализа и автоаннотации"""
import logging
import asyncio
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException

from src.schemas.api import NLPAnalyzeRequest
from services.annotation_service import AnnotationService
from services.nlp_service import NLPService
from services.multilevel_nlp_service import MultiLevelNLPService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nlp"])
annotation_service = AnnotationService()
nlp_service = NLPService()
multilevel_nlp_service = MultiLevelNLPService()


@router.post("/nlp/analyze")
async def analyze_text(request: NLPAnalyzeRequest):
    """
    NLP анализ текста с помощью spaCy
    Если указаны start и end, анализируется только выделенный фрагмент
    """
    try:
        if request.start is not None and request.end is not None:
            # Анализ выделенного фрагмента для подсказок
            return nlp_service.analyze_selection(request.text, request.start, request.end)
        else:
            # Полный анализ текста
            return nlp_service.analyze_text(request.text)
    except Exception as e:
        logger.error(f"Ошибка NLP анализа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка NLP анализа: {str(e)}")


@router.post("/documents/{doc_id}/auto-annotate")
async def auto_annotate_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    processors: list[str] = ["spacy"],
    annotation_types: list[str] | None = None,
    min_confidence: float = 0.7
):
    """
    Автоматическая аннотация документа с помощью NLP процессоров.

    Args:
        doc_id: ID документа
        processors: Список процессоров для использования (по умолчанию: ["spacy"])
        annotation_types: Фильтр типов аннотаций (None = все типы)
        min_confidence: Минимальная уверенность модели (0.0-1.0)

    Returns:
        Количество созданных аннотаций и связей
    """
    try:
        result = await annotation_service.auto_annotate_document(
            doc_id=doc_id,
            processors=processors,
            annotation_types=annotation_types,
            min_confidence=min_confidence
        )
        return result
    except Exception as e:
        logger.error(f"Ошибка автоаннотации документа {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка автоаннотации: {str(e)}")


@router.post("/documents/{doc_id}/auto-annotate/batch")
async def auto_annotate_batch(
    doc_id: str,
    background_tasks: BackgroundTasks,
    processors: list[str] = ["spacy"],
    annotation_types: list[str] | None = None,
    min_confidence: float = 0.7,
    chunk_size: int = 5000
):
    """
    Фоновая автоаннотация большого документа частями.

    Args:
        doc_id: ID документа
        processors: Список процессоров
        annotation_types: Фильтр типов
        min_confidence: Минимальная уверенность
        chunk_size: Размер чанка для обработки

    Returns:
        Сообщение о запуске фоновой задачи
    """

    def process_in_background():
        try:
            logger.info(f"Запуск фоновой автоаннотации документа {doc_id}")
            # Синхронная версия для фоновой задачи
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                annotation_service.auto_annotate_document(
                    doc_id=doc_id,
                    processors=processors,
                    annotation_types=annotation_types,
                    min_confidence=min_confidence
                )
            )
            logger.info(f"Фоновая автоаннотация завершена: {result}")
        except Exception as e:
            logger.error(f"Ошибка в фоновой автоаннотации: {e}")

    background_tasks.add_task(process_in_background)

    return {
        "success": True,
        "message": f"Автоаннотация документа {doc_id} запущена в фоне",
        "doc_id": doc_id
    }


@router.get("/nlp/supported-types")
async def get_supported_types():
    """
    Получить все поддерживаемые типы аннотаций от всех процессоров.

    Returns:
        Словарь категорий и типов аннотаций
    """
    try:
        return nlp_service.get_all_supported_types()
    except Exception as e:
        logger.error(f"Ошибка получения поддерживаемых типов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.post("/documents/{doc_id}/analyze-multilevel")
async def analyze_document_multilevel(
    doc_id: str,
    enable_voting: bool = True,
    max_level: int = 3,
    create_annotations: bool = True,
    min_confidence: float = 0.8
):
    """
    Multi-level NLP analysis with voting and confidence scores.

    Args:
        doc_id: Document ID
        enable_voting: Use voting between multiple processors (spaCy + NLTK)
        max_level: Maximum analysis level (1-3)
        create_annotations: Automatically create annotations in database
        min_confidence: Minimum confidence threshold for annotations

    Returns:
        Analysis results with annotations and graph data for visualization
    """
    try:
        # Get document from Neo4j
        from src.models import PDFDocument
        from services import settings
        from services.s3_client import get_s3_client

        document = PDFDocument.nodes.get_or_none(uid=doc_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Get markdown text from S3
        s3_client = get_s3_client()
        bucket = settings.S3_BUCKET_NAME
        md_key = f"documents/{doc_id}/{doc_id}.md"

        if not await s3_client.object_exists(bucket, md_key):
            raise HTTPException(status_code=400, detail="No markdown text available in S3")

        markdown_text = await s3_client.download_text(bucket, md_key)
        if not markdown_text:
            raise HTTPException(status_code=400, detail="Markdown text is empty")

        logger.info(f"Starting multi-level analysis for document {doc_id}, text length: {len(markdown_text)}")

        # Analyze text to get UnifiedDocument (with filtering applied)
        doc = multilevel_nlp_service.analyze_text_to_document(
            text=markdown_text,
            doc_id=doc_id,
            enable_voting=enable_voting,
            max_level=max_level
        )

        # Convert to dict for response
        analyzer = multilevel_nlp_service._get_analyzer(enable_voting, max_level)
        result = analyzer.to_dict(doc)
        summary = analyzer.get_summary(doc)
        result['summary'] = summary.get('statistics', {})
        result['graph'] = multilevel_nlp_service._prepare_graph_data(doc)

        # Create annotations if requested
        if create_annotations:
            from src.models import MarkdownAnnotation

            # Create annotations from the already analyzed document
            annotations_data = multilevel_nlp_service.create_annotations_for_database(
                doc,
                confidence_threshold=min_confidence
            )

            # Save to Neo4j
            created_annotations = []
            annotation_uid_map = {}  # (sent_idx, token_idx) -> uid

            for ann_data in annotations_data:
                annotation = MarkdownAnnotation(
                    text=ann_data['text'],
                    annotation_type=ann_data['annotation_type'],
                    start_offset=ann_data['start_offset'],
                    end_offset=ann_data['end_offset'],
                    color=ann_data['color'],
                    metadata=ann_data['metadata'],
                    confidence=ann_data['confidence'],
                    source=ann_data['source'],
                    processor_version=ann_data['processor_version']
                ).save()

                # Connect to document
                annotation.document.connect(document)

                # Store for relations - use metadata to get sent_idx and token_idx
                if 'sent_idx' in ann_data['metadata'] and 'token_idx' in ann_data['metadata']:
                    sent_idx = ann_data['metadata']['sent_idx']
                    token_idx = ann_data['metadata']['token_idx']
                    annotation_uid_map[(sent_idx, token_idx)] = annotation.uid

                created_annotations.append({
                    'uid': annotation.uid,
                    'text': annotation.text,
                    'type': annotation.annotation_type,
                    'confidence': annotation.confidence,
                    'start': annotation.start_offset,
                    'end': annotation.end_offset,
                    'color': annotation.color,
                })

            # Create relations (dependencies) between annotations
            relations_data = multilevel_nlp_service.create_relations_for_database(
                doc,
                annotation_uid_map,
                confidence_threshold=min_confidence
            )

            created_relations = []
            for rel_data in relations_data:
                # Get source and target annotations
                source_ann = MarkdownAnnotation.nodes.get(uid=rel_data['source_uid'])
                target_ann = MarkdownAnnotation.nodes.get(uid=rel_data['target_uid'])

                # Create relation using Neo4j relationship
                rel = source_ann.relations_to.connect(
                    target_ann,
                    {
                        'relation_type': rel_data['relation_type'],
                        'metadata': rel_data['metadata'],
                        'created_date': datetime.utcnow()
                    }
                )

                created_relations.append({
                    'type': rel_data['relation_type'],
                    'source': rel_data['source_uid'],
                    'target': rel_data['target_uid'],
                    'confidence': rel_data['confidence'],
                })

            result['created_annotations'] = created_annotations
            result['annotations_count'] = len(created_annotations)
            result['created_relations'] = created_relations
            result['relations_count'] = len(created_relations)

            logger.info(f"Created {len(created_annotations)} annotations and {len(created_relations)} relations for document {doc_id}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in multi-level analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.get("/nlp/analyzer-info")
async def get_multilevel_analyzer_info():
    """
    Get information about multi-level analyzer configuration.

    Returns:
        Analyzer settings and available levels
    """
    try:
        if multilevel_nlp_service.analyzer:
            return multilevel_nlp_service.analyzer.get_info()
        else:
            return {
                "status": "not_initialized",
                "message": "Analyzer will be initialized on first use"
            }
    except Exception as e:
        logger.error(f"Error getting analyzer info: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
