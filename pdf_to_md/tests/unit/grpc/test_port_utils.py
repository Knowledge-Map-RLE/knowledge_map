"""Тесты для утилит проверки портов gRPC сервера"""

import pytest
import socket
import subprocess
from unittest.mock import patch, MagicMock
from src.grpc_server import (
    is_port_available, 
    get_process_using_port, 
    kill_process_on_port, 
    ensure_port_available
)


class TestPortUtils:
    """Тесты для утилит проверки портов"""
    
    def test_is_port_available_free_port(self):
        """Тест проверки свободного порта"""
        with patch('socket.socket') as mock_socket:
            # Настраиваем мок для свободного порта
            mock_sock = MagicMock()
            mock_socket.return_value.__enter__.return_value = mock_sock
            mock_sock.connect_ex.return_value = 1  # Соединение не удалось = порт свободен
            
            result = is_port_available(8080)
            assert result is True
            mock_sock.connect_ex.assert_called_once_with(('localhost', 8080))
    
    def test_is_port_available_occupied_port(self):
        """Тест проверки занятого порта"""
        with patch('socket.socket') as mock_socket:
            # Настраиваем мок для занятого порта
            mock_sock = MagicMock()
            mock_socket.return_value.__enter__.return_value = mock_sock
            mock_sock.connect_ex.return_value = 0  # Соединение удалось = порт занят
            
            result = is_port_available(8080)
            assert result is False
            mock_sock.connect_ex.assert_called_once_with(('localhost', 8080))
    
    def test_is_port_available_socket_exception(self):
        """Тест обработки исключения сокета"""
        with patch('socket.socket') as mock_socket:
            mock_socket.side_effect = socket.error("Socket error")
            
            result = is_port_available(8080)
            assert result is False
    
    
    def test_get_process_using_port_windows(self):
        """Тест поиска процесса на порту в Windows"""
        with patch('src.grpc_server.platform.system') as mock_system, \
             patch('subprocess.run') as mock_run:
            
            mock_system.return_value = "Windows"
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "TCP    0.0.0.0:8080    0.0.0.0:0    LISTENING    1234"
            
            result = get_process_using_port(8080)
            assert result == 1234
            mock_run.assert_called_once_with(
                ['netstat', '-ano'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
    
    def test_get_process_using_port_linux(self):
        """Тест поиска процесса на порту в Linux"""
        with patch('src.grpc_server.platform.system') as mock_system, \
             patch('subprocess.run') as mock_run:
            
            mock_system.return_value = "Linux"
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "1234"
            
            result = get_process_using_port(8080)
            assert result == 1234
            mock_run.assert_called_once_with(
                ['lsof', '-ti', ':8080'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
    
    def test_get_process_using_port_not_found(self):
        """Тест поиска процесса на свободном порту"""
        with patch('src.grpc_server.platform.system') as mock_system, \
             patch('subprocess.run') as mock_run:
            
            mock_system.return_value = "Windows"
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "No processes found"
            
            result = get_process_using_port(8080)
            assert result is None
    
    def test_kill_process_on_port_success(self):
        """Тест успешного завершения процесса"""
        with patch('src.grpc_server.get_process_using_port') as mock_get_pid, \
             patch('src.grpc_server.platform.system') as mock_system, \
             patch('subprocess.run') as mock_run, \
             patch('src.grpc_server.is_port_available') as mock_is_available:
            
            mock_get_pid.return_value = 1234
            mock_system.return_value = "Windows"
            mock_run.return_value.returncode = 0
            mock_is_available.return_value = True
            
            result = kill_process_on_port(8080)
            assert result is True
            mock_run.assert_called_once_with(
                ['taskkill', '/PID', '1234', '/F'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
    
    def test_kill_process_on_port_failure(self):
        """Тест неудачного завершения процесса"""
        with patch('src.grpc_server.get_process_using_port') as mock_get_pid, \
             patch('src.grpc_server.platform.system') as mock_system, \
             patch('subprocess.run') as mock_run:
            
            mock_get_pid.return_value = 1234
            mock_system.return_value = "Windows"
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "Access denied"
            
            result = kill_process_on_port(8080)
            assert result is False
    
    def test_kill_process_on_port_free(self):
        """Тест завершения процесса на свободном порту"""
        with patch('src.grpc_server.get_process_using_port') as mock_get_pid:
            mock_get_pid.return_value = None
            
            result = kill_process_on_port(8080)
            assert result is True
    
    def test_ensure_port_available_free(self):
        """Тест обеспечения доступности свободного порта"""
        with patch('src.grpc_server.is_port_available') as mock_is_available:
            mock_is_available.return_value = True
            
            result = ensure_port_available(8080)
            assert result is True
            mock_is_available.assert_called_once_with(8080)
    
    def test_ensure_port_available_occupied_success(self):
        """Тест успешного освобождения занятого порта"""
        with patch('src.grpc_server.is_port_available') as mock_is_available, \
             patch('src.grpc_server.kill_process_on_port') as mock_kill:
            
            mock_is_available.return_value = False
            mock_kill.return_value = True
            
            result = ensure_port_available(8080)
            assert result is True
            mock_kill.assert_called_once_with(8080)
    
    def test_ensure_port_available_occupied_failure(self):
        """Тест неудачного освобождения занятого порта"""
        with patch('src.grpc_server.is_port_available') as mock_is_available, \
             patch('src.grpc_server.kill_process_on_port') as mock_kill:
            
            mock_is_available.return_value = False
            mock_kill.return_value = False
            
            result = ensure_port_available(8080)
            assert result is False
            mock_kill.assert_called_once_with(8080)
