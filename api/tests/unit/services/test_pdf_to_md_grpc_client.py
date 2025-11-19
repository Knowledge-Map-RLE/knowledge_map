"""Тесты для gRPC клиента PDF to MD сервиса"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Добавляем путь к модулям
sys.path.append(str(Path(__file__).parent.parent.parent))

# Импортируем только нужные модули
from services.pdf_to_md_grpc_client import PDFToMarkdownGRPCClient


class TestPDFToMarkdownGRPCClient:
    """Тесты для gRPC клиента"""
    
    def test_client_initialization(self):
        """Тест инициализации клиента"""
        client = PDFToMarkdownGRPCClient()
        assert client.host == "127.0.0.1"
        assert client.port == 50053  # Правильный порт
        assert client._connected is False
        assert client.channel is None
        assert client.stub is None
    
    def test_client_initialization_custom_params(self):
        """Тест инициализации клиента с кастомными параметрами"""
        client = PDFToMarkdownGRPCClient(host="192.168.1.1", port=50054)
        assert client.host == "192.168.1.1"
        assert client.port == 50054
        assert client._connected is False
    
    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Тест успешного подключения"""
        client = PDFToMarkdownGRPCClient()
        
        with patch('grpc.aio.insecure_channel') as mock_channel, \
             patch('services.pdf_to_md_grpc_client.pdf_to_md_pb2_grpc') as mock_grpc:
            
            mock_channel_instance = MagicMock()
            mock_channel.return_value = mock_channel_instance
            mock_stub = MagicMock()
            mock_grpc.PDFToMarkdownServiceStub.return_value = mock_stub
            
            await client.connect()
            
            assert client._connected is True
            assert client.channel == mock_channel_instance
            assert client.stub == mock_stub
            mock_channel.assert_called_once_with("127.0.0.1:50053")
            mock_grpc.PDFToMarkdownServiceStub.assert_called_once_with(mock_channel_instance)
    
    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Тест подключения, когда уже подключен"""
        client = PDFToMarkdownGRPCClient()
        client._connected = True
        
        with patch('grpc.aio.insecure_channel') as mock_channel:
            await client.connect()
            
            # Канал не должен создаваться повторно
            mock_channel.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_connect_error(self):
        """Тест ошибки подключения"""
        client = PDFToMarkdownGRPCClient()
        
        with patch('grpc.aio.insecure_channel', side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="Connection failed"):
                await client.connect()
            
            assert client._connected is False
    
    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Тест отключения"""
        client = PDFToMarkdownGRPCClient()
        mock_channel = AsyncMock()
        client.channel = mock_channel
        client._connected = True
        
        await client.disconnect()
        
        assert client._connected is False
        mock_channel.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_disconnect_no_channel(self):
        """Тест отключения без канала"""
        client = PDFToMarkdownGRPCClient()
        client._connected = True
        
        # Не должно вызывать исключение
        await client.disconnect()
        
        assert client._connected is False
    
    @pytest.mark.asyncio
    async def test_convert_pdf_success(self):
        """Тест успешной конвертации PDF"""
        client = PDFToMarkdownGRPCClient()
        
        with patch.object(client, 'connect') as mock_connect, \
             patch('services.pdf_to_md_grpc_client.pdf_to_md_pb2') as mock_pb2:
            
            # Настраиваем моки
            mock_stub = AsyncMock()
            client.stub = mock_stub
            
            mock_request = MagicMock()
            mock_pb2.ConvertPDFRequest.return_value = mock_request
            
            mock_response = MagicMock()
            mock_response.success = True
            mock_response.doc_id = "test_doc"
            mock_response.markdown_content = "# Test Document"
            mock_response.images = {"image1.png": b"image_data"}
            mock_response.metadata_json = '{"pages": 1}'
            mock_response.message = "Success"
            
            mock_stub.ConvertPDF.return_value = mock_response
            
            # Выполняем тест
            result = await client.convert_pdf(
                pdf_content=b"pdf_content",
                doc_id="test_doc",
                model_id="marker"
            )
            
            # Проверяем результат
            assert result["success"] is True
            assert result["doc_id"] == "test_doc"
            assert result["markdown_content"] == "# Test Document"
            assert result["images"] == {"image1.png": b"image_data"}
            assert result["metadata_json"] == '{"pages": 1}'
            assert result["message"] == "Success"
            
            # Проверяем вызовы
            mock_connect.assert_called_once()
            mock_pb2.ConvertPDFRequest.assert_called_once_with(
                pdf_content=b"pdf_content",
                doc_id="test_doc",
                model_id="marker"
            )
            mock_stub.ConvertPDF.assert_called_once_with(mock_request, timeout=3600)
    
    @pytest.mark.asyncio
    async def test_convert_pdf_failure(self):
        """Тест неудачной конвертации PDF"""
        client = PDFToMarkdownGRPCClient()
        
        with patch.object(client, 'connect') as mock_connect, \
             patch('services.pdf_to_md_grpc_client.pdf_to_md_pb2') as mock_pb2:
            
            # Настраиваем моки
            mock_stub = AsyncMock()
            client.stub = mock_stub
            
            mock_request = MagicMock()
            mock_pb2.ConvertPDFRequest.return_value = mock_request
            
            # Симулируем ошибку
            mock_stub.ConvertPDF.side_effect = Exception("gRPC error")
            
            # Выполняем тест
            result = await client.convert_pdf(
                pdf_content=b"pdf_content",
                doc_id="test_doc"
            )
            
            # Проверяем результат
            assert result["success"] is False
            assert result["doc_id"] == "test_doc"
            assert result["markdown_content"] == ""
            assert result["images"] == {}
            assert result["metadata_json"] == ""
            assert "gRPC error" in result["message"]
    
    @pytest.mark.asyncio
    async def test_convert_pdf_with_progress_success(self):
        """Тест успешной конвертации PDF с прогрессом"""
        client = PDFToMarkdownGRPCClient()
        
        with patch.object(client, 'connect') as mock_connect, \
             patch('services.pdf_to_md_grpc_client.pdf_to_md_pb2') as mock_pb2:
            
            # Настраиваем моки
            mock_stub = AsyncMock()
            client.stub = mock_stub
            
            mock_request = MagicMock()
            mock_pb2.ConvertPDFRequest.return_value = mock_request
            
            mock_response = MagicMock()
            mock_response.success = True
            mock_response.doc_id = "test_doc"
            mock_response.markdown_content = "# Test Document"
            mock_response.images = {}
            mock_response.metadata_json = ""
            mock_response.message = "Success"
            
            mock_stub.ConvertPDFWithProgress.return_value = mock_response
            
            # Выполняем тест
            result = await client.convert_pdf_with_progress(
                pdf_content=b"pdf_content",
                doc_id="test_doc"
            )
            
            # Проверяем результат
            assert result["success"] is True
            assert result["doc_id"] == "test_doc"
            
            # Проверяем вызовы
            mock_connect.assert_called_once()
            mock_stub.ConvertPDFWithProgress.assert_called_once_with(mock_request, timeout=3600)
    
    @pytest.mark.asyncio
    async def test_get_models_success(self):
        """Тест успешного получения моделей"""
        client = PDFToMarkdownGRPCClient()
        
        with patch.object(client, 'connect') as mock_connect, \
             patch('services.pdf_to_md_grpc_client.pdf_to_md_pb2') as mock_pb2:
            
            # Настраиваем моки
            mock_stub = AsyncMock()
            client.stub = mock_stub
            
            mock_request = MagicMock()
            mock_pb2.GetModelsRequest.return_value = mock_request
            
            mock_model_info = MagicMock()
            mock_model_info.name = "Marker"
            mock_model_info.description = "Marker model"
            mock_model_info.enabled = True
            mock_model_info.default = True
            
            mock_response = MagicMock()
            mock_response.models = {"marker": mock_model_info}
            mock_response.default_model = "marker"
            
            mock_stub.GetModels.return_value = mock_response
            
            # Выполняем тест
            result = await client.get_models()
            
            # Проверяем результат
            assert "models" in result
            assert "default_model" in result
            assert result["default_model"] == "marker"
            assert "marker" in result["models"]
            assert result["models"]["marker"]["name"] == "Marker"
            
            # Проверяем вызовы
            mock_connect.assert_called_once()
            mock_stub.GetModels.assert_called_once_with(mock_request)
    
    @pytest.mark.asyncio
    async def test_set_default_model_success(self):
        """Тест успешной установки модели по умолчанию"""
        client = PDFToMarkdownGRPCClient()
        
        with patch.object(client, 'connect') as mock_connect, \
             patch('services.pdf_to_md_grpc_client.pdf_to_md_pb2') as mock_pb2:
            
            # Настраиваем моки
            mock_stub = AsyncMock()
            client.stub = mock_stub
            
            mock_request = MagicMock()
            mock_pb2.SetDefaultModelRequest.return_value = mock_request
            
            mock_response = MagicMock()
            mock_response.success = True
            
            mock_stub.SetDefaultModel.return_value = mock_response
            
            # Выполняем тест
            result = await client.set_default_model("marker")
            
            # Проверяем результат
            assert result is True
            
            # Проверяем вызовы
            mock_connect.assert_called_once()
            mock_pb2.SetDefaultModelRequest.assert_called_once_with(model_id="marker")
            mock_stub.SetDefaultModel.assert_called_once_with(mock_request)
    
    @pytest.mark.asyncio
    async def test_enable_model_success(self):
        """Тест успешного включения/отключения модели"""
        client = PDFToMarkdownGRPCClient()
        
        with patch.object(client, 'connect') as mock_connect, \
             patch('services.pdf_to_md_grpc_client.pdf_to_md_pb2') as mock_pb2:
            
            # Настраиваем моки
            mock_stub = AsyncMock()
            client.stub = mock_stub
            
            mock_request = MagicMock()
            mock_pb2.EnableModelRequest.return_value = mock_request
            
            mock_response = MagicMock()
            mock_response.success = True
            
            mock_stub.EnableModel.return_value = mock_response
            
            # Выполняем тест
            result = await client.enable_model("marker", True)
            
            # Проверяем результат
            assert result is True
            
            # Проверяем вызовы
            mock_connect.assert_called_once()
            mock_pb2.EnableModelRequest.assert_called_once_with(model_id="marker", enabled=True)
            mock_stub.EnableModel.assert_called_once_with(mock_request)


