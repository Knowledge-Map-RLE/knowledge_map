#!/usr/bin/env python3
"""
Пример интеграции Python сервисов с Rust микросервисом через gRPC

Этот скрипт демонстрирует как заменить Python + Neo4j укладку
на высокопроизводительный Rust сервис.
"""

import asyncio
import grpc
import logging
import time
from typing import List, Dict, Any

# Импорт сгенерированных protobuf классов
# В реальном проекте эти файлы будут сгенерированы из proto/graph_layout.proto
# import graph_layout_pb2
# import graph_layout_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RustLayoutIntegration:
    """Интеграция с Rust микросервисом укладки графов"""
    
    def __init__(self, grpc_endpoint: str = "localhost:50051"):
        self.grpc_endpoint = grpc_endpoint
        self.channel = None
        self.client = None
    
    async def connect(self):
        """Подключение к Rust gRPC сервису"""
        logger.info(f"🔌 Подключение к Rust сервису на {self.grpc_endpoint}")
        
        self.channel = grpc.aio.insecure_channel(self.grpc_endpoint)
        # self.client = graph_layout_pb2_grpc.GraphLayoutServiceStub(self.channel)
        
        # Проверка здоровья сервиса
        await self.health_check()
    
    async def health_check(self):
        """Проверка здоровья Rust сервиса"""
        try:
            # В реальной реализации:
            # request = graph_layout_pb2.HealthRequest(service="graph_layout")
            # response = await self.client.GetHealth(request)
            
            logger.info("✅ Rust сервис работает нормально")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Rust сервису: {e}")
            return False
    
    async def compute_layout_rust(
        self, 
        task_id: str,
        edges: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Вычисление укладки через Rust сервис
        
        Args:
            task_id: Идентификатор задачи
            edges: Список связей (если None, загружается из Neo4j)
        
        Returns:
            Результат укладки с позициями вершин
        """
        logger.info(f"🦀 Запуск Rust укладки (задача: {task_id})")
        start_time = time.time()
        
        try:
            # В реальной реализации:
            # 
            # # Подготовка запроса
            # graph_edges = []
            # if edges:
            #     for edge in edges:
            #         graph_edges.append(graph_layout_pb2.GraphEdge(
            #             source_id=edge['source_id'],
            #             target_id=edge['target_id'],
            #             weight=edge.get('weight', 1.0),
            #             edge_type=edge.get('edge_type', 'BIBLIOGRAPHIC_LINK')
            #         ))
            # 
            # options = graph_layout_pb2.LayoutOptions(
            #     block_width=200.0,
            #     block_height=80.0,
            #     horizontal_gap=40.0,
            #     vertical_gap=50.0,
            #     exclude_isolated_vertices=True,
            #     enable_simd=True,
            #     max_workers=4,
            #     chunk_size=10000
            # )
            # 
            # request = graph_layout_pb2.LayoutRequest(
            #     task_id=task_id,
            #     edges=graph_edges,
            #     options=options
            # )
            # 
            # # Выполнение укладки
            # response = await self.client.ComputeLayout(request)
            # 
            # if not response.success:
            #     raise Exception(f"Rust укладка не удалась: {response.error_message}")
            # 
            # # Конвертация результата
            # positions = []
            # for pos in response.positions:
            #     positions.append({
            #         'article_id': pos.article_id,
            #         'layer': pos.layer,
            #         'level': pos.level,
            #         'x': pos.x,
            #         'y': pos.y,
            #         'status': pos.status
            #     })
            
            # Заглушка для демонстрации
            positions = [
                {
                    'article_id': f'article_{i}',
                    'layer': i % 5,
                    'level': i // 5,
                    'x': (i % 5) * 240.0,
                    'y': (i // 5) * 130.0,
                    'status': 'placed'
                }
                for i in range(100)
            ]
            
            processing_time = time.time() - start_time
            
            result = {
                'success': True,
                'positions': positions,
                'statistics': {
                    'processing_time_seconds': processing_time,
                    'vertices_processed': len(positions),
                    'algorithm_version': 'rust-0.1.0',
                },
                'metadata': {
                    'server_id': 'rust-server-1',
                    'optimizations_used': ['SIMD', 'Parallel Processing'],
                }
            }
            
            logger.info(
                f"✅ Rust укладка завершена за {processing_time:.2f}с "
                f"({len(positions)} позиций)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка Rust укладки: {e}")
            return {
                'success': False,
                'error': str(e),
                'positions': [],
                'statistics': {
                    'processing_time_seconds': time.time() - start_time,
                }
            }
    
    async def compute_layout_streaming(self, task_id: str):
        """Потоковая укладка для больших графов"""
        logger.info(f"🌊 Запуск потоковой Rust укладки (задача: {task_id})")
        
        # В реальной реализации:
        # request = graph_layout_pb2.LayoutRequest(task_id=task_id, ...)
        # async for chunk in self.client.ComputeLayoutStreaming(request):
        #     yield {
        #         'chunk_id': chunk.chunk_id,
        #         'progress': chunk.progress,
        #         'positions': [pos for pos in chunk.positions],
        #         'is_final': chunk.is_final
        #     }
        
        # Заглушка
        for i in range(5):
            await asyncio.sleep(0.1)
            yield {
                'chunk_id': i,
                'progress': (i + 1) / 5.0,
                'positions': [f'chunk_{i}_position_{j}' for j in range(10)],
                'is_final': i == 4
            }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик производительности"""
        try:
            # request = graph_layout_pb2.MetricsRequest()
            # response = await self.client.GetMetrics(request)
            
            # Заглушка
            return {
                'requests_total': 150,
                'requests_success': 145,
                'requests_failed': 5,
                'avg_processing_time': 2.5,
                'memory_usage_mb': 512,
                'cpu_usage_percent': 45.0,
                'vertices_per_second': 2500.0
            }
        except Exception as e:
            logger.error(f"Ошибка получения метрик: {e}")
            return {}
    
    async def close(self):
        """Закрытие соединения"""
        if self.channel:
            await self.channel.close()


async def compare_python_vs_rust():
    """Сравнение производительности Python vs Rust укладки"""
    logger.info("📊 Сравнение производительности Python vs Rust")
    
    rust_integration = RustLayoutIntegration()
    await rust_integration.connect()
    
    # Тест производительности
    test_cases = [
        {"name": "Маленький граф", "vertex_count": 100},
        {"name": "Средний граф", "vertex_count": 1000},
        {"name": "Большой граф", "vertex_count": 10000},
    ]
    
    for test_case in test_cases:
        logger.info(f"🧪 Тестирование: {test_case['name']}")
        
        # Симуляция Python укладки
        python_start = time.time()
        await asyncio.sleep(0.5)  # Имитация работы Python
        python_time = time.time() - python_start
        
        # Rust укладка
        rust_result = await rust_integration.compute_layout_rust(
            task_id=f"test_{test_case['name'].lower().replace(' ', '_')}"
        )
        rust_time = rust_result['statistics']['processing_time_seconds']
        
        speedup = python_time / rust_time if rust_time > 0 else float('inf')
        
        logger.info(f"  Python: {python_time:.3f}с")
        logger.info(f"  Rust:   {rust_time:.3f}с")
        logger.info(f"  Ускорение: {speedup:.1f}x")
        logger.info(f"  Успех: {'✅' if rust_result['success'] else '❌'}")
    
    await rust_integration.close()


async def integration_example():
    """Пример полной интеграции с заменой Python воркера"""
    logger.info("🔄 Пример интеграции Rust микросервиса")
    
    rust_integration = RustLayoutIntegration()
    await rust_integration.connect()
    
    # 1. Проверка здоровья
    health_ok = await rust_integration.health_check()
    if not health_ok:
        logger.error("❌ Rust сервис недоступен")
        return
    
    # 2. Получение метрик
    metrics = await rust_integration.get_metrics()
    logger.info(f"📈 Метрики сервиса: {metrics}")
    
    # 3. Вычисление укладки
    result = await rust_integration.compute_layout_rust(
        task_id="integration_test",
        edges=None  # Загрузится из Neo4j
    )
    
    if result['success']:
        logger.info(f"✅ Укладка успешна: {len(result['positions'])} позиций")
        logger.info(f"📊 Статистика: {result['statistics']}")
    else:
        logger.error(f"❌ Ошибка укладки: {result.get('error', 'Unknown')}")
    
    # 4. Потоковая обработка (для больших графов)
    logger.info("🌊 Тестирование потоковой обработки")
    async for chunk in rust_integration.compute_layout_streaming("streaming_test"):
        logger.info(f"  Чанк {chunk['chunk_id']}: {chunk['progress']*100:.1f}%")
        if chunk['is_final']:
            logger.info("  ✅ Потоковая обработка завершена")
    
    await rust_integration.close()


async def main():
    """Главная функция для демонстрации интеграции"""
    logger.info("🚀 Демонстрация интеграции Python ↔ Rust")
    
    try:
        await integration_example()
        logger.info("\n" + "="*50)
        await compare_python_vs_rust()
        
        logger.info("\n🎉 Демонстрация завершена успешно!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка демонстрации: {e}")


if __name__ == "__main__":
    asyncio.run(main())
