"""Сервис для извлечения данных из PDF"""
import logging
import asyncio
import tempfile
import shutil
import mimetypes
import re
from pathlib import Path as SysPath
from typing import Dict, Any

from fastapi import UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from utils.hash_utils import _compute_md5
from .pdf_to_md_grpc_client import get_pdf_to_md_grpc_client_instance
from src.schemas.api import DataExtractionResponse, ImportAnnotationsRequest
from . import settings, get_s3_client
from src.models import Document

logger = logging.getLogger(__name__)

# Хранилище прогресса конвертации (doc_id → {percent, phase, message})
_conversion_progress: Dict[str, Any] = {}

# Слежение за фоновыми задачами конвертации для отмены при delete
_background_tasks: Dict[str, asyncio.Task] = {}


def extract_title_from_markdown(markdown_content: str) -> str | None:
    """Извлекает заголовок первого уровня из markdown контента.

    Args:
        markdown_content: Текст markdown документа

    Returns:
        Заголовок без символа #, или None если не найден
    """
    if not markdown_content:
        return None

    lines = markdown_content.split('\n')
    for line in lines:
        line = line.strip()
        # Ищем заголовок первого уровня: строка начинается с одной решётки и пробела
        if line.startswith('# ') and not line.startswith('## '):
            # Убираем '# ' и возвращаем заголовок
            title = line[2:].strip()
            if title:
                return title

    return None


