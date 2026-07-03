"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_extraction.documents
Responsibility: HTTP route handlers для загрузки и управления PDF-документами.

Тонкий контроллер: парсит запрос → вызывает use case → возвращает ответ.
Длинная бизнес-логика (конвертация PDF → MD, валидация) делегирована в application/.

Allowed imports: fastapi, application.documents.*, web.dependencies, src.schemas.api
Forbidden imports: neomodel (напрямую), services (напрямую), infrastructure (напрямую)
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Request, Query
from fastapi.responses import Response

from src.schemas.api import (
    DataExtractionResponse,
    DocumentAssetsResponse,
    UpdateMarkdownRequest,
    UpdateMarkdownResponse,
    AnalyzePatternsRequest,
    AnalyzePatternsResponse,
    AnnotationTypePatterns,
    PatternRow,
    DataAvailabilityStatus,
    SaveForTestsRequest,
    SaveForTestsResponse,
)
from application.documents.upload_pdf import upload_pdf
from application.documents.get_document_assets import get_document_assets
from application.documents.delete_document import delete_document
from application.documents.list_documents import list_documents
from application.documents.search_documents import SearchDocumentsUseCase
from application.documents.get_markdown import get_markdown
from application.documents.update_markdown import update_markdown
from web.dependencies import (
    get_document_repository,
    get_s3,
    get_annotation_repository,
    get_linguistic_pattern_repository,
)

from utils.hash_utils import _compute_md5
from infrastructure.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


@router.post("/data_extraction", response_model=DataExtractionResponse)
async def data_extraction_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Загружает PDF, выполняет MD5-дедупликацию и запускает конвертацию в Markdown."""
    from services.data_extraction_service import DataExtractionService  # TRANSITIONAL
    svc = DataExtractionService()
    result = await svc.upload_and_process_pdf(background_tasks, file)
    return result


@router.get("/documents/{doc_id}/assets", response_model=DocumentAssetsResponse)
async def get_document_assets_route(
    doc_id: str,
    request: Request,
    include_urls: bool = True,
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Возвращает markdown и список изображений документа."""
    result = await get_document_assets(
        document_repo=doc_repo,
        storage=storage,
        doc_id=doc_id,
    )
    return DocumentAssetsResponse(success=True, **result)


@router.delete("/documents/{doc_id}")
async def delete_document_route(
    doc_id: str,
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Удаляет документ и все его файлы из S3."""
    await delete_document(document_repo=doc_repo, storage=storage, doc_id=doc_id)
    return {"success": True, "message": f"Document {doc_id} deleted"}


@router.get("/documents")
async def list_documents_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    doc_repo=Depends(get_document_repository),
):
    """Список документов из Neo4j с пагинацией."""
    import asyncio
    docs, total = await asyncio.to_thread(list_documents, repo=doc_repo, skip=skip, limit=limit)
    return {
        "success": True,
        "total_count": total,
        "skip": skip,
        "limit": limit,
        "documents": [
            {
                "doc_id": d.uid,
                "title": d.title,
                "original_filename": d.original_filename,
                "processing_status": d.processing_status,
                "is_processed": d.is_processed,
                "source": d.source,
                "has_markdown": d.get_active_markdown_key() is not None,
                "pubmed_id": d.pubmed_id,
                "pmc_id": d.pmc_id,
                "files": {"pdf": f"/api/v1/s3/image/{d.s3_key}"} if d.s3_key else {},
            }
            for d in docs
        ],
    }


@router.get("/documents/search")
async def search_documents_route(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    doc_repo=Depends(get_document_repository),
):
    """Нечёткий поиск документов по названию через APOC Levenshtein."""
    import asyncio
    use_case = SearchDocumentsUseCase(repo=doc_repo)
    docs, total = await asyncio.to_thread(use_case.execute, q=q, skip=skip, limit=limit)
    return {
        "success": True,
        "total_count": total,
        "skip": skip,
        "limit": limit,
        "query": q,
        "documents": [
            {
                "doc_id": d.uid,
                "title": d.title,
                "original_filename": d.original_filename,
                "processing_status": d.processing_status,
                "is_processed": d.is_processed,
                "source": d.source,
                "has_markdown": d.get_active_markdown_key() is not None,
                "pubmed_id": d.pubmed_id,
                "pmc_id": d.pmc_id,
                "files": {"pdf": f"/api/v1/s3/image/{d.s3_key}"} if d.s3_key else {},
            }
            for d in docs
        ],
    }


@router.put("/documents/{doc_id}/markdown", response_model=UpdateMarkdownResponse)
async def update_document_markdown(
    doc_id: str,
    request_body: UpdateMarkdownRequest,
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Обновляет markdown документа с опциональной валидацией."""
    validation_result = None

    # Авто-валидация через NLP сервис (делегируем через старый сервис — TRANSITIONAL)
    if request_body.auto_validate:
        try:
            from services.nlp_grpc_client import get_nlp_grpc_client
            grpc_client = get_nlp_grpc_client()
            validation_result = await grpc_client.validate_markdown(
                markdown=request_body.markdown,
                strict_mode=request_body.strict_mode,
            )
            if request_body.strict_mode and not validation_result.get("is_valid"):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": f"Валидация не пройдена: {validation_result.get('total_errors')} ошибок",
                        "validation": validation_result,
                    },
                )
        except Exception as e:
            logger.warning(f"[documents] Валидация markdown не удалась: {e}")

    result = await update_markdown(
        document_repo=doc_repo,
        storage=storage,
        doc_id=doc_id,
        markdown=request_body.markdown,
        bucket=settings.S3_BUCKET_NAME,
    )
    return UpdateMarkdownResponse(
        success=True,
        doc_id=doc_id,
        s3_key=result["s3_key"],
        title=result.get("title"),
        validation=validation_result,
    )


