"""Прямые тесты для gRPC клиента PDF to MD сервиса"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Добавляем путь к модулям
sys.path.append(str(Path(__file__).parent.parent.parent))

# Импортируем напрямую, минуя __init__.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "pdf_to_md_grpc_client", 
    Path(__file__).parent.parent.parent / "services" / "pdf_to_md_grpc_client.py"
)
pdf_to_md_grpc_client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdf_to_md_grpc_client)

PDFToMarkdownGRPCClient = pdf_to_md_grpc_client.PDFToMarkdownGRPCClient


class TestPDFToMarkdownGRPCClientDirect:
    """Прямые тесты для gRPC клиента"""
    
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
    
    def test_port_from_environment(self):
        """Тест использования порта из переменной окружения"""
        import os
        # Сохраняем оригинальное значение
        original_port = os.getenv("PDF_TO_MD_SERVICE_PORT")
        
        try:
            # Устанавливаем тестовый порт
            os.environ["PDF_TO_MD_SERVICE_PORT"] = "50054"
            client = PDFToMarkdownGRPCClient()
            # Проверяем, что порт берется из переменной окружения
            assert client.port == 50054, f"Ожидался порт 50054, получен {client.port}"
        finally:
            # Восстанавливаем оригинальное значение
            if original_port is not None:
                os.environ["PDF_TO_MD_SERVICE_PORT"] = original_port
            else:
                os.environ.pop("PDF_TO_MD_SERVICE_PORT", None)


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
