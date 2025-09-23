"""Тесты для сервиса координатного извлечения"""

import pytest
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from pathlib import Path

from src.services.coordinate_extraction_service import CoordinateExtractionService


class TestCoordinateExtractionService:
    """Тесты для CoordinateExtractionService"""
    
    @pytest.fixture
    def extraction_service(self):
        """Фикстура сервиса извлечения"""
        return CoordinateExtractionService()
    
    @pytest.fixture
    def mock_docling_result(self):
        """Мок результата Docling"""
        
        # Создаем мок bbox
        mock_bbox = Mock()
        mock_bbox.l = 100.0
        mock_bbox.t = 200.0
        mock_bbox.r = 300.0
        mock_bbox.b = 150.0
        mock_bbox.coord_origin = "BOTTOMLEFT"
        
        # Создаем мок provenance
        mock_prov = Mock()
        mock_prov.bbox = mock_bbox
        mock_prov.page_no = 1
        
        # Создаем мок picture
        mock_picture = Mock()
        mock_picture.prov = [mock_prov]
        mock_picture.self_ref = "#/pictures/0"
        
        # Создаем мок document
        mock_document = Mock()
        mock_document.pictures = [mock_picture]
        mock_document.export_to_markdown.return_value = "# Test\n<!-- image -->\nSome text"
        
        # Создаем мок result
        mock_result = Mock()
        mock_result.document = mock_document
        
        return mock_result
    
    @pytest.fixture
    def mock_s3_service(self):
        """Мок S3 сервиса"""
        mock_s3 = AsyncMock()
        
        # Настраиваем методы
        mock_s3.health_check.return_value = {'success': True}
        mock_s3.upload_image.return_value = {
            'success': True,
            'filename': 'test_image.png',
            'object_key': 'documents/test_doc/images/test_image.png',
            'url': 'http://localhost:9000/bucket/documents/test_doc/images/test_image.png',
            'size_bytes': 1024
        }
        mock_s3.list_images.return_value = {
            'success': True,
            'images': [],
            'count': 0
        }
        mock_s3.delete_image.return_value = {'success': True}
        
        return mock_s3
    
    @pytest.fixture
    def test_pdf_path(self, tmp_path):
        """Тестовый PDF файл"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"fake pdf content")
        return pdf_path
    
    @pytest.mark.asyncio
    async def test_extract_coordinates_from_docling(self, extraction_service, mock_docling_result):
        """Тест извлечения координат из результата Docling"""
        
        coordinates = extraction_service._extract_coordinates_from_docling(mock_docling_result)
        
        assert len(coordinates) == 1
        
        coord = coordinates[0]
        assert coord['picture_index'] == 0
        assert coord['page_no'] == 1
        assert coord['page_index'] == 0
        assert coord['bbox']['left'] == 100.0
        assert coord['bbox']['top'] == 200.0
        assert coord['bbox']['right'] == 300.0
        assert coord['bbox']['bottom'] == 150.0
        assert coord['width'] == 200.0  # 300 - 100
        assert coord['height'] == 50.0  # 200 - 150
        assert coord['self_ref'] == "#/pictures/0"
    
    @pytest.mark.asyncio
    async def test_extract_coordinates_from_docling_no_pictures(self, extraction_service):
        """Тест извлечения координат когда нет изображений"""
        
        mock_result = Mock()
        mock_document = Mock()
        mock_document.pictures = []
        mock_result.document = mock_document
        
        coordinates = extraction_service._extract_coordinates_from_docling(mock_result)
        
        assert len(coordinates) == 0
    
    @pytest.mark.asyncio
    async def test_extract_coordinates_from_docling_no_document(self, extraction_service):
        """Тест извлечения координат когда нет документа"""
        
        mock_result = Mock()
        mock_result.document = None
        
        coordinates = extraction_service._extract_coordinates_from_docling(mock_result)
        
        assert len(coordinates) == 0
    
    @pytest.mark.asyncio
    async def test_update_markdown_with_s3_urls(self, extraction_service):
        """Тест обновления markdown с S3 URL"""
        
        markdown_content = "# Test Document\n<!-- image -->\nSome text\n<!-- image -->\nMore text"
        
        extracted_images = [
            {
                'picture_index': 0,
                's3_url': 'http://s3.example.com/image1.png',
                'filename': 'image1.png'
            },
            {
                'picture_index': 1,
                's3_url': 'http://s3.example.com/image2.png',
                'filename': 'image2.png'
            }
        ]
        
        result = extraction_service._update_markdown_with_s3_urls(markdown_content, extracted_images)
        
        expected = "# Test Document\n![Изображение 1](http://s3.example.com/image1.png)\nSome text\n![Изображение 2](http://s3.example.com/image2.png)\nMore text"
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_update_markdown_with_s3_urls_no_images(self, extraction_service):
        """Тест обновления markdown без изображений"""
        
        markdown_content = "# Test Document\nSome text"
        extracted_images = []
        
        result = extraction_service._update_markdown_with_s3_urls(markdown_content, extracted_images)
        
        assert result == markdown_content
    
    @pytest.mark.asyncio
    async def test_get_document_images_success(self, extraction_service, mock_s3_service):
        """Тест успешного получения изображений документа"""
        
        # Подменяем s3_service
        extraction_service.s3_service = mock_s3_service
        
        mock_s3_service.list_images.return_value = {
            'success': True,
            'images': [
                {
                    'object_key': 'documents/test_doc/images/img1.png',
                    'filename': 'img1.png',
                    'url': 'http://s3.example.com/img1.png',
                    'size_bytes': 1024
                }
            ],
            'count': 1
        }
        
        result = await extraction_service.get_document_images('test_doc')
        
        assert result['success'] is True
        assert result['document_id'] == 'test_doc'
        assert result['count'] == 1
        assert len(result['images']) == 1
        
        mock_s3_service.list_images.assert_called_once_with(folder='documents/test_doc/images')
    
    @pytest.mark.asyncio
    async def test_get_document_images_failure(self, extraction_service, mock_s3_service):
        """Тест неудачного получения изображений документа"""
        
        extraction_service.s3_service = mock_s3_service
        
        mock_s3_service.list_images.return_value = {
            'success': False,
            'error': 'S3 error'
        }
        
        result = await extraction_service.get_document_images('test_doc')
        
        assert result['success'] is False
        assert result['document_id'] == 'test_doc'
        assert 'error' in result
    
    @pytest.mark.asyncio
    async def test_delete_document_images_success(self, extraction_service, mock_s3_service):
        """Тест успешного удаления изображений документа"""
        
        extraction_service.s3_service = mock_s3_service
        
        # Настраиваем мок для получения изображений
        mock_s3_service.list_images.return_value = {
            'success': True,
            'images': [
                {'object_key': 'documents/test_doc/images/img1.png', 'filename': 'img1.png'},
                {'object_key': 'documents/test_doc/images/img2.png', 'filename': 'img2.png'}
            ],
            'count': 2
        }
        
        # Настраиваем мок для удаления
        mock_s3_service.delete_image.return_value = {'success': True}
        
        result = await extraction_service.delete_document_images('test_doc')
        
        assert result['success'] is True
        assert result['document_id'] == 'test_doc'
        assert result['deleted_count'] == 2
        assert result['total_count'] == 2
        assert len(result['errors']) == 0
        
        # Проверяем что delete_image вызывался для каждого изображения
        assert mock_s3_service.delete_image.call_count == 2
    
    @pytest.mark.asyncio
    async def test_delete_document_images_partial_failure(self, extraction_service, mock_s3_service):
        """Тест частичной неудачи при удалении изображений"""
        
        extraction_service.s3_service = mock_s3_service
        
        mock_s3_service.list_images.return_value = {
            'success': True,
            'images': [
                {'object_key': 'documents/test_doc/images/img1.png', 'filename': 'img1.png'},
                {'object_key': 'documents/test_doc/images/img2.png', 'filename': 'img2.png'}
            ],
            'count': 2
        }
        
        # Первое удаление успешно, второе неудачно
        mock_s3_service.delete_image.side_effect = [
            {'success': True},
            {'success': False, 'error': 'Delete failed'}
        ]
        
        result = await extraction_service.delete_document_images('test_doc')
        
        assert result['success'] is False  # Общий результат неудачный
        assert result['deleted_count'] == 1
        assert result['total_count'] == 2
        assert len(result['errors']) == 1
        assert 'img2.png' in result['errors'][0]
    
    @pytest.mark.asyncio
    @patch('src.services.coordinate_extraction_service.fitz')
    async def test_extract_and_upload_images_success(self, mock_fitz, extraction_service, mock_s3_service, test_pdf_path):
        """Тест успешного извлечения и загрузки изображений"""
        
        extraction_service.s3_service = mock_s3_service
        
        # Настраиваем мок PyMuPDF
        mock_doc = Mock()
        mock_page = Mock()
        mock_rect = Mock()
        mock_rect.width = 800
        mock_rect.height = 600
        mock_page.rect = mock_rect
        
        mock_pixmap = Mock()
        mock_pixmap.width = 200
        mock_pixmap.height = 100
        mock_pixmap.tobytes.return_value = b"fake png data"
        
        mock_page.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap
        
        mock_doc.__len__.return_value = 1
        mock_doc.load_page.return_value = mock_page
        mock_doc.close = Mock()
        
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Rect.return_value = Mock()
        mock_fitz.Matrix.return_value = Mock()
        
        # Тестовые координаты
        coordinates = [
            {
                'picture_index': 0,
                'page_no': 1,
                'page_index': 0,
                'bbox': {
                    'left': 100,
                    'top': 500,
                    'right': 300,
                    'bottom': 400
                },
                'self_ref': '#/pictures/0'
            }
        ]
        
        with patch('src.services.coordinate_extraction_service.Image') as mock_image:
            mock_pil_image = Mock()
            mock_pil_image.size = (200, 100)
            mock_image.open.return_value = mock_pil_image
            
            result = await extraction_service._extract_and_upload_images(
                test_pdf_path, coordinates, 'test_doc', None
            )
        
        assert len(result) == 1
        assert result[0]['picture_index'] == 0
        assert result[0]['page_no'] == 1
        assert result[0]['extraction_method'] == 'coordinate_based_s3'
        assert result[0]['document_id'] == 'test_doc'
        
        # Проверяем что S3 upload был вызван
        mock_s3_service.upload_image.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_images_with_s3_success(self, extraction_service, test_pdf_path):
        """Тест полного процесса извлечения с S3"""
        
        mock_s3_service = AsyncMock()
        mock_s3_service.health_check.return_value = {'success': True}
        extraction_service.s3_service = mock_s3_service
        
        # Мокаем Docling
        with patch('src.services.coordinate_extraction_service.DocumentConverter') as mock_converter_class:
            mock_converter = Mock()
            mock_result = Mock()
            mock_document = Mock()
            mock_document.export_to_markdown.return_value = "# Test\n<!-- image -->"
            mock_result.document = mock_document
            
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            # Мокаем извлечение координат
            with patch.object(extraction_service, '_extract_coordinates_from_docling', return_value=[]):
                with patch.object(extraction_service, '_extract_and_upload_images', return_value=[]):
                    
                    result = await extraction_service.extract_images_with_s3(
                        test_pdf_path, 'test_doc'
                    )
        
        assert result['success'] is True
        assert result['method'] == 'coordinate_based_s3'
        assert result['document_id'] == 'test_doc'
        assert 'markdown_content' in result
    
    @pytest.mark.asyncio
    async def test_extract_images_with_s3_s3_unavailable(self, extraction_service, test_pdf_path):
        """Тест когда S3 недоступен"""
        
        mock_s3_service = AsyncMock()
        mock_s3_service.health_check.return_value = {
            'success': False, 
            'error': 'S3 connection failed'
        }
        extraction_service.s3_service = mock_s3_service
        
        result = await extraction_service.extract_images_with_s3(
            test_pdf_path, 'test_doc'
        )
        
        assert result['success'] is False
        assert 'S3 service unavailable' in result['error']
    
    @pytest.mark.asyncio
    async def test_extract_images_with_s3_docling_error(self, extraction_service, test_pdf_path):
        """Тест когда Docling выдает ошибку"""
        
        mock_s3_service = AsyncMock()
        mock_s3_service.health_check.return_value = {'success': True}
        extraction_service.s3_service = mock_s3_service
        
        # Мокаем Docling с ошибкой
        with patch('src.services.coordinate_extraction_service.DocumentConverter') as mock_converter_class:
            mock_converter_class.side_effect = Exception("Docling conversion failed")
            
            result = await extraction_service.extract_images_with_s3(
                test_pdf_path, 'test_doc'
            )
        
        assert result['success'] is False
        assert 'Docling conversion failed' in result['error']


if __name__ == "__main__":
    pytest.main([__file__])