@router.get("/documents/{doc_id}/progress")
async def get_document_progress_route(
    doc_id: str,
    doc_repo=Depends(get_document_repository),
):
    """Возвращает текущий прогресс конвертации документа."""
    from services.data_extraction_service import _conversion_progress
    doc = doc_repo.get_by_id(doc_id)
    progress = _conversion_progress.get(doc_id, {})
    return {
        "doc_id": doc_id,
        "processing_status": doc.processing_status if doc else "unknown",
        "percent": progress.get("percent", 0),
        "phase": progress.get("phase", ""),
        "message": progress.get("message", ""),
    }


@router.get("/documents/{doc_id}/markdown")
async def get_document_markdown(
    doc_id: str,
    version: str = Query("active", pattern="^(active|raw|formatted|user)$"),
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Возвращает markdown выбранной версии."""
    content = await get_markdown(
        document_repo=doc_repo,
        storage=storage,
        doc_id=doc_id,
        version=version,
    )
    if content is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Markdown version '{version}' not found")
    return Response(content=content, media_type="text/markdown")





@router.post("/documents/{doc_id}/analyze-patterns", response_model=AnalyzePatternsResponse)
async def analyze_patterns_endpoint(
    doc_id: str,
    request_body: AnalyzePatternsRequest,
    ann_repo=Depends(get_annotation_repository),
    doc_repo=Depends(get_document_repository),
    pattern_repo=Depends(get_linguistic_pattern_repository),
):
    from application.patterns.analyze_document_patterns import analyze_document_patterns
    from services.nlp_grpc_client import get_nlp_grpc_client
    from fastapi import HTTPException

    nlp_client = get_nlp_grpc_client()

    # Проверяем что документ имеет аннотации перед запуском анализа
    doc = doc_repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    ann_types = request_body.annotation_types or [
        "Успешная цель", "Не успешная цель",
        "Фрагмент ведёт к успеху", "Фрагмент ведёт к неуспеху",
    ]
    annotations, _ = ann_repo.get_by_document(
        doc_id, skip=0, limit=None, annotation_types=ann_types,
    )
    if not annotations:
        raise HTTPException(
            status_code=400,
            detail=(
                f"В документе нет аннотаций типов: {', '.join(ann_types)}. "
                "Сначала создайте аннотации во вкладке 'Аннотации'."
            ),
        )

    try:
        results = await analyze_document_patterns(
            annotation_repo=ann_repo,
            document_repo=doc_repo,
            pattern_repo=pattern_repo,
            nlp_client=nlp_client,
            doc_id=doc_id,
            annotation_types=request_body.annotation_types,
            clear_existing=request_body.clear_existing,
            min_frequency=request_body.min_frequency,
        )
    except Exception as e:
        logger.exception(f"[analyze-patterns] Ошибка анализа паттернов для doc={doc_id}")
        raise HTTPException(status_code=500, detail=f"Ошибка NLP-анализа: {e}")

    pydantic_results = [
        AnnotationTypePatterns(
            annotation_type=r.annotation_type,
            patterns=[PatternRow(pattern_str=p.pattern_str, pattern_type=p.pattern_type, frequency=p.frequency) for p in r.patterns],
            total_annotations=r.total_annotations,
        )
        for r in results
    ]
    total = sum(len(r.patterns) for r in pydantic_results)
    return AnalyzePatternsResponse(success=True, doc_id=doc_id, results=pydantic_results, total_patterns_saved=total, message=f"Проанализировано {total} паттернов")


@router.get("/documents/{doc_id}/patterns/specific", response_model=AnalyzePatternsResponse)
async def get_specific_patterns_endpoint(
    doc_id: str,
    pattern_repo=Depends(get_linguistic_pattern_repository),
    doc_repo=Depends(get_document_repository),
):
    from fastapi import HTTPException
    from application.patterns.get_specific_patterns import get_specific_patterns
    doc = doc_repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    results = get_specific_patterns(pattern_repo=pattern_repo, doc_id=doc_id)
    pydantic_results = [
        AnnotationTypePatterns(
            annotation_type=r.annotation_type,
            patterns=[PatternRow(pattern_str=p.pattern_str, pattern_type=p.pattern_type, frequency=p.frequency) for p in r.patterns],
            total_annotations=r.total_annotations,
        )
        for r in results
    ]
    total = sum(len(r.patterns) for r in pydantic_results)
    return AnalyzePatternsResponse(success=True, doc_id=doc_id, results=pydantic_results, total_patterns_saved=total, message=f"Специфичных паттернов: {total}")


@router.get("/documents/{doc_id}/patterns", response_model=AnalyzePatternsResponse)
async def get_patterns_endpoint(
    doc_id: str,
    pattern_repo=Depends(get_linguistic_pattern_repository),
    doc_repo=Depends(get_document_repository),
):
    from fastapi import HTTPException
    doc = doc_repo.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    rows = pattern_repo.get_for_document(doc_id)
    groups: dict = {}
    for row in rows:
        at = row.get("annotation_type", "")
        if at not in groups:
            groups[at] = []
        groups[at].append(PatternRow(pattern_str=row["pattern_str"], pattern_type=row["pattern_type"], frequency=row["frequency"]))
    pydantic_results = [AnnotationTypePatterns(annotation_type=at, patterns=groups[at], total_annotations=0) for at in groups]
    total = sum(len(r.patterns) for r in pydantic_results)
    return AnalyzePatternsResponse(success=True, doc_id=doc_id, results=pydantic_results, total_patterns_saved=total, message=f"Загружено {total} паттернов" if total > 0 else "Паттерны не найдены")


@router.get("/documents/{doc_id}/data-availability", response_model=DataAvailabilityStatus)
async def check_document_data_availability(doc_id: str):
    """Проверяет доступность данных документа для экспорта в тестовый датасет."""
    from fastapi import HTTPException
    from services.data_extraction_service import DataExtractionService
    try:
        svc = DataExtractionService()
        result = await svc.check_data_availability(doc_id)
        return DataAvailabilityStatus(**result)
    except Exception as e:
        logger.error(f"Ошибка проверки доступности данных: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{doc_id}/save-for-tests", response_model=SaveForTestsResponse)
async def save_document_for_tests(doc_id: str, request: SaveForTestsRequest):
    """Экспортирует документ с аннотациями, связями и графом действий в тестовый датасет."""
    from fastapi import HTTPException
    from services.data_extraction_service import DataExtractionService
    try:
        svc = DataExtractionService()
        availability = await svc.check_data_availability(doc_id)
        if not availability["is_ready"]:
            missing = ", ".join(availability["missing_items"])
            raise HTTPException(
                status_code=400,
                detail=f"Документ не готов к экспорту. Отсутствуют: {missing}."
            )
        result = await svc.save_for_tests(doc_id=doc_id, validate=request.run_validation)
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("message", "Ошибка экспорта"))
        return SaveForTestsResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка сохранения для тестов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/images/{image_name}")
async def get_document_image(doc_id: str, image_name: str):
    """Получает изображение документа из S3."""
    try:
        from services import get_s3_client
        s3_client = get_s3_client()
        bucket = settings.S3_BUCKET_NAME
        image_key = f"documents/{doc_id}/{image_name}"

        if not await s3_client.object_exists(bucket, image_key):
            raise HTTPException(status_code=404, detail="Изображение не найдено")

        image_data = await s3_client.download_bytes(bucket, image_key)
        if not image_data:
            raise HTTPException(status_code=500, detail="Не удалось загрузить изображение")

        content_type = "image/jpeg"
        if image_name.lower().endswith('.png'):
            content_type = "image/png"
        elif image_name.lower().endswith('.gif'):
            content_type = "image/gif"
        elif image_name.lower().endswith('.bmp'):
            content_type = "image/bmp"

        return Response(content=image_data, media_type=content_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения изображения: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



