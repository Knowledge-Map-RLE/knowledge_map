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
    
    def CalculateLayout(self, request: layout_pb2.LayoutRequest, context: grpc.ServicerContext) -> layout_pb2.LayoutResponse:
        """
        Основной метод для расчета укладки графа.
        """
        start_time = time.time()
        
        # Логируем входные данные
        logger.info(f"🔥 === ПОЛУЧЕН ЗАПРОС НА УКЛАДКУ - НОВАЯ ВЕРСИЯ СЕРВИСА! ===")
        logger.info(f"Количество блоков: {len(request.blocks)}")
        logger.info(f"Количество связей: {len(request.links)}")
        
        # Проверяем закреплённые блоки
        pinned_blocks = [b for b in request.blocks if b.is_pinned]
        logger.info(f"🔥 ЗАКРЕПЛЁННЫХ БЛОКОВ В ЗАПРОСЕ: {len(pinned_blocks)} из {len(request.blocks)}")
        

        
        try:
            # Извлекаем блоки и связи из запроса
            blocks_data = {
                block.id: {
                    "is_pinned": block.is_pinned,
                    "level": getattr(block, 'level', 0),  # Передаем уровень если поле существует
                    "physical_scale": getattr(block, 'physical_scale', 0)  # Передаем физический масштаб
                } 
                for block in request.blocks
            }
            blocks = list(blocks_data.keys())
            links = [(link.source_id, link.target_id) for link in request.links]
            
            # КРИТИЧЕСКОЕ ЛОГИРОВАНИЕ
            logger.info(f"🔥 ДЕТАЛИ BLOCKS_DATA:")
            for block_id, data in blocks_data.items():
                if data['is_pinned']:
                    logger.info(f"   🔥 PINNED: {block_id[:8]}... level={data['level']}, is_pinned={data['is_pinned']}")
                    
            pinned_count_check = sum(1 for data in blocks_data.values() if data['is_pinned'])
            logger.info(f"🔥 ПОДСЧЁТ ЗАКРЕПЛЁННЫХ В BLOCKS_DATA: {pinned_count_check}")
            
            # Собираем опции укладки
            options = {
                'max_layers': request.options.max_layers if request.options.max_layers > 0 else None,
                'max_levels': request.options.max_levels if request.options.max_levels > 0 else None,
                'blocks_per_sublevel': request.options.blocks_per_sublevel if request.options.blocks_per_sublevel > 0 else None,
                'optimize_layout': request.options.optimize_layout,
                'blocks_data': blocks_data
            }
            
            logger.info(f"Опции укладки: {options}")
            logger.info(f"Закрепленные блоки: {[bid for bid, data in blocks_data.items() if data['is_pinned']]}")
                        
            # Выполняем укладку
            result = layout_knowledge_map(blocks, links, options)
            
            # КРИТИЧЕСКОЕ ЛОГИРОВАНИЕ РЕЗУЛЬТАТА
            logger.info(f"🔥 РЕЗУЛЬТАТ АЛГОРИТМА:")
            logger.info(f"   Levels structure: {result.get('levels', {})}")
            logger.info(f"   Sublevels structure: {result.get('sublevels', {})}")
            
            # Проверяем где оказались закреплённые блоки
            pinned_block_ids = [bid for bid, data in blocks_data.items() if data['is_pinned']]
            if pinned_block_ids:
                logger.info(f"🔥 ГДЕ ОКАЗАЛИСЬ ЗАКРЕПЛЁННЫЕ БЛОКИ:")
                for block_id in pinned_block_ids:
                    # Найти уровень и подуровень этого блока в результате
                    found_level = None
                    found_sublevel = None
                    for level_id, sublevel_ids in result.get('levels', {}).items():
                        for sublevel_id in sublevel_ids:
                            if block_id in result.get('sublevels', {}).get(sublevel_id, []):
                                found_level = level_id
                                found_sublevel = sublevel_id
                                break
                        if found_level is not None:
                            break
                    logger.info(f"   🔥 {block_id[:8]}... -> уровень {found_level}, подуровень {found_sublevel}")
            
            # Создаем ответ
            response = layout_pb2.LayoutResponse()
            
            # Добавляем блоки с позициями
            for block_id in result['layers'].keys():
                block_data = next(b for b in request.blocks if b.id == block_id)
                block = response.blocks.add()
                block.id = block_id
                block.content = block_data.content
                block.layer = result['layers'][block_id]
                block.is_pinned = block_data.is_pinned
                block.physical_scale = getattr(block_data, 'physical_scale', 0)  # Добавляем физический масштаб
                
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
                
                sublevel.block_ids.extend(block_ids)
                sublevel.color = self._get_sublevel_color(sublevel_id)
            
            # Добавляем статистику
            response.statistics.total_blocks = result['statistics']['total_blocks']
            response.statistics.total_links = result['statistics']['total_links']
            response.statistics.total_levels = result['statistics']['total_levels']
            response.statistics.total_sublevels = result['statistics']['total_sublevels']
            response.statistics.max_layer = result['statistics']['max_layer']
            response.statistics.processing_time_ms = int((time.time() - start_time) * 1000)
            response.statistics.is_acyclic = result['statistics']['is_acyclic']
            response.statistics.isolated_blocks = result['statistics']['isolated_blocks']

            response.success = True
            
            logger.info(f"=== УКЛАДКА ЗАВЕРШЕНА за {response.statistics.processing_time_ms}мс ===")
            
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
    logger.info("Настройка сервера")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    
    layout_pb2_grpc.add_LayoutServiceServicer_to_server(LayoutService(), server)
    
    server_address = f"{host}:{port}"
    server.add_insecure_port(server_address)
    server.start()
    
    logger.info(f"Сервер запущен на {server_address}")
    server.wait_for_termination()