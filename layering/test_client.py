"""
Тестовый gRPC клиент для проверки работы микросервиса укладки графа.
"""

import sys
from pathlib import Path

# Добавляем путь к src
sys.path.insert(0, str(Path(__file__).parent / "src"))

import grpc
from generated import layout_pb2, layout_pb2_grpc


def test_grpc_service(host: str = 'localhost', port: int = 50051):
    """Тестирует gRPC сервис с тестовыми данными из km_hand_layout.py"""
    
    print("🔧 Тестирование gRPC сервиса укладки графа...")
    
    # Тестовые данные из km_hand_layout.py
    test_links = [
        (0, 11), (0, 16), (0, 7), (1, 19), (1, 17), (1, 9), (1, 7), 
        (2, 8), (2, 11), (2, 18), (2, 19), (2, 9), (2, 12), (3, 10), 
        (3, 18), (3, 19), (4, 19), (5, 6), (5, 7), (5, 9), (6, 14), 
        (6, 9), (7, 8), (7, 10), (7, 9), (7, 12), (8, 15), (8, 10), 
        (9, 16), (9, 10), (12, 18), (12, 19), (13, 14), (15, 19), 
        (15, 17), (16, 13), (17, 12), (17, 11), (19, 16)
    ]
    
    test_blocks = list(range(20))  # Блоки 0-19
    
    try:
        # Создаем gRPC канал
        channel = grpc.insecure_channel(f'{host}:{port}')
        stub = layout_pb2_grpc.LayoutServiceStub(channel)
        
        # Проверяем здоровье сервиса
        print("🏥 Проверка здоровья сервиса...")
        health_request = layout_pb2.HealthCheckRequest(service="layout")
        health_response = stub.HealthCheck(health_request)
        
        if health_response.status != layout_pb2.HealthCheckResponse.SERVING:
            print(f"❌ Сервис не готов: {health_response.message}")
            return False
        
        print("✅ Сервис работает нормально")
        
        # Создаем запрос на укладку
        request = layout_pb2.LayoutRequest()
        
        # Добавляем блоки
        for block_id in test_blocks:
            block = request.blocks.add()
            block.id = str(block_id)
            block.content = f"Блок {block_id}"
            block.metadata["type"] = "test_block"
        
        # Добавляем связи
        for i, (source, target) in enumerate(test_links):
            link = request.links.add()
            link.id = f"link_{i}"
            link.source_id = str(source)
            link.target_id = str(target)
            link.metadata["type"] = "test_link"
        
        # Настраиваем опции
        request.options.sublevel_spacing = 150
        request.options.layer_spacing = 200
        request.options.optimize_layout = True
        
        # Отправляем запрос
        print(f"📊 Отправка запроса: {len(request.blocks)} блоков, {len(request.links)} связей")
        response = stub.CalculateLayout(request)
        
        if response.success:
            print("✅ Укладка успешно завершена!")
            print(f"⏱️  Время выполнения: {response.statistics.processing_time_ms}мс")
            print(f"📏 Размеры графа: {response.statistics.total_width:.1f} × {response.statistics.total_height:.1f} пикселей")
            print(f"🏗️ Структура: {response.statistics.total_levels} уровней, {response.statistics.total_sublevels} подуровней")
            print(f"📈 Максимальный слой: {response.statistics.max_layer}")
            print(f"🔗 Граф ациклический: {'Да' if response.statistics.is_acyclic else 'Нет'}")
            print(f"🏝️ Изолированные блоки: {response.statistics.isolated_blocks}")
            
            print("\n📍 Первые 5 блоков с позициями:")
            for block in response.blocks[:5]:
                print(f"  {block.id}: ({block.x:.0f}, {block.y:.0f}) "
                      f"слой={block.layer}, уровень={block.level}, подуровень={block.sublevel_id}")
            
            return True
        else:
            print(f"❌ Ошибка укладки: {response.error_message}")
            return False
            
    except grpc.RpcError as e:
        print(f"❌ Ошибка gRPC: {e.details() if hasattr(e, 'details') else str(e)}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {str(e)}")
        return False


if __name__ == "__main__":
    print("🧪 Запуск тестов gRPC сервиса укладки графа\n")
    
    # Запускаем тест
    success = test_grpc_service()
    
    print("\n🎉 Тест завершен!")
    
    if not success:
        print("\n💡 Подсказка: Убедитесь что:")
        print("   1. Сгенерированы protobuf файлы: scripts\\generate_proto.bat")
        print("   2. Запущен сервер: poetry run start-layout-service")
        print("   3. Сервер доступен по адресу localhost:50051")