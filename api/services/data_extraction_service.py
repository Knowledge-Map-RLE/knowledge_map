"""Сервис для извлечения данных из PDF"""
import logging
import asyncio
import tempfile
import shutil
import mimetypes
from pathlib import Path as SysPath
from typing import Dict, Any

from fastapi import BackgroundTasks, UploadFile, HTTPException
from fastapi.responses import StreamingResponse

from utils.hash_utils import _compute_md5
from .pdf_to_md_client import pdf_to_md_client
from src.schemas.api import DataExtractionResponse, ImportAnnotationsRequest
from . import settings, get_s3_client
from .marker_progress import marker_progress_store

logger = logging.getLogger(__name__)


class DataExtractionService:
    """Сервис для извлечения данных из PDF файлов"""
    
    def __init__(self):
        self.s3_client = get_s3_client()
    
    async def upload_and_process_pdf(
        self, 
        background_tasks: BackgroundTasks, 
        file: UploadFile
    ) -> DataExtractionResponse:
        """Загрузка PDF, MD5-дедупликация, Marker→Markdown, загрузка md+изображений+json в S3."""
        if file.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(status_code=400, detail="Ожидается PDF файл")

        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Пустой файл")

        doc_id = _compute_md5(raw)
        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"
        pdf_key = f"{prefix}{doc_id}.pdf"

        pdf_exists = await self.s3_client.object_exists(bucket, pdf_key)

        async def process_marker_and_upload(pdf_bytes: bytes):
            await marker_progress_store.init_doc(doc_id)
            
            # Модели загрузятся автоматически при первом запуске Marker
            logger.info(f"[marker] Начинаем обработку doc_id={doc_id} - модели загрузятся автоматически")
            
            tmp_dir = SysPath(tempfile.mkdtemp(prefix="km_marker_"))
            try:
                logger.info(f"[marker] Начинаем обработку doc_id={doc_id}, tmp_dir={tmp_dir}")
                pdf_name = f"{doc_id}.pdf"
                tmp_pdf = tmp_dir / pdf_name
                with open(tmp_pdf, "wb") as f:
                    f.write(pdf_bytes)

                loop = asyncio.get_running_loop()

                def _on_progress(payload: dict) -> None:
                    """Callback для отслеживания реального прогресса обработки документа из фоновых потоков"""
                    try:
                        percent = payload.get('percent')
                        phase = payload.get('phase') or 'processing'
                        # Поддерживаем оба ключа: 'message' и 'last_message'
                        message = payload.get('message') or payload.get('last_message') or ''
                        if percent is not None:
                            asyncio.run_coroutine_threadsafe(
                                marker_progress_store.update_doc(doc_id, percent=percent, phase=phase, last_message=message),
                                loop
                            )
                        else:
                            # даже без процента обновим last_message для UX
                            asyncio.run_coroutine_threadsafe(
                                marker_progress_store.update_doc(doc_id, phase=phase, last_message=message),
                                loop
                            )
                    except Exception:
                        pass

                # Используем новый PDF to Markdown микросервис
                result = await pdf_to_md_client.convert_pdf(
                    pdf_content=pdf_bytes,
                    doc_id=doc_id,
                    timeout=3600
                )
                
                if not result["success"]:
                    raise RuntimeError(f"Ошибка конвертации: {result['message']}")
                
                # Создаем виртуальные outputs для совместимости
                outputs = {"markdown": None, "images_dir": tmp_dir}
                
                # Сохраняем markdown во временную директорию
                if result.get("markdown_content"):
                    md_path = tmp_dir / f"{doc_id}.md"
                    md_path.write_text(result["markdown_content"], encoding="utf-8", errors="ignore")
                    outputs["markdown"] = md_path
                    logger.info(f"[pdf_to_md] Markdown сохранен: {md_path}")
                
                # Сохраняем изображения
                if result.get("images"):
                    for img_name, img_data in result["images"].items():
                        img_path = tmp_dir / img_name
                        img_path.write_bytes(img_data)
                        logger.info(f"[pdf_to_md] Изображение сохранено: {img_name}")
                
                # Сохраняем метаданные если есть
                if result.get("metadata"):
                    import json
                    meta_path = tmp_dir / f"{doc_id}_meta.json"
                    meta_path.write_text(json.dumps(result["metadata"], ensure_ascii=False), encoding="utf-8")
                    outputs["meta"] = meta_path
                    logger.info(f"[pdf_to_md] Метаданные сохранены: {meta_path}")

                if "markdown" in outputs:
                    md_bytes = outputs["markdown"].read_bytes()
                    md_key = f"{prefix}{doc_id}.md"
                    await self.s3_client.upload_bytes(
                        md_bytes, bucket, md_key, content_type="text/markdown; charset=utf-8"
                    )
                    logger.info(f"[marker] Загружен markdown: s3://{bucket}/{md_key}")

                if "meta" in outputs:
                    meta_bytes = outputs["meta"].read_bytes()
                    meta_key = f"{prefix}{doc_id}_meta.json"
                    await self.s3_client.upload_bytes(
                        meta_bytes, bucket, meta_key, content_type="application/json"
                    )
                    logger.info(f"[marker] Загружен meta: s3://{bucket}/{meta_key}")

                img_exts = ("*.jpeg", "*.jpg", "*.png")
                for pattern in img_exts:
                    for img in outputs["images_dir"].glob(pattern):
                        await self.s3_client.upload_bytes(
                            img.read_bytes(), bucket, f"{prefix}{img.name}", 
                            content_type=mimetypes.guess_type(img.name)[0] or "image/jpeg"
                        )
                        logger.info(f"[marker] Загружено изображение: {img.name}")
                await marker_progress_store.complete_doc(doc_id, True)
            except Exception as e:
                await marker_progress_store.complete_doc(doc_id, False)
                logger.exception(f"Marker processing failed: {e}")
            finally:
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

        if pdf_exists:
            # если markdown отсутствует, запускаем конвертацию
            md_key = f"{prefix}{doc_id}.md"
            if not await self.s3_client.object_exists(bucket, md_key):
                # скачиваем существующий pdf и запускаем маркер
                existing_pdf = await self.s3_client.download_bytes(bucket, pdf_key)
                if not existing_pdf:
                    raise HTTPException(status_code=500, detail="Не удалось прочитать существующий PDF из S3")
                background_tasks.add_task(process_marker_and_upload, existing_pdf)
                logger.info(f"[marker] Переобработка запущена для существующего PDF: doc_id={doc_id}")
                return DataExtractionResponse(
                    success=True, doc_id=doc_id, 
                    message="Конвертация запущена для существующего PDF", 
                    files={"pdf": pdf_key}
                )
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

        background_tasks.add_task(process_marker_and_upload, raw)

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

    async def get_document_assets(self, doc_id: str, include_urls: bool = False) -> Dict[str, Any]:
        """Возвращает markdown и список изображений (ключей) для документа.
        Если include_urls=True, добавляет presigned URL для изображений.
        """
        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"

        md_key = f"{prefix}{doc_id}.md"
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
        if include_urls:
            result["image_urls"] = image_urls
        return result

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """Удаляет документ и все его файлы из S3 (префикс documents/{doc_id}/)."""
        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"
        deleted = 0

        # Многократная попытка удаления на случай eventual consistency
        import asyncio
        for _ in range(10):
            contents = await self.s3_client.list_objects(bucket, prefix)
            if not contents:
                break
            for obj in contents:
                key = obj.get('Key') or obj.get('key') or ''
                if not key:
                    continue
                ok = await self.s3_client.delete_object(bucket, key)
                if ok:
                    deleted += 1
            # Небольшая пауза перед повторной проверкой
            await asyncio.sleep(0.3)

        # Если ключи всё ещё остаются, пробуем удалить версии (для MinIO/S3 с versioning)
        remaining = await self.s3_client.list_objects(bucket, prefix)
        if remaining:
            try:
                async with self.s3_client.client_context() as s3:
                    # Полный цикл удаления всех версий до полного опустошения префикса
                    for _ in range(10):
                        versions_resp = await s3.list_object_versions(Bucket=bucket, Prefix=prefix)
                        found_any = False
                        for v in versions_resp.get('Versions', []):
                            key = v.get('Key'); ver = v.get('VersionId')
                            if key and ver:
                                found_any = True
                                await s3.delete_object(Bucket=bucket, Key=key, VersionId=ver)
                                deleted += 1
                        for m in versions_resp.get('DeleteMarkers', []):
                            key = m.get('Key'); ver = m.get('VersionId')
                            if key and ver:
                                found_any = True
                                await s3.delete_object(Bucket=bucket, Key=key, VersionId=ver)
                                deleted += 1
                        if not found_any:
                            break
            except Exception as e:
                logging.getLogger(__name__).warning(f"versioned delete failed for {prefix}: {e}")

        # Финальная проверка и логирование оставшихся ключей (если есть)
        remaining = await self.s3_client.list_objects(bucket, prefix)
        if remaining:
            rem_keys = [o.get('Key') or o.get('key') or '' for o in remaining]
            logging.getLogger(__name__).warning(f"S3 still has keys under {prefix}: {rem_keys}")

        return {"success": True, "deleted": deleted}

    async def list_documents(self) -> Dict[str, Any]:
        """Список документов по префиксу documents/ из S3."""
        bucket = settings.S3_BUCKET_NAME
        contents = await self.s3_client.list_objects(bucket, "documents/")
        doc_map: Dict[str, Dict[str, Any]] = {}
        # Сначала собираем кандидатов
        for obj in contents:
            key = obj.get('Key') or obj.get('key') or ''
            if not key.startswith('documents/'):
                continue
            parts = key.split('/')
            if len(parts) < 3:
                continue
            doc_id = parts[1]
            item = doc_map.get(doc_id)
            if not item:
                item = {
                    "doc_id": doc_id,
                    "has_markdown": False,
                    "files": {}
                }
                doc_map[doc_id] = item
            # track files (пока без валидации)
            if key.endswith('.md'):
                item['files']['markdown'] = key
            elif key.endswith('.pdf'):
                item['files']['pdf'] = key
            elif key.endswith('.json'):
                item['files']['json'] = key

        # Валидация существования ключей .md/.pdf (обход eventual consistency list_objects)
        for item in doc_map.values():
            files = item.get('files', {})
            # markdown
            md_key = files.get('markdown')
            if md_key and await self.s3_client.object_exists(bucket, md_key):
                item['has_markdown'] = True
            else:
                files.pop('markdown', None)
            # pdf
            pdf_key = files.get('pdf')
            if pdf_key and not await self.s3_client.object_exists(bucket, pdf_key):
                files.pop('pdf', None)
        # Отфильтровываем «пустые» документы: показываем только если есть markdown
        documents = []
        for item in doc_map.values():
            if item.get('has_markdown'):
                documents.append(item)
        return {"success": True, "documents": documents}
