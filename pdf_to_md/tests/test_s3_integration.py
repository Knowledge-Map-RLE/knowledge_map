"""Интеграционные тесты для S3 функционала"""

import pytest
import asyncio
import uuid
from pathlib import Path
from PIL import Image
import io

from src.services.s3_service import S3Service
from src.services.coordinate_extraction_service import CoordinateExtractionService


@pytest.mark.integration
class TestS3Integration:
    """Интеграционные тесты для S3"""
    
    @pytest.fixture(scope="class")
    def s3_service(self):
        """Фикстура S3 сервиса для интеграционных тестов"""
        return S3Service()
    
    @pytest.fixture(scope="class")
    def extraction_service(self):
        """Фикстура сервиса извлечения для интеграционных тестов"""
        return CoordinateExtractionService()
    
    @pytest.fixture
    def test_image(self):
        """Создание тестового изображения"""
        img = Image.new('RGB', (200, 100), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()
    
    @pytest.fixture
    def test_document_id(self):
        """Уникальный ID документа для тестов"""
        return f"test_doc_{uuid.uuid4().hex[:8]}"
    
    @pytest.mark.asyncio
    async def test_s3_health_check_real(self, s3_service):
        """Реальная проверка состояния S3"""
        
        result = await s3_service.health_check()
        
        # В зависимости от окружения, S3 может быть доступен или нет
        if result['success']:
            assert 'endpoint' in result
            assert 'bucket' in result
            print(f"S3 доступен: {result['endpoint']}")
        else:
            print(f"S3 недоступен: {result.get('error')}")
            pytest.skip("S3 сервис недоступен для интеграционных тестов")
    
    @pytest.mark.asyncio
    async def test_s3_bucket_operations_real(self, s3_service):
        """Реальные операции с bucket"""
        
        # Пропускаем если S3 недоступен
        health = await s3_service.health_check()
        if not health['success']:
            pytest.skip("S3 недоступен")
        
        # Проверяем/создаем bucket
        bucket_exists = await s3_service.ensure_bucket_exists()
        assert bucket_exists is True
    
    @pytest.mark.asyncio
    async def test_s3_image_upload_download_cycle_real(self, s3_service, test_image, test_document_id):
        """Реальный цикл загрузки-скачивания изображения"""
        
        # Пропускаем если S3 недоступен
        health = await s3_service.health_check()
        if not health['success']:
            pytest.skip("S3 недоступен")
        
        try:
            # Загружаем изображение
            upload_result = await s3_service.upload_image(
                image_data=test_image,
                filename=f"integration_test_{test_document_id}.png",
                folder=f"integration_tests/{test_document_id}"
            )
            
            assert upload_result['success'] is True
            assert 'object_key' in upload_result
            assert 'url' in upload_result
            
            object_key = upload_result['object_key']
            print(f"Загружено: {object_key}")
            
            # Скачиваем изображение
            download_result = await s3_service.download_image(object_key)
            
            assert download_result['success'] is True
            assert download_result['data'] == test_image
            assert download_result['size_bytes'] == len(test_image)
            
            print(f"Скачано: {len(download_result['data'])} байт")
            
            # Проверяем список изображений
            list_result = await s3_service.list_images(f"integration_tests/{test_document_id}")
            
            assert list_result['success'] is True
            assert list_result['count'] >= 1
            
            # Находим наше изображение в списке
            our_image = None
            for img in list_result['images']:
                if img['object_key'] == object_key:
                    our_image = img
                    break
            
            assert our_image is not None
            assert our_image['size_bytes'] == len(test_image)
            
            print(f"Найдено в списке: {our_image['filename']}")
            
        finally:
            # Удаляем тестовое изображение
            if 'object_key' in locals():
                delete_result = await s3_service.delete_image(object_key)
                if delete_result['success']:
                    print(f"Удалено: {object_key}")
                else:
                    print(f"Ошибка удаления: {delete_result.get('error')}")
    
    @pytest.mark.asyncio
    async def test_s3_document_image_management_real(self, extraction_service, test_document_id):
        """Реальные операции управления изображениями документа"""
        
        # Пропускаем если S3 недоступен
        health = await extraction_service.s3_service.health_check()
        if not health['success']:
            pytest.skip("S3 недоступен")
        
        try:
            # Создаем несколько тестовых изображений
            test_images = []
            for i in range(3):
                img = Image.new('RGB', (100, 50), color=['red', 'green', 'blue'][i])
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                
                upload_result = await extraction_service.s3_service.upload_image(
                    image_data=buffer.getvalue(),
                    filename=f"doc_img_{i}.png",
                    folder=f"documents/{test_document_id}/images"
                )
                
                assert upload_result['success'] is True
                test_images.append(upload_result['object_key'])
                
                print(f"Создано изображение {i}: {upload_result['object_key']}")
            
            # Получаем список изображений документа
            doc_images_result = await extraction_service.get_document_images(test_document_id)
            
            assert doc_images_result['success'] is True
            assert doc_images_result['count'] == 3
            assert doc_images_result['document_id'] == test_document_id
            
            print(f"Найдено {doc_images_result['count']} изображений документа")
            
            # Удаляем все изображения документа
            delete_result = await extraction_service.delete_document_images(test_document_id)
            
            assert delete_result['success'] is True
            assert delete_result['deleted_count'] == 3
            assert delete_result['total_count'] == 3
            
            print(f"Удалено {delete_result['deleted_count']} изображений")
            
            # Проверяем что изображения действительно удалены
            final_check = await extraction_service.get_document_images(test_document_id)
            assert final_check['count'] == 0
            
        except Exception as e:
            # В случае ошибки, пытаемся почистить за собой
            print(f"Ошибка в тесте: {e}")
            try:
                await extraction_service.delete_document_images(test_document_id)
            except:
                pass
            raise
    
    @pytest.mark.asyncio 
    async def test_s3_url_generation_real(self, s3_service, test_image, test_document_id):
        """Реальная проверка генерации URL"""
        
        health = await s3_service.health_check()
        if not health['success']:
            pytest.skip("S3 недоступен")
        
        try:
            # Загружаем изображение
            upload_result = await s3_service.upload_image(
                image_data=test_image,
                filename=f"url_test_{test_document_id}.png",
                folder="url_tests"
            )
            
            assert upload_result['success'] is True
            object_key = upload_result['object_key']
            
            # Проверяем URL
            generated_url = s3_service.get_image_url(object_key)
            expected_url = f"{s3_service.endpoint_url}/{s3_service.bucket_name}/{object_key}"
            
            assert generated_url == expected_url
            assert s3_service.bucket_name in generated_url
            assert object_key in generated_url
            
            print(f"URL сгенерирован: {generated_url}")
            
        finally:
            # Очистка
            if 'object_key' in locals():
                await s3_service.delete_image(object_key)
    
    @pytest.mark.asyncio
    async def test_s3_error_handling_real(self, s3_service):
        """Реальная проверка обработки ошибок"""
        
        health = await s3_service.health_check()
        if not health['success']:
            pytest.skip("S3 недоступен")
        
        # Пытаемся скачать несуществующий файл
        download_result = await s3_service.download_image("nonexistent/file.png")
        assert download_result['success'] is False
        assert 'error' in download_result
        
        # Пытаемся удалить несуществующий файл
        delete_result = await s3_service.delete_image("nonexistent/file.png")
        # В MinIO удаление несуществующего файла может быть успешным
        # так что просто проверяем что метод не упал
        assert 'success' in delete_result
        
        print("Обработка ошибок работает корректно")
    
    @pytest.mark.asyncio
    async def test_s3_concurrent_operations_real(self, s3_service, test_document_id):
        """Реальная проверка конкурентных операций"""
        
        health = await s3_service.health_check()
        if not health['success']:
            pytest.skip("S3 недоступен")
        
        # Создаем несколько изображений параллельно
        async def upload_test_image(index):
            img = Image.new('RGB', (50, 50), color=f"#{index:02d}{index:02d}{index:02d}")
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            
            return await s3_service.upload_image(
                image_data=buffer.getvalue(),
                filename=f"concurrent_{index}.png",
                folder=f"concurrent_tests/{test_document_id}"
            )
        
        try:
            # Запускаем 5 параллельных загрузок
            tasks = [upload_test_image(i) for i in range(5)]
            results = await asyncio.gather(*tasks)
            
            # Проверяем что все загрузки успешны
            successful_uploads = 0
            object_keys = []
            
            for result in results:
                if result['success']:
                    successful_uploads += 1
                    object_keys.append(result['object_key'])
                else:
                    print(f"Неудачная загрузка: {result.get('error')}")
            
            assert successful_uploads == 5
            print(f"Успешно загружено {successful_uploads} изображений параллельно")
            
            # Проверяем список
            list_result = await s3_service.list_images(f"concurrent_tests/{test_document_id}")
            assert list_result['success'] is True
            assert list_result['count'] == 5
            
        finally:
            # Очистка
            try:
                if 'object_keys' in locals():
                    delete_tasks = [s3_service.delete_image(key) for key in object_keys]
                    await asyncio.gather(*delete_tasks, return_exceptions=True)
            except:
                pass


if __name__ == "__main__":
    # Запуск только интеграционных тестов
    pytest.main([__file__, "-m", "integration", "-v"])
