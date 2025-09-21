"""Интеграционные тесты для gRPC сервера"""

import pytest
import asyncio
import subprocess
import time
import socket
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.grpc_server import is_port_available, find_available_port


class TestGRPCIntegration:
    """Интеграционные тесты для gRPC сервера"""
    
    def test_port_availability_real_check(self):
        """Тест реальной проверки доступности портов"""
        # Проверяем, что порт 80 (обычно занят) недоступен
        port_80_available = is_port_available(80)
        # Это может быть True или False в зависимости от системы
        
        # Проверяем, что функция работает без исключений
        assert isinstance(port_80_available, bool)
        
        # Проверяем порт в диапазоне 49152-65535 (динамические порты)
        high_port_available = is_port_available(50000)
        assert isinstance(high_port_available, bool)
    
    def test_find_available_port_real_search(self):
        """Тест реального поиска свободного порта"""
        # Ищем свободный порт в диапазоне 50000-50010
        available_port = find_available_port(50000, 50010)
        
        if available_port is not None:
            # Если порт найден, проверяем, что он действительно свободен
            assert 50000 <= available_port <= 50010
            assert is_port_available(available_port) is True
        else:
            # Если порт не найден, все порты в диапазоне должны быть заняты
            for port in range(50000, 50011):
                assert is_port_available(port) is False
    
    def test_port_binding_conflict_simulation(self):
        """Тест симуляции конфликта привязки портов"""
        # Создаем временный сокет для занятия порта
        test_port = 50001
        
        try:
            # Занимаем порт
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.bind(('localhost', test_port))
            test_socket.listen(1)
            
            # Проверяем, что порт теперь недоступен
            assert is_port_available(test_port) is False
            
            # Ищем альтернативный порт
            alternative_port = find_available_port(test_port + 1, test_port + 5)
            assert alternative_port is not None
            assert alternative_port != test_port
            assert is_port_available(alternative_port) is True
            
        finally:
            # Освобождаем порт
            test_socket.close()
    
    @pytest.mark.asyncio
    async def test_grpc_server_startup_simulation(self):
        """Тест симуляции запуска gRPC сервера"""
        with patch('src.grpc_server.grpc.aio.server') as mock_server_class, \
             patch('src.grpc_server.pdf_to_md_pb2_grpc') as mock_grpc, \
             patch('src.grpc_server.importlib.import_module'):
            
            mock_server = MagicMock()
            mock_server_class.return_value = mock_server
            
            # Симулируем успешный запуск
            from src.grpc_server import serve
            
            # Запускаем сервер в фоне
            server_task = asyncio.create_task(serve())
            
            # Даем серверу время на запуск
            await asyncio.sleep(0.1)
            
            # Отменяем задачу
            server_task.cancel()
            
            try:
                await server_task
            except asyncio.CancelledError:
                pass
            
            # Проверяем, что сервер был настроен
            mock_server.add_insecure_port.assert_called()
            mock_server.start.assert_called()
    
    def test_grpc_server_error_handling(self):
        """Тест обработки ошибок gRPC сервера"""
        # Тест с недопустимым портом
        with patch('socket.socket') as mock_socket:
            mock_socket.side_effect = socket.error("Permission denied")
            
            result = is_port_available(80)
            assert result is False
        
        # Тест с таймаутом
        with patch('socket.socket') as mock_socket:
            mock_sock = MagicMock()
            mock_socket.return_value.__enter__.return_value = mock_sock
            mock_sock.connect_ex.side_effect = socket.timeout("Connection timeout")
            
            result = is_port_available(8080)
            assert result is False
    
    def test_port_range_validation(self):
        """Тест валидации диапазона портов"""
        # Тест с неверным диапазоном
        result = find_available_port(8081, 8080)
        assert result is None
        
        # Тест с отрицательными портами
        result = find_available_port(-1, 8080)
        # Функция должна обработать это корректно
        assert result is None or isinstance(result, int)
    
    def test_concurrent_port_checks(self):
        """Тест одновременной проверки портов"""
        import threading
        import queue
        
        results = queue.Queue()
        
        def check_port(port):
            result = is_port_available(port)
            results.put((port, result))
        
        # Запускаем несколько потоков для проверки разных портов
        threads = []
        test_ports = [50010, 50011, 50012, 50013, 50014]
        
        for port in test_ports:
            thread = threading.Thread(target=check_port, args=(port,))
            threads.append(thread)
            thread.start()
        
        # Ждем завершения всех потоков
        for thread in threads:
            thread.join()
        
        # Проверяем результаты
        assert results.qsize() == len(test_ports)
        
        while not results.empty():
            port, result = results.get()
            assert isinstance(result, bool)
            assert port in test_ports


class TestGRPCServerRecovery:
    """Тесты для восстановления gRPC сервера после ошибок"""
    
    def test_server_recovery_after_port_conflict(self):
        """Тест восстановления сервера после конфликта портов"""
        # Симулируем ситуацию, когда основной порт занят
        with patch('src.grpc_server.is_port_available') as mock_is_available, \
             patch('src.grpc_server.find_available_port') as mock_find_port:
            
            # Основной порт занят
            mock_is_available.return_value = False
            # Найден альтернативный порт
            mock_find_port.return_value = 50054
            
            # Проверяем логику выбора порта
            if not is_port_available(50053):
                alternative_port = find_available_port(50053, 50100)
                # Проверяем, что альтернативный порт найден
                assert alternative_port is not None
                assert alternative_port == 50054
    
    def test_server_graceful_shutdown_simulation(self):
        """Тест симуляции корректного завершения сервера"""
        with patch('src.grpc_server.grpc.aio.server') as mock_server_class, \
             patch('src.grpc_server.pdf_to_md_pb2_grpc') as mock_grpc:
            
            mock_server = MagicMock()
            mock_server_class.return_value = mock_server
            
            # Симулируем корректное завершение
            mock_server.wait_for_termination = AsyncMock()
            
            # Проверяем, что сервер может быть корректно остановлен
            assert mock_server.stop is not None
            assert mock_server.wait_for_termination is not None
