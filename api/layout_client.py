"""
gRPC клиент для взаимодействия с микросервисом укладки графа.
"""
import os
import asyncio
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

import grpc
import sys
from pathlib import Path

# Добавляем путь к generated в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent / "generated"))

from generated import layout_pb2, layout_pb2_grpc

logger = logging.getLogger(__name__)

@dataclass
class LayoutConfig:
    """Конфигурация подключения к сервису укладки"""
    host: str = "localhost"
    port: int = 50051
    timeout: int = 30  # секунды
    
    @classmethod
    def from_env(cls):
        """Создает конфигурацию из переменных окружения"""
        return cls(
            host=os.getenv("LAYOUT_SERVICE_HOST", "localhost"),
            port=int(os.getenv("LAYOUT_SERVICE_PORT", "50051")),
            timeout=int(os.getenv("LAYOUT_SERVICE_TIMEOUT", "30"))
        )


@dataclass
class LayoutOptions:
    """Опции для алгоритма укладки"""
    sublevel_spacing: int = 200
    layer_spacing: int = 250
    optimize_layout: bool = True
    # УБИРАЕМ: blocks_per_sublevel больше не используется


class LayoutClient:
    """gRPC клиент для микросервиса укладки графа"""
    
    def __init__(self, config: LayoutConfig = None):
        self.config = config or LayoutConfig()
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[layout_pb2_grpc.LayoutServiceStub] = None
    
    async def connect(self):
        """Устанавливает соединение с gRPC сервисом"""
        if self._channel is None:
            address = f"{self.config.host}:{self.config.port}"
            self._channel = grpc.aio.insecure_channel(address)
            self._stub = layout_pb2_grpc.LayoutServiceStub(self._channel)
            logger.info(f"Подключение к Layout Service: {address}")
    
    async def disconnect(self):
        """Закрывает соединение"""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("Отключение от Layout Service")
    
    async def health_check(self) -> bool:
        """Проверяет здоровье сервиса"""
        try:
            await self.connect()
            
            request = layout_pb2.HealthCheckRequest()
            request.service = "layout"
            
            response = await self._stub.HealthCheck(
                request, 
                timeout=self.config.timeout
            )
            
            is_healthy = response.status == layout_pb2.HealthCheckResponse.ServingStatus.SERVING
            logger.info(f"Health check: {'OK' if is_healthy else 'FAIL'} - {response.message}")
            return is_healthy
            
        except grpc.aio.AioRpcError as e:
            logger.error(f"Health check failed: {e.code()} - {e.details()}")
            return False
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return False
    
    async def calculate_layout(
        self, 
        blocks: List[Dict], 
        links: List[Dict], 
        options: LayoutOptions = None
    ) -> Dict:
        """
        Рассчитывает укладку графа
        
        Args:
            blocks: Список блоков [{"id": str, "content": str, "metadata": dict}, ...]
            links: Список связей [{"id": str, "source_id": str, "target_id": str, "metadata": dict}, ...]
            options: Опции алгоритма укладки
        
        Returns:
            Dict с результатом укладки или ошибкой
        """
        try:
            await self.connect()
            
            logger.info(f"Отправка запроса на укладку: {len(blocks)} блоков, {len(links)} связей")
            
            # Создаем gRPC запрос
            request = layout_pb2.LayoutRequest()
            
            # Добавляем блоки
            for block in blocks:
                grpc_block = request.blocks.add()
                grpc_block.id = block["id"]
                grpc_block.content = block["content"]
                grpc_block.is_pinned = block.get("is_pinned", False)
                grpc_block.level = block.get("level", 0)  # Передаем уровень блока
                grpc_block.physical_scale = block.get("physical_scale", 0)  # Передаем физический масштаб
                grpc_block.metadata.update(block.get("metadata", {}))
            
            # Добавляем связи
            for link in links:
                grpc_link = request.links.add()
                grpc_link.source_id = link["source_id"]
                grpc_link.target_id = link["target_id"]
            
            # Добавляем опции
            request.options.sublevel_spacing = options.sublevel_spacing if options else 200
            request.options.layer_spacing = options.layer_spacing if options else 250
            request.options.optimize_layout = options.optimize_layout if options else True
            # УБИРАЕМ: больше не передаём blocks_per_sublevel
            
            # Отправляем запрос на gRPC сервис
            response = await self._stub.CalculateLayout(
                request, 
                timeout=self.config.timeout
            )
            
            logger.info(f"Получен ответ от gRPC сервиса: success={response.success}")
            
            if not response.success:
                error_msg = response.error_message or "Неизвестная ошибка сервиса укладки"
                logger.error(f"Layout service error: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
            
            logger.info(f"Статистика ответа: блоков={len(response.blocks)}, уровней={len(response.levels)}, подуровней={len(response.sublevels)}")
            
            # Конвертируем ответ в нужный формат
            result = {
                'success': True,
                'blocks': [],
                'links': [],
                'levels': [],
                'sublevels': [],
                'statistics': {
                    'total_blocks': response.statistics.total_blocks,
                    'total_links': response.statistics.total_links,
                    'total_levels': response.statistics.total_levels,
                    'total_sublevels': response.statistics.total_sublevels,
                    'max_layer': response.statistics.max_layer,
                    'total_width': response.statistics.total_width,
                    'total_height': response.statistics.total_height,
                    'processing_time_ms': response.statistics.processing_time_ms,
                    'is_acyclic': response.statistics.is_acyclic,
                    'isolated_blocks': response.statistics.isolated_blocks
                }
            }
            
            # Блоки с позициями
            logger.info("Обработка блоков...")
            for i, block in enumerate(response.blocks):
                try:
                    result["blocks"].append({
                        "id": block.id,
                        "content": block.content,
                        "layer": block.layer,
                        "level": block.level,
                        "sublevel_id": block.sublevel_id,
                        "is_pinned": block.is_pinned,
                        "physical_scale": getattr(block, 'physical_scale', 0),
                        "metadata": dict(block.metadata)
                    })
                except Exception as e:
                    logger.error(f"Ошибка при обработке блока {i} (id={getattr(block, 'id', 'unknown')}): {e}")
                    raise
            
            # Связи
            logger.info("Обработка связей...")
            for link in links:
                result["links"].append({
                    "id": link["id"],
                    "source_id": link["source_id"],
                    "target_id": link["target_id"],
                    "metadata": link.get("metadata", {})
                })
            
            # Уровни
            logger.info("Обработка уровней...")
            for i, level in enumerate(response.levels):
                try:
                    logger.debug(f"Уровень {i}: id={level.id}")
                    result["levels"].append({
                        "id": level.id,
                        "sublevel_ids": list(level.sublevel_ids),
                        "name": getattr(level, 'name', f"Уровень {level.id}"),
                        "color": f"#{level.color:06x}" if hasattr(level, 'color') else "#000000"
                    })
                except Exception as e:
                    logger.error(f"Ошибка при обработке уровня {i} (id={getattr(level, 'id', 'unknown')}): {e}")
                    logger.error(f"Доступные поля уровня: {dir(level)}")
                    raise
            
            # Подуровни  
            logger.info("Обработка подуровней...")
            for i, sublevel in enumerate(response.sublevels):
                try:
                    logger.debug(f"Подуровень {i}: id={sublevel.id}")
                    result["sublevels"].append({
                        "id": sublevel.id,
                        "block_ids": list(sublevel.block_ids) if hasattr(sublevel, 'block_ids') else [],
                        "level_id": getattr(sublevel, 'level_id', 0),
                        "color": f"#{sublevel.color:06x}" if hasattr(sublevel, 'color') else "#000000"
                    })
                except Exception as e:
                    logger.error(f"Ошибка при обработке подуровня {i} (id={getattr(sublevel, 'id', 'unknown')}): {e}")
                    logger.error(f"Доступные поля подуровня: {dir(sublevel)}")
                    raise
            
            logger.info("Укладка успешно получена от gRPC сервиса")
            return result
            
        except grpc.aio.AioRpcError as e:
            error_msg = f"gRPC ошибка: {e.code()} - {e.details()}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Неожиданная ошибка: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    def _get_level_color(self, level_id: int) -> str:
        """Возвращает цвет для уровня в формате hex строки."""
        colors = [
            "#B0C4DE",  # lightsteelblue
            "#20B2AA",  # lightseagreen
            "#FA8072",  # lightsalmon
            "#FAFAD2",  # lightgoldenrodyellow
            "#DDA0DD",  # plum
            "#D3D3D3",  # lightgray
            "#E0FFFF",  # lightcyan
            "#E6E6FA",  # lavender
        ]
        return colors[level_id % len(colors)]
    
    def _get_sublevel_color(self, sublevel_id: int) -> str:
        """Возвращает цвет для подуровня в формате hex строки."""
        colors = [
            "#ADD8E6",  # lightblue
            "#90EE90",  # lightgreen
            "#F08080",  # lightcoral
            "#FFFFE0",  # lightyellow
            "#FFB6C1",  # lightpink
            "#D3D3D3",  # lightgray
            "#E0FFFF",  # lightcyan
            "#E6E6FA",  # lavender
            "#FFE4E1",  # mistyrose
            "#F0FFF0",  # honeydew
        ]
        return colors[sublevel_id % len(colors)]
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()


# Глобальный экземпляр клиента
_layout_client: Optional[LayoutClient] = None


def get_layout_client(config: LayoutConfig = None) -> LayoutClient:
    """Получает глобальный экземпляр клиента"""
    global _layout_client
    if _layout_client is None:
        if config is None:
            config = LayoutConfig.from_env()
        _layout_client = LayoutClient(config)
    return _layout_client


async def calculate_graph_layout(
    blocks: List[Dict], 
    links: List[Dict], 
    options: LayoutOptions = None
) -> Dict:
    """
    Удобная функция для расчета укладки графа
    
    Args:
        blocks: Список блоков
        links: Список связей
        options: Опции алгоритма
    
    Returns:
        Результат укладки
    """
    client = get_layout_client()
    return await client.calculate_layout(blocks, links, options) 