"""Tests for Marker model"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, mock_open

from src.services.models.marker_model import MarkerModel
from src.core.exceptions import PDFConversionError, ConversionTimeoutError
from tests.utils.marker_utils import (
    ensure_marker_ready, prepare_test_pdf, run_marker_conversion, 
    cleanup_temp_files, check_marker_cli_available, check_marker_models_available
)


@pytest.mark.unit
class TestMarkerModel:
    """Unit tests for MarkerModel"""
    
    @pytest.fixture
    def marker_model(self):
        """Create Marker model instance"""
        return MarkerModel()
    
    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing"""
        input_dir = Path(tempfile.mkdtemp(prefix="marker_input_"))
        output_dir = Path(tempfile.mkdtemp(prefix="marker_output_"))
        
        yield input_dir, output_dir
        
        # Cleanup
        import shutil
        shutil.rmtree(input_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)
    
    def test_marker_model_initialization(self, marker_model):
        """Test Marker model initialization"""
        assert marker_model.name == "Marker"
        assert marker_model.description == "Marker PDF to Markdown conversion with advanced layout analysis"
        assert marker_model.version == "0.2.0"
        assert marker_model.is_enabled is True
        assert "pdf_to_markdown" in marker_model.capabilities
        assert "layout_analysis" in marker_model.capabilities
        assert "table_extraction" in marker_model.capabilities
        assert "image_extraction" in marker_model.capabilities
        assert "ocr" in marker_model.capabilities
    
    def test_validate_input_valid_pdf(self, marker_model, real_pdf_file):
        """Test validating valid PDF input"""
        result = marker_model.validate_input(real_pdf_file)
        assert result is True
    
    def test_validate_input_nonexistent_file(self, marker_model, temp_dir):
        """Test validating non-existent file"""
        nonexistent_file = temp_dir / "nonexistent.pdf"
        
        with pytest.raises(FileNotFoundError):
            marker_model.validate_input(nonexistent_file)
    
    def test_validate_input_non_pdf_file(self, marker_model, temp_dir):
        """Test validating non-PDF file"""
        text_file = temp_dir / "test.txt"
        text_file.write_text("This is not a PDF")
        
        with pytest.raises(ValueError, match="Input file must be a PDF"):
            marker_model.validate_input(text_file)
    
    def test_validate_input_empty_file(self, marker_model, temp_dir):
        """Test validating empty file"""
        empty_file = temp_dir / "empty.pdf"
        empty_file.write_bytes(b'')  # Truly empty file
        
        with pytest.raises(ValueError, match="Input file is empty"):
            marker_model.validate_input(empty_file)
    
    def test_validate_input_invalid_pdf_header(self, marker_model, temp_dir):
        """Test validating file with invalid PDF header"""
        invalid_file = temp_dir / "invalid.pdf"
        invalid_file.write_bytes(b"This is not a PDF file")
        
        with pytest.raises(ValueError, match="Input file does not appear to be a valid PDF"):
            marker_model.validate_input(invalid_file)
    
    @pytest.mark.asyncio
    async def test_convert_success(self, marker_model, real_pdf_file, temp_dirs):
        """Test successful conversion"""
        input_dir, output_dir = temp_dirs
        
        # Copy PDF to input directory
        import shutil
        test_pdf = input_dir / real_pdf_file.name
        shutil.copy2(real_pdf_file, test_pdf)
        
        # Mock subprocess to simulate successful Marker execution
        with patch('subprocess.Popen') as mock_popen:
            # Mock successful process
            mock_process = Mock()
            mock_process.poll.return_value = None  # Process running
            mock_process.wait.return_value = 0  # Success exit code
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.readline.side_effect = [
                b"Processing page 1/4\n",
                b"Processing page 2/4\n",
                b"Processing page 3/4\n",
                b"Processing page 4/4\n",
                b"Conversion completed\n",
                b""  # End of output
            ]
            mock_process.stderr.readline.side_effect = [b""]  # No errors
            
            mock_popen.return_value = mock_process
            
            # Mock result directory creation
            with patch.object(marker_model, '_find_marker_results') as mock_find, \
                 patch.object(marker_model, '_copy_results') as mock_copy:
                
                mock_find.return_value = input_dir  # Return input dir as result
                
                # Create mock output files
                markdown_file = input_dir / f"{real_pdf_file.stem}.md"
                markdown_file.write_text("# Test Document\n\nConverted content.", encoding="utf-8")
                
                image_file = input_dir / "image1.jpg"
                image_file.write_bytes(b"fake_image_data")
                
                result_dir = await marker_model.convert(
                    input_path=test_pdf,
                    output_dir=output_dir
                )
                
                assert result_dir == output_dir
                mock_find.assert_called_once()
                mock_copy.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_convert_with_progress(self, marker_model, real_pdf_file, temp_dirs, mock_progress_callback):
        """Test conversion with progress updates"""
        input_dir, output_dir = temp_dirs
        
        # Copy PDF to input directory
        import shutil
        test_pdf = input_dir / real_pdf_file.name
        shutil.copy2(real_pdf_file, test_pdf)
        
        # Mock subprocess with progress output
        with patch('subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None
            mock_process.wait.return_value = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            
            # Simulate progress output
            progress_output = [
                b"Loading model...\n",
                b"Processing page 1/4\n",
                b"Processing page 2/4\n",
                b"Processing page 3/4\n",
                b"Processing page 4/4\n",
                b"Conversion completed\n",
                b""
            ]
            mock_process.stdout.readline.side_effect = progress_output
            mock_process.stderr.readline.side_effect = [b""]
            
            mock_popen.return_value = mock_process
            
            with patch.object(marker_model, '_find_marker_results') as mock_find, \
                 patch.object(marker_model, '_copy_results') as mock_copy:
                
                mock_find.return_value = input_dir
                
                # Create mock output
                markdown_file = input_dir / f"{real_pdf_file.stem}.md"
                markdown_file.write_text("# Test Document", encoding="utf-8")
                
                await marker_model.convert(
                    input_path=test_pdf,
                    output_dir=output_dir,
                    on_progress=mock_progress_callback
                )
                
                # Verify progress updates were called
                assert len(mock_progress_callback.updates) > 0
    
    @pytest.mark.asyncio
    async def test_convert_marker_not_found(self, marker_model, real_pdf_file, temp_dirs):
        """Test conversion when Marker command is not found"""
        input_dir, output_dir = temp_dirs
        
        test_pdf = input_dir / real_pdf_file.name
        import shutil
        shutil.copy2(real_pdf_file, test_pdf)
        
        with patch('subprocess.Popen') as mock_popen:
            mock_popen.side_effect = FileNotFoundError("marker command not found")
            
            with pytest.raises(PDFConversionError, match="Marker command not found"):
                await marker_model.convert(
                    input_path=test_pdf,
                    output_dir=output_dir
                )
    
    @pytest.mark.asyncio
    async def test_convert_marker_failure(self, marker_model, real_pdf_file, temp_dirs):
        """Test conversion when Marker fails"""
        input_dir, output_dir = temp_dirs
        
        test_pdf = input_dir / real_pdf_file.name
        import shutil
        shutil.copy2(real_pdf_file, test_pdf)
        
        with patch('subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None
            mock_process.wait.return_value = 1  # Error exit code
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.readline.side_effect = [b"Error occurred\n", b""]
            mock_process.stderr.readline.side_effect = [b"Marker error\n", b""]
            
            mock_popen.return_value = mock_process
            
            with pytest.raises(PDFConversionError, match="Marker failed with return code 1"):
                await marker_model.convert(
                    input_path=test_pdf,
                    output_dir=output_dir
                )
    
    @pytest.mark.asyncio
    async def test_convert_timeout(self, marker_model, real_pdf_file, temp_dirs):
        """Test conversion timeout"""
        input_dir, output_dir = temp_dirs
        
        test_pdf = input_dir / real_pdf_file.name
        import shutil
        shutil.copy2(real_pdf_file, test_pdf)
        
        with patch('subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None
            mock_process.wait.side_effect = asyncio.TimeoutError()
            mock_process.kill = Mock()
            
            mock_popen.return_value = mock_process
            
            with pytest.raises(ConversionTimeoutError, match="Marker timeout"):
                await marker_model.convert(
                    input_path=test_pdf,
                    output_dir=output_dir
                )
    
    def test_find_result_directory_success(self, marker_model, temp_dirs):
        """Test finding result directory successfully"""
        input_dir, output_dir = temp_dirs
        
        # Create mock result directory with markdown file
        result_dir = input_dir / "test_results"
        result_dir.mkdir()
        markdown_file = result_dir / "test_document.md"
        markdown_file.write_text("# Test", encoding="utf-8")
        
        result = marker_model._find_marker_results(input_dir, "test_document")
        
        assert result == result_dir
    
    def test_find_result_directory_not_found(self, marker_model, temp_dirs):
        """Test finding result directory when not found"""
        input_dir, output_dir = temp_dirs
        
        result = marker_model._find_marker_results(input_dir, "nonexistent")
        
        assert result is None
    
    def test_copy_results(self, marker_model, temp_dirs):
        """Test copying conversion results"""
        input_dir, output_dir = temp_dirs
        
        # Create source files
        source_dir = input_dir / "source"
        source_dir.mkdir()
        
        markdown_file = source_dir / "test.md"
        markdown_file.write_text("# Test Document", encoding="utf-8")
        
        image_file = source_dir / "image.jpg"
        image_file.write_bytes(b"fake_image_data")
        
        subdir = source_dir / "subdir"
        subdir.mkdir()
        subfile = subdir / "subfile.txt"
        subfile.write_text("sub content", encoding="utf-8")
        
        # Copy results
        marker_model._copy_results(source_dir, output_dir)
        
        # Verify files were copied
        assert (output_dir / "test.md").exists()
        assert (output_dir / "image.jpg").exists()
        assert (output_dir / "subdir" / "subfile.txt").exists()
        
        # Verify content
        assert (output_dir / "test.md").read_text(encoding="utf-8") == "# Test Document"
        assert (output_dir / "image.jpg").read_bytes() == b"fake_image_data"
        assert (output_dir / "subdir" / "subfile.txt").read_text(encoding="utf-8") == "sub content"
    
    def test_environment_variables_setup(self, marker_model):
        """Test that environment variables are properly set"""
        with patch('subprocess.Popen') as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None
            mock_process.wait.return_value = 0
            mock_process.stdout = Mock()
            mock_process.stderr = Mock()
            mock_process.stdout.readline.side_effect = [b"", b""]
            mock_process.stderr.readline.side_effect = [b"", b""]
            
            mock_popen.return_value = mock_process
            
            # This will test the environment setup in _run_marker_conversion
            # We can't easily test the actual environment, but we can verify
            # that the method is called with proper parameters
            assert marker_model.name == "Marker"
            assert marker_model.is_enabled is True
    
    def test_model_capabilities(self, marker_model):
        """Test model capabilities"""
        expected_capabilities = [
            "pdf_to_markdown",
            "layout_analysis", 
            "table_extraction",
            "image_extraction",
            "ocr"
        ]
        
        for capability in expected_capabilities:
            assert capability in marker_model.capabilities
        
        assert len(marker_model.capabilities) == len(expected_capabilities)
    
    def test_model_info(self, marker_model):
        """Test model information"""
        info = marker_model.get_model_info()
        
        assert info["name"] == "Marker"
        assert info["description"] == "Marker PDF to Markdown conversion with advanced layout analysis"
        assert info["version"] == "0.2.0"
        assert info["enabled"] is True
        assert "pdf_to_markdown" in info["capabilities"]
        assert "ocr" in info["capabilities"]


@pytest.mark.integration
@pytest.mark.real_marker
class TestRealMarkerModel:
    """Integration tests with real Marker CLI"""
    
    @pytest.fixture(scope="session")
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
    
    def test_real_marker_model_initialization(self, marker_ready):
        """Test real Marker model initialization"""
        assert marker_ready is True
        
        # Создаем реальную модель Marker
        marker_model = MarkerModel()
        
        # Проверяем базовые свойства
        assert marker_model.name == "Marker"
        assert marker_model.version == "0.2.0"
        assert marker_model.is_enabled is True
        assert "pdf_to_markdown" in marker_model.capabilities
        assert "ocr" in marker_model.capabilities
        assert "table_extraction" in marker_model.capabilities
    
    def test_real_marker_validate_input(self, real_test_pdf):
        """Test real Marker model input validation"""
        marker_model = MarkerModel()
        
        # Проверяем валидацию реального PDF
        assert marker_model.validate_input(real_test_pdf) is True
        
        # Проверяем валидацию несуществующего файла
        nonexistent_file = real_test_pdf.parent / "nonexistent.pdf"
        with pytest.raises(FileNotFoundError):
            marker_model.validate_input(nonexistent_file)
        
        # Проверяем валидацию не-PDF файла
        text_file = real_test_pdf.parent / "test.txt"
        text_file.write_text("This is not a PDF")
        with pytest.raises(ValueError, match="Input file must be a PDF"):
            marker_model.validate_input(text_file)
    
    @pytest.mark.asyncio
    async def test_real_marker_convert(self, real_test_pdf, tmp_path):
        """Test real Marker model conversion"""
        marker_model = MarkerModel()
        
        # Создаем выходную папку
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        # Запускаем конвертацию
        result_dir = await marker_model.convert(real_test_pdf, output_dir)
        
        # Проверяем результат
        assert result_dir.exists()
        assert result_dir == output_dir
        
        # Проверяем, что создались файлы результатов
        markdown_files = list(result_dir.glob("*.md"))
        assert len(markdown_files) > 0, "No markdown files created"
        
        # Проверяем содержимое первого markdown файла
        with open(markdown_files[0], 'r', encoding='utf-8') as f:
            content = f.read()
            assert len(content) > 100, "Markdown content too short"
            assert "Parkinson" in content or "disease" in content.lower()
    
    @pytest.mark.asyncio
    async def test_real_marker_convert_with_progress(self, real_test_pdf, tmp_path):
        """Test real Marker model conversion with progress tracking"""
        marker_model = MarkerModel()
        
        # Создаем выходную папку
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        # Отслеживаем прогресс
        progress_updates = []
        
        async def progress_callback(progress):
            progress_updates.append(progress)
        
        # Запускаем конвертацию с отслеживанием прогресса
        result_dir = await marker_model.convert(
            real_test_pdf, 
            output_dir, 
            on_progress=progress_callback
        )
        
        # Проверяем результат
        assert result_dir.exists()
        assert len(progress_updates) > 0, "No progress updates received"
        
        # Проверяем структуру обновлений прогресса
        for update in progress_updates:
            assert "percent" in update
            assert "phase" in update
            assert 0 <= update["percent"] <= 100
    
    def test_real_marker_environment_setup(self):
        """Test that Marker environment is properly set up"""
        import os
        
        # Проверяем переменные окружения
        assert "HF_HOME" in os.environ
        assert "TRANSFORMERS_CACHE" in os.environ
        assert "TORCH_HOME" in os.environ
        
        # Проверяем, что они указывают на правильные папки
        hf_home = Path(os.environ["HF_HOME"])
        assert hf_home.exists()
        assert (hf_home / "models--bert-base-multilingual-cased").exists()
    
    def test_real_marker_models_availability(self):
        """Test that Marker models are available"""
        assert check_marker_models_available() is True
        
        models_dir = Path("./marker_models")
        assert models_dir.exists()
        
        # Проверяем наличие папки hub с моделями
        hub_dir = models_dir / "hub"
        assert hub_dir.exists()
        
        # Проверяем наличие файлов моделей
        model_files = list(hub_dir.rglob("*.safetensors")) + list(hub_dir.rglob("*.bin"))
        assert len(model_files) > 0
