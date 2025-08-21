"""
Менеджер памяти для мониторинга и оптимизации использования ресурсов
"""

import asyncio
import logging
import gc
from typing import Dict, Any, Optional
import psutil
import structlog

logger = structlog.get_logger(__name__)


class MemoryManager:
    """
    Управляет использованием памяти и определяет стратегии обработки
    """
    
    def __init__(self):
        self.process = psutil.Process()
        self.memory_limit_gb = 4.0  # Ограничение для 16GB системы
        
    def get_system_info(self) -> Dict[str, Any]:
        """
        Получает информацию о системе
        """
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent()
            
            return {
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "percentage": memory.percent
                },
                "cpu": {
                    "percentage": cpu_percent,
                    "count": psutil.cpu_count()
                },
                "process": {
                    "memory_mb": round(self.process.memory_info().rss / (1024**2), 2),
                    "cpu_percent": self.process.cpu_percent()
                }
            }
        except Exception as e:
            logger.error("Failed to get system info", error=str(e))
            return {
                "memory": {"total_gb": 16, "available_gb": 8, "used_gb": 8, "percentage": 50},
                "cpu": {"percentage": 10, "count": 4},
                "process": {"memory_mb": 100, "cpu_percent": 5}
            }
    
    def adaptive_processing_strategy(self, node_count: int) -> str:
        """
        Определяет стратегию обработки на основе размера графа и доступной памяти
        """
        system_info = self.get_system_info()
        available_memory_gb = system_info["memory"]["available_gb"]
        
        # Примерные расчёты для разных стратегий
        if node_count < 1000 and available_memory_gb > 2:
            return "single_pass"
        elif node_count < 50000 and available_memory_gb > 1:
            return "chunked"
        else:
            return "fully_distributed"
    
    def calculate_optimal_chunk_size(self, total_nodes: int) -> int:
        """
        Вычисляет оптимальный размер чанка
        """
        system_info = self.get_system_info()
        available_memory_gb = system_info["memory"]["available_gb"]
        
        # Консервативный расчёт
        base_chunk_size = int(available_memory_gb * 500)  # ~500 узлов на GB
        return min(base_chunk_size, max(100, total_nodes // 10))
    
    async def monitor_memory_usage(self, interval_seconds: int = 30):
        """
        Мониторинг использования памяти
        """
        while True:
            try:
                system_info = self.get_system_info()
                memory_percent = system_info["memory"]["percentage"]
                process_memory_mb = system_info["process"]["memory_mb"]
                
                if memory_percent > 90:
                    logger.warning(
                        "High memory usage detected",
                        memory_percent=memory_percent,
                        process_memory_mb=process_memory_mb
                    )
                    self.cleanup_memory()
                
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Memory monitoring failed", error=str(e))
                await asyncio.sleep(interval_seconds)
    
    def cleanup_memory(self):
        """
        Принудительная очистка памяти
        """
        try:
            gc.collect()
            logger.info("Memory cleanup completed")
        except Exception as e:
            logger.error("Memory cleanup failed", error=str(e))


# Глобальный экземпляр
memory_manager = MemoryManager()