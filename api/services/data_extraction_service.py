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
from .pdf_to_md_grpc_client import get_pdf_to_md_grpc_client_instance
from src.schemas.api import DataExtractionResponse, ImportAnnotationsRequest
from . import settings, get_s3_client
from src.models import PDFDocument

logger = logging.getLogger(__name__)

# Отладочная информация о переменных окружения
import os
logger.info(f"[data_extraction] Переменные окружения при импорте: PDF_TO_MD_SERVICE_HOST={os.getenv('PDF_TO_MD_SERVICE_HOST', 'НЕ УСТАНОВЛЕНА')}, PDF_TO_MD_SERVICE_PORT={os.getenv('PDF_TO_MD_SERVICE_PORT', 'НЕ УСТАНОВЛЕНА')}")


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
                logger.info(f"[extract_title] Найден заголовок: {title}")
                return title

    logger.warning("[extract_title] Заголовок первого уровня не найден в markdown")
    return None


class DataExtractionService:
    """Сервис для извлечения данных из PDF файлов"""
    
    def __init__(self):
        self.s3_client = get_s3_client()
    
    async def upload_and_process_pdf(
        self, 
        background_tasks: BackgroundTasks, 
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

        pdf_exists = await self.s3_client.object_exists(bucket, pdf_key)

        async def process_pdf_and_upload(pdf_bytes: bytes, filename: str = None):
            # Конвертация PDF в Markdown через gRPC сервис
            logger.info(f"[pdf_to_md] Начинаем обработку doc_id={doc_id}")
            
            tmp_dir = SysPath(tempfile.mkdtemp(prefix="km_pdf_"))
            try:
                logger.info(f"[pdf_to_md] Начинаем обработку doc_id={doc_id}, tmp_dir={tmp_dir}")
                pdf_name = f"{doc_id}.pdf"
                tmp_pdf = tmp_dir / pdf_name
                with open(tmp_pdf, "wb") as f:
                    f.write(pdf_bytes)

                loop = asyncio.get_running_loop()

                def _on_progress(payload: dict) -> None:
                    """Callback для отслеживания прогресса обработки документа"""
                    try:
                        percent = payload.get('percent')
                        phase = payload.get('phase') or 'processing'
                        message = payload.get('message') or payload.get('last_message') or ''
                        logger.info(f"[pdf_to_md] Progress: {percent}% - {phase} - {message}")
                    except Exception:
                        pass

                # Используем gRPC сервис для конвертации PDF в Markdown
                grpc_client = get_pdf_to_md_grpc_client_instance()
                logger.info(f"[data_extraction] Используем gRPC клиент: host={grpc_client.host}, port={grpc_client.port}")
                logger.info(f"[data_extraction] Переменные окружения в момент вызова: PDF_TO_MD_SERVICE_HOST={os.getenv('PDF_TO_MD_SERVICE_HOST', 'НЕ УСТАНОВЛЕНА')}, PDF_TO_MD_SERVICE_PORT={os.getenv('PDF_TO_MD_SERVICE_PORT', 'НЕ УСТАНОВЛЕНА')}")
                
                result = await grpc_client.convert_pdf(
                    pdf_content=pdf_bytes,
                    doc_id=doc_id,
                    timeout=3600,
                    on_progress=_on_progress
                )
                
                if not result["success"]:
                    raise RuntimeError(f"Ошибка конвертации: {result['message']}")
                
                # Создаем виртуальные outputs для совместимости
                outputs = {"markdown": None, "images_dir": tmp_dir}
                
                # Сохраняем markdown во временную директорию
                extracted_title = None
                if result.get("markdown_content"):
                    md_path = tmp_dir / f"{doc_id}.md"
                    md_path.write_text(result["markdown_content"], encoding="utf-8", errors="ignore")
                    outputs["markdown"] = md_path
                    logger.info(f"[pdf_to_md] Markdown сохранен: {md_path}")

                    # Извлекаем заголовок из markdown
                    extracted_title = extract_title_from_markdown(result["markdown_content"])
                    if extracted_title:
                        logger.info(f"[pdf_to_md] Извлечен заголовок документа: {extracted_title}")
                
                # Сохраняем изображения
                if result.get("images"):
                    for img_name, img_data in result["images"].items():
                        img_path = tmp_dir / img_name
                        img_path.write_bytes(img_data)
                        logger.info(f"[pdf_to_md] Изображение сохранено: {img_name}")
                
                # Сохраняем метаданные если есть
                if result.get("metadata_json"):
                    import json
                    meta_path = tmp_dir / f"{doc_id}_meta.json"
                    # metadata_json уже в формате JSON строки
                    meta_path.write_text(result["metadata_json"], encoding="utf-8")
                    outputs["meta"] = meta_path
                    logger.info(f"[pdf_to_md] Метаданные сохранены: {meta_path}")

                if outputs.get("markdown") is not None:
                    md_bytes = outputs["markdown"].read_bytes()
                    md_key = f"{prefix}{doc_id}.md"
                    await self.s3_client.upload_bytes(
                        md_bytes, bucket, md_key, content_type="text/markdown; charset=utf-8"
                    )
                    logger.info(f"[pdf_to_md] Загружен markdown: s3://{bucket}/{md_key}")

                if outputs.get("meta") is not None:
                    meta_bytes = outputs["meta"].read_bytes()
                    meta_key = f"{prefix}{doc_id}_meta.json"
                    await self.s3_client.upload_bytes(
                        meta_bytes, bucket, meta_key, content_type="application/json"
                    )
                    logger.info(f"[pdf_to_md] Загружен meta: s3://{bucket}/{meta_key}")

                img_exts = ("*.jpeg", "*.jpg", "*.png")
                for pattern in img_exts:
                    for img in outputs["images_dir"].glob(pattern):
                        await self.s3_client.upload_bytes(
                            img.read_bytes(), bucket, f"{prefix}{img.name}", 
                            content_type=mimetypes.guess_type(img.name)[0] or "image/jpeg"
                        )
                        logger.info(f"[pdf_to_md] Загружено изображение: {img.name}")
                
                # Извлекаем S3 ключи для markdown версий
                docling_raw_s3_key = result.get("docling_raw_s3_key")
                formatted_s3_key = result.get("formatted_s3_key")

                # Сохраняем документ в Neo4j для поддержки аннотаций
                try:
                    # Проверяем, существует ли документ
                    existing_doc = PDFDocument.nodes.get_or_none(uid=doc_id)
                    if not existing_doc:
                        # Создаем новый документ с заголовком из markdown и S3 ключами
                        pdf_doc = PDFDocument(
                            uid=doc_id,
                            original_filename=filename or f"{doc_id}.pdf",
                            md5_hash=doc_id,
                            s3_key=pdf_key,
                            processing_status='annotated',
                            is_processed=True,
                            title=extracted_title,  # Сохраняем извлечённый заголовок
                            docling_raw_md_s3_key=docling_raw_s3_key,
                            formatted_md_s3_key=formatted_s3_key
                        ).save()
                        logger.info(f"[Neo4j] Создан документ {doc_id} с заголовком: {extracted_title}, "
                                   f"raw_key: {docling_raw_s3_key}, formatted_key: {formatted_s3_key}")
                    else:
                        # Обновляем существующий документ
                        update_needed = False
                        if extracted_title and not existing_doc.title:
                            existing_doc.title = extracted_title
                            update_needed = True
                            logger.info(f"[Neo4j] Обновлён заголовок документа {doc_id}: {extracted_title}")

                        # Обновляем S3 ключи если они были получены
                        if docling_raw_s3_key:
                            existing_doc.docling_raw_md_s3_key = docling_raw_s3_key
                            update_needed = True
                            logger.info(f"[Neo4j] Обновлён raw markdown key: {docling_raw_s3_key}")

                        if formatted_s3_key:
                            existing_doc.formatted_md_s3_key = formatted_s3_key
                            update_needed = True
                            logger.info(f"[Neo4j] Обновлён formatted markdown key: {formatted_s3_key}")

                        if update_needed:
                            existing_doc.save()
                        else:
                            logger.info(f"[Neo4j] Документ {doc_id} уже существует, обновления не требуются")
                except Exception as neo_err:
                    logger.error(f"[Neo4j] Ошибка сохранения документа {doc_id}: {neo_err}")
                    # Не прерываем выполнение, т.к. файлы уже загружены в S3

                logger.info(f"[pdf_to_md] Обработка документа {doc_id} успешно завершена")
            except Exception as e:
                logger.exception(f"PDF to MD processing failed: {e}")
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
                background_tasks.add_task(process_pdf_and_upload, existing_pdf, file.filename)
                logger.info(f"[pdf_to_md] Переобработка запущена для существующего PDF: doc_id={doc_id}")
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

        background_tasks.add_task(process_pdf_and_upload, raw, file.filename)

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
            document = PDFDocument.nodes.get_or_none(uid=doc_id)
        except Exception as e:
            logger.error(f"Ошибка получения документа из Neo4j: {e}")
            document = None

        # Определяем S3 ключ в зависимости от версии
        if version == "active":
            # Используем логику из PDFDocument.get_active_markdown_key()
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

        return {
            "success": True,
            "doc_id": doc_id,
            "version": version,
            "s3_key": md_key,
            "markdown": markdown_text
        }

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """Удаляет документ и все его файлы из S3 (префикс documents/{doc_id}/), а также все аннотации из Neo4j."""
        # Сначала удаляем аннотации из Neo4j
        try:
            document = PDFDocument.nodes.get_or_none(uid=doc_id)
            if document:
                # Удаляем все связанные аннотации
                from neomodel import db
                query = """
                MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
                DETACH DELETE a
                """
                db.cypher_query(query, {'doc_id': doc_id})
                logger.info(f"Удалены все аннотации для документа {doc_id}")
        except Exception as e:
            logger.error(f"Ошибка удаления аннотаций для документа {doc_id}: {e}")

        # Затем удаляем файлы из S3
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

        logger.info(f"[data_extraction] Пользовательский markdown сохранен: s3://{bucket}/{md_key}")

        # Обновляем Neo4j PDFDocument с user_md_s3_key
        try:
            document = PDFDocument.nodes.get_or_none(uid=doc_id)
            if document:
                document.user_md_s3_key = md_key
                document.save()
                logger.info(f"[Neo4j] Обновлен user_md_s3_key для документа {doc_id}: {md_key}")
            else:
                logger.warning(f"[Neo4j] Документ {doc_id} не найден в Neo4j, не удалось обновить user_md_s3_key")
        except Exception as e:
            logger.error(f"[Neo4j] Ошибка обновления user_md_s3_key для {doc_id}: {e}")
            # Не прерываем выполнение, т.к. файл уже сохранен в S3

        return {
            "success": True,
            "doc_id": doc_id,
            "s3_key": md_key,
            "message": "Пользовательский markdown успешно сохранен"
        }

    async def list_documents(self) -> Dict[str, Any]:
        """Список документов по префиксу documents/ из S3 с метаданными из Neo4j."""
        from src.models import PDFDocument

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
                    "files": {},
                    "title": None,
                    "original_filename": None,
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

        # Получаем метаданные из Neo4j для каждого документа
        for doc_id, item in doc_map.items():
            try:
                # Ищем документ в Neo4j по uid
                pdf_doc = PDFDocument.nodes.get_or_none(uid=doc_id)
                if pdf_doc:
                    item['title'] = pdf_doc.title
                    item['original_filename'] = pdf_doc.original_filename
            except Exception as e:
                logger.warning(f"Не удалось получить метаданные для документа {doc_id}: {e}")

        # Отфильтровываем «пустые» документы: показываем только если есть markdown
        documents = []
        for item in doc_map.values():
            if item.get('has_markdown'):
                documents.append(item)
        return {"success": True, "documents": documents}
