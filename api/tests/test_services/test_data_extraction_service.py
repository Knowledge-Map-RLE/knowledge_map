"""Тесты для сервиса извлечения данных из PDF"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import BackgroundTasks, UploadFile
from io import BytesIO

from services.data_extraction_service import DataExtractionService
from src.schemas.api import DataExtractionResponse


class TestDataExtractionService:
    """Тесты для DataExtractionService"""
    
    def test_service_initialization(self):
        """Тест инициализации сервиса"""
        service = DataExtractionService()
        assert service.s3_client is not None
    
    @pytest.mark.asyncio
    async def test_upload_and_process_pdf_invalid_content_type(self):
        """Тест загрузки PDF с неверным типом контента"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем мок файла с неверным типом
        file = MagicMock(spec=UploadFile)
        file.content_type = "text/plain"
        
        with pytest.raises(Exception) as exc_info:
            await service.upload_and_process_pdf(background_tasks, file)
        
        assert "Ожидается PDF файл" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_upload_and_process_pdf_empty_file(self):
        """Тест загрузки пустого PDF файла"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем мок файла
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=b"")
        
        with pytest.raises(Exception) as exc_info:
            await service.upload_and_process_pdf(background_tasks, file)
        
        assert "Пустой файл" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_upload_and_process_pdf_new_file_success(self):
        """Тест успешной загрузки нового PDF файла"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем мок файла
        test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=test_pdf_content)
        
        with patch.object(service.s3_client, 'object_exists', return_value=False) as mock_exists, \
             patch.object(service.s3_client, 'upload_bytes', return_value=True) as mock_upload, \
             patch('services.data_extraction_service.pdf_to_md_grpc_client') as mock_grpc_client, \
             patch('services.data_extraction_service.marker_progress_store') as mock_progress:
            
            # Настраиваем моки
            mock_grpc_client.convert_pdf = AsyncMock(return_value={
                "success": True,
                "doc_id": "test_doc",
                "markdown_content": "# Test Document",
                "images": {"image1.png": b"image_data"},
                "metadata_json": '{"pages": 1}',
                "message": "Success"
            })
            
            mock_progress.init_doc = AsyncMock()
            mock_progress.complete_doc = AsyncMock()
            
            # Выполняем тест
            result = await service.upload_and_process_pdf(background_tasks, file)
            
            # Проверяем результат
            assert isinstance(result, DataExtractionResponse)
            assert result.success is True
            assert result.doc_id is not None
            assert "Файл принят, конвертация запущена" in result.message
            
            # Проверяем вызовы
            mock_exists.assert_called_once()
            mock_upload.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_and_process_pdf_existing_file_with_markdown(self):
        """Тест загрузки существующего PDF файла с уже существующим markdown"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем мок файла
        test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=test_pdf_content)
        
        with patch.object(service.s3_client, 'object_exists', side_effect=[True, True]) as mock_exists, \
             patch('services.data_extraction_service._compute_md5', return_value="test_doc_hash"):
            
            # Выполняем тест
            result = await service.upload_and_process_pdf(background_tasks, file)
            
            # Проверяем результат
            assert isinstance(result, DataExtractionResponse)
            assert result.success is True
            assert "Дубликат: уже существует" in result.message
            
            # Проверяем вызовы
            assert mock_exists.call_count == 2
    
    @pytest.mark.asyncio
    async def test_upload_and_process_pdf_existing_file_without_markdown(self):
        """Тест загрузки существующего PDF файла без markdown"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем мок файла
        test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=test_pdf_content)
        
        with patch.object(service.s3_client, 'object_exists', side_effect=[True, False]) as mock_exists, \
             patch.object(service.s3_client, 'download_bytes', return_value=test_pdf_content) as mock_download, \
             patch('services.data_extraction_service._compute_md5', return_value="test_doc_hash"), \
             patch('services.data_extraction_service.pdf_to_md_grpc_client') as mock_grpc_client, \
             patch('services.data_extraction_service.marker_progress_store') as mock_progress:
            
            # Настраиваем моки
            mock_grpc_client.convert_pdf = AsyncMock(return_value={
                "success": True,
                "doc_id": "test_doc",
                "markdown_content": "# Test Document",
                "images": {},
                "metadata_json": "",
                "message": "Success"
            })
            
            mock_progress.init_doc = AsyncMock()
            mock_progress.complete_doc = AsyncMock()
            
            # Выполняем тест
            result = await service.upload_and_process_pdf(background_tasks, file)
            
            # Проверяем результат
            assert isinstance(result, DataExtractionResponse)
            assert result.success is True
            assert "Конвертация запущена для существующего PDF" in result.message
            
            # Проверяем вызовы
            assert mock_exists.call_count == 2
            mock_download.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_and_process_pdf_s3_upload_failure(self):
        """Тест неудачной загрузки в S3"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем мок файла
        test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=test_pdf_content)
        
        with patch.object(service.s3_client, 'object_exists', return_value=False) as mock_exists, \
             patch.object(service.s3_client, 'upload_bytes', return_value=False) as mock_upload:
            
            with pytest.raises(Exception) as exc_info:
                await service.upload_and_process_pdf(background_tasks, file)
            
            assert "Не удалось сохранить PDF в S3" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_export_annotations_success(self):
        """Тест успешного экспорта аннотаций"""
        service = DataExtractionService()
        
        test_annotations = b'{"annotations": [{"id": 1, "text": "test"}]}'
        
        with patch.object(service.s3_client, 'object_exists', return_value=True) as mock_exists, \
             patch.object(service.s3_client, 'download_bytes', return_value=test_annotations) as mock_download:
            
            result = await service.export_annotations("test_doc")
            
            # Проверяем, что возвращается StreamingResponse
            assert hasattr(result, 'body_iterator')
            assert hasattr(result, 'media_type')
            assert result.media_type == "application/json"
            
            # Проверяем вызовы
            mock_exists.assert_called_once()
            mock_download.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_export_annotations_not_found(self):
        """Тест экспорта несуществующих аннотаций"""
        service = DataExtractionService()
        
        with patch.object(service.s3_client, 'object_exists', return_value=False) as mock_exists:
            with pytest.raises(Exception) as exc_info:
                await service.export_annotations("test_doc")
            
            assert "Аннотации не найдены" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_import_annotations_success(self):
        """Тест успешного импорта аннотаций"""
        service = DataExtractionService()
        
        from src.schemas.api import ImportAnnotationsRequest
        
        request = ImportAnnotationsRequest(
            doc_id="test_doc",
            annotations_json={"annotations": [{"id": 1, "text": "test"}]}
        )
        
        with patch.object(service.s3_client, 'upload_bytes', return_value=True) as mock_upload:
            result = await service.import_annotations(request)
            
            assert result["success"] is True
            assert "key" in result
            
            mock_upload.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_import_annotations_missing_doc_id(self):
        """Тест импорта аннотаций без doc_id"""
        service = DataExtractionService()
        
        from src.schemas.api import ImportAnnotationsRequest
        
        request = ImportAnnotationsRequest(
            doc_id="",
            annotations_json={"annotations": []}
        )
        
        with pytest.raises(Exception) as exc_info:
            await service.import_annotations(request)
        
        assert "doc_id обязателен" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_document_assets_success(self):
        """Тест успешного получения ресурсов документа"""
        service = DataExtractionService()
        
        test_markdown = "# Test Document\n\nContent here"
        test_objects = [
            {"Key": "documents/test_doc/test_doc.md"},
            {"Key": "documents/test_doc/image1.png"},
            {"Key": "documents/test_doc/image2.jpg"}
        ]
        
        with patch.object(service.s3_client, 'object_exists', return_value=True) as mock_exists, \
             patch.object(service.s3_client, 'download_text', return_value=test_markdown) as mock_download_text, \
             patch.object(service.s3_client, 'list_objects', return_value=test_objects) as mock_list, \
             patch.object(service.s3_client, 'get_object_url', return_value="http://example.com/image.png") as mock_url:
            
            result = await service.get_document_assets("test_doc", include_urls=True)
            
            assert result["success"] is True
            assert result["doc_id"] == "test_doc"
            assert result["markdown"] == test_markdown
            assert len(result["images"]) == 2
            assert "image_urls" in result
            assert len(result["image_urls"]) == 2
            
            # Проверяем вызовы
            mock_exists.assert_called_once()
            mock_download_text.assert_called_once()
            mock_list.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_document_success(self):
        """Тест успешного удаления документа"""
        service = DataExtractionService()
        
        test_objects = [
            {"Key": "documents/test_doc/test_doc.pdf"},
            {"Key": "documents/test_doc/test_doc.md"},
            {"Key": "documents/test_doc/image1.png"}
        ]
        
        with patch.object(service.s3_client, 'list_objects', return_value=test_objects) as mock_list, \
             patch.object(service.s3_client, 'delete_object', return_value=True) as mock_delete:
            
            result = await service.delete_document("test_doc")
            
            assert result["success"] is True
            assert result["deleted"] == 3
            
            # Проверяем вызовы
            assert mock_list.call_count >= 1
            assert mock_delete.call_count == 3
    
    @pytest.mark.asyncio
    async def test_list_documents_success(self):
        """Тест успешного получения списка документов"""
        service = DataExtractionService()
        
        test_objects = [
            {"Key": "documents/doc1/doc1.pdf"},
            {"Key": "documents/doc1/doc1.md"},
            {"Key": "documents/doc2/doc2.pdf"},
            {"Key": "documents/doc2/doc2.md"},
            {"Key": "documents/doc3/doc3.pdf"}  # Без markdown
        ]
        
        with patch.object(service.s3_client, 'list_objects', return_value=test_objects) as mock_list, \
             patch.object(service.s3_client, 'object_exists', side_effect=[True, True, True, True, False]) as mock_exists:
            
            result = await service.list_documents()
            
            assert result["success"] is True
            assert len(result["documents"]) == 2  # Только документы с markdown
            
            # Проверяем структуру документов
            for doc in result["documents"]:
                assert "doc_id" in doc
                assert "has_markdown" in doc
                assert "files" in doc
                assert doc["has_markdown"] is True
            
            mock_list.assert_called_once()


class TestDataExtractionServiceIntegration:
    """Интеграционные тесты для DataExtractionService"""
    
    @pytest.mark.asyncio
    async def test_full_pdf_processing_workflow(self):
        """Тест полного рабочего процесса обработки PDF"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем тестовый PDF
        test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=test_pdf_content)
        
        with patch.object(service.s3_client, 'object_exists', return_value=False) as mock_exists, \
             patch.object(service.s3_client, 'upload_bytes', return_value=True) as mock_upload, \
             patch('services.data_extraction_service.pdf_to_md_grpc_client') as mock_grpc_client, \
             patch('services.data_extraction_service.marker_progress_store') as mock_progress:
            
            # Настраиваем моки для успешной конвертации
            mock_grpc_client.convert_pdf = AsyncMock(return_value={
                "success": True,
                "doc_id": "integration_test_doc",
                "markdown_content": "# Integration Test Document\n\nThis is a test document.",
                "images": {"test_image.png": b"fake_image_data"},
                "metadata_json": '{"pages": 1, "title": "Test Document"}',
                "message": "Success"
            })
            
            mock_progress.init_doc = AsyncMock()
            mock_progress.complete_doc = AsyncMock()
            
            # Выполняем тест
            result = await service.upload_and_process_pdf(background_tasks, file)
            
            # Проверяем результат
            assert isinstance(result, DataExtractionResponse)
            assert result.success is True
            assert result.doc_id is not None
            assert "Файл принят, конвертация запущена" in result.message
            
            # Проверяем, что все необходимые вызовы были сделаны
            mock_exists.assert_called_once()
            mock_upload.assert_called_once()
            mock_progress.init_doc.assert_called_once()
            
            # Проверяем, что gRPC клиент был вызван
            mock_grpc_client.convert_pdf.assert_called_once()
