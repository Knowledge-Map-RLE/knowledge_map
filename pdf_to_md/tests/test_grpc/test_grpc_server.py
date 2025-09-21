"""Тесты для gRPC сервера"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import grpc
from concurrent import futures

from src.grpc_server import PDFToMarkdownServicer, serve, ensure_port_available


class TestPDFToMarkdownServicer:
    """Тесты для gRPC сервиса"""
    
    def test_servicer_initialization(self):
        """Тест инициализации сервиса"""
        servicer = PDFToMarkdownServicer()
        assert servicer is not None
    
    @pytest.mark.asyncio
    async def test_convert_pdf_success(self):
        """Тест успешной конвертации PDF"""
        servicer = PDFToMarkdownServicer()
        
        # Создаем мок запроса
        request = MagicMock()
        request.document_id = "test_doc"
        request.file_path = "test.pdf"
        request.model_id = "marker"
        
        # Создаем мок контекста
        context = MagicMock()
        
        with patch('src.grpc_server.convert_pdf_to_markdown_marker_async') as mock_convert:
            mock_convert.return_value = {
                'success': True,
                'markdown_content': '# Test Document\n\nContent here',
                'processing_time': 1.5,
                'metadata': {'pages': 1, 'model_used': 'marker'}
            }
            
            # Вызываем метод сервиса
            response = await servicer.ConvertPDF(request, context)
            
            assert response.success is True
            assert response.document_id == "test_doc"
            assert "Test Document" in response.markdown_content
            assert response.processing_time == 1.5
            assert response.metadata['pages'] == 1
    
    @pytest.mark.asyncio
    async def test_convert_pdf_failure(self):
        """Тест неудачной конвертации PDF"""
        servicer = PDFToMarkdownServicer()
        
        request = MagicMock()
        request.document_id = "test_doc"
        request.file_path = "nonexistent.pdf"
        request.model_id = "marker"
        
        context = MagicMock()
        
        with patch('src.grpc_server.convert_pdf_to_markdown_marker_async') as mock_convert:
            mock_convert.return_value = {
                'success': False,
                'error': 'File not found',
                'processing_time': 0.1
            }
            
            response = await servicer.ConvertPDF(request, context)
            
            assert response.success is False
            assert response.document_id == "test_doc"
            assert "File not found" in response.error
            assert response.processing_time == 0.1
    
    @pytest.mark.asyncio
    async def test_convert_pdf_with_progress(self):
        """Тест конвертации PDF с отслеживанием прогресса"""
        servicer = PDFToMarkdownServicer()
        
        request = MagicMock()
        request.document_id = "test_doc"
        request.file_path = "test.pdf"
        request.model_id = "marker"
        
        context = MagicMock()
        
        with patch('src.grpc_server.convert_pdf_to_markdown_marker_async') as mock_convert:
            # Настраиваем мок для отправки прогресса
            progress_updates = []
            
            def mock_progress_callback(progress):
                progress_updates.append(progress)
            
            mock_convert.return_value = {
                'success': True,
                'markdown_content': '# Test Document',
                'processing_time': 2.0,
                'metadata': {'pages': 1}
            }
            
            # Мокаем функцию конвертации с колбэком прогресса
            async def mock_convert_with_progress(*args, **kwargs):
                callback = kwargs.get('progress_callback')
                if callback:
                    await callback({'progress': 50, 'status': 'processing'})
                    await callback({'progress': 100, 'status': 'completed'})
                return mock_convert.return_value
            
            mock_convert.side_effect = mock_convert_with_progress
            
            response = await servicer.ConvertPDF(request, context)
            
            assert response.success is True
            # Проверяем, что прогресс был отправлен
            assert context.write.call_count >= 1


class TestGRPCServer:
    """Тесты для gRPC сервера"""
    
    @pytest.mark.asyncio
    async def test_serve_with_available_port(self):
        """Тест запуска сервера с доступным портом"""
        with patch('src.grpc_server.ensure_port_available') as mock_ensure_port, \
             patch('src.grpc_server.grpc.aio.server') as mock_server_class, \
             patch('src.grpc_server.pdf_to_md_pb2_grpc') as mock_grpc:
            
            # Настраиваем моки
            mock_ensure_port.return_value = True
            mock_server = AsyncMock()
            mock_server_class.return_value = mock_server
            
            # Мокаем импорты
            with patch('src.grpc_server.importlib.import_module'):
                try:
                    await serve()
                except asyncio.CancelledError:
                    # Ожидаем, что сервер будет работать до отмены
                    pass
            
            # Проверяем, что сервер был настроен
            mock_ensure_port.assert_called_once_with(50053)
            mock_server.add_insecure_port.assert_called_once_with('0.0.0.0:50053')
            mock_server.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_serve_with_occupied_port_success(self):
        """Тест запуска сервера с успешным освобождением занятого порта"""
        with patch('src.grpc_server.ensure_port_available') as mock_ensure_port, \
             patch('src.grpc_server.grpc.aio.server') as mock_server_class, \
             patch('src.grpc_server.pdf_to_md_pb2_grpc') as mock_grpc:
            
            # Настраиваем моки
            mock_ensure_port.return_value = True  # Порт успешно освобожден
            mock_server = AsyncMock()
            mock_server_class.return_value = mock_server
            
            with patch('src.grpc_server.importlib.import_module'):
                try:
                    await serve()
                except asyncio.CancelledError:
                    pass
            
            # Проверяем, что порт был освобожден и сервер запустился
            mock_ensure_port.assert_called_once_with(50053)
            mock_server.add_insecure_port.assert_called_once_with('0.0.0.0:50053')
    
    @pytest.mark.asyncio
    async def test_serve_port_cannot_be_freed(self):
        """Тест запуска сервера, когда порт не может быть освобожден"""
        with patch('src.grpc_server.ensure_port_available') as mock_ensure_port:
            
            # Настраиваем моки
            mock_ensure_port.return_value = False  # Порт не может быть освобожден
            
            with pytest.raises(RuntimeError, match="Не удалось освободить порт 50053"):
                await serve()
    
    @pytest.mark.asyncio
    async def test_serve_import_error(self):
        """Тест обработки ошибки импорта"""
        with patch('src.grpc_server.is_port_available') as mock_is_available, \
             patch('src.grpc_server.grpc.aio.server') as mock_server_class, \
             patch('src.grpc_server.pdf_to_md_pb2_grpc') as mock_grpc:
            
            mock_is_available.return_value = True
            mock_server = AsyncMock()
            mock_server_class.return_value = mock_server
            
            # Мокаем ошибку импорта
            with patch('src.grpc_server.importlib.import_module', side_effect=ImportError("Module not found")):
                try:
                    await serve()
                except asyncio.CancelledError:
                    pass
            
            # Сервер должен запуститься даже при ошибке импорта
            mock_server.add_insecure_port.assert_called_once()
            mock_server.start.assert_called_once()


class TestPortBindingErrorHandling:
    """Тесты для обработки ошибок привязки портов"""
    
    @pytest.mark.asyncio
    async def test_port_binding_error(self):
        """Тест обработки ошибки привязки порта"""
        with patch('src.grpc_server.is_port_available') as mock_is_available, \
             patch('src.grpc_server.grpc.aio.server') as mock_server_class, \
             patch('src.grpc_server.pdf_to_md_pb2_grpc') as mock_grpc:
            
            mock_is_available.return_value = True
            mock_server = AsyncMock()
            mock_server_class.return_value = mock_server
            
            # Мокаем ошибку привязки порта
            mock_server.add_insecure_port.side_effect = RuntimeError("Failed to bind to port")
            
            with patch('src.grpc_server.importlib.import_module'):
                with pytest.raises(RuntimeError, match="Failed to bind to port"):
                    await serve()
    
    def test_port_availability_edge_cases(self):
        """Тест граничных случаев проверки портов"""
        # Тест с портом 0 (недопустимый)
        with patch('socket.socket') as mock_socket:
            mock_sock = MagicMock()
            mock_socket.return_value.__enter__.return_value = mock_sock
            mock_sock.connect_ex.return_value = 1
            
            result = is_port_available(0)
            assert result is True  # Функция должна работать с любым портом
    
    def test_find_available_port_edge_cases(self):
        """Тест граничных случаев поиска портов"""
        # Тест с одинаковыми start и end портами
        with patch('src.grpc_server.is_port_available') as mock_is_available:
            mock_is_available.return_value = True
            
            result = find_available_port(8080, 8080)
            assert result == 8080
            mock_is_available.assert_called_once_with(8080)
        
        # Тест с большим диапазоном портов
        with patch('src.grpc_server.is_port_available') as mock_is_available:
            mock_is_available.return_value = False
            
            result = find_available_port(8080, 8090)
            assert result is None
            assert mock_is_available.call_count == 11  # 8080-8090 включительно
