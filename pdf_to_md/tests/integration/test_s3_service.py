"""Тесты для S3 сервиса"""

import pytest
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import io

from src.services.s3_service import S3Service


class TestS3Service:
    """Тесты для S3Service"""
    
    @pytest.fixture
    def s3_service(self):
        """Фикстура S3 сервиса"""
        return S3Service()
    
    @pytest.fixture
    def test_image(self):
        """Тестовое изображение"""
        img = Image.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()
    
    @pytest.fixture
    def test_pil_image(self):
        """Тестовое PIL изображение"""
        return Image.new('RGB', (100, 100), color='blue')
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, s3_service):
        """Тест успешной проверки состояния"""
        
        with patch.object(s3_service.s3_client, 'list_buckets') as mock_list_buckets:
            with patch.object(s3_service, 'ensure_bucket_exists', return_value=True) as mock_ensure:
                
                result = await s3_service.health_check()
                
                assert result['success'] is True
                assert 'endpoint' in result
                assert 'bucket' in result
                assert result['bucket_exists'] is True
                
                mock_list_buckets.assert_called_once()
                mock_ensure.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, s3_service):
        """Тест неудачной проверки состояния"""
        
        with patch.object(s3_service.s3_client, 'list_buckets', side_effect=Exception("Connection failed")):
            
            result = await s3_service.health_check()
            
            assert result['success'] is False
            assert 'error' in result
            assert 'Connection failed' in result['error']
    
    @pytest.mark.asyncio
    async def test_upload_image_bytes(self, s3_service, test_image):
        """Тест загрузки изображения в формате bytes"""
        
        mock_put_object = MagicMock()
        
        with patch.object(s3_service, 'ensure_bucket_exists', return_value=True):
            with patch.object(s3_service.s3_client, 'put_object', mock_put_object):
                
                result = await s3_service.upload_image(
                    image_data=test_image,
                    filename="test.png",
                    folder="test"
                )
                
                assert result['success'] is True
                assert result['filename'] == "test.png"
                assert result['object_key'] == "test/test.png"
                assert 'url' in result
                assert result['size_bytes'] == len(test_image)
                
                mock_put_object.assert_called_once()
                call_args = mock_put_object.call_args
                assert call_args[1]['Key'] == "test/test.png"
                assert call_args[1]['ContentType'] == 'image/png'
    
    @pytest.mark.asyncio
    async def test_upload_image_pil(self, s3_service, test_pil_image):
        """Тест загрузки PIL изображения"""
        
        mock_put_object = MagicMock()
        
        with patch.object(s3_service, 'ensure_bucket_exists', return_value=True):
            with patch.object(s3_service.s3_client, 'put_object', mock_put_object):
                
                result = await s3_service.upload_image(
                    image_data=test_pil_image,
                    filename="test_pil.png",
                    folder="test"
                )
                
                assert result['success'] is True
                assert result['filename'] == "test_pil.png"
                assert result['object_key'] == "test/test_pil.png"
                
                mock_put_object.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_image_auto_filename(self, s3_service, test_image):
        """Тест загрузки с автоматическим именем файла"""
        
        mock_put_object = MagicMock()
        
        with patch.object(s3_service, 'ensure_bucket_exists', return_value=True):
            with patch.object(s3_service.s3_client, 'put_object', mock_put_object):
                
                result = await s3_service.upload_image(
                    image_data=test_image,
                    folder="test"
                )
                
                assert result['success'] is True
                assert result['filename'].startswith("image_")
                assert result['filename'].endswith(".png")
                assert result['object_key'].startswith("test/image_")
    
    @pytest.mark.asyncio
    async def test_upload_image_failure(self, s3_service, test_image):
        """Тест неудачной загрузки изображения"""
        
        with patch.object(s3_service, 'ensure_bucket_exists', return_value=True):
            with patch.object(s3_service.s3_client, 'put_object', side_effect=Exception("Upload failed")):
                
                result = await s3_service.upload_image(
                    image_data=test_image,
                    filename="test.png"
                )
                
                assert result['success'] is False
                assert 'error' in result
                assert 'Upload failed' in result['error']
    
    @pytest.mark.asyncio
    async def test_download_image_success(self, s3_service):
        """Тест успешного скачивания изображения"""
        
        test_data = b"fake image data"
        mock_response = {
            'Body': MagicMock(),
            'ContentType': 'image/png'
        }
        mock_response['Body'].read.return_value = test_data
        
        with patch.object(s3_service.s3_client, 'get_object', return_value=mock_response):
            
            result = await s3_service.download_image("test/image.png")
            
            assert result['success'] is True
            assert result['data'] == test_data
            assert result['content_type'] == 'image/png'
            assert result['size_bytes'] == len(test_data)
    
    @pytest.mark.asyncio
    async def test_download_image_failure(self, s3_service):
        """Тест неудачного скачивания изображения"""
        
        from botocore.exceptions import ClientError
        
        with patch.object(s3_service.s3_client, 'get_object', 
                         side_effect=ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')):
            
            result = await s3_service.download_image("test/nonexistent.png")
            
            assert result['success'] is False
            assert 'error' in result
    
    @pytest.mark.asyncio
    async def test_delete_image_success(self, s3_service):
        """Тест успешного удаления изображения"""
        
        with patch.object(s3_service.s3_client, 'delete_object') as mock_delete:
            
            result = await s3_service.delete_image("test/image.png")
            
            assert result['success'] is True
            assert result['object_key'] == "test/image.png"
            
            mock_delete.assert_called_once_with(
                Bucket=s3_service.bucket_name,
                Key="test/image.png"
            )
    
    @pytest.mark.asyncio
    async def test_delete_image_failure(self, s3_service):
        """Тест неудачного удаления изображения"""
        
        from botocore.exceptions import ClientError
        
        with patch.object(s3_service.s3_client, 'delete_object',
                         side_effect=ClientError({'Error': {'Code': 'NoSuchKey'}}, 'DeleteObject')):
            
            result = await s3_service.delete_image("test/nonexistent.png")
            
            assert result['success'] is False
            assert 'error' in result
    
    @pytest.mark.asyncio
    async def test_list_images_success(self, s3_service):
        """Тест успешного получения списка изображений"""
        
        mock_response = {
            'Contents': [
                {
                    'Key': 'images/img1.png',
                    'Size': 1024,
                    'LastModified': '2023-01-01T12:00:00Z'
                },
                {
                    'Key': 'images/img2.jpg', 
                    'Size': 2048,
                    'LastModified': '2023-01-02T12:00:00Z'
                }
            ]
        }
        
        with patch.object(s3_service.s3_client, 'list_objects_v2', return_value=mock_response):
            
            result = await s3_service.list_images("images", limit=10)
            
            assert result['success'] is True
            assert result['count'] == 2
            assert len(result['images']) == 2
            
            # Проверяем структуру первого изображения
            img1 = result['images'][0]
            assert img1['object_key'] == 'images/img1.png'
            assert img1['filename'] == 'img1.png'
            assert img1['size_bytes'] == 1024
            assert 'url' in img1
    
    @pytest.mark.asyncio
    async def test_list_images_empty(self, s3_service):
        """Тест получения пустого списка изображений"""
        
        mock_response = {'Contents': []}
        
        with patch.object(s3_service.s3_client, 'list_objects_v2', return_value=mock_response):
            
            result = await s3_service.list_images("empty_folder")
            
            assert result['success'] is True
            assert result['count'] == 0
            assert len(result['images']) == 0
    
    @pytest.mark.asyncio
    async def test_list_images_failure(self, s3_service):
        """Тест неудачного получения списка изображений"""
        
        from botocore.exceptions import ClientError
        
        with patch.object(s3_service.s3_client, 'list_objects_v2',
                         side_effect=ClientError({'Error': {'Code': 'AccessDenied'}}, 'ListObjectsV2')):
            
            result = await s3_service.list_images("images")
            
            assert result['success'] is False
            assert 'error' in result
    
    def test_get_image_url(self, s3_service):
        """Тест генерации URL изображения"""
        
        url = s3_service.get_image_url("test/image.png")
        
        assert url == f"{s3_service.endpoint_url}/{s3_service.bucket_name}/test/image.png"
    
    @pytest.mark.asyncio
    async def test_ensure_bucket_exists_bucket_exists(self, s3_service):
        """Тест когда bucket уже существует"""
        
        with patch.object(s3_service.s3_client, 'head_bucket') as mock_head:
            
            result = await s3_service.ensure_bucket_exists()
            
            assert result is True
            mock_head.assert_called_once_with(Bucket=s3_service.bucket_name)
    
    @pytest.mark.asyncio
    async def test_ensure_bucket_exists_create_bucket(self, s3_service):
        """Тест создания bucket когда он не существует"""
        
        from botocore.exceptions import ClientError
        
        # Первый вызов - bucket не существует
        # Второй вызов - bucket создан успешно
        with patch.object(s3_service.s3_client, 'head_bucket',
                         side_effect=ClientError({'Error': {'Code': '404'}}, 'HeadBucket')):
            with patch.object(s3_service.s3_client, 'create_bucket') as mock_create:
                
                result = await s3_service.ensure_bucket_exists()
                
                assert result is True
                mock_create.assert_called_once_with(Bucket=s3_service.bucket_name)
    
    @pytest.mark.asyncio
    async def test_ensure_bucket_exists_create_failure(self, s3_service):
        """Тест неудачного создания bucket"""
        
        from botocore.exceptions import ClientError
        
        with patch.object(s3_service.s3_client, 'head_bucket',
                         side_effect=ClientError({'Error': {'Code': '404'}}, 'HeadBucket')):
            with patch.object(s3_service.s3_client, 'create_bucket',
                             side_effect=ClientError({'Error': {'Code': 'BucketAlreadyExists'}}, 'CreateBucket')):
                
                result = await s3_service.ensure_bucket_exists()
                
                assert result is False


if __name__ == "__main__":
    pytest.main([__file__])
