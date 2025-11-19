"""Tests for file management feature"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from src.file_management.service import FileManagementService
from src.file_management.models import FileOperation


class TestFileManagementService:
    """Test cases for FileManagementService"""
    
    def test_file_service_initialization(self):
        """Test that FileManagementService initializes correctly"""
        service = FileManagementService()
        assert service is not None
        assert hasattr(service, 'temp_dir')
        assert hasattr(service, 'output_dir')
        assert hasattr(service, '_file_registry')
    
    def test_create_temp_directory(self):
        """Test creating temporary directory"""
        service = FileManagementService()
        temp_dir = service.create_temp_directory()
        assert isinstance(temp_dir, Path)
        assert temp_dir.exists()
    
    def test_save_pdf(self):
        """Test saving PDF content"""
        service = FileManagementService()
        temp_dir = service.create_temp_directory()
        
        content = b"fake pdf content"
        filename = "test.pdf"
        pdf_path = service.save_pdf(content, filename, temp_dir)
        
        assert pdf_path.exists()
        assert pdf_path.name == filename
    
    def test_save_result(self):
        """Test saving conversion result"""
        service = FileManagementService()
        temp_dir = service.create_temp_directory()
        
        content = "# Test markdown content"
        filename = "test.md"
        result_path = service.save_result(content, filename, temp_dir)
        
        assert result_path.exists()
        assert result_path.name == filename
    
    def test_save_to_output(self):
        """Test saving to output directory"""
        service = FileManagementService()
        
        content = "# Test content"
        filename = "output_test.md"
        file_path = service.save_to_output(content, filename)
        
        assert file_path.exists()
        assert file_path.name == filename
    
    def test_get_file_info(self):
        """Test getting file information"""
        service = FileManagementService()
        file_info = service.get_file_info("nonexistent_id")
        assert file_info is None
    
    def test_list_files(self):
        """Test listing files"""
        service = FileManagementService()
        files = service.list_files()
        assert isinstance(files, list)
    
    def test_delete_file(self):
        """Test deleting file"""
        service = FileManagementService()
        result = service.delete_file("nonexistent_id")
        assert result.operation == FileOperation.DELETE
        assert result.success is False
    
    def test_cleanup_old_files(self):
        """Test cleanup of old files"""
        service = FileManagementService()
        result = service.cleanup_old_files()
        assert result.operation == FileOperation.CLEANUP
        assert result.success is True
    
    def test_get_storage_stats(self):
        """Test getting storage statistics"""
        service = FileManagementService()
        stats = service.get_storage_stats()
        assert isinstance(stats, dict)
        assert "total_files" in stats
        assert "total_size" in stats
        assert "total_size_mb" in stats
