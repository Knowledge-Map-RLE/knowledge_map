"""
Система метрик для мониторинга производительности (упрощённая версия)
"""

import time
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

# Отключаем Prometheus для избежания конфликтов
_metrics_enabled = False

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, start_http_server, REGISTRY
    _metrics_enabled = True
except ImportError:
    logger.warning("Prometheus client not available, metrics disabled")

# Prometheus метрики (создаются только если доступны)
if _metrics_enabled:
    try:
        # Очищаем реестр перед созданием новых метрик
        REGISTRY._collector_to_names.clear()
        REGISTRY._names_to_collectors.clear()
        
        TASK_COUNTER = Counter('layout_tasks_total', 'Total layout tasks processed', ['task_type', 'status'])
        TASK_DURATION = Histogram('layout_task_duration_seconds', 'Task execution time', ['task_type'])
        NEO4J_QUERY_DURATION = Histogram('neo4j_query_duration_seconds', 'Neo4j query execution time', ['query_type'])
        MEMORY_USAGE = Gauge('memory_usage_bytes', 'Memory usage in bytes')
        CPU_USAGE = Gauge('cpu_usage_percent', 'CPU usage percentage')
        ACTIVE_TASKS = Gauge('active_tasks', 'Number of active tasks')
    except Exception as e:
        logger.warning("Failed to initialize Prometheus metrics", error=str(e))
        _metrics_enabled = False


class MetricsCollector:
    """
    Коллектор метрик для системы
    """
    
    def __init__(self):
        self.start_time = time.time()
        self.task_stats = {
            'total_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
            'total_processing_time': 0.0
        }
        
    def record_task_execution(self, task_type: str, duration: float, success: bool):
        """
        Записывает выполнение задачи
        """
        status = 'success' if success else 'failure'
        
        if _metrics_enabled:
            try:
                TASK_COUNTER.labels(task_type=task_type, status=status).inc()
                TASK_DURATION.labels(task_type=task_type).observe(duration)
            except Exception as e:
                logger.warning("Failed to record task metrics", error=str(e))
        
        self.task_stats['total_tasks'] += 1
        self.task_stats['total_processing_time'] += duration
        
        if success:
            self.task_stats['successful_tasks'] += 1
        else:
            self.task_stats['failed_tasks'] += 1
    
    def record_neo4j_query(self, query_type: str, duration: float):
        """
        Записывает выполнение Neo4j запроса
        """
        if _metrics_enabled:
            try:
                NEO4J_QUERY_DURATION.labels(query_type=query_type).observe(duration)
            except Exception as e:
                logger.warning("Failed to record Neo4j metrics", error=str(e))
    
    def update_system_metrics(self, system_info: Dict[str, Any]):
        """
        Обновляет системные метрики
        """
        try:
            memory_bytes = system_info.get('process', {}).get('memory_mb', 0) * 1024 * 1024
            cpu_percent = system_info.get('process', {}).get('cpu_percent', 0)
            
            if _metrics_enabled:
                MEMORY_USAGE.set(memory_bytes)
                CPU_USAGE.set(cpu_percent)
            
        except Exception as e:
            logger.error("Failed to update system metrics", error=str(e))
    
    def update_active_tasks(self, count: int):
        """
        Обновляет количество активных задач
        """
        if _metrics_enabled:
            try:
                ACTIVE_TASKS.set(count)
            except Exception as e:
                logger.warning("Failed to update active tasks metric", error=str(e))
    
    def get_current_metrics_summary(self) -> Dict[str, Any]:
        """
        Возвращает сводку текущих метрик
        """
        uptime = time.time() - self.start_time
        
        return {
            'uptime_seconds': round(uptime, 2),
            'task_stats': self.task_stats.copy(),
            'success_rate': (
                self.task_stats['successful_tasks'] / max(1, self.task_stats['total_tasks'])
            ) * 100,
            'avg_task_duration': (
                self.task_stats['total_processing_time'] / max(1, self.task_stats['total_tasks'])
            )
        }
    
    def get_prometheus_metrics(self) -> str:
        """
        Возвращает метрики в формате Prometheus
        """
        return generate_latest().decode('utf-8')


def initialize_metrics(port: int = 9100):
    """
    Инициализирует систему метрик
    """
    if not _metrics_enabled:
        logger.info("Metrics disabled, skipping initialization")
        return
        
    try:
        # Проверяем, не запущен ли уже сервер метрик
        # Если уже поднят, то просто логируем и выходим
        start_http_server(port)
        logger.info(f"Metrics server started on port {port}")
    except Exception as e:
        logger.warning(f"Failed to start metrics server on port {port}", error=str(e))


# Глобальный экземпляр
metrics_collector = MetricsCollector()