"""Роутер для NLP анализа и автоаннотации"""
import json
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
            return await nlp_service.analyze_selection(request.text, request.start, request.end)
        else:
            # Полный анализ текста
            return await nlp_service.analyze_text(request.text)
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
        return await nlp_service.get_all_supported_types()
    except Exception as e:
        logger.error(f"Ошибка получения поддерживаемых типов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


async def _run_multilevel_analysis(
    doc_id: str,
    enable_voting: bool,
    max_level: int,
    create_annotations: bool,
    min_confidence: float
):
    """Фоновая задача: полный NLP анализ + сохранение аннотаций."""
    try:
        from src.models import PDFDocument
        from services import settings
        from services.s3_client import get_s3_client

        document = PDFDocument.nodes.get_or_none(uid=doc_id)
        if not document:
            logger.error(f"Background NLP: document {doc_id} not found")
            return

        s3_client = get_s3_client()
        bucket = settings.S3_BUCKET_NAME

        md_key = None
        if document.user_md_s3_key:
            md_key = document.user_md_s3_key
        elif document.formatted_md_s3_key:
            md_key = document.formatted_md_s3_key
        elif document.docling_raw_md_s3_key:
            md_key = document.docling_raw_md_s3_key
        else:
            md_key = f"documents/{doc_id}/{doc_id}.md"

        if not await s3_client.object_exists(bucket, md_key):
            logger.error(f"Background NLP: no markdown in S3 for {doc_id}")
            return

        markdown_text = await s3_client.download_text(bucket, md_key)
        if not markdown_text:
            logger.error(f"Background NLP: markdown is empty for {doc_id}")
            return

        logger.info(f"Background NLP: starting analysis for {doc_id}, text length: {len(markdown_text)}")

        doc = await multilevel_nlp_service.analyze_text_to_document(
            text=markdown_text,
            doc_id=doc_id,
            enable_voting=enable_voting,
            max_level=max_level
        )

        if not create_annotations:
            logger.info(f"Background NLP: analysis done for {doc_id}, annotations skipped")
            return

        from neomodel import db

        annotations_data = multilevel_nlp_service.create_annotations_for_database(
            doc,
            confidence_threshold=min_confidence
        )

        if not annotations_data:
            logger.info(f"Background NLP: no annotations to create for {doc_id}")
            return

        import uuid
        import time as _time
        now_ts = _time.time()  # Unix timestamp (float) — neomodel DateTimeProperty format

        annotation_uid_map = {}
        for ann_data in annotations_data:
            ann_uid = str(uuid.uuid4())
            ann_data['_uid'] = ann_uid
            meta = ann_data.get('metadata', {})
            if 'sent_idx' in meta and 'token_idx' in meta:
                annotation_uid_map[(meta['sent_idx'], meta['token_idx'])] = ann_uid

        BATCH_SIZE = 500
        batches = [annotations_data[i:i+BATCH_SIZE] for i in range(0, len(annotations_data), BATCH_SIZE)]
        for batch in batches:
            params = [
                {
                    'uid': a['_uid'],
                    'text': a['text'],
                    'annotation_type': a['annotation_type'],
                    'start_offset': a['start_offset'],
                    'end_offset': a['end_offset'],
                    'color': a['color'],
                    'metadata': json.dumps(a['metadata']),
                    'confidence': a['confidence'],
                    'source': a['source'],
                    'processor_version': a['processor_version'],
                    'created_date': now_ts,
                }
                for a in batch
            ]
            db.cypher_query(
                """
                UNWIND $rows AS row
                MATCH (d:PDFDocument {uid: $doc_id})
                CREATE (a:MarkdownAnnotation {
                    uid: row.uid,
                    text: row.text,
                    annotation_type: row.annotation_type,
                    start_offset: row.start_offset,
                    end_offset: row.end_offset,
                    color: row.color,
                    metadata: row.metadata,
                    confidence: row.confidence,
                    source: row.source,
                    processor_version: row.processor_version,
                    created_date: row.created_date
                })
                CREATE (d)-[:HAS_MARKDOWN_ANNOTATION]->(a)
                """,
                {'rows': params, 'doc_id': doc_id}
            )

        logger.info(f"Background NLP: created {len(annotations_data)} annotations for {doc_id}")

        relations_data = multilevel_nlp_service.create_relations_for_database(
            doc,
            annotation_uid_map,
            confidence_threshold=min_confidence
        )

        if relations_data:
            rel_batches = [relations_data[i:i+BATCH_SIZE] for i in range(0, len(relations_data), BATCH_SIZE)]
            for batch in rel_batches:
                rel_params = [
                    {
                        'src': r['source_uid'],
                        'tgt': r['target_uid'],
                        'relation_type': r['relation_type'],
                        'metadata': json.dumps(r['metadata']),
                        'created_date': now_ts,
                    }
                    for r in batch
                ]
                db.cypher_query(
                    """
                    UNWIND $rows AS row
                    MATCH (a:MarkdownAnnotation {uid: row.src})
                    MATCH (b:MarkdownAnnotation {uid: row.tgt})
                    CREATE (a)-[:RELATES_TO {
                        relation_type: row.relation_type,
                        metadata: row.metadata,
                        created_date: row.created_date
                    }]->(b)
                    """,
                    {'rows': rel_params}
                )

        logger.info(f"Background NLP: created {len(annotations_data)} annotations and {len(relations_data)} relations for {doc_id}")

    except Exception as e:
        logger.error(f"Background NLP error for {doc_id}: {e}", exc_info=True)


@router.post("/documents/{doc_id}/analyze-multilevel")
async def analyze_document_multilevel(
    doc_id: str,
    background_tasks: BackgroundTasks,
    enable_voting: bool = True,
    max_level: int = 3,
    create_annotations: bool = True,
    min_confidence: float = 0.8
):
    """
    Multi-level NLP analysis with voting and confidence scores.
    Запускается в фоне — сразу возвращает статус, не блокирует API.
    """
    try:
        from src.models import PDFDocument

        document = PDFDocument.nodes.get_or_none(uid=doc_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        background_tasks.add_task(
            _run_multilevel_analysis,
            doc_id=doc_id,
            enable_voting=enable_voting,
            max_level=max_level,
            create_annotations=create_annotations,
            min_confidence=min_confidence
        )

        logger.info(f"Multi-level analysis started in background for {doc_id}")
        return {"status": "started", "doc_id": doc_id, "message": "Анализ запущен в фоне"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting multi-level analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.get("/nlp/analyzer-info")
async def get_multilevel_analyzer_info():
    """
    Get information about multi-level analyzer configuration.

    Returns:
        Analyzer settings and available levels
    """
    try:
        # Получаем информацию о поддерживаемых типах через gRPC
        from services.nlp_grpc_client import get_nlp_grpc_client
        
        grpc_client = get_nlp_grpc_client()
        await grpc_client.connect()
        result = await grpc_client.get_supported_types()
        
        return {
            "status": "initialized",
            "processors": result.get("processors", []),
            "annotation_types": result.get("annotation_types", []),
            "relation_types": result.get("relation_types", []),
            "message": "Using gRPC NLP service"
        }
    except Exception as e:
        logger.error(f"Error getting analyzer info: {e}")
        return {
            "status": "error",
            "message": f"Error connecting to NLP service: {str(e)}"
        }