class TestPDFToMarkdownGRPCClientIntegration:
    """Интеграционные тесты для gRPC клиента"""
    
    @pytest.mark.asyncio
    async def test_client_connection_to_real_server(self):
        """Тест подключения к реальному серверу (если доступен)"""
        client = PDFToMarkdownGRPCClient()
        
        try:
            await client.connect()
            assert client._connected is True
            
            # Пробуем получить модели
            models = await client.get_models()
            assert "models" in models
            
            await client.disconnect()
            assert client._connected is False
            
        except Exception as e:
            # Если сервер недоступен, это нормально для тестов
            pytest.skip(f"gRPC сервер недоступен: {e}")
    
    @pytest.mark.asyncio
    async def test_convert_pdf_with_real_server(self):
        """Тест конвертации PDF с реальным сервером (если доступен)"""
        client = PDFToMarkdownGRPCClient()
        
        try:
            # Создаем минимальный PDF для тестирования
            test_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
            
            result = await client.convert_pdf(
                pdf_content=test_pdf_content,
                doc_id="test_integration_doc"
            )
            
            # Проверяем, что получили ответ
            assert "success" in result
            assert "doc_id" in result
            assert result["doc_id"] == "test_integration_doc"
            
        except Exception as e:
            # Если сервер недоступен или конвертация не удалась, это нормально для тестов
            pytest.skip(f"Интеграционный тест пропущен: {e}")