class DataExtractionService:
    """Сервис для извлечения данных из PDF файлов"""

    def __init__(self):
        self.s3_client = get_s3_client()

    def _convert_relative_image_paths(self, markdown_text: str, doc_id: str, request: Any = None) -> str:
        """
        Преобразует относительные пути изображений в абсолютные.

        Заменяет пути вида 'page_1_pic_0.png' на полные URL:
        'http://localhost:8000/api/data_extraction/documents/{doc_id}/images/page_1_pic_0.png'

        Args:
            markdown_text: Исходный markdown с относительными путями
            doc_id: ID документа
            request: FastAPI Request объект для определения базового URL (опционально)

        Returns:
            Markdown с абсолютными путями к изображениям
        """
        # Определяем базовый URL в порядке приоритета:
        # 1. Из request (если передан)
        # 2. Из настроек API_BASE_URL
        # 3. Фоллбэк на localhost:8000
        if request:
            # Извлекаем из request
            scheme = request.url.scheme
            host = request.headers.get('host', f"{settings.API_HOST}:{settings.API_PORT}")
            base_url = f"{scheme}://{host}"
        elif settings.API_BASE_URL:
            # Из настроек
            base_url = settings.API_BASE_URL
        else:
            # Фоллбэк
            base_url = 'http://localhost:8000'

        image_prefix = f"{base_url}/api/data_extraction/documents/{doc_id}/images/"

        # Заменяем относительные пути изображений на абсолютные
        # Паттерн: ![alt](filename.png) где filename не содержит http
        def replace_image_path(match):
            alt_text = match.group(1)
            image_path = match.group(2)

            # Если путь уже абсолютный (http/https) или API-относительный (/api/...) — не меняем
            if (image_path.startswith('http://') or image_path.startswith('https://')
                    or image_path.startswith('/api/')):
                return match.group(0)

            # Если путь относительный, добавляем префикс
            # Используем angle brackets для корректного парсинга URL со слешами в marked
            return f"![{alt_text}](<{image_prefix}{image_path}>)"

        # Применяем замену для всех изображений
        result = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_image_path, markdown_text)

        return result

    async def _start_conversion_task(self, doc_id: str, pdf_bytes: bytes, filename: str | None = None) -> None:
        """Запускает process_pdf_and_upload как отслеживаемую asyncio-задачу."""
        import time as _time_module
        from .pdf_to_md_grpc_client import get_pdf_to_md_grpc_client_instance

        _task_t0 = _time_module.time()
        pdf_size = len(pdf_bytes) if pdf_bytes else 0
        logger.info(
            f"[background_task] Создание задачи: doc_id={doc_id}, "
            f"pdf_size={pdf_size} байт ({pdf_size/1024:.1f} KB), "
            f"filename='{filename}'"
        )

        async def process_pdf_and_upload(pdf_bytes: bytes, filename: str | None = None):
            # Конвертация PDF в Markdown через gRPC сервис
            logger.info(f"[background_task] STARTED process_pdf_and_upload for doc_id={doc_id}")

            # Обновляем статус на pdf_to_markdown
            try:
                doc = Document.nodes.get_or_none(uid=doc_id)
                if doc:
                    doc.processing_status = 'pdf_to_markdown'
                    doc.save()
            except Exception as e:
                logger.warning(f"[Neo4j] Не удалось обновить статус на pdf_to_markdown: {e}")

            tmp_dir = SysPath(tempfile.mkdtemp(prefix="km_pdf_"))
            try:
                logger.info(f"[pdf_to_md] Начало обработки doc_id={doc_id}")
                pdf_name = f"{doc_id}.pdf"
                tmp_pdf = tmp_dir / pdf_name
                with open(tmp_pdf, "wb") as f:
                    f.write(pdf_bytes)

                def _on_progress(payload: dict) -> None:
                    _conversion_progress[doc_id] = {
                        "percent": payload.get("percent", 0),
                        "phase": payload.get("phase", "pdf_to_markdown"),
                        "message": payload.get("message", ""),
                    }

                grpc_client = get_pdf_to_md_grpc_client_instance()

                result = await grpc_client.convert_pdf(
                    pdf_content=pdf_bytes,
                    doc_id=doc_id,
                    timeout=3600,
                    on_progress=_on_progress
                )

                if not result["success"]:
                    raise RuntimeError(f"Ошибка конвертации: {result['message']}")

                outputs = {"markdown": None, "images_dir": tmp_dir}

                extracted_title = None
                if result.get("markdown_content"):
                    md_path = tmp_dir / f"{doc_id}.md"
                    md_path.write_text(result["markdown_content"], encoding="utf-8", errors="ignore")
                    outputs["markdown"] = md_path
                    extracted_title = extract_title_from_markdown(result["markdown_content"])

                if result.get("images"):
                    for img_name, img_data in result["images"].items():
                        img_path = tmp_dir / img_name
                        img_path.write_bytes(img_data)

                if result.get("metadata_json"):
                    import json
                    meta_path = tmp_dir / f"{doc_id}_meta.json"
                    meta_path.write_text(result["metadata_json"], encoding="utf-8")
                    outputs["meta"] = meta_path

                prefix = f"documents/{doc_id}/"
                bucket = settings.S3_BUCKET_NAME

                if outputs.get("markdown") is not None:
                    md_bytes = outputs["markdown"].read_bytes()
                    md_key = f"{prefix}{doc_id}.md"
                    await self.s3_client.upload_bytes(
                        md_bytes, bucket, md_key, content_type="text/markdown; charset=utf-8"
                    )

                if outputs.get("meta") is not None:
                    meta_bytes = outputs["meta"].read_bytes()
                    meta_key = f"{prefix}{doc_id}_meta.json"
                    await self.s3_client.upload_bytes(
                        meta_bytes, bucket, meta_key, content_type="application/json"
                    )
                img_exts = ("*.jpeg", "*.jpg", "*.png")
                for pattern in img_exts:
                    for img in outputs["images_dir"].glob(pattern):
                        await self.s3_client.upload_bytes(
                            img.read_bytes(), bucket, f"{prefix}{img.name}",
                            content_type=mimetypes.guess_type(img.name)[0] or "image/jpeg"
                        )

                docling_raw_s3_key = result.get("docling_raw_s3_key")
                formatted_s3_key = result.get("formatted_s3_key")

                try:
                    existing_doc = Document.nodes.get_or_none(uid=doc_id)
                    if not existing_doc:
                        Document(
                            uid=doc_id,
                            original_filename=filename or f"{doc_id}.pdf",
                            md5_hash=doc_id,
                            s3_key=f"{prefix}{doc_id}.pdf",
                            processing_status='ready_for_annotation',
                            is_processed=True,
                            title=extracted_title,
                            docling_raw_md_s3_key=docling_raw_s3_key,
                            formatted_md_s3_key=formatted_s3_key,
                            has_full_text=bool(docling_raw_s3_key or formatted_s3_key),
                        ).save()
                        logger.info(f"[pdf_to_md] Документ {doc_id} сохранён в Neo4j")
                    else:
                        existing_doc.processing_status = 'ready_for_annotation'
                        existing_doc.is_processed = True
                        if extracted_title and not existing_doc.title:
                            existing_doc.title = extracted_title
                        if docling_raw_s3_key:
                            existing_doc.docling_raw_md_s3_key = docling_raw_s3_key
                            existing_doc.has_full_text = True
                            if existing_doc.user_md_s3_key:
                                existing_doc.user_md_s3_key = None
                        if formatted_s3_key:
                            existing_doc.formatted_md_s3_key = formatted_s3_key
                            existing_doc.has_full_text = True
                        existing_doc.save()
                        logger.info(f"[pdf_to_md] Документ {doc_id} обновлён в Neo4j")
                    _conversion_progress.pop(doc_id, None)
                except Exception as neo_err:
                    logger.error(f"[Neo4j] Ошибка сохранения документа {doc_id}: {neo_err}")

                _elapsed = _time_module.time() - _task_t0
                logger.info(f"[pdf_to_md] Обработка документа {doc_id} завершена за {_elapsed:.2f}s")
            except asyncio.CancelledError:
                _elapsed = _time_module.time() - _task_t0
                logger.info(f"[pdf_to_md] Задача отменена для doc_id={doc_id} через {_elapsed:.2f}s")
                raise
            except Exception as e:
                _elapsed = _time_module.time() - _task_t0
                logger.error(
                    f"[background_task] FAILED for doc_id={doc_id}: {e} "
                    f"(elapsed={_elapsed:.2f}s)",
                    exc_info=True
                )
                try:
                    err_doc = Document.nodes.get_or_none(uid=doc_id)
                    if err_doc:
                        err_doc.processing_status = 'error'
                        err_doc.save()
                except Exception:
                    pass
                _conversion_progress[doc_id] = {
                    "percent": 0,
                    "phase": "error",
                    "message": str(e)[:200],
                }
            finally:
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

        # Отменяем предыдущую задачу для того же doc_id, если есть
        old = _background_tasks.pop(doc_id, None)
        if old is not None:
            if not old.done():
                logger.info(f"[background_task] Отмена предыдущей задачи doc_id={doc_id}")
                old.cancel()
                try:
                    await old
                    logger.info(f"[background_task] Предыдущая задача doc_id={doc_id} отменена")
                except asyncio.CancelledError:
                    logger.info(f"[background_task] Предыдущая задача doc_id={doc_id} подтвердила отмену")
                    pass
            else:
                logger.info(f"[background_task] Предыдущая задача doc_id={doc_id} уже завершена (done={old.done()})")

        task = asyncio.create_task(process_pdf_and_upload(pdf_bytes, filename))
        _background_tasks[doc_id] = task

        def _on_task_done(t: asyncio.Task) -> None:
            _background_tasks.pop(doc_id, None)
            exc = t.exception()
            if isinstance(exc, asyncio.CancelledError):
                logger.info(f"[background_task] Задача doc_id={doc_id} подтвердила отмену в done_callback")
            elif exc:
                logger.error(f"[background_task] Задача doc_id={doc_id} необработанная ошибка: {exc}")

        task.add_done_callback(_on_task_done)
        logger.info(f"[background_task] Задача doc_id={doc_id} создана")

    async def _cleanup_s3_prefixes(self, doc_id: str) -> int:
        """Удаляет все S3-объекты для doc_id, включая версии. Возвращает количество удалённых."""
        bucket = settings.S3_BUCKET_NAME
        deleted = 0

        for prefix in [f"documents/{doc_id}/", f"markdown/{doc_id}"]:
            keys = await self._list_all_objects(bucket, prefix)
            if not keys:
                continue
            for key in keys:
                ok = await self.s3_client.delete_object(bucket, key)
                if ok:
                    deleted += 1

            # Retry с versioning-aware удалением
            for retry in range(3):
                await asyncio.sleep(0.5)
                remaining = await self.s3_client.list_objects(bucket, prefix)
                if not remaining:
                    break
                try:
                    async with self.s3_client.client_context() as s3:
                        versions_resp = await s3.list_object_versions(Bucket=bucket, Prefix=prefix)
                        for v in versions_resp.get('Versions', []):
                            key, ver = v.get('Key'), v.get('VersionId')
                            if key and ver:
                                await s3.delete_object(Bucket=bucket, Key=key, VersionId=ver)
                                deleted += 1
                        for m in versions_resp.get('DeleteMarkers', []):
                            key, ver = m.get('Key'), m.get('VersionId')
                            if key and ver:
                                await s3.delete_object(Bucket=bucket, Key=key, VersionId=ver)
                                deleted += 1
                        if not versions_resp.get('Versions') and not versions_resp.get('DeleteMarkers'):
                            for obj in remaining:
                                key = obj.get('Key') or obj.get('key') or ''
                                if key:
                                    await s3.delete_object(Bucket=bucket, Key=key)
                                    deleted += 1
                except Exception as e:
                    logger.warning(f"[delete] Попытка {retry + 1}/3 для {prefix}: {e}")

            await asyncio.sleep(1.0)
            remaining = await self.s3_client.list_objects(bucket, prefix)
            if remaining:
                rem_keys = [o.get('Key') or o.get('key') or '' for o in remaining]
                logger.warning(f"[delete] Остались объекты под {prefix}: {rem_keys}")

        return deleted

    async def _list_all_objects(self, bucket: str, prefix: str) -> list[str]:
        """list_objects_v2 с пагинацией — собирает все ключи под префиксом."""
        keys = []
        continuation_token = None
        while True:
            params = {"Bucket": bucket, "Prefix": prefix}
            if continuation_token:
                params["ContinuationToken"] = continuation_token
            try:
                async with self.s3_client.client_context() as s3:
                    resp = await s3.list_objects_v2(**params)
                for obj in resp.get("Contents", []):
                    key = obj.get("Key")
                    if key:
                        keys.append(key)
                if resp.get("IsTruncated"):
                    continuation_token = resp.get("NextContinuationToken")
                else:
                    break
            except Exception as e:
                logger.error(f"_list_all_objects({prefix}): {e}")
                break
        return keys

    async def upload_and_process_pdf(
        self, 
        file: UploadFile
    ) -> DataExtractionResponse:
        """Загрузка PDF, MD5-дедупликация, конвертация в Markdown, загрузка md+изображений+json в S3."""
        if file.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(status_code=400, detail="Ожидается PDF файл")

        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Пустой файл")

        doc_id = _compute_md5(raw)
        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"
        pdf_key = f"{prefix}{doc_id}.pdf"

        logger.info(f"[upload] {file.filename} → doc_id={doc_id}")
        pdf_exists = await self.s3_client.object_exists(bucket, pdf_key)

        # Fix 2: если PDF есть в S3, но нет записи в Neo4j — чистим S3 и грузим заново
        if pdf_exists:
            neo4j_doc = Document.nodes.get_or_none(uid=doc_id)
            if neo4j_doc is None:
                logger.info(f"[upload] PDF найден в S3, но Neo4j пуст для {doc_id} — очищаем S3 и грузим заново")
                await self._cleanup_s3_prefixes(doc_id)
                pdf_exists = False

        # Создаём запись в Neo4j сразу, до запуска фоновой задачи
        try:
            if not Document.nodes.get_or_none(uid=doc_id):
                Document(
                    uid=doc_id,
                    original_filename=file.filename or f"{doc_id}.pdf",
                    md5_hash=doc_id,
                    s3_key=pdf_key,
                    processing_status='uploading',
                    is_processed=False,
                ).save()
                logger.info(f"[upload] Документ {doc_id} создан в Neo4j со статусом 'uploading'")
        except Exception as neo_err:
            logger.warning(f"[Neo4j] Не удалось создать запись при загрузке: {neo_err}")

        if pdf_exists:
            md_key_old = f"{prefix}{doc_id}.md"
            md_key_raw = f"{prefix}{doc_id}_docling_raw.md"
            md_exists = (
                await self.s3_client.object_exists(bucket, md_key_old) or
                await self.s3_client.object_exists(bucket, md_key_raw)
            )
            if not md_exists:
                existing_pdf = await self.s3_client.download_bytes(bucket, pdf_key)
                if not existing_pdf:
                    raise HTTPException(status_code=500, detail="Не удалось прочитать существующий PDF из S3")
                logger.info(f"[upload] PDF exists but no markdown, launching conversion for doc_id={doc_id}")
                await self._start_conversion_task(doc_id, existing_pdf, file.filename)
                return DataExtractionResponse(
                    success=True, doc_id=doc_id,
                    message="Конвертация запущена для существующего PDF",
                    files={"pdf": pdf_key}
                )
            logger.info(f"[upload] Дубликат с markdown: doc_id={doc_id}")
            try:
                dup_doc = Document.nodes.get_or_none(uid=doc_id)
                if dup_doc and dup_doc.processing_status == 'uploading':
                    dup_doc.processing_status = 'ready_for_annotation'
                    dup_doc.is_processed = True
                    dup_doc.save()
            except Exception:
                pass
            return DataExtractionResponse(
                success=True, doc_id=doc_id,
                message="Дубликат: уже существует",
                files={"pdf": pdf_key}
            )

        uploaded = await self.s3_client.upload_bytes(
            raw, bucket, pdf_key, content_type="application/pdf"
        )
        if not uploaded:
            raise HTTPException(status_code=500, detail="Не удалось сохранить PDF в S3")

        await self._start_conversion_task(doc_id, raw, file.filename)
        logger.info(f"[upload] doc_id={doc_id} загружен, конвертация запущена")

        return DataExtractionResponse(
            success=True, doc_id=doc_id,
            message="Файл принят, конвертация запущена",
            files={"pdf": pdf_key}
        )

    async def export_annotations(self, doc_id: str) -> StreamingResponse:
        """Экспорт аннотаций"""
        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"
        key = f"{prefix}{doc_id}_annotations.json"
        
        if not await self.s3_client.object_exists(bucket, key):
            raise HTTPException(status_code=404, detail="Аннотации не найдены")
        data = await self.s3_client.download_bytes(bucket, key)
        return StreamingResponse(iter([data]), media_type="application/json")

    async def import_annotations(self, payload: ImportAnnotationsRequest) -> Dict[str, Any]:
        """Импорт аннотаций"""
        if not payload.doc_id:
            raise HTTPException(status_code=400, detail="doc_id обязателен")
        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{payload.doc_id}/"
        key = f"{prefix}{payload.doc_id}_annotations.json"
        
        import json
        ok = await self.s3_client.upload_bytes(
            json.dumps(payload.annotations_json, ensure_ascii=False).encode("utf-8"),
            bucket,
            key,
            content_type="application/json"
        )
        if not ok:
            raise HTTPException(status_code=500, detail="Не удалось сохранить аннотации")
        return {"success": True, "key": key}

    async def get_document_assets(self, doc_id: str, include_urls: bool = False, request: Any = None) -> Dict[str, Any]:
        """Возвращает markdown и список изображений (ключей) для документа.
        Если include_urls=True, добавляет presigned URL для изображений.

        Args:
            doc_id: ID документа
            include_urls: Добавлять ли presigned URL для изображений
            request: FastAPI Request объект для определения базового URL
        """
        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"

        # Получаем активную версию markdown используя логику версионирования
        try:
            document = Document.nodes.get_or_none(uid=doc_id)
        except Exception as e:
            logger.error(f"Ошибка получения документа из Neo4j: {e}")
            document = None

        # Определяем S3 ключ для markdown (приоритет: user > formatted > raw > старый формат)
        md_key = None
        if document:
            if document.user_md_s3_key:
                md_key = document.user_md_s3_key
            elif document.formatted_md_s3_key:
                md_key = document.formatted_md_s3_key
            elif document.docling_raw_md_s3_key:
                md_key = document.docling_raw_md_s3_key

        # Fallback к старому формату
        if not md_key:
            md_key = f"{prefix}{doc_id}.md"

        pdf_key = f"{prefix}{doc_id}.pdf"
        markdown_text = None
        if await self.s3_client.object_exists(bucket, md_key):
            markdown_text = await self.s3_client.download_text(bucket, md_key)

        # перечислим изображения
        contents = await self.s3_client.list_objects(bucket, prefix)
        images: list[str] = []
        image_urls: Dict[str, str] = {}
        for obj in contents:
            key = obj.get('Key') or obj.get('Key'.lower()) or ''
            if key.lower().endswith(('.jpeg', '.jpg', '.png')):
                images.append(key)
                if include_urls:
                    url = await self.s3_client.get_object_url(bucket, key)
                    if url:
                        image_urls[SysPath(key).name] = url

        result: Dict[str, Any] = {
            "success": True,
            "doc_id": doc_id,
            "markdown": markdown_text,
            "images": images,
        }
        # Добавляем ссылки на файлы
        files: Dict[str, Any] = {}
        if await self.s3_client.object_exists(bucket, pdf_key):
            files["pdf"] = pdf_key
        if await self.s3_client.object_exists(bucket, md_key):
            files["markdown"] = md_key
        if files:
            result["files"] = files
        if include_urls:
            result["image_urls"] = image_urls
            # presigned URL для PDF, если он существует
            if await self.s3_client.object_exists(bucket, pdf_key):
                url = await self.s3_client.get_object_url(bucket, pdf_key)
                if url:
                    result["pdf_url"] = url
        return result

    async def get_markdown(self, doc_id: str, version: str = "active") -> Dict[str, Any]:
        """
        Получает markdown документа из S3.

        Args:
            doc_id: ID документа
            version: Версия markdown файла:
                - "active": возвращает user версию если есть, иначе formatted, иначе raw
                - "raw": возвращает raw Docling markdown
                - "formatted": возвращает AI-форматированный markdown
                - "user": возвращает пользовательскую версию

        Returns:
            Dict с markdown контентом и метаданными

        Raises:
            HTTPException: Если markdown не найден
        """
        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"

        # Получаем документ из Neo4j для определения активной версии
        try:
            document = Document.nodes.get_or_none(uid=doc_id)
        except Exception as e:
            logger.error(f"Ошибка получения документа из Neo4j: {e}")
            document = None

        # Определяем S3 ключ в зависимости от версии
        if version == "active":
            # Используем логику из Document.get_active_markdown_key()
            if document:
                if document.user_md_s3_key:
                    md_key = document.user_md_s3_key
                elif document.formatted_md_s3_key:
                    md_key = document.formatted_md_s3_key
                elif document.docling_raw_md_s3_key:
                    md_key = document.docling_raw_md_s3_key
                else:
                    # Fallback к старому формату
                    md_key = f"{prefix}{doc_id}.md"
            else:
                # Нет записи в Neo4j - используем старый формат
                md_key = f"{prefix}{doc_id}.md"
        elif version == "raw":
            if document and document.docling_raw_md_s3_key:
                md_key = document.docling_raw_md_s3_key
            else:
                # Fallback к ожидаемому имени файла
                md_key = f"markdown/{doc_id}_docling_raw.md"
        elif version == "formatted":
            if document and document.formatted_md_s3_key:
                md_key = document.formatted_md_s3_key
            else:
                # Fallback к ожидаемому имени файла
                md_key = f"markdown/{doc_id}_formatted.md"
        elif version == "user":
            if document and document.user_md_s3_key:
                md_key = document.user_md_s3_key
            else:
                # User версия еще не создана
                raise HTTPException(
                    status_code=404,
                    detail="Пользовательская версия markdown еще не создана"
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Неверная версия: {version}. Допустимые значения: active, raw, formatted, user"
            )

        # Проверяем существование файла
        if not await self.s3_client.object_exists(bucket, md_key):
            raise HTTPException(
                status_code=404,
                detail=f"Markdown не найден для версии '{version}'"
            )

        # Загружаем markdown
        markdown_text = await self.s3_client.download_text(bucket, md_key)
        if markdown_text is None:
            raise HTTPException(
                status_code=500,
                detail="Не удалось загрузить markdown из S3"
            )

        # Преобразуем относительные пути изображений в абсолютные
        markdown_text = self._convert_relative_image_paths(markdown_text, doc_id)

        return {
            "success": True,
            "doc_id": doc_id,
            "version": version,
            "s3_key": md_key,
            "markdown": markdown_text
        }

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """
        Удаляет документ и все связанные данные:
        - Аннотации из Neo4j
        - Связи между аннотациями
        - Паттерны (patterns)
        - Цепочки действий (action chains)
        - Сам документ PDFDocument из Neo4j
        - Все файлы из S3 (documents/{doc_id}/ и markdown/{doc_id}*)
        """
        from neomodel import db

        # Удаляем все связанные данные из Neo4j одним запросом
        try:
            document = Document.nodes.get_or_none(uid=doc_id)
            if document:
                # Комплексное удаление всех связанных данных
                query = """
                MATCH (d:Document {uid: $doc_id})
                OPTIONAL MATCH (d)-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
                OPTIONAL MATCH (p:Pattern {source_token_uid: a.uid})
                DETACH DELETE p, a, d
                RETURN count(d) as deleted_count
                """
                result, _ = db.cypher_query(query, {'doc_id': doc_id})
                deleted_count = result[0][0] if result else 0
                logger.info(f"[delete] Neo4j: удалено {deleted_count} объектов для doc_id={doc_id}")

                check_doc = Document.nodes.get_or_none(uid=doc_id)
                if check_doc:
                    logger.error(f"[delete] Документ {doc_id} всё ещё существует в Neo4j после удаления")
            else:
                logger.warning(f"[delete] Документ {doc_id} не найден в Neo4j")
        except Exception as e:
            logger.error(f"[delete] Ошибка удаления Neo4j для {doc_id}: {e}", exc_info=True)

        # Отменяем фоновую задачу конвертации (Fix 1)
        old = _background_tasks.pop(doc_id, None)
        if old and not old.done():
            old.cancel()
            try:
                await old
            except asyncio.CancelledError:
                pass
            logger.info(f"[delete] Отменена фоновая задача для doc_id={doc_id}")

        # Затем удаляем файлы из S3 (Fix 3: pagination в list_objects)
        deleted = await self._cleanup_s3_prefixes(doc_id)
        logger.info(f"[delete] doc_id={doc_id}: удалено {deleted} файлов из S3")
        return {"success": True, "deleted": deleted, "doc_id": doc_id}

    async def update_markdown(self, doc_id: str, markdown: str) -> Dict[str, Any]:
        """
        Обновляет markdown документа в S3 как пользовательскую версию.

        При первом сохранении создает {doc_id}.md файл в папке markdown/.
        При последующих сохранениях обновляет этот файл.
        Также обновляет user_md_s3_key в Neo4j PDFDocument.
        """
        bucket = settings.S3_BUCKET_NAME
        md_key = f"markdown/{doc_id}.md"

        # Сохраняем markdown в S3
        ok = await self.s3_client.upload_bytes(
            markdown.encode("utf-8"),
            bucket,
            md_key,
            content_type="text/markdown; charset=utf-8"
        )

        if not ok:
            raise HTTPException(status_code=500, detail="Не удалось сохранить markdown в S3")

        # Обновляем Neo4j PDFDocument с user_md_s3_key и title
        extracted_title = None
        try:
            document = Document.nodes.get_or_none(uid=doc_id)
            if document:
                document.user_md_s3_key = md_key
                extracted_title = extract_title_from_markdown(markdown)
                if extracted_title:
                    document.title = extracted_title
                document.save()
            else:
                logger.warning(f"[update_markdown] Документ {doc_id} не найден в Neo4j")
        except Exception as e:
            logger.error(f"[update_markdown] Ошибка обновления Neo4j для {doc_id}: {e}")

        return {
            "success": True,
            "doc_id": doc_id,
            "s3_key": md_key,
            "title": extracted_title,
            "message": "Пользовательский markdown успешно сохранен"
        }

    async def list_documents(
        self,
        skip: int = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """
        Список документов из Neo4j (без S3-проверок — они выполняются per-document).

        Args:
            skip: смещение
            limit: максимальное количество
        """
        import asyncio

        try:
            from application.documents.list_documents import list_documents as list_docs_usecase
            from adapters.repositories.document_repository import DocumentRepository

            repo = DocumentRepository()
            docs, total = list_docs_usecase(repo=repo, skip=skip, limit=limit)

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
        except Exception as e:
            logger.error(f"list_documents failed: {e}")
            return {"success": False, "documents": [], "total_count": 0, "skip": skip, "limit": limit}

    async def check_data_availability(self, doc_id: str) -> Dict[str, Any]:
        """
        Проверяет доступность всех данных для экспорта в тестовый датасет.

        Args:
            doc_id: ID документа

        Returns:
            Dict со статусом доступности данных
        """
        from src.models import Document
        from neomodel import db

        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"

        # Проверка PDF
        pdf_key = f"{prefix}{doc_id}.pdf"
        pdf_exists = await self.s3_client.object_exists(bucket, pdf_key)

        # Проверка Markdown
        markdown_exists = False
        document = Document.nodes.get_or_none(uid=doc_id)
        if document:
            # Проверяем активный markdown
            if document.user_md_s3_key:
                markdown_exists = await self.s3_client.object_exists(bucket, document.user_md_s3_key)
            elif document.formatted_md_s3_key:
                markdown_exists = await self.s3_client.object_exists(bucket, document.formatted_md_s3_key)
            elif document.docling_raw_md_s3_key:
                markdown_exists = await self.s3_client.object_exists(bucket, document.docling_raw_md_s3_key)

        if not markdown_exists:
            # Fallback к старому формату
            md_key = f"{prefix}{doc_id}.md"
            markdown_exists = await self.s3_client.object_exists(bucket, md_key)

        # Проверка аннотаций
        query_annotations = """
        MATCH (d:Document {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
        RETURN count(a) as count
        """
        results, _ = db.cypher_query(query_annotations, {"doc_id": doc_id})
        annotation_count = results[0][0] if results else 0
        has_annotations = annotation_count > 0

        # Проверка связей
        query_relations = """
        MATCH (d:Document {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a1:MarkdownAnnotation)
        MATCH (a1)-[r:RELATES_TO]->(a2:MarkdownAnnotation)
        RETURN count(r) as count
        """
        results, _ = db.cypher_query(query_relations, {"doc_id": doc_id})
        relation_count = results[0][0] if results else 0
        has_relations = relation_count > 0

        # Проверка графа действий
        query_action_nodes = """
        MATCH (a:Action {doc_id: $doc_id})
        RETURN count(a) as count
        """
        results, _ = db.cypher_query(query_action_nodes, {"doc_id": doc_id})
        action_node_count = results[0][0] if results else 0
        has_action_graph = action_node_count > 0

        query_action_edges = """
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO]->(t:Action {doc_id: $doc_id})
        RETURN count(r) as count
        """
        results, _ = db.cypher_query(query_action_edges, {"doc_id": doc_id})
        action_edge_count = results[0][0] if results else 0

        # Готовность к экспорту (PDF + MD + аннотации обязательны)
        is_ready = pdf_exists and markdown_exists and has_annotations

        missing_items = []
        if not pdf_exists:
            missing_items.append("PDF файл")
        if not markdown_exists:
            missing_items.append("Markdown файл")
        if not has_annotations:
            missing_items.append("Аннотации")

        return {
            "pdf_exists": pdf_exists,
            "markdown_exists": markdown_exists,
            "has_annotations": has_annotations,
            "has_annotation_relations": has_relations,
            "has_action_graph": has_action_graph,
            "annotation_count": annotation_count,
            "relation_count": relation_count,
            "action_node_count": action_node_count,
            "action_edge_count": action_edge_count,
            "is_ready": is_ready,
            "missing_items": missing_items,
        }

    async def save_for_tests(
        self,
        doc_id: str,
        validate: bool = True
    ) -> Dict[str, Any]:
        """
        Экспортирует документ в тестовый датасет.

        Все компоненты обязательны: PDF, markdown, annotations, patterns, chains.
        Имя датасета генерируется автоматически: {md5_hash}_{YYYY}.{MM}.{DD}_{HH}.{mm}.{ss}_{random6}

        Args:
            doc_id: ID документа
            validate: Валидировать датасет после экспорта

        Returns:
            Dict с результатом экспорта
        """
        import sys
        from pathlib import Path

        # Импортируем DatasetExporter
        api_root = Path(__file__).parent.parent
        sys.path.insert(0, str(api_root))

        from tools.dataset_builder.export_dataset import DatasetExporter

        try:
            # Создаем экспортер с автоматической генерацией имени
            exporter = DatasetExporter(doc_id=doc_id)

            # Выполняем экспорт (все компоненты обязательны)
            result = await exporter.export_all()

            if not result["success"]:
                return {
                    "success": False,
                    "sample_id": sample_name,
                    "exported_files": [],
                    "message": f"Ошибка экспорта: {', '.join(result['errors'])}",
                    "dvc_command": "",
                }

            # Получаем сгенерированный sample_id из результата экспорта
            sample_id = result["sample_id"]

            # Формируем DVC команду
            dvc_command = "dvc add data/datasets && git add data/datasets.dvc && git commit -m 'Add test dataset: {}'".format(sample_id)

            # Валидация (если запрошена)
            validation_result = None
            if validate:
                try:
                    from tools.dataset_builder.validate_dataset import validate_dataset_programmatic
                    validation_result = validate_dataset_programmatic(sample_id)
                except Exception as ve:
                    logger.warning(f"Валидация не удалась: {ve}")
                    validation_result = {"valid": False, "errors": [str(ve)]}

            return {
                "success": True,
                "sample_id": sample_id,
                "exported_files": result["exported_files"],
                "validation_result": validation_result,
                "dvc_command": dvc_command,
                "message": f"Датасет успешно экспортирован: {len(result['exported_files'])} файлов",
            }

        except Exception as e:
            logger.error(f"Ошибка при сохранении для тестов: {e}", exc_info=True)
            return {
                "success": False,
                "sample_id": "",
                "exported_files": [],
                "message": f"Ошибка: {str(e)}",
                "dvc_command": "",
            }
