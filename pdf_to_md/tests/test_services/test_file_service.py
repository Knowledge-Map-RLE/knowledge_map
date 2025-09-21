"""Tests for file service"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, mock_open
from datetime import datetime, timedelta

from src.services.file_service import FileService


@pytest.mark.unit
class TestFileService:
    """Unit tests for FileService"""
    
    @pytest.fixture
    def file_service(self, temp_dir):
        """Create file service with test directories"""
        with patch('src.core.config.settings') as mock_settings:
            mock_settings.temp_dir = temp_dir / "temp"
            mock_settings.output_dir = temp_dir / "output"
            
            service = FileService()
            return service
    
    def test_create_temp_directory(self, file_service):
        """Test creating temporary directory"""
        temp_path = file_service.create_temp_directory("test_prefix_")
        
        assert temp_path.exists()
        assert temp_path.is_dir()
        assert "test_prefix_" in temp_path.name
    
    def test_save_pdf(self, file_service, temp_dir, sample_pdf_content):
        """Test saving PDF content"""
        pdf_path = file_service.save_pdf(
            content=sample_pdf_content,
            filename="test.pdf",
            temp_dir=temp_dir
        )
        
        assert pdf_path.exists()
        assert pdf_path.name == "test.pdf"
        assert pdf_path.read_bytes() == sample_pdf_content
    
    def test_save_markdown(self, file_service, temp_dir, sample_markdown_content):
        """Test saving markdown content"""
        markdown_path = file_service.save_markdown(
            content=sample_markdown_content,
            doc_id="test_doc",
            output_dir=temp_dir
        )
        
        assert markdown_path.exists()
        assert markdown_path.name == "test_doc.md"
        assert markdown_path.read_text(encoding="utf-8") == sample_markdown_content
    
    def test_save_images(self, file_service, temp_dir, sample_images):
        """Test saving images"""
        saved_paths = file_service.save_images(
            images=sample_images,
            doc_id="test_doc",
            output_dir=temp_dir
        )
        
        assert len(saved_paths) == len(sample_images)
        
        for path in saved_paths:
            assert path.exists()
            assert path.name in sample_images
        
        # Check content
        for name, content in sample_images.items():
            image_path = temp_dir / name
            assert image_path.read_bytes() == content
    
    def test_save_metadata(self, file_service, temp_dir, sample_metadata):
        """Test saving metadata"""
        metadata_path = file_service.save_metadata(
            metadata=sample_metadata,
            doc_id="test_doc",
            output_dir=temp_dir
        )
        
        assert metadata_path.exists()
        assert metadata_path.name == "test_doc_metadata.json"
        
        # Check content
        import json
        saved_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert saved_metadata == sample_metadata
    
    def test_cleanup_temp_directory(self, file_service, temp_dir):
        """Test cleaning up temporary directory"""
        # Create some files in temp directory
        test_file = temp_dir / "test_file.txt"
        test_file.write_text("test content")
        
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        subfile = subdir / "subfile.txt"
        subfile.write_text("sub content")
        
        # Cleanup
        file_service.cleanup_temp_directory(temp_dir)
        
        # Directory should be gone
        assert not temp_dir.exists()
    
    def test_cleanup_nonexistent_directory(self, file_service, temp_dir):
        """Test cleaning up non-existent directory"""
        nonexistent_dir = temp_dir / "nonexistent"
        
        # Should not raise exception
        file_service.cleanup_temp_directory(nonexistent_dir)
    
    def test_cleanup_old_files(self, file_service, temp_dir):
        """Test cleaning up old files"""
        # Create files in the output directory (not temp_dir)
        output_dir = file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create files with different ages
        now = datetime.now()
        
        # Recent file (should not be deleted)
        recent_file = output_dir / "recent.txt"
        recent_file.write_text("recent content")
        recent_time = now - timedelta(hours=1)
        os.utime(recent_file, (recent_time.timestamp(), recent_time.timestamp()))
        
        # Old file (should be deleted)
        old_file = output_dir / "old.txt"
        old_file.write_text("old content")
        old_time = now - timedelta(hours=25)
        os.utime(old_file, (old_time.timestamp(), old_time.timestamp()))
        
        # Cleanup old files
        file_service.cleanup_old_files(max_age_hours=24)
        
        # Check results
        assert recent_file.exists()
        assert not old_file.exists()
    
    def test_get_file_info(self, file_service, temp_dir, sample_pdf_content):
        """Test getting file information"""
        # Create test file
        test_file = temp_dir / "test.pdf"
        test_file.write_bytes(sample_pdf_content)
        
        info = file_service.get_file_info(test_file)
        
        assert info["path"] == str(test_file)
        assert info["size"] == len(sample_pdf_content)
        assert info["size_mb"] == len(sample_pdf_content) / (1024 * 1024)
        assert info["extension"] == ".pdf"
        assert info["name"] == "test.pdf"
        assert isinstance(info["created"], datetime)
        assert isinstance(info["modified"], datetime)
    
    def test_get_file_info_nonexistent(self, file_service, temp_dir):
        """Test getting info for non-existent file"""
        nonexistent_file = temp_dir / "nonexistent.txt"
        
        with pytest.raises(FileNotFoundError):
            file_service.get_file_info(nonexistent_file)
    
    def test_list_output_files(self, file_service, temp_dir):
        """Test listing output files"""
        # Create test files in the output directory (not temp_dir)
        output_dir = file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean up any existing files in output directory
        for existing_file in output_dir.glob("*"):
            if existing_file.is_file():
                existing_file.unlink()
        
        files_to_create = [
            "doc1.md",
            "doc1_metadata.json",
            "doc2.md",
            "doc2_metadata.json",
            "image1.jpg",
            "other.txt"
        ]
        
        for filename in files_to_create:
            (output_dir / filename).write_text("test content")
        
        # List all files
        all_files = file_service.list_output_files()
        assert len(all_files) == len(files_to_create)
        
        # List files for specific doc_id
        doc1_files = file_service.list_output_files("doc1")
        assert len(doc1_files) == 2  # doc1.md and doc1_metadata.json
        
        # Check file names
        doc1_names = [f["name"] for f in doc1_files]
        assert "doc1.md" in doc1_names
        assert "doc1_metadata.json" in doc1_names
    
    def test_directory_creation(self, file_service):
        """Test that required directories are created"""
        # Directories should be created in __init__
        assert file_service.temp_dir.exists()
        assert file_service.output_dir.exists()
        assert file_service.temp_dir.is_dir()
        assert file_service.output_dir.is_dir()
    
    def test_save_markdown_default_output_dir(self, file_service, sample_markdown_content):
        """Test saving markdown with default output directory"""
        markdown_path = file_service.save_markdown(
            content=sample_markdown_content,
            doc_id="test_doc"
            # No output_dir specified, should use default
        )
        
        assert markdown_path.exists()
        assert markdown_path.parent == file_service.output_dir
        assert markdown_path.name == "test_doc.md"
    
    def test_save_images_empty(self, file_service, temp_dir):
        """Test saving empty images dictionary"""
        saved_paths = file_service.save_images(
            images={},
            doc_id="test_doc",
            output_dir=temp_dir
        )
        
        assert saved_paths == []
    
    def test_save_metadata_none(self, file_service, temp_dir):
        """Test saving None metadata"""
        metadata_path = file_service.save_metadata(
            metadata=None,
            doc_id="test_doc",
            output_dir=temp_dir
        )
        
        assert metadata_path.exists()
        
        # Should save "null"
        import json
        content = metadata_path.read_text(encoding="utf-8")
        assert json.loads(content) is None
    
    def test_file_operations_with_special_characters(self, file_service, temp_dir):
        """Test file operations with special characters in names"""
        special_content = "Content with special chars: àáâãäåæçèéêë"
        special_doc_id = "doc_with_special_chars_àáâãäå"
        
        markdown_path = file_service.save_markdown(
            content=special_content,
            doc_id=special_doc_id,
            output_dir=temp_dir
        )
        
        assert markdown_path.exists()
        assert markdown_path.read_text(encoding="utf-8") == special_content
    
    def test_concurrent_file_operations(self, file_service, temp_dir, sample_pdf_content):
        """Test concurrent file operations"""
        import threading
        import time
        
        results = []
        
        def save_file(index):
            time.sleep(0.01)  # Small delay
            path = file_service.save_pdf(
                content=sample_pdf_content,
                filename=f"concurrent_{index}.pdf",
                temp_dir=temp_dir
            )
            results.append(path)
        
        # Start multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=save_file, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Check results
        assert len(results) == 5
        for path in results:
            assert path.exists()
            assert path.read_bytes() == sample_pdf_content


# Import os for utime
import os
