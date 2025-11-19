"""Tests for health monitoring feature"""

import pytest
from unittest.mock import Mock, patch
from src.health_monitoring.service import HealthMonitoringService
from src.health_monitoring.models import HealthStatus


class TestHealthMonitoringService:
    """Test cases for HealthMonitoringService"""
    
    def test_health_service_initialization(self):
        """Test that HealthMonitoringService initializes correctly"""
        service = HealthMonitoringService()
        assert service is not None
        assert hasattr(service, 'start_time')
        assert hasattr(service, '_request_count')
        assert hasattr(service, '_successful_requests')
        assert hasattr(service, '_failed_requests')
        assert hasattr(service, '_response_times')
    
    def test_record_request(self):
        """Test recording request metrics"""
        service = HealthMonitoringService()
        initial_count = service._request_count
        
        service.record_request(success=True, response_time=0.5)
        
        assert service._request_count == initial_count + 1
        assert service._successful_requests == 1
        assert service._failed_requests == 0
        assert len(service._response_times) == 1
        assert service._response_times[0] == 0.5
    
    def test_record_failed_request(self):
        """Test recording failed request"""
        service = HealthMonitoringService()
        initial_count = service._request_count
        
        service.record_request(success=False, response_time=1.0)
        
        assert service._request_count == initial_count + 1
        assert service._successful_requests == 0
        assert service._failed_requests == 1
        assert len(service._response_times) == 1
        assert service._response_times[0] == 1.0
    
    def test_get_uptime_seconds(self):
        """Test getting uptime in seconds"""
        service = HealthMonitoringService()
        uptime = service.get_uptime_seconds()
        assert isinstance(uptime, float)
        assert uptime >= 0
    
    @patch('psutil.Process')
    def test_get_memory_usage_mb(self, mock_process):
        """Test getting memory usage"""
        mock_memory_info = Mock()
        mock_memory_info.rss = 100 * 1024 * 1024  # 100 MB
        mock_process.return_value.memory_info.return_value = mock_memory_info
        
        service = HealthMonitoringService()
        memory_usage = service.get_memory_usage_mb()
        assert memory_usage == 100.0
    
    @patch('psutil.cpu_percent')
    def test_get_cpu_usage_percent(self, mock_cpu_percent):
        """Test getting CPU usage"""
        mock_cpu_percent.return_value = 25.5
        
        service = HealthMonitoringService()
        cpu_usage = service.get_cpu_usage_percent()
        assert cpu_usage == 25.5
    
    @patch('psutil.disk_usage')
    def test_get_disk_usage_mb(self, mock_disk_usage):
        """Test getting disk usage"""
        mock_disk_info = Mock()
        mock_disk_info.used = 500 * 1024 * 1024  # 500 MB
        mock_disk_usage.return_value = mock_disk_info
        
        service = HealthMonitoringService()
        disk_usage = service.get_disk_usage_mb()
        assert disk_usage == 500.0
    
    def test_get_average_response_time(self):
        """Test getting average response time"""
        service = HealthMonitoringService()
        
        # Test with no response times
        avg_time = service.get_average_response_time()
        assert avg_time == 0.0
        
        # Add some response times
        service._response_times = [0.5, 1.0, 1.5]
        avg_time = service.get_average_response_time()
        assert avg_time == 1.0
    
    def test_get_service_metrics(self):
        """Test getting service metrics"""
        service = HealthMonitoringService()
        metrics = service.get_service_metrics()
        
        assert hasattr(metrics, 'service_name')
        assert hasattr(metrics, 'version')
        assert hasattr(metrics, 'uptime_seconds')
        assert hasattr(metrics, 'total_requests')
        assert hasattr(metrics, 'successful_requests')
        assert hasattr(metrics, 'failed_requests')
        assert hasattr(metrics, 'average_response_time')
        assert hasattr(metrics, 'active_conversions')
        assert hasattr(metrics, 'memory_usage_mb')
        assert hasattr(metrics, 'cpu_usage_percent')
        assert hasattr(metrics, 'disk_usage_mb')
    
    def test_check_model_registry_health(self):
        """Test checking model registry health"""
        service = HealthMonitoringService()
        health = service.check_model_registry_health()
        
        assert hasattr(health, 'component_name')
        assert hasattr(health, 'status')
        assert hasattr(health, 'message')
        assert health.component_name == "model_registry"
        assert health.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
    
    def test_check_file_service_health(self):
        """Test checking file service health"""
        service = HealthMonitoringService()
        health = service.check_file_service_health()
        
        assert hasattr(health, 'component_name')
        assert hasattr(health, 'status')
        assert hasattr(health, 'message')
        assert health.component_name == "file_service"
        assert health.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
    
    def test_check_conversion_service_health(self):
        """Test checking conversion service health"""
        service = HealthMonitoringService()
        health = service.check_conversion_service_health()
        
        assert hasattr(health, 'component_name')
        assert hasattr(health, 'status')
        assert hasattr(health, 'message')
        assert health.component_name == "conversion_service"
        assert health.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
    
    def test_get_system_health(self):
        """Test getting overall system health"""
        service = HealthMonitoringService()
        system_health = service.get_system_health()
        
        assert hasattr(system_health, 'overall_status')
        assert hasattr(system_health, 'service_metrics')
        assert hasattr(system_health, 'components')
        assert system_health.overall_status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN]
        assert len(system_health.components) == 3  # model_registry, file_service, conversion_service
    
    def test_get_health_status(self):
        """Test getting simple health status"""
        service = HealthMonitoringService()
        status = service.get_health_status()
        assert status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN]
