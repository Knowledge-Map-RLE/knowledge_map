"""Tests for S3 client functionality"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

try:
    from src.services.s3_client import AsyncS3Client, S3Config, get_s3_client
except ImportError:
    from pdf_to_md.src.services.s3_client import AsyncS3Client, S3Config, get_s3_client


class TestS3Config:
    """Test S3 configuration"""
    
    def test_s3_config_defaults(self):
        """Test S3 config with default values"""
        config = S3Config()
        
        assert config.endpoint_url == "http://localhost:9000"
        assert config.access_key == "minio"
        assert config.secret_key == "minio123456"
        assert config.region == "us-east-1"
        assert config.bucket_name == "knowledge-map"
    
    def test_s3_config_boto3_config(self):
        """Test boto3 config generation"""
        config = S3Config()
        boto_config = config.get_boto3_config()
        
        assert "endpoint_url" in boto_config
        assert "aws_access_key_id" in boto_config
        assert "aws_secret_access_key" in boto_config
        assert "region_name" in boto_config


class TestAsyncS3Client:
    """Test AsyncS3Client"""
    
    @pytest.fixture
    def s3_client(self):
        """Create S3 client for testing"""
        config = S3Config()
        return AsyncS3Client(config)
    
    @pytest.fixture
    def mock_s3_session(self):
        """Mock aioboto3 session"""
        with patch('aioboto3.Session') as mock:
            yield mock
    
    def test_init(self, s3_client):
        """Test S3 client initialization"""
        assert s3_client.config is not None
        assert s3_client.session is not None
    
    @pytest.mark.asyncio
    async def test_ensure_bucket_exists_already_exists(self, s3_client, mock_s3_session):
        """Test bucket already exists"""
        mock_client = AsyncMock()
        mock_client.head_bucket = AsyncMock()
        mock_s3_session.return_value.client.return_value.__aenter__.return_value = mock_client
        
        result = await s3_client.ensure_bucket_exists("test-bucket")
        assert result is True
        mock_client.head_bucket.assert_called_once_with(Bucket="test-bucket")
    
    @pytest.mark.asyncio
    async def test_upload_bytes_success(self, s3_client, mock_s3_session):
        """Test successful bytes upload"""
        mock_client = AsyncMock()
        mock_client.put_object = AsyncMock()
        mock_client.head_bucket = AsyncMock()
        mock_s3_session.return_value.client.return_value.__aenter__.return_value = mock_client
        
        test_data = b"test image data"
        result = await s3_client.upload_bytes(
            data=test_data,
            bucket_name="test-bucket",
            object_key="test.jpg",
            content_type="image/jpeg"
        )
        
        assert result is True
        mock_client.put_object.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_download_bytes_success(self, s3_client, mock_s3_session):
        """Test successful bytes download"""
        test_data = b"test image data"
        mock_stream = AsyncMock()
        mock_stream.read = AsyncMock(return_value=test_data)
        
        mock_response = {"Body": mock_stream}
        mock_client = AsyncMock()
        mock_client.get_object = AsyncMock(return_value=mock_response)
        mock_s3_session.return_value.client.return_value.__aenter__.return_value = mock_client
        
        result = await s3_client.download_bytes("test-bucket", "test.jpg")
        
        assert result == test_data
        mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="test.jpg")
    
    @pytest.mark.asyncio
    async def test_object_exists_true(self, s3_client, mock_s3_session):
        """Test object exists check returns True"""
        mock_client = AsyncMock()
        mock_client.head_object = AsyncMock()
        mock_s3_session.return_value.client.return_value.__aenter__.return_value = mock_client
        
        result = await s3_client.object_exists("test-bucket", "test.jpg")
        
        assert result is True
        mock_client.head_object.assert_called_once_with(Bucket="test-bucket", Key="test.jpg")
    
    @pytest.mark.asyncio
    async def test_list_objects_success(self, s3_client, mock_s3_session):
        """Test successful object listing"""
        mock_contents = [
            {"Key": "documents/doc1/image1.jpg", "Size": 1024},
            {"Key": "documents/doc1/image2.png", "Size": 2048}
        ]
        mock_response = {"Contents": mock_contents}
        
        mock_client = AsyncMock()
        mock_client.list_objects_v2 = AsyncMock(return_value=mock_response)
        mock_s3_session.return_value.client.return_value.__aenter__.return_value = mock_client
        
        result = await s3_client.list_objects("test-bucket", "documents/doc1/")
        
        assert result == mock_contents
        mock_client.list_objects_v2.assert_called_once_with(Bucket="test-bucket", Prefix="documents/doc1/")
    
    @pytest.mark.asyncio
    async def test_get_object_url_success(self, s3_client, mock_s3_session):
        """Test presigned URL generation"""
        test_url = "https://example.com/presigned-url"
        
        mock_client = AsyncMock()
        mock_client.generate_presigned_url = AsyncMock(return_value=test_url)
        mock_s3_session.return_value.client.return_value.__aenter__.return_value = mock_client
        
        result = await s3_client.get_object_url("test-bucket", "test.jpg", 3600)
        
        assert result == test_url
        mock_client.generate_presigned_url.assert_called_once()


def test_get_s3_client_singleton():
    """Test S3 client singleton pattern"""
    client1 = get_s3_client()
    client2 = get_s3_client()
    
    assert client1 is client2
