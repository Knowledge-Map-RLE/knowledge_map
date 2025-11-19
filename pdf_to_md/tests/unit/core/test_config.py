"""Tests for configuration module"""

import pytest
from pathlib import Path
from src.core.config import Settings


def test_default_settings():
    """Test default settings values"""
    settings = Settings()
    
    assert settings.service_name == "pdf-to-md-service"
    assert settings.version == "0.1.0"
    assert settings.debug is False
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8002
    assert settings.grpc_port == 50053
    assert settings.max_file_size_mb == 100
    assert settings.max_concurrent_conversions == 5
    assert settings.conversion_timeout_seconds == 1800
    assert settings.default_model == "marker"
    assert settings.log_level == "INFO"
    assert settings.enable_rate_limiting is True


def test_custom_settings():
    """Test custom settings values"""
    settings = Settings(
        service_name="custom-service",
        debug=True,
        api_port=9000,
        max_file_size_mb=50
    )
    
    assert settings.service_name == "custom-service"
    assert settings.debug is True
    assert settings.api_port == 9000
    assert settings.max_file_size_mb == 50


def test_path_settings():
    """Test path settings"""
    settings = Settings()
    
    assert isinstance(settings.temp_dir, Path)
    assert isinstance(settings.output_dir, Path)
    assert isinstance(settings.model_cache_dir, Path)


def test_settings_validation():
    """Test settings validation"""
    # Test valid settings
    settings = Settings(
        max_file_size_mb=10,
        conversion_timeout_seconds=300
    )
    assert settings.max_file_size_mb == 10
    assert settings.conversion_timeout_seconds == 300
    
    # Test edge cases
    settings = Settings(
        max_file_size_mb=1,
        conversion_timeout_seconds=1
    )
    assert settings.max_file_size_mb == 1
    assert settings.conversion_timeout_seconds == 1
