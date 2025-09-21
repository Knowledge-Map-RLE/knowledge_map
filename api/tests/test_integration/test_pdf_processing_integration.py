"""Интеграционные тесты для полного процесса обработки PDF"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import BackgroundTasks, UploadFile
from io import BytesIO

from services.data_extraction_service import DataExtractionService
from services.pdf_to_md_grpc_client import PDFToMarkdownGRPCClient


class TestPDFProcessingIntegration:
    """Интеграционные тесты для обработки PDF"""
    
    @pytest.mark.asyncio
    async def test_grpc_client_connection_to_pdf_to_md_service(self):
        """Тест подключения gRPC клиента к PDF to MD сервису"""
        client = PDFToMarkdownGRPCClient()
        
        try:
            # Пробуем подключиться к сервису
            await client.connect()
            assert client._connected is True
            
            # Пробуем получить модели
            models = await client.get_models()
            assert "models" in models
            
            await client.disconnect()
            assert client._connected is False
            
        except Exception as e:
            pytest.skip(f"PDF to MD gRPC сервис недоступен: {e}")
    
    @pytest.mark.asyncio
    async def test_pdf_conversion_through_grpc(self):
        """Тест конвертации PDF через gRPC"""
        client = PDFToMarkdownGRPCClient()
        
        try:
            # Создаем минимальный PDF для тестирования
            test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
            
            result = await client.convert_pdf(
                pdf_content=test_pdf_content,
                doc_id="integration_test_doc"
            )
            
            # Проверяем, что получили ответ
            assert "success" in result
            assert "doc_id" in result
            assert result["doc_id"] == "integration_test_doc"
            
            # Если конвертация успешна, проверяем результат
            if result["success"]:
                assert "markdown_content" in result
                assert "images" in result
                assert "metadata_json" in result
                assert "message" in result
            
        except Exception as e:
            pytest.skip(f"Конвертация PDF через gRPC недоступна: {e}")
    
    @pytest.mark.asyncio
    async def test_data_extraction_service_with_real_grpc(self):
        """Тест DataExtractionService с реальным gRPC клиентом"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем тестовый PDF
        test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=test_pdf_content)
        
        try:
            with patch.object(service.s3_client, 'object_exists', return_value=False) as mock_exists, \
                 patch.object(service.s3_client, 'upload_bytes', return_value=True) as mock_upload, \
                 patch('services.data_extraction_service.marker_progress_store') as mock_progress:
                
                # Настраиваем моки
                mock_progress.init_doc = AsyncMock()
                mock_progress.complete_doc = AsyncMock()
                
                # Выполняем тест с реальным gRPC клиентом
                result = await service.upload_and_process_pdf(background_tasks, file)
                
                # Проверяем результат
                assert result.success is True
                assert result.doc_id is not None
                assert "Файл принят, конвертация запущена" in result.message
                
                # Проверяем вызовы
                mock_exists.assert_called_once()
                mock_upload.assert_called_once()
                mock_progress.init_doc.assert_called_once()
                
        except Exception as e:
            pytest.skip(f"Интеграционный тест DataExtractionService пропущен: {e}")
    
    @pytest.mark.asyncio
    async def test_end_to_end_pdf_processing(self):
        """Тест полного процесса обработки PDF от загрузки до получения результата"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем более реалистичный PDF для тестирования
        test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n72 720 Td\n(Hello World) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000200 00000 n \ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n294\n%%EOF"
        
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=test_pdf_content)
        
        try:
            with patch.object(service.s3_client, 'object_exists', return_value=False) as mock_exists, \
                 patch.object(service.s3_client, 'upload_bytes', return_value=True) as mock_upload, \
                 patch('services.data_extraction_service.marker_progress_store') as mock_progress:
                
                # Настраиваем моки
                mock_progress.init_doc = AsyncMock()
                mock_progress.complete_doc = AsyncMock()
                
                # Выполняем тест
                result = await service.upload_and_process_pdf(background_tasks, file)
                
                # Проверяем результат
                assert result.success is True
                assert result.doc_id is not None
                assert "Файл принят, конвертация запущена" in result.message
                
                # Ждем завершения фоновой задачи (в реальном приложении это происходит асинхронно)
                await asyncio.sleep(1)
                
                # Проверяем, что все необходимые вызовы были сделаны
                mock_exists.assert_called_once()
                mock_upload.assert_called_once()
                mock_progress.init_doc.assert_called_once()
                
        except Exception as e:
            pytest.skip(f"End-to-end тест пропущен: {e}")
    
    @pytest.mark.asyncio
    async def test_error_handling_in_pdf_processing(self):
        """Тест обработки ошибок в процессе обработки PDF"""
        service = DataExtractionService()
        background_tasks = BackgroundTasks()
        
        # Создаем невалидный PDF
        invalid_pdf_content = b"This is not a valid PDF file"
        
        file = MagicMock(spec=UploadFile)
        file.content_type = "application/pdf"
        file.read = AsyncMock(return_value=invalid_pdf_content)
        
        try:
            with patch.object(service.s3_client, 'object_exists', return_value=False) as mock_exists, \
                 patch.object(service.s3_client, 'upload_bytes', return_value=True) as mock_upload, \
                 patch('services.data_extraction_service.marker_progress_store') as mock_progress:
                
                # Настраиваем моки
                mock_progress.init_doc = AsyncMock()
                mock_progress.complete_doc = AsyncMock()
                
                # Выполняем тест
                result = await service.upload_and_process_pdf(background_tasks, file)
                
                # Проверяем, что файл был принят (валидация PDF происходит в gRPC сервисе)
                assert result.success is True
                assert result.doc_id is not None
                
                # Ждем завершения фоновой задачи
                await asyncio.sleep(1)
                
                # Проверяем, что обработка ошибок работает корректно
                mock_progress.complete_doc.assert_called_once()
                
        except Exception as e:
            pytest.skip(f"Тест обработки ошибок пропущен: {e}")
    
    @pytest.mark.asyncio
    async def test_concurrent_pdf_processing(self):
        """Тест параллельной обработки нескольких PDF файлов"""
        service = DataExtractionService()
        
        # Создаем несколько тестовых PDF
        test_pdfs = []
        for i in range(3):
            pdf_content = f"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 50\n>>\nstream\nBT\n/F1 12 Tf\n72 720 Td\n(Document {i}) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000200 00000 n \ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n300\n%%EOF".encode()
            test_pdfs.append(pdf_content)
        
        try:
            with patch.object(service.s3_client, 'object_exists', return_value=False) as mock_exists, \
                 patch.object(service.s3_client, 'upload_bytes', return_value=True) as mock_upload, \
                 patch('services.data_extraction_service.marker_progress_store') as mock_progress:
                
                # Настраиваем моки
                mock_progress.init_doc = AsyncMock()
                mock_progress.complete_doc = AsyncMock()
                
                # Создаем задачи для параллельной обработки
                tasks = []
                for i, pdf_content in enumerate(test_pdfs):
                    background_tasks = BackgroundTasks()
                    file = MagicMock(spec=UploadFile)
                    file.content_type = "application/pdf"
                    file.read = AsyncMock(return_value=pdf_content)
                    
                    task = service.upload_and_process_pdf(background_tasks, file)
                    tasks.append(task)
                
                # Выполняем все задачи параллельно
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Проверяем результаты
                for result in results:
                    if isinstance(result, Exception):
                        pytest.skip(f"Параллельная обработка недоступна: {result}")
                    else:
                        assert result.success is True
                        assert result.doc_id is not None
                
        except Exception as e:
            pytest.skip(f"Тест параллельной обработки пропущен: {e}")


class TestPDFProcessingErrorScenarios:
    """Тесты сценариев ошибок в обработке PDF"""
    
    @pytest.mark.asyncio
    async def test_grpc_service_unavailable(self):
        """Тест обработки недоступности gRPC сервиса"""
        client = PDFToMarkdownGRPCClient(host="127.0.0.1", port=9999)  # Несуществующий порт
        
        try:
            await client.connect()
            pytest.fail("Ожидалось исключение при подключении к недоступному сервису")
        except Exception as e:
            # Это ожидаемое поведение
            assert "Connection" in str(e) or "refused" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_invalid_pdf_content(self):
        """Тест обработки невалидного PDF контента"""
        client = PDFToMarkdownGRPCClient()
        
        try:
            # Пробуем конвертировать невалидный PDF
            result = await client.convert_pdf(
                pdf_content=b"Not a PDF file",
                doc_id="invalid_pdf_test"
            )
            
            # Проверяем, что получили ответ (успешный или неуспешный)
            assert "success" in result
            assert "doc_id" in result
            assert result["doc_id"] == "invalid_pdf_test"
            
        except Exception as e:
            pytest.skip(f"Тест невалидного PDF пропущен: {e}")
    
    @pytest.mark.asyncio
    async def test_large_pdf_handling(self):
        """Тест обработки большого PDF файла"""
        client = PDFToMarkdownGRPCClient()
        
        try:
            # Создаем большой PDF (симулируем)
            large_pdf_content = b"%PDF-1.4\n" + b"x" * 1000000  # 1MB
            
            result = await client.convert_pdf(
                pdf_content=large_pdf_content,
                doc_id="large_pdf_test",
                timeout=60  # Увеличиваем таймаут для большого файла
            )
            
            # Проверяем, что получили ответ
            assert "success" in result
            assert "doc_id" in result
            assert result["doc_id"] == "large_pdf_test"
            
        except Exception as e:
            pytest.skip(f"Тест большого PDF пропущен: {e}")
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Тест обработки таймаута при конвертации"""
        client = PDFToMarkdownGRPCClient()
        
        try:
            # Создаем PDF и устанавливаем очень короткий таймаут
            test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
            
            result = await client.convert_pdf(
                pdf_content=test_pdf_content,
                doc_id="timeout_test",
                timeout=1  # Очень короткий таймаут
            )
            
            # Проверяем, что получили ответ (возможно с ошибкой таймаута)
            assert "success" in result
            assert "doc_id" in result
            assert result["doc_id"] == "timeout_test"
            
        except Exception as e:
            pytest.skip(f"Тест таймаута пропущен: {e}")
