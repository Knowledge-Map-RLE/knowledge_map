#!/usr/bin/env python3
"""
Главный файл для запуска распределённого воркера укладки графов.
Поддерживает несколько режимов работы и полную конфигурацию.
"""

import argparse
import asyncio
import logging
import signal
import sys
from typing import Optional
import structlog
import subprocess
from pathlib import Path

from src.config import settings, get_celery_config
from src.utils.metrics import initialize_metrics, metrics_collector
from src.utils.memory_manager import memory_manager
from src.neo4j_client import neo4j_client
from src.tasks import celery_app
from src.algorithms.distributed_layout import distributed_layout

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = structlog.get_logger(__name__)


class DistributedLayoutWorkerManager:
    """
    Менеджер для управления распределённым воркером укладки графов
    """

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.background_tasks = []

    async def start_standalone_worker(self):
        """
        Запускает воркер в автономном режиме (без Celery)
        """
        logger.info("Starting standalone distributed layout worker")
        
        try:
            # Инициализируем компоненты
            await self._initialize_components()
            
            # Запускаем фоновые задачи
            await self._start_background_tasks()
            
            logger.info("Standalone worker started successfully")
            
            # Ожидаем сигнал завершения
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error("Failed to start standalone worker", error=str(e))
            raise
        finally:
            await self._cleanup()

    async def start_celery_worker(self):
        """
        Запускает Celery воркер
        """
        logger.info("Starting Celery distributed layout worker")
        
        try:
            # Инициализируем компоненты
            await self._initialize_components()
            
            # Запускаем фоновые задачи
            await self._start_background_tasks()
            
            logger.info("Celery worker components initialized")
            
            # Запускаем Celery воркер в отдельном потоке
            import threading
            
            def run_celery():
                celery_app.worker_main([
                    'worker',
                    '--loglevel=info',
                    '--concurrency=4',
                    '--queues=graph_processing,optimization,persistence',
                ])
            
            celery_thread = threading.Thread(target=run_celery, daemon=True)
            celery_thread.start()
            
            # Ожидаем сигнал завершения
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error("Failed to start Celery worker", error=str(e))
            raise
        finally:
            await self._cleanup()

    async def run_single_layout_task(
        self, 
        node_labels: Optional[list] = None,
        filters: Optional[dict] = None,
        options: Optional[dict] = None
    ):
        """
        Выполняет одну задачу укладки и завершается
        """
        logger.info("Running single layout task")
        
        try:
            # Инициализируем компоненты
            await self._initialize_components()
            
            # Выполняем укладку
            result = await distributed_layout.calculate_distributed_layout(
                node_labels=node_labels,
                filters=filters,
                options=options
            )
            
            logger.info(
                "Single layout task completed",
                success=result.get("success", False),
                processing_time=result.get("statistics", {}).get("processing_time_seconds", 0),
                nodes_processed=result.get("statistics", {}).get("total_blocks", 0),
            )
            
            return result
            
        except Exception as e:
            logger.error("Single layout task failed", error=str(e))
            raise
        finally:
            await self._cleanup()

    async def health_check(self):
        """
        Проверка здоровья воркера
        """
        logger.info("Performing health check")
        
        health_status = {
            "status": "unknown",
            "components": {},
            "metrics": {},
            "system": {},
        }
        
        try:
            # Проверяем Neo4j соединение
            try:
                await neo4j_client.connect()
                stats = await neo4j_client.get_graph_statistics()
                health_status["components"]["neo4j"] = {
                    "status": "healthy",
                    "article_count": stats.get("article_count", 0),
                    "edge_count": stats.get("edge_count", 0),
                }
            except Exception as e:
                health_status["components"]["neo4j"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
            
            # Проверяем систему
            system_info = memory_manager.get_system_info()
            health_status["system"] = system_info
            
            # Получаем метрики
            health_status["metrics"] = metrics_collector.get_current_metrics_summary()
            
            # Определяем общий статус
            neo4j_healthy = health_status["components"]["neo4j"]["status"] == "healthy"
            memory_usage = system_info["memory"]["percentage"]
            
            if neo4j_healthy and memory_usage < 90:
                health_status["status"] = "healthy"
            elif neo4j_healthy and memory_usage < 95:
                health_status["status"] = "degraded"
            else:
                health_status["status"] = "unhealthy"
            
            logger.info("Health check completed", status=health_status["status"])
            return health_status
            
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            health_status["status"] = "error"
            health_status["error"] = str(e)
            return health_status

    async def _install_neo4j_procedures(self):
        """Устанавливает Neo4j процедуры при запуске"""
        logger.info("Installing Neo4j procedures...")
        
        try:
            # Запускаем скрипт установки процедур
            script_path = Path(__file__).parent / "scripts" / "install_procedures.py"
            
            if script_path.exists():
                result = subprocess.run([
                    sys.executable, str(script_path)
                ], capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0:
                    logger.info("Neo4j procedures installed successfully")
                    return True
                else:
                    logger.warning(f"Procedures installation failed: {result.stderr}")
                    return False
            else:
                logger.warning("Installation script not found, skipping procedures installation")
                return False
                
        except Exception as e:
            logger.error(f"Failed to install procedures: {str(e)}")
            return False

    async def _initialize_components(self):
        """
        Инициализирует все компоненты воркера
        """
        logger.info("Initializing worker components")
        
        # Инициализируем метрики
        initialize_metrics()
        
        # Подключаемся к Neo4j
        await neo4j_client.connect()
        
        # Устанавливаем процедуры (если нужно)
        await self._install_neo4j_procedures()
        
        # Обновляем системные метрики
        system_info = memory_manager.get_system_info()
        metrics_collector.update_system_metrics(system_info)
        
        logger.info("Worker components initialized successfully")

    async def _start_background_tasks(self):
        """
        Запускает фоновые задачи
        """
        logger.info("Starting background tasks")
        
        # Мониторинг памяти
        memory_monitor_task = asyncio.create_task(
            memory_manager.monitor_memory_usage(interval_seconds=30)
        )
        self.background_tasks.append(memory_monitor_task)
        
        # Периодическое обновление системных метрик
        metrics_update_task = asyncio.create_task(
            self._periodic_metrics_update(interval_seconds=60)
        )
        self.background_tasks.append(metrics_update_task)
        
        logger.info(f"Started {len(self.background_tasks)} background tasks")

    async def _periodic_metrics_update(self, interval_seconds: int = 60):
        """
        Периодическое обновление метрик
        """
        while not self.shutdown_event.is_set():
            try:
                system_info = memory_manager.get_system_info()
                metrics_collector.update_system_metrics(system_info)
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Metrics update failed", error=str(e))
                await asyncio.sleep(interval_seconds)

    async def _cleanup(self):
        """
        Очистка ресурсов
        """
        logger.info("Cleaning up worker resources")
        
        # Отменяем фоновые задачи
        for task in self.background_tasks:
            task.cancel()
        
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # Закрываем соединения
        await neo4j_client.close()
        
        # Очищаем память
        memory_manager.cleanup_memory()
        
        logger.info("Worker cleanup completed")

    def _setup_signal_handlers(self):
        """
        Настраивает обработчики сигналов для graceful shutdown
        """
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, initiating shutdown")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """
    Главная функция приложения
    """
    parser = argparse.ArgumentParser(description="Distributed Layout Worker")
    parser.add_argument(
        "mode",
        choices=["standalone", "celery", "single", "health"],
        help="Worker mode: standalone, celery, single task, or health check"
    )
    parser.add_argument("--node-labels", nargs="*", help="Node labels to filter")
    parser.add_argument("--filters", type=str, help="JSON filters for nodes")
    parser.add_argument("--options", type=str, help="JSON options for layout")
    
    args = parser.parse_args()
    
    manager = DistributedLayoutWorkerManager()
    manager._setup_signal_handlers()
    
    try:
        if args.mode == "standalone":
            await manager.start_standalone_worker()
        
        elif args.mode == "celery":
            await manager.start_celery_worker()
        
        elif args.mode == "single":
            import json
            
            filters = json.loads(args.filters) if args.filters else None
            options = json.loads(args.options) if args.options else None
            
            result = await manager.run_single_layout_task(
                node_labels=args.node_labels,
                filters=filters,
                options=options
            )
            
            print(f"Layout result: {result}")
        
        elif args.mode == "health":
            health = await manager.health_check()
            print(f"Health status: {health}")
            
            # Завершаемся с кодом 0 если здоровы, иначе 1
            sys.exit(0 if health["status"] == "healthy" else 1)
    
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        logger.error("Worker failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
