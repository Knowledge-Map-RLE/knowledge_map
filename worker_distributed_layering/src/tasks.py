"""
Celery задачи для распределённой обработки укладки графов.
"""

import asyncio
import time
import random
from typing import Dict, List, Any, Optional
from celery import Celery
from celery.exceptions import Retry
import structlog

from .config import get_celery_config, settings
from .algorithms.distributed_incremental_layout import distributed_incremental_layout
from .neo4j_client import neo4j_client
from .utils.metrics import metrics_collector

logger = structlog.get_logger(__name__)

# Создаём Celery приложение
celery_config = get_celery_config()
celery_app = Celery("distributed_layout_worker")
celery_app.config_from_object(celery_config)


@celery_app.task(bind=True, max_retries=settings.max_retries)
def process_large_graph_layout(
    self,
    node_labels: Optional[List[str]] = None,
    filters: Optional[Dict] = None,
    options: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Основная задача для обработки больших графов
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        "Starting large graph layout processing",
        task_id=task_id,
        node_labels=node_labels,
        filters=filters,
    )
    
    try:
        # Запускаем асинхронную обработку в синхронном контексте Celery
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                distributed_incremental_layout.calculate_incremental_layout()
            )
        finally:
            loop.close()
        
        processing_time = time.time() - start_time
        
        if result.get("success"):
            metrics_collector.record_task_execution("large_graph_layout", processing_time, True)
            logger.info(
                "Large graph layout processing completed successfully",
                task_id=task_id,
                processing_time=processing_time,
                nodes_processed=result.get("statistics", {}).get("total_blocks", 0),
            )
        else:
            metrics_collector.record_task_execution("large_graph_layout", processing_time, False)
            logger.error(
                "Large graph layout processing failed",
                task_id=task_id,
                error=result.get("error"),
                processing_time=processing_time,
            )
        return result
        
    except Exception as e:
        processing_time = time.time() - start_time
        metrics_collector.record_task_execution("large_graph_layout", processing_time, False)
        
        logger.error(
            "Large graph layout processing failed with exception",
            task_id=task_id,
            error=str(e),
            processing_time=processing_time,
            retry_count=self.request.retries,
        )
        
        # Retry с экспоненциальной задержкой
        if self.request.retries < settings.max_retries:
            retry_delay = settings.retry_delay * (2 ** self.request.retries)
            logger.info(
                "Retrying task",
                task_id=task_id,
                retry_delay=retry_delay,
                retry_count=self.request.retries + 1,
            )
            raise self.retry(countdown=retry_delay, exc=e)
        
        return {
            "success": False,
            "error": str(e),
            "statistics": {"processing_time_seconds": processing_time},
        }


@celery_app.task(bind=True, max_retries=settings.max_retries)
def process_graph_chunk(
    self,
    nodes: List[Dict],
    edges: List[Dict],
    chunk_id: str,
    options: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Задача для обработки отдельного чанка графа
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        "Starting graph chunk processing",
        task_id=task_id,
        chunk_id=chunk_id,
        nodes_count=len(nodes),
        edges_count=len(edges),
    )
    
    try:
        # Запускаем асинхронную обработку с высокопроизводительным алгоритмом
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Временно используем инкрементальный алгоритм и для чанков
            result = loop.run_until_complete(
                distributed_incremental_layout.calculate_incremental_layout()
            )
        finally:
            loop.close()
        
        processing_time = time.time() - start_time
        
        if result.get("success"):
            logger.info(
                "Graph chunk processing completed successfully",
                task_id=task_id,
                chunk_id=chunk_id,
                processing_time=processing_time,
            )
        else:
            logger.error(
                "Graph chunk processing failed",
                task_id=task_id,
                chunk_id=chunk_id,
                error=result.get("error"),
                processing_time=processing_time,
            )
        
        return result
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        logger.error(
            "Graph chunk processing failed with exception",
            task_id=task_id,
            chunk_id=chunk_id,
            error=str(e),
            processing_time=processing_time,
            retry_count=self.request.retries,
        )
        
        # Retry с экспоненциальной задержкой
        if self.request.retries < settings.max_retries:
            retry_delay = settings.retry_delay * (2 ** self.request.retries)
            raise self.retry(countdown=retry_delay, exc=e)
        
        return {
            "success": False,
            "error": str(e),
            "chunk_id": chunk_id,
            "statistics": {"processing_time_seconds": processing_time},
        }


