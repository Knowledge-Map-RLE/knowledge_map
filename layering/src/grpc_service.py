"""
gRPC сервис для укладки графа карты знаний.
"""

import logging
import time
from concurrent import futures
from typing import Dict, List, Tuple

import grpc
from generated import layout_pb2, layout_pb2_grpc
from layout_algorithm import layout_knowledge_map

logger = logging.getLogger(__name__)

class LayoutService(layout_pb2_grpc.LayoutServiceServicer):
    """Реализация gRPC сервиса укладки графа"""
    
    def CalculateLayout(self, request: layout_pb2.LayoutRequest, 
                       context: grpc.ServicerContext) -> layout_pb2.LayoutResponse:
        """
        Основной метод для расчета укладки графа.
        """
        start_time = time.time()
        
        try:
            # Извлекаем блоки и связи из запроса
            blocks = [block.id for block in request.blocks]
            links = [(link.source_id, link.target_id) for link in request.links]
            
            # Собираем опции укладки
            options = {
                'max_layers': request.options.max_layers if request.options.max_layers > 0 else None,
                'max_levels': request.options.max_levels if request.options.max_levels > 0 else None,
                'blocks_per_sublevel': request.options.blocks_per_sublevel if request.options.blocks_per_sublevel > 0 else None,
                'optimize_layout': request.options.optimize_layout,
                'sublevel_spacing': request.options.sublevel_spacing,
                'layer_spacing': request.options.layer_spacing
            }
            
            # Выполняем укладку
            result = layout_knowledge_map(blocks, links, options)
            
            # Создаем ответ
            response = layout_pb2.LayoutResponse()
            
            # Добавляем блоки с позициями
            for block_id, (x, y) in result['positions'].items():
                block_data = next(b for b in request.blocks if b.id == block_id)
                block = response.blocks.add()
                block.id = block_id
                block.content = block_data.content
                block.x = float(x)
                block.y = float(y)
                block.layer = result['layers'][block_id]
                
                # Находим уровень и подуровень для блока
                for level_id, sublevel_ids in result['levels'].items():
                    for sublevel_id in sublevel_ids:
                        if block_id in result['sublevels'][sublevel_id]:
                            block.level = level_id
                            block.sublevel_id = sublevel_id
                            break
                
                block.metadata.update(block_data.metadata)
            
            # Добавляем уровни
            for level_id, sublevel_ids in result['levels'].items():
                level = response.levels.add()
                level.id = level_id
                level.sublevel_ids.extend(sublevel_ids)
                
                # Вычисляем границы уровня
                blocks_in_level = []
                for sublevel_id in sublevel_ids:
                    blocks_in_level.extend(result['sublevels'][sublevel_id])
                
                if blocks_in_level:
                    positions = [result['positions'][block_id] for block_id in blocks_in_level]
                    level.min_x = min(x for x, _ in positions) - options['layer_spacing'] / 2
                    level.max_x = max(x for x, _ in positions) + options['layer_spacing'] / 2
                    level.min_y = min(y for _, y in positions) - options['sublevel_spacing'] / 2
                    level.max_y = max(y for _, y in positions) + options['sublevel_spacing'] / 2
                
                level.name = f"Уровень {level_id}"
                level.color = self._get_level_color(level_id)
            
            # Добавляем подуровни
            for sublevel_id, block_ids in result['sublevels'].items():
                sublevel = response.sublevels.add()
                sublevel.id = sublevel_id
                
                # Находим уровень для подуровня
                for level_id, sublevel_ids in result['levels'].items():
                    if sublevel_id in sublevel_ids:
                        sublevel.level_id = level_id
                        break
                
                # Вычисляем координаты подуровня
                if block_ids:
                    positions = [result['positions'][block_id] for block_id in block_ids]
                    sublevel.y = positions[0][1]  # Все блоки на одном подуровне имеют одинаковую y координату
                    sublevel.min_x = min(x for x, _ in positions) - options['layer_spacing'] / 2
                    sublevel.max_x = max(x for x, _ in positions) + options['layer_spacing'] / 2
                    sublevel.height = options['sublevel_spacing'] * 0.8
                
                sublevel.block_ids.extend(block_ids)
                sublevel.color = self._get_sublevel_color(sublevel_id)
            
            # Добавляем статистику
            response.statistics.total_blocks = result['statistics']['total_blocks']
            response.statistics.total_links = result['statistics']['total_links']
            response.statistics.total_levels = result['statistics']['total_levels']
            response.statistics.total_sublevels = result['statistics']['total_sublevels']
            response.statistics.max_layer = result['statistics']['max_layer']
            response.statistics.total_width = result['statistics']['total_width']
            response.statistics.total_height = result['statistics']['total_height']
            response.statistics.processing_time_ms = int((time.time() - start_time) * 1000)
            response.statistics.is_acyclic = result['statistics']['is_acyclic']
            response.statistics.isolated_blocks = result['statistics']['isolated_blocks']
            
            response.success = True
            return response
            
        except Exception as e:
            logger.exception("Ошибка при расчете укладки")
            response = layout_pb2.LayoutResponse()
            response.success = False
            response.error_message = str(e)
            response.statistics.processing_time_ms = int((time.time() - start_time) * 1000)
            return response
    
    def HealthCheck(self, request: layout_pb2.HealthCheckRequest, 
                   context: grpc.ServicerContext) -> layout_pb2.HealthCheckResponse:
        """
        Проверка здоровья сервиса.
        """
        response = layout_pb2.HealthCheckResponse()
        response.status = layout_pb2.HealthCheckResponse.SERVING
        response.message = "Service is healthy"
        return response
    
    def _get_level_color(self, level_id: int) -> int:
        """Возвращает цвет для уровня в формате RGB int."""
        colors = [
            0xB0C4DE,  # lightsteelblue
            0x20B2AA,  # lightseagreen
            0xFA8072,  # lightsalmon
            0xFAFAD2,  # lightgoldenrodyellow
            0xDDA0DD,  # plum
            0xD3D3D3,  # lightgray
            0xE0FFFF,  # lightcyan
            0xE6E6FA,  # lavender
        ]
        return colors[level_id % len(colors)]
    
    def _get_sublevel_color(self, sublevel_id: int) -> int:
        """Возвращает цвет для подуровня в формате RGB int."""
        colors = [
            0xADD8E6,  # lightblue
            0x90EE90,  # lightgreen
            0xF08080,  # lightcoral
            0xFFFFE0,  # lightyellow
            0xFFB6C1,  # lightpink
            0xD3D3D3,  # lightgray
            0xE0FFFF,  # lightcyan
            0xE6E6FA,  # lavender
            0xFFE4E1,  # mistyrose
            0xF0FFF0,  # honeydew
        ]
        return colors[sublevel_id % len(colors)]


def run_server(host: str = '0.0.0.0', port: int = 50051, max_workers: int = 10) -> None:
    """
    Запускает gRPC сервер.
    
    Args:
        host: Хост для прослушивания
        port: Порт для прослушивания
        max_workers: Максимальное количество рабочих потоков
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    layout_pb2_grpc.add_LayoutServiceServicer_to_server(LayoutService(), server)
    
    server_address = f"{host}:{port}"
    server.add_insecure_port(server_address)
    server.start()
    
    logger.info(f"Сервер запущен на {server_address}")
    server.wait_for_termination()