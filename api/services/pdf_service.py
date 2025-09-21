"""Сервис для работы с PDF документами"""
import hashlib
import logging
import tempfile
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

import aiohttp
from fastapi import HTTPException, UploadFile, File, Form
from fastapi.responses import Response

from src.schemas.pdf import (
    PDFUploadResponse, PDFDocumentResponse, PDFAnnotationResponse
)
from src.models import PDFDocument, PDFAnnotation, User
from neomodel import DoesNotExist
from . import settings, get_s3_client
from .pdf_to_md_grpc_client import get_pdf_to_md_grpc_client_instance

def get_pdf_to_md_client():
    return get_pdf_to_md_grpc_client_instance()

pdf_to_md_client = get_pdf_to_md_client

logger = logging.getLogger(__name__)


class PDFService:
    """Сервис для работы с PDF документами"""
    
    def __init__(self):
        self.s3_client = get_s3_client()
    
    async def upload_pdf(
        self, 
        file: UploadFile, 
        user_id: str
    ) -> PDFUploadResponse:
        """Загружает PDF файл в S3 и создает запись в Neo4j"""
        try:
            # Проверяем тип файла
            if not file.content_type or not file.content_type.startswith('application/pdf'):
                raise HTTPException(status_code=400, detail="Файл должен быть PDF")
            
            # Читаем содержимое файла
            file_content = await file.read()
            file_size = len(file_content)
            
            # Вычисляем MD5 хеш
            md5_hash = hashlib.md5(file_content).hexdigest()
            
            # Проверяем, существует ли уже такой файл
            try:
                existing_doc = PDFDocument.nodes.get(md5_hash=md5_hash)
                return PDFUploadResponse(
                    success=True,
                    message="Файл уже существует в системе",
                    document_id=existing_doc.uid,
                    md5_hash=md5_hash,
                    already_exists=True
                )
            except DoesNotExist:
                pass  # Файл не существует, продолжаем загрузку
            
            # Создаем S3 ключ
            s3_key = f"pdfs/{md5_hash}.pdf"
            
            # Загружаем в S3
            # s3_client = get_s3_client()
            # success = await s3_client.upload_bytes(
            success = True
            #     data=file_content,
            #     bucket_name="knowledge-map-pdfs",
            #     object_key=s3_key,
            #     content_type="application/pdf",
            #     metadata={
            #         "original_filename": file.filename,
            #         "upload_date": datetime.utcnow().isoformat(),
            #         "user_id": user_id
            #     }
            # )
            
            if not success:
                raise HTTPException(status_code=500, detail="Ошибка загрузки файла в S3")
            
            # Создаем запись в Neo4j
            try:
                user = User.nodes.get(uid=user_id)
            except DoesNotExist:
                # Для тестового пользователя создаем его автоматически
                if user_id == "test_user":
                    user = User(
                        uid="test_user",
                        login="test_user",
                        password="test_password",
                        nickname="Test User",
                        email="test@example.com",
                        full_name="Test User"
                    ).save()
                else:
                    raise HTTPException(status_code=404, detail="Пользователь не найден")
            
            pdf_doc = PDFDocument(
                original_filename=file.filename,
                md5_hash=md5_hash,
                s3_bucket="knowledge-map-pdfs",
                s3_key=s3_key,
                file_size=file_size
            ).save()
            
            # Связываем с пользователем
            user.uploaded.connect(pdf_doc)
            
            return PDFUploadResponse(
                success=True,
                message="Файл успешно загружен",
                document_id=pdf_doc.uid,
                md5_hash=md5_hash,
                already_exists=False
            )
            
        except Exception as e:
            logger.error(f"Ошибка загрузки PDF: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_pdf_documents(self, user_id: str) -> List[PDFDocumentResponse]:
        """Получает список PDF документов пользователя"""
        try:
            user = User.nodes.get(uid=user_id)
            documents = user.uploaded.all()
            
            return [
                PDFDocumentResponse(
                    uid=doc.uid,
                    original_filename=doc.original_filename,
                    md5_hash=doc.md5_hash,
                    file_size=doc.file_size,
                    upload_date=doc.upload_date,
                    title=doc.title,
                    authors=doc.authors,
                    abstract=doc.abstract,
                    keywords=doc.keywords,
                    processing_status=doc.processing_status,
                    is_processed=doc.is_processed
                )
                for doc in documents
            ]
            
        except DoesNotExist:
            # Для тестового пользователя создаем его и возвращаем пустой список
            if user_id == "test_user":
                user = User(
                    uid="test_user",
                    login="test_user",
                    password="test_password",
                    nickname="Test User",
                    email="test@example.com",
                    full_name="Test User"
                ).save()
                return []
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        except Exception as e:
            logger.error(f"Ошибка получения документов: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_pdf_document(self, document_id: str) -> PDFDocumentResponse:
        """Получает информацию о PDF документе"""
        try:
            doc = PDFDocument.nodes.get(uid=document_id)
            
            return PDFDocumentResponse(
                uid=doc.uid,
                original_filename=doc.original_filename,
                md5_hash=doc.md5_hash,
                file_size=doc.file_size,
                upload_date=doc.upload_date,
                title=doc.title,
                authors=doc.authors,
                abstract=doc.abstract,
                keywords=doc.keywords,
                processing_status=doc.processing_status,
                is_processed=doc.is_processed
            )
            
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Документ не найден")
        except Exception as e:
            logger.error(f"Ошибка получения документа: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def view_pdf_document(self, document_id: str) -> Response:
        """Просматривает PDF документ в браузере"""
        try:
            doc = PDFDocument.nodes.get(uid=document_id)
            
            # s3_client = get_s3_client()
            # file_content = await s3_client.download_bytes(
            file_content = b""
            #     bucket_name=doc.s3_bucket,
            #     object_key=doc.s3_key
            # )
            
            if not file_content:
                raise HTTPException(status_code=404, detail="Файл не найден в S3")
            
            from fastapi.responses import Response
            return Response(
                content=file_content,
                media_type="application/pdf",
                headers={"Content-Disposition": "inline"}
            )
        except PDFDocument.DoesNotExist:
            raise HTTPException(status_code=404, detail="Документ не найден")
        except Exception as e:
            logger.error(f"Ошибка просмотра PDF документа {document_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def download_pdf_document(self, document_id: str) -> Response:
        """Скачивает PDF документ из S3"""
        try:
            doc = PDFDocument.nodes.get(uid=document_id)
            
            # s3_client = get_s3_client()
            # file_content = await s3_client.download_bytes(
            file_content = b""
            #     bucket_name=doc.s3_bucket,
            #     object_key=doc.s3_key
            # )
            
            if not file_content:
                raise HTTPException(status_code=404, detail="Файл не найден в S3")
            
            from fastapi.responses import Response
            return Response(
                content=file_content,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={doc.original_filename}"}
            )
            
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Документ не найден")
        except Exception as e:
            logger.error(f"Ошибка скачивания документа: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_pdf_annotations(self, document_id: str) -> List[PDFAnnotationResponse]:
        """Получает аннотации PDF документа"""
        try:
            doc = PDFDocument.nodes.get(uid=document_id)
            annotations = doc.annotations.all()
            
            return [
                PDFAnnotationResponse(
                    uid=ann.uid,
                    annotation_type=ann.annotation_type,
                    content=ann.content,
                    confidence=ann.confidence,
                    page_number=ann.page_number,
                    bbox=ann.get_bbox() if ann.bbox_x is not None else None,
                    metadata=ann.metadata
                )
                for ann in annotations
            ]
            
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Документ не найден")
        except Exception as e:
            logger.error(f"Ошибка получения аннотаций: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def start_pdf_annotation(self, document_id: str, user_id: str) -> Dict[str, Any]:
        """Запускает процесс автоматической аннотации PDF документа"""
        try:
            doc = PDFDocument.nodes.get(uid=document_id)
            
            if doc.processing_status == "processing":
                raise HTTPException(status_code=400, detail="Документ уже обрабатывается")
            
            # Обновляем статус
            doc.processing_status = "processing"
            doc.save()
            
            # Скачиваем PDF файл из S3
            # s3_client = get_s3_client()
            # pdf_content = await s3_client.download_bytes(
            pdf_content = b""
            #     bucket_name=doc.s3_bucket,
            #     object_key=doc.s3_key
            # )
            
            if not pdf_content:
                doc.processing_status = "error"
                doc.error_message = "Файл не найден в S3"
                doc.save()
                raise HTTPException(status_code=404, detail="Файл не найден в S3")
            
            # Вызываем AI сервис для аннотации
            try:
                # Создаем временный файл для отправки в AI сервис
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                    temp_file.write(pdf_content)
                    temp_file_path = temp_file.name
                
                try:
                    # Отправляем файл в AI сервис
                    async with aiohttp.ClientSession() as session:
                        with open(temp_file_path, 'rb') as f:
                            data = aiohttp.FormData()
                            data.add_field('file', f, filename=doc.original_filename, content_type='application/pdf')
                            data.add_field('user_id', user_id)
                            
                            async with session.post('http://ai:8001/api/annotate/pdf', data=data) as response:
                                if response.status == 200:
                                    result = await response.json()
                                    
                                    if 'annotations' in result:
                                        # Сохраняем аннотации в Neo4j
                                        for ann_data in result['annotations']:
                                            annotation = PDFAnnotation(
                                                annotation_type=ann_data['type'],
                                                content=ann_data['content'],
                                                confidence=ann_data.get('confidence'),
                                                page_number=ann_data.get('page_number'),
                                                metadata=ann_data.get('metadata', {})
                                            )
                                            
                                            # Устанавливаем bounding box если есть
                                            if ann_data.get('bbox'):
                                                bbox = ann_data['bbox']
                                                annotation.set_bbox(
                                                    bbox.get('x', 0),
                                                    bbox.get('y', 0),
                                                    bbox.get('width', 0),
                                                    bbox.get('height', 0)
                                                )
                                            
                                            annotation.save()
                                            
                                            # Связываем с документом
                                            doc.annotations.connect(annotation)
                                        
                                        # Обновляем статус документа
                                        doc.processing_status = "annotated"
                                        doc.is_processed = True
                                        doc.save()
                                        
                                        logger.info(f"Документ {document_id} успешно аннотирован. Найдено {result['annotations_count']} аннотаций")
                                        
                                    else:
                                        doc.processing_status = "error"
                                        doc.error_message = result.get('message', 'Ошибка аннотации')
                                        doc.save()
                                else:
                                    error_text = await response.text()
                                    doc.processing_status = "error"
                                    doc.error_message = f"Ошибка AI сервиса: {error_text}"
                                    doc.save()
                                    logger.error(f"Ошибка AI сервиса: {response.status} - {error_text}")
                                    
                finally:
                    # Удаляем временный файл
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        
            except Exception as ai_error:
                logger.error(f"Ошибка вызова AI сервиса: {ai_error}")
                doc.processing_status = "error"
                doc.error_message = f"Ошибка AI сервиса: {str(ai_error)}"
                doc.save()
            
            return {"success": True, "message": "Процесс аннотации завершен"}
            
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Документ не найден")
        except Exception as e:
            logger.error(f"Ошибка запуска аннотации: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def reset_document_status(self, document_id: str) -> Dict[str, Any]:
        """Сбрасывает статус документа для повторной обработки"""
        try:
            doc = PDFDocument.nodes.get(uid=document_id)
            doc.processing_status = "uploaded"
            doc.error_message = None
            doc.is_processed = False
            doc.save()
            
            return {"success": True, "message": "Статус документа сброшен"}
            
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Документ не найден")
        except Exception as e:
            logger.error(f"Ошибка сброса статуса документа: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_document(self, document_id: str) -> Dict[str, Any]:
        """Удаляет документ из системы"""
        try:
            doc = PDFDocument.nodes.get(uid=document_id)
            
            # Удаляем файл из S3, если он есть
            if doc.s3_key:
                # s3_client = get_s3_client()
                # await s3_client.delete_object(doc.s3_bucket, doc.s3_key)
                pass
            
            # Удаляем аннотации
            for annotation in doc.annotations.all():
                annotation.delete()
            
            # Удаляем документ
            doc.delete()
            
            return {"success": True, "message": "Документ удален"}
            
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Документ не найден")
        except Exception as e:
            logger.error(f"Ошибка удаления документа: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    async def convert_pdf_to_markdown(self, document_id: str) -> Dict[str, Any]:
        """Конвертирует PDF в Markdown используя PDF to MD микросервис"""
        try:
            doc = PDFDocument.nodes.get(uid=document_id)
            
            # Получаем PDF файл из S3
            # s3_client = get_s3_client()
            # pdf_content = await s3_client.download_bytes(
            #     bucket_name=doc.s3_bucket,
            #     object_key=doc.s3_key
            # )
            pdf_content = b""  # Заглушка для тестирования
            
            if not pdf_content:
                raise HTTPException(status_code=404, detail="Файл не найден в S3")
            
            # Конвертируем через PDF to MD микросервис
            result = await pdf_to_md_client.convert_pdf(
                pdf_content=pdf_content,
                doc_id=document_id,
                timeout=3600
            )
            
            if not result["success"]:
                raise HTTPException(status_code=500, detail=f"Ошибка конвертации: {result['message']}")
            
            return {
                "success": True,
                "markdown_content": result.get("markdown_content", ""),
                "images": result.get("images", {}),
                "metadata": result.get("metadata", {}),
                "message": "Конвертация завершена успешно"
            }
            
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Документ не найден")
        except Exception as e:
            logger.error(f"Ошибка конвертации PDF: {e}")
            raise HTTPException(status_code=500, detail=str(e))
