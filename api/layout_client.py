"""
gRPC клиент для взаимодействия с микросервисом укладки графа.
"""

import asyncio
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

import grpc
import sys
from pathlib import Path

# Добавляем путь к generated в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent / "generated"))
# Добавляем путь к layering/src в PYTHONPATH
layering_path = Path(__file__).parent.parent / "layering" / "src"
sys.path.insert(0, str(layering_path))

from layout_algorithm import layout_knowledge_map
import layout_pb2
import layout_pb2_grpc

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
        import os
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
            
            # Преобразуем данные в формат для сервиса укладки
            block_ids = [block["id"] for block in blocks]
            link_tuples = [(link["source_id"], link["target_id"]) for link in links]
            
            # Отправляем запрос
            logger.info(f"Отправка запроса на укладку: {len(blocks)} блоков, {len(links)} связей")
            logger.debug(f"Блоки: {block_ids}")
            logger.debug(f"Связи: {link_tuples}")
            
            # Настройки укладки
            layout_options = {
                'sublevel_spacing': options.sublevel_spacing if options else 200,
                'layer_spacing': options.layer_spacing if options else 250,
                'optimize_layout': options.optimize_layout if options else True
            }
            
            # Вызываем алгоритм укладки
            result = layout_knowledge_map(block_ids, link_tuples, layout_options)
            
            # Конвертируем результат в формат ответа
            response = {
                'success': True,
                'blocks': [],
                'links': [],
                'levels': [],
                'sublevels': [],
                'statistics': result['statistics']
            }
            
            # Блоки с позициями
            try:
                for block_id, (x, y) in result['positions'].items():
                    block_data = next(b for b in blocks if b["id"] == block_id)
                    response["blocks"].append({
                        "id": block_id,
                        "content": block_data["content"],
                        "x": float(x),
                        "y": float(y),
                        "layer": result['layers'][block_id],
                        "level": 0,  # Будет обновлено позже
                        "sublevel_id": 0,  # Будет обновлено позже
                        "metadata": block_data.get("metadata", {})
                    })
            except Exception as e:
                logger.error(f"Ошибка при обработке блоков: {e}")
                raise
            
            # Обновляем level и sublevel_id для блоков
            for level_id, sublevel_ids in result['levels'].items():
                for sublevel_id in sublevel_ids:
                    for block_id in result['sublevels'][sublevel_id]:
                        block = next(b for b in response["blocks"] if b["id"] == block_id)
                        block["level"] = level_id
                        block["sublevel_id"] = sublevel_id
            
            # Связи
            try:
                for link in links:
                    response["links"].append({
                        "id": link["id"],
                        "source_id": link["source_id"],
                        "target_id": link["target_id"],
                        "metadata": link.get("metadata", {})
                    })
            except Exception as e:
                logger.error(f"Ошибка при обработке связей: {e}")
                raise
            
            # Уровни
            for level_id, sublevel_ids in result['levels'].items():
                blocks_in_level = []
                for sublevel_id in sublevel_ids:
                    blocks_in_level.extend(result['sublevels'][sublevel_id])
                
                if blocks_in_level:
                    positions = [result['positions'][block_id] for block_id in blocks_in_level]
                    min_x = min(x for x, _ in positions) - layout_options['layer_spacing'] / 2
                    max_x = max(x for x, _ in positions) + layout_options['layer_spacing'] / 2
                    min_y = min(y for _, y in positions) - layout_options['sublevel_spacing'] / 2
                    max_y = max(y for _, y in positions) + layout_options['sublevel_spacing'] / 2
                    
                    response["levels"].append({
                        "id": level_id,
                        "min_x": min_x,
                        "max_x": max_x,
                        "min_y": min_y,
                        "max_y": max_y,
                        "color": self._get_level_color(level_id)
                    })
            
            # Подуровни
            for sublevel_id, block_ids in result['sublevels'].items():
                if block_ids:
                    positions = [result['positions'][block_id] for block_id in block_ids]
                    level_id = next(level_id for level_id, sublevel_ids in result['levels'].items() 
                                  if sublevel_id in sublevel_ids)
                    
                    min_y = min(y for _, y in positions) - layout_options['sublevel_spacing'] / 2
                    max_y = max(y for _, y in positions) + layout_options['sublevel_spacing'] / 2
                    
                    response["sublevels"].append({
                        "id": sublevel_id,
                        "min_x": min(x for x, _ in positions) - layout_options['layer_spacing'] / 2,
                        "max_x": max(x for x, _ in positions) + layout_options['layer_spacing'] / 2,
                        "min_y": min_y,
                        "max_y": max_y,
                        "color": self._get_sublevel_color(sublevel_id),
                        "block_ids": block_ids,
                        "level": level_id
                    })
            
            logger.info("Укладка успешна")
            return response
            
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