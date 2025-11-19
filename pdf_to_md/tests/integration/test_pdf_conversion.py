"""Integration tests for PDF conversion"""

import pytest
import asyncio
import tempfile
import json
import shutil
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock

from src.services.conversion_service import ConversionService
from src.services.model_service import ModelService
from src.services.file_service import FileService
from src.core.types import ConversionResult, ConversionProgress, ConversionStatus
from tests.utils.marker_utils import (
    ensure_marker_ready, prepare_test_pdf, run_marker_conversion, 
    cleanup_temp_files, check_marker_cli_available, check_marker_models_available
)


@pytest.mark.integration
class TestPDFConversionIntegration:
    """Integration tests for PDF conversion"""
    
    @pytest.fixture(scope="function")
    def marker_ready(self):
        """Проверяет, что Marker готов к использованию"""
        return ensure_marker_ready()
    
    @pytest.fixture
    def real_test_pdf(self):
        """Подготавливает реальный тестовый PDF"""
        pdf_path = prepare_test_pdf()
        if pdf_path is None:
            pytest.skip("Не удалось подготовить тестовый PDF")
        yield pdf_path
        cleanup_temp_files(pdf_path.parent)
    
    @pytest.fixture
    def conversion_service(self, temp_dir):
        """Create real conversion service with mocked models"""
        with patch('src.core.config.settings') as mock_settings:
            mock_settings.temp_dir = temp_dir / "temp"
            mock_settings.output_dir = temp_dir / "output"
            mock_settings.max_file_size_mb = 10
            mock_settings.conversion_timeout_seconds = 60
            
            service = ConversionService()
            return service
    
    @pytest.fixture
    def mock_marker_model(self):
        """Mock Marker model for integration testing"""
        model = AsyncMock()
        model.name = "Marker"
        model.description = "Test Marker model"
        model.version = "0.2.0"
        model.is_enabled = True
        model.capabilities = ["pdf_to_markdown", "ocr", "table_extraction"]
        
        async def mock_convert(input_path, output_dir, on_progress=None):
            # Simulate conversion process with progress updates
            if on_progress:
                on_progress({
                    'percent': 10,
                    'phase': 'initializing',
                    'message': 'Initializing conversion'
                })
                
                await asyncio.sleep(0.1)  # Simulate processing time
                
                on_progress({
                    'percent': 50,
                    'phase': 'processing',
                    'message': 'Processing pages',
                    'pages_processed': 2,
                    'total_pages': 4
                })
                
                await asyncio.sleep(0.1)
                
                on_progress({
                    'percent': 90,
                    'phase': 'finalizing',
                    'message': 'Finalizing conversion'
                })
            
            # Create mock output files
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create markdown file
            markdown_file = output_dir / "test_document.md"
            markdown_file.write_text("""# Test Document

This is a test document converted from PDF.

## Section 1

Some content here.

### Subsection

More content.

## Section 2

- Item 1
- Item 2
- Item 3

**Bold text** and *italic text*.

[Link](https://example.com)

```python
def hello():
    print("Hello, World!")
```

> This is a quote.

---

End of document.
""", encoding="utf-8")
            
            # Create mock images
            image1 = output_dir / "image1.jpg"
            image1.write_bytes(b"fake_jpeg_data_1")
            
            image2 = output_dir / "diagram.png"
            image2.write_bytes(b"fake_png_data_2")
            
            # Create metadata file
            import json
            metadata_file = output_dir / "metadata.json"
            metadata_file.write_text(json.dumps({
                "pages_processed": 4,
                "processing_time": 2.5,
                "throughput": 1.6,
                "file_size_mb": 0.5,
                "images_count": 2,
                "model_used": "marker",
                "conversion_date": "2024-01-15T10:30:00Z"
            }), encoding="utf-8")
            
            return output_dir
        
        model.convert = mock_convert
        return model
    
    @pytest.mark.asyncio
    async def test_full_conversion_workflow(
        self, 
        conversion_service, 
        real_pdf_file, 
        mock_marker_model,
        mock_progress_callback
    ):
        """Test complete PDF conversion workflow"""
        # Setup model service with mock model
        conversion_service.model_service._models = {"marker": mock_marker_model}
        conversion_service.model_service._default_model = "marker"
        
        # Read PDF content
        pdf_content = real_pdf_file.read_bytes()
        
        # Perform conversion
        result = await conversion_service.convert_pdf(
            pdf_content=pdf_content,
            doc_id="integration_test_doc",
            model_id="marker",
            filename=real_pdf_file.name,
            on_progress=mock_progress_callback
        )
        
        # Verify result
        assert result.success is True
        assert result.doc_id == "integration_test_doc"
        assert result.markdown_content is not None
        assert len(result.markdown_content) > 0
        assert "# Test Document" in result.markdown_content
        assert "## Section 1" in result.markdown_content
        assert "**Bold text**" in result.markdown_content
        
        # Verify images
        assert len(result.images) == 2
        assert "image1.jpg" in result.images
        assert "diagram.png" in result.images
        assert result.images["image1.jpg"] == b"fake_jpeg_data_1"
        assert result.images["diagram.png"] == b"fake_png_data_2"
        
        # Verify metadata
        assert result.metadata is not None
        assert result.metadata["pages_processed"] == 4
        assert result.metadata["processing_time"] == 2.5
        assert result.metadata["throughput"] == 1.6
        assert result.metadata["images_count"] == 2
        assert result.metadata["model_used"] == "marker"
        
        # Verify processing time
        assert result.processing_time is not None
        assert result.processing_time > 0
        
        # Verify progress updates
        assert len(mock_progress_callback.updates) >= 3
        progress_updates = mock_progress_callback.updates
        
        # Check first update
        assert progress_updates[0].percent == 10
        assert progress_updates[0].phase == "initializing"
        
        # Check middle update
        assert progress_updates[1].percent == 50
        assert progress_updates[1].phase == "processing"
        assert progress_updates[1].pages_processed == 2
        assert progress_updates[1].total_pages == 4
        
        # Check final update
        assert progress_updates[2].percent == 90
        assert progress_updates[2].phase == "finalizing"
    
    @pytest.mark.asyncio
    async def test_conversion_with_marker_model(
        self, 
        conversion_service, 
        real_pdf_file,
        mock_marker_model
    ):
        """Test conversion with marker model"""
        # Setup marker model
        conversion_service.model_service._models = {
            "marker": mock_marker_model
        }
        conversion_service.model_service._default_model = "marker"
        
        pdf_content = real_pdf_file.read_bytes()
        
        # Test Marker conversion
        result_marker = await conversion_service.convert_pdf(
            pdf_content=pdf_content,
            doc_id="test_marker",
            model_id="marker"
        )
        
        assert result_marker.success is True
        assert "Test Document" in result_marker.markdown_content
    
    @pytest.mark.asyncio
    async def test_conversion_error_handling(
        self, 
        conversion_service, 
        real_pdf_file
    ):
        """Test conversion error handling"""
        # Create failing model
        failing_model = AsyncMock()
        failing_model.name = "Failing Model"
        failing_model.is_enabled = True
        
        async def failing_convert(input_path, output_dir, on_progress=None):
            raise Exception("Simulated conversion error")
        
        failing_model.convert = failing_convert
        
        conversion_service.model_service._models = {"failing": failing_model}
        conversion_service.model_service._default_model = "failing"
        
        pdf_content = real_pdf_file.read_bytes()
        
        result = await conversion_service.convert_pdf(
            pdf_content=pdf_content,
            doc_id="test_failing",
            model_id="failing"
        )
        
        assert result.success is False
        assert "Simulated conversion error" in result.error_message
    
    @pytest.mark.asyncio
    async def test_concurrent_conversions(
        self, 
        conversion_service, 
        generate_test_pdfs,
        mock_marker_model
    ):
        """Test concurrent PDF conversions"""
        conversion_service.model_service._models = {"marker": mock_marker_model}
        conversion_service.model_service._default_model = "marker"
        
        # Create multiple conversion tasks
        tasks = []
        for i, pdf_path in enumerate(generate_test_pdfs):
            pdf_content = pdf_path.read_bytes()
            task = conversion_service.convert_pdf(
                pdf_content=pdf_content,
                doc_id=f"concurrent_test_{i}",
                model_id="marker"
            )
            tasks.append(task)
        
        # Run all conversions concurrently
        results = await asyncio.gather(*tasks)
        
        # Verify all conversions succeeded
        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.success is True
            assert result.doc_id == f"concurrent_test_{i}"
            assert result.markdown_content is not None
    
    @pytest.mark.asyncio
    async def test_conversion_cancellation(
        self, 
        conversion_service, 
        real_pdf_file
    ):
        """Test conversion cancellation"""
        # Create slow model
        slow_model = AsyncMock()
        slow_model.name = "Slow Model"
        slow_model.is_enabled = True
        
        async def slow_convert(input_path, output_dir, on_progress=None):
            await asyncio.sleep(10)  # Simulate slow conversion
            return output_dir
        
        slow_model.convert = slow_convert
        
        conversion_service.model_service._models = {"slow": slow_model}
        conversion_service.model_service._default_model = "slow"
        
        pdf_content = real_pdf_file.read_bytes()
        
        # Start conversion
        conversion_task = asyncio.create_task(
            conversion_service.convert_pdf(
                pdf_content=pdf_content,
                doc_id="test_cancellation",
                model_id="slow"
            )
        )
        
        # Wait a bit then cancel
        await asyncio.sleep(0.1)
        cancelled = await conversion_service.cancel_conversion("test_cancellation")
        
        assert cancelled is True
        
        # Wait for task to complete
        try:
            result = await conversion_task
            # If it completes, it should be cancelled
            assert result.success is False
        except asyncio.CancelledError:
            # Expected if task was cancelled
            pass
    
    @pytest.mark.asyncio
    async def test_large_file_handling(
        self, 
        conversion_service, 
        large_pdf_content,
        mock_marker_model
    ):
        """Test handling of large PDF files"""
        conversion_service.model_service._models = {"marker": mock_marker_model}
        conversion_service.model_service._default_model = "marker"
        
        # This should fail due to file size limit
        result = await conversion_service.convert_pdf(
            pdf_content=large_pdf_content,
            doc_id="test_large_file",
            model_id="marker"
        )
        
        assert result.success is False
        assert "File size" in result.error_message
    
    @pytest.mark.asyncio
    async def test_invalid_pdf_handling(
        self, 
        conversion_service, 
        invalid_pdf_content,
        mock_marker_model
    ):
        """Test handling of invalid PDF files"""
        conversion_service.model_service._models = {"marker": mock_marker_model}
        conversion_service.model_service._default_model = "marker"
        
        result = await conversion_service.convert_pdf(
            pdf_content=invalid_pdf_content,
            doc_id="test_invalid_pdf",
            model_id="marker"
        )
        
        assert result.success is False
        assert "not appear to be a valid PDF" in result.error_message
    
    @pytest.mark.asyncio
    async def test_conversion_with_metadata_extraction(
        self, 
        conversion_service, 
        real_pdf_file,
        mock_marker_model
    ):
        """Test conversion with comprehensive metadata extraction"""
        conversion_service.model_service._models = {"marker": mock_marker_model}
        conversion_service.model_service._default_model = "marker"
        
        pdf_content = real_pdf_file.read_bytes()
        
        result = await conversion_service.convert_pdf(
            pdf_content=pdf_content,
            doc_id="test_metadata",
            model_id="marker"
        )
        
        assert result.success is True
        assert result.metadata is not None
        
        # Verify metadata fields
        metadata = result.metadata
        assert "pages_processed" in metadata
        assert "processing_time" in metadata
        assert "throughput" in metadata
        assert "file_size_mb" in metadata
        assert "images_count" in metadata
        assert "model_used" in metadata
        assert "conversion_date" in metadata
        
        # Verify metadata values
        assert metadata["pages_processed"] > 0
        assert metadata["processing_time"] > 0
        assert metadata["throughput"] > 0
        assert metadata["file_size_mb"] > 0
        assert metadata["images_count"] >= 0
        assert metadata["model_used"] == "marker"
        assert metadata["conversion_date"] is not None


@pytest.mark.integration
@pytest.mark.real_marker
class TestRealMarkerIntegration:
    """Integration tests with real Marker CLI"""
    
    @pytest.fixture(scope="function")
    def marker_ready(self):
        """Проверяет, что Marker готов к использованию"""
        return ensure_marker_ready()
    
    @pytest.fixture
    def real_test_pdf(self):
        """Подготавливает реальный тестовый PDF"""
        pdf_path = prepare_test_pdf()
        if pdf_path is None:
            pytest.skip("Не удалось подготовить тестовый PDF")
        yield pdf_path
        cleanup_temp_files(pdf_path.parent)
    
    def test_marker_cli_availability(self, marker_ready):
        """Test that Marker CLI is available"""
        assert marker_ready is True
        assert check_marker_cli_available() is True
        assert check_marker_models_available() is True
    
    def test_marker_direct_conversion(self, real_test_pdf):
        """Test direct Marker CLI conversion"""
        # Создаем временную папку для вывода
        output_dir = real_test_pdf.parent / "output"
        output_dir.mkdir(exist_ok=True)
        
        # Запускаем Marker CLI
        success, stdout, stderr = run_marker_conversion(real_test_pdf, output_dir)
        
        assert success is True, f"Marker CLI failed: {stderr}"
        # Marker успешно обработал PDF, если в stdout есть информация о страницах
        assert "pages" in stdout.lower() or "inferenced" in stdout.lower()
        
        # Проверяем, что создались файлы результатов
        results_dir = real_test_pdf.parent / "input" / "conversion_results"
        if results_dir.exists():
            markdown_files = list(results_dir.glob("*.md"))
            assert len(markdown_files) > 0, "No markdown files created"
            
            # Проверяем содержимое первого markdown файла
            with open(markdown_files[0], 'r', encoding='utf-8') as f:
                content = f.read()
                assert len(content) > 100, "Markdown content too short"
                assert "Parkinson" in content or "disease" in content.lower()
    
    @pytest.mark.asyncio
    async def test_real_marker_model_conversion(self, real_test_pdf, tmp_path):
        """Test conversion using real Marker model"""
        # Создаем реальный сервис конвертации
        with patch('src.core.config.settings') as mock_settings:
            mock_settings.temp_dir = tmp_path / "temp"
            mock_settings.output_dir = tmp_path / "output"
            mock_settings.max_file_size_mb = 100
            mock_settings.conversion_timeout_seconds = 600
            
            # Создаем реальные сервисы
            file_service = FileService()
            model_service = ModelService()
            conversion_service = ConversionService()
            conversion_service.model_service = model_service
            conversion_service.file_service = file_service
            
            # Читаем PDF
            pdf_content = real_test_pdf.read_bytes()
            
            # Запускаем конвертацию
            result = await conversion_service.convert_pdf(
                pdf_content=pdf_content,
                doc_id="real_marker_test",
                model_id="marker"
            )
            
            # Проверяем результат
            assert result.success is True
            assert result.doc_id == "real_marker_test"
            assert len(result.markdown_content) > 100
            assert "Parkinson" in result.markdown_content or "disease" in result.markdown_content.lower()
            assert result.processing_time > 0
            assert result.metadata is not None
            assert result.metadata.get("model_used") == "marker"
    
    def test_marker_models_directory_structure(self):
        """Test that marker_models directory has correct structure"""
        models_dir = Path("./marker_models")
        assert models_dir.exists(), "marker_models directory not found"
        
        # Проверяем наличие папки hub с моделями
        hub_dir = models_dir / "hub"
        assert hub_dir.exists(), "Required directory hub not found"
        
        # Проверяем наличие файлов моделей
        model_files = list(hub_dir.rglob("*.safetensors")) + list(hub_dir.rglob("*.bin"))
        assert len(model_files) > 0, "No model files found in hub directory"
        
        # Проверяем наличие моделей в hub
        model_dirs = [d for d in hub_dir.iterdir() if d.is_dir()]
        assert len(model_dirs) > 0, "No model directories found in hub"
    
    def test_marker_environment_variables(self):
        """Test that Marker environment variables are set correctly"""
        import os
        
        # Проверяем, что переменные окружения установлены
        assert "HF_HOME" in os.environ, "HF_HOME not set"
        assert "TRANSFORMERS_CACHE" in os.environ, "TRANSFORMERS_CACHE not set"
        assert "TORCH_HOME" in os.environ, "TORCH_HOME not set"
        
        # Проверяем, что они указывают на правильные папки
        hf_home = Path(os.environ["HF_HOME"])
        assert hf_home.exists(), f"HF_HOME directory not found: {hf_home}"
        assert (hf_home / "models--bert-base-multilingual-cased").exists(), "BERT model not found"
    
    @pytest.mark.asyncio
    async def test_conversion_with_progress_tracking(self, real_test_pdf, tmp_path):
        """Test conversion with progress tracking"""
        progress_updates = []
        
        async def progress_callback(progress):
            progress_updates.append(progress)
        
        # Создаем реальный сервис конвертации
        with patch('src.core.config.settings') as mock_settings:
            mock_settings.temp_dir = tmp_path / "temp"
            mock_settings.output_dir = tmp_path / "output"
            mock_settings.max_file_size_mb = 100
            mock_settings.conversion_timeout_seconds = 600
            
            file_service = FileService()
            model_service = ModelService()
            conversion_service = ConversionService()
            conversion_service.model_service = model_service
            conversion_service.file_service = file_service
            
            # Читаем PDF
            pdf_content = real_test_pdf.read_bytes()
            
            # Запускаем конвертацию с отслеживанием прогресса
            result = await conversion_service.convert_pdf(
                pdf_content=pdf_content,
                doc_id="progress_test",
                model_id="marker",
                on_progress=progress_callback
            )
            
            # Проверяем результат
            assert result.success is True
            assert len(progress_updates) > 0, "No progress updates received"
            
            # Проверяем структуру обновлений прогресса
            for update in progress_updates:
                assert "percent" in update
                assert "phase" in update
                assert 0 <= update["percent"] <= 100
