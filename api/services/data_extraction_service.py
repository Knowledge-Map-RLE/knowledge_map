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

        # Получаем активную версию markdown используя логику версионирования
        try:
            document = PDFDocument.nodes.get_or_none(uid=doc_id)
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
            document = PDFDocument.nodes.get_or_none(uid=doc_id)
            if document:
                # Комплексное удаление всех связанных данных
                query = """
                MATCH (d:PDFDocument {uid: $doc_id})

                // Удаляем паттерны, связанные с аннотациями документа
                OPTIONAL MATCH (d)-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
                OPTIONAL MATCH (p:Pattern {source_token_uid: a.uid})
                DETACH DELETE p

                // Удаляем все аннотации со всеми связями
                WITH d, collect(a) as annotations
                UNWIND annotations as ann
                DETACH DELETE ann

                // Удаляем сам документ
                WITH d
                DETACH DELETE d

                RETURN count(d) as deleted_count
                """
                result, _ = db.cypher_query(query, {'doc_id': doc_id})
                deleted_count = result[0][0] if result else 0
                logger.info(f"Удалены все данные из Neo4j для документа {doc_id}: аннотации, связи, паттерны, цепочки, документ (удалено: {deleted_count})")

                # Проверяем, что документ действительно удален
                check_doc = PDFDocument.nodes.get_or_none(uid=doc_id)
                if check_doc:
                    logger.error(f"ОШИБКА: Документ {doc_id} всё ещё существует в Neo4j после удаления!")
                else:
                    logger.info(f"Подтверждено: документ {doc_id} успешно удалён из Neo4j")
            else:
                logger.warning(f"Документ {doc_id} не найден в Neo4j, нечего удалять")
        except Exception as e:
            logger.error(f"Ошибка удаления данных из Neo4j для документа {doc_id}: {e}", exc_info=True)

        # Затем удаляем файлы из S3
        bucket = settings.S3_BUCKET_NAME
        deleted = 0

        # Префиксы для удаления:
        # 1. documents/{doc_id}/ - основные файлы
        # 2. markdown/{doc_id}* - версионированные markdown файлы
        prefixes_to_delete = [
            f"documents/{doc_id}/",
            f"markdown/{doc_id}"
        ]

        import asyncio
        for prefix in prefixes_to_delete:
            # Собираем все ключи для удаления (один раз)
            contents = await self.s3_client.list_objects(bucket, prefix)
            keys_to_delete = []

            for obj in contents:
                key = obj.get('Key') or obj.get('key') or ''
                if key and not key in keys_to_delete:
                    keys_to_delete.append(key)

            if not keys_to_delete:
                continue

            # Удаляем все собранные ключи
            for key in keys_to_delete:
                ok = await self.s3_client.delete_object(bucket, key)
                if ok:
                    deleted += 1
                    logger.info(f"Удален S3 объект: {key}")

            # Даём время на eventual consistency и повторно пытаемся удалить
            for retry in range(3):
                await asyncio.sleep(0.5)

                remaining = await self.s3_client.list_objects(bucket, prefix)
                if not remaining:
                    break

                # Если остались файлы - пробуем удалить версии или повторить удаление
                try:
                    async with self.s3_client.client_context() as s3:
                        # Удаление всех версий
                        versions_resp = await s3.list_object_versions(Bucket=bucket, Prefix=prefix)

                        # Удаляем версии
                        for v in versions_resp.get('Versions', []):
                            key = v.get('Key')
                            ver = v.get('VersionId')
                            if key and ver:
                                await s3.delete_object(Bucket=bucket, Key=key, VersionId=ver)
                                deleted += 1
                                logger.info(f"Удалена версия S3 объекта: {key} (version: {ver})")

                        # Удаляем delete markers
                        for m in versions_resp.get('DeleteMarkers', []):
                            key = m.get('Key')
                            ver = m.get('VersionId')
                            if key and ver:
                                await s3.delete_object(Bucket=bucket, Key=key, VersionId=ver)
                                deleted += 1
                                logger.info(f"Удален delete marker: {key} (version: {ver})")

                        # Если версий нет, просто повторяем удаление основных ключей
                        if not versions_resp.get('Versions') and not versions_resp.get('DeleteMarkers'):
                            for obj in remaining:
                                key = obj.get('Key') or obj.get('key') or ''
                                if key:
                                    await s3.delete_object(Bucket=bucket, Key=key)
                                    logger.info(f"Повторное удаление S3 объекта: {key}")
                                    deleted += 1
                except Exception as e:
                    logger.warning(f"Попытка {retry + 1}/3 удаления версий для {prefix}: {e}")

            # Финальная проверка после всех попыток
            await asyncio.sleep(1.0)
            remaining = await self.s3_client.list_objects(bucket, prefix)
            if remaining:
                rem_keys = [o.get('Key') or o.get('key') or '' for o in remaining]
                logger.warning(f"S3 всё ещё содержит ключи под {prefix} после {retry + 1} попыток: {rem_keys}")

        logger.info(f"Успешно удален документ {doc_id}: удалено {deleted} файлов из S3")
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
        """
        Список документов из Neo4j с проверкой файлов в S3.

        Использует Neo4j как source of truth для избежания проблем с eventual consistency в S3.
        """
        from src.models import PDFDocument

        bucket = settings.S3_BUCKET_NAME
        documents = []

        try:
            # Получаем все документы из Neo4j
            all_docs = PDFDocument.nodes.all()

            for pdf_doc in all_docs:
                doc_id = pdf_doc.uid
                prefix = f"documents/{doc_id}/"

                # Формируем пути к файлам
                pdf_key = f"{prefix}{doc_id}.pdf"

                # Определяем markdown ключ (приоритет: user > formatted > raw > старый формат)
                md_key = None
                if pdf_doc.user_md_s3_key:
                    md_key = pdf_doc.user_md_s3_key
                elif pdf_doc.formatted_md_s3_key:
                    md_key = pdf_doc.formatted_md_s3_key
                elif pdf_doc.docling_raw_md_s3_key:
                    md_key = pdf_doc.docling_raw_md_s3_key
                else:
                    md_key = f"{prefix}{doc_id}.md"

                # Проверяем реальное существование файлов в S3
                pdf_exists = await self.s3_client.object_exists(bucket, pdf_key)
                md_exists = await self.s3_client.object_exists(bucket, md_key)

                # Показываем документ только если markdown реально существует
                if md_exists:
                    item = {
                        "doc_id": doc_id,
                        "has_markdown": True,
                        "files": {},
                        "title": pdf_doc.title,
                        "original_filename": pdf_doc.original_filename,
                    }

                    # Добавляем файлы только если они реально существуют
                    if md_exists:
                        item['files']['markdown'] = md_key
                    if pdf_exists:
                        item['files']['pdf'] = pdf_key

                    documents.append(item)

        except Exception as e:
            logger.error(f"Ошибка получения списка документов: {e}")

        return {"success": True, "documents": documents}

    async def check_data_availability(self, doc_id: str) -> Dict[str, Any]:
        """
        Проверяет доступность всех данных для экспорта в тестовый датасет.

        Args:
            doc_id: ID документа

        Returns:
            Dict со статусом доступности данных
        """
        from src.models import PDFDocument
        from neomodel import db

        bucket = settings.S3_BUCKET_NAME
        prefix = f"documents/{doc_id}/"

        # Проверка PDF
        pdf_key = f"{prefix}{doc_id}.pdf"
        pdf_exists = await self.s3_client.object_exists(bucket, pdf_key)

        # Проверка Markdown
        markdown_exists = False
        document = PDFDocument.nodes.get_or_none(uid=doc_id)
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
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
        RETURN count(a) as count
        """
        results, _ = db.cypher_query(query_annotations, {"doc_id": doc_id})
        annotation_count = results[0][0] if results else 0
        has_annotations = annotation_count > 0

        # Проверка связей
        query_relations = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a1:MarkdownAnnotation)
        MATCH (a1)-[r:RELATES_TO]->(a2:MarkdownAnnotation)
        RETURN count(r) as count
        """
        results, _ = db.cypher_query(query_relations, {"doc_id": doc_id})
        relation_count = results[0][0] if results else 0
        has_relations = relation_count > 0

        # Проверка цепочек (action chains)
        # Паттерны связаны с документом через аннотации (MarkdownAnnotation)
        query_chains = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
        MATCH (p1:Pattern {source_token_uid: a.uid})-[r:ACTION_SEQUENCE]->(p2:Pattern)
        RETURN count(DISTINCT r) as count
        """
        results, _ = db.cypher_query(query_chains, {"doc_id": doc_id})
        chain_count = results[0][0] if results else 0
        has_chains = chain_count > 0

        # Проверка паттернов
        # Паттерны связаны с документом через аннотации (MarkdownAnnotation)
        query_patterns = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
        MATCH (p:Pattern {source_token_uid: a.uid})
        RETURN count(DISTINCT p) as count
        """
        results, _ = db.cypher_query(query_patterns, {"doc_id": doc_id})
        pattern_count = results[0][0] if results else 0
        has_patterns = pattern_count > 0

        # Определяем готовность к экспорту (все компоненты обязательны)
        is_ready = pdf_exists and markdown_exists and has_annotations and has_patterns and has_chains

        # Список отсутствующих компонентов
        missing_items = []
        if not pdf_exists:
            missing_items.append("PDF файл")
        if not markdown_exists:
            missing_items.append("Markdown файл")
        if not has_annotations:
            missing_items.append("Аннотации")
        if not has_patterns:
            missing_items.append("Паттерны")
        if not has_chains:
            missing_items.append("Цепочки действий")

        return {
            "pdf_exists": pdf_exists,
            "markdown_exists": markdown_exists,
            "has_annotations": has_annotations,
            "has_relations": has_relations,
            "has_chains": has_chains,
            "has_patterns": has_patterns,
            "annotation_count": annotation_count,
            "relation_count": relation_count,
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