@celery_app.task(bind=True, max_retries=settings.max_retries)
def optimize_layout(
    self,
    layout_data: Dict[str, Any],
    optimization_options: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Задача для оптимизации укладки
    """
    task_id = self.request.id
    start_time = time.time()

    logger.info(
        "Starting layout optimization",
        task_id=task_id,
        blocks_count=len(layout_data.get("blocks", [])),
    )

    try:
        # Получаем слои из layout_data
        layers = layout_data.get("layers", {})

        # Немного перемешиваем слои для примера
        # В реальном коде здесь должен быть более сложный алгоритм
        for block_id in layers:
            layers[block_id] += random.randint(-1, 1)  # Сдвигаем слой случайным образом

        # Обновляем layout_data с новыми слоями
        layout_data["layers"] = layers
        result = layout_data.copy()
        result["optimized"] = True

        processing_time = time.time() - start_time

        logger.info(
            "Layout optimization completed",
            task_id=task_id,
            processing_time=processing_time,
        )

        return result

    except Exception as e:
        processing_time = time.time() - start_time

        logger.error(
            "Layout optimization failed",
            task_id=task_id,
            error=str(e),
            processing_time=processing_time,
            retry_count=self.request.retries,
        )

        if self.request.retries < settings.max_retries:
            retry_delay = settings.retry_delay * (2 ** self.request.retries)
            raise self.retry(countdown=retry_delay, exc=e)

        return {
            "success": False,
            "error": str(e),
            "statistics": {"processing_time_seconds": processing_time},
        }


@celery_app.task(bind=True, max_retries=settings.max_retries)
def save_results(
    self,
    layout_result: Dict[str, Any],
    save_options: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Задача для сохранения результатов укладки в Neo4j
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(
        "Starting results saving",
        task_id=task_id,
        blocks_count=len(layout_result.get("blocks", [])),
    )
    
    try:
        # Запускаем асинхронное сохранение
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(
                distributed_layout._save_layout_results(layout_result)
            )
        finally:
            loop.close()
        
        processing_time = time.time() - start_time
        
        logger.info(
            "Results saving completed",
            task_id=task_id,
            processing_time=processing_time,
        )
        
        return {
            "success": True,
            "saved_blocks": len(layout_result.get("blocks", [])),
            "statistics": {"processing_time_seconds": processing_time},
        }
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        logger.error(
            "Results saving failed",
            task_id=task_id,
            error=str(e),
            processing_time=processing_time,
            retry_count=self.request.retries,
        )
        
        if self.request.retries < settings.max_retries:
            retry_delay = settings.retry_delay * (2 ** self.request.retries)
            raise self.retry(countdown=retry_delay, exc=e)
        
        return {
            "success": False,
            "error": str(e),
            "statistics": {"processing_time_seconds": processing_time},
        }


@celery_app.task
def health_check() -> Dict[str, Any]:
    """
    Задача для проверки здоровья воркера
    """
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "worker_id": celery_app.control.inspect().active(),
    }


# Периодические задачи
@celery_app.task
def cleanup_old_results():
    """
    Периодическая задача для очистки старых результатов
    """
    logger.info("Running cleanup of old results")
    # Здесь будет логика очистки
    return {"cleaned": True}


# Настройка периодических задач
celery_app.conf.beat_schedule = {
    "cleanup-old-results": {
        "task": "distributed_layout_worker.tasks.cleanup_old_results",
        "schedule": 3600.0,  # Каждый час
    },
}

celery_app.conf.timezone = "UTC"


# Обработчики событий
@celery_app.task(bind=True)
def on_task_failure(self, task_id, error, traceback):
    """
    Обработчик неудачных задач
    """
    logger.error(
        "Task failed",
        task_id=task_id,
        error=str(error),
        traceback=traceback,
    )


@celery_app.task(bind=True)
def on_task_success(self, task_id, result):
    """
    Обработчик успешных задач
    """
    logger.info(
        "Task completed successfully",
        task_id=task_id,
        result_summary={"success": result.get("success", False)},
    )
