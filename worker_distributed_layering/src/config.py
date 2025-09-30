"""
Конфигурация для распределённого воркера укладки графов.
"""

from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Neo4j настройки
    neo4j_uri: str = Field(default="bolt://localhost:7687", env="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", env="NEO4J_USER")
    neo4j_password: str = Field(default="password", env="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", env="NEO4J_DATABASE")
    neo4j_pool_size: int = Field(default=50, env="NEO4J_POOL_SIZE")
    neo4j_connection_timeout: int = Field(default=300, env="NEO4J_CONNECTION_TIMEOUT")
    
    # Redis настройки
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    redis_max_connections: int = Field(default=100, env="REDIS_MAX_CONNECTIONS")
    
    # Celery настройки
    celery_broker_url: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND")
    celery_task_serializer: str = Field(default="json", env="CELERY_TASK_SERIALIZER")
    celery_result_serializer: str = Field(default="json", env="CELERY_RESULT_SERIALIZER")
    celery_accept_content: list[str] = Field(default=["json"], env="CELERY_ACCEPT_CONTENT")
    celery_timezone: str = Field(default="UTC", env="CELERY_TIMEZONE")
    celery_enable_utc: bool = Field(default=True, env="CELERY_ENABLE_UTC")
    
    # Настройки обработки (оптимизированы для 4GB RAM)
    chunk_size: int = Field(default=8000, env="CHUNK_SIZE", description="Размер чанка для обработки")
    max_workers: int = Field(default=4, env="MAX_WORKERS", description="Максимальное количество воркеров")
    batch_size: int = Field(default=1000, env="BATCH_SIZE", description="Размер батча для Neo4j операций")
    
    # Настройки алгоритма
    max_iterations: int = Field(default=100, env="MAX_ITERATIONS", description="Максимальное количество итераций оптимизации")
    convergence_threshold: float = Field(default=0.001, env="CONVERGENCE_THRESHOLD", description="Порог сходимости")
    enable_cython_optimization: bool = Field(default=True, env="ENABLE_CYTHON_OPTIMIZATION")
    enable_numba_jit: bool = Field(default=True, env="ENABLE_NUMBA_JIT")
    
    # Настройки параллельной обработки
    parallel_chunk_processing: bool = Field(default=True, env="PARALLEL_CHUNK_PROCESSING")
    max_parallel_workers: int = Field(default=4, env="MAX_PARALLEL_WORKERS")
    
    # Настройки мониторинга
    prometheus_port: int = Field(default=9101, env="PROMETHEUS_PORT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    enable_profiling: bool = Field(default=False, env="ENABLE_PROFILING")
    
    # Настройки производительности (адаптированы под 4GB RAM)
    memory_limit_gb: float = Field(default=4.0, env="MEMORY_LIMIT_GB", description="Лимит памяти в ГБ")
    cpu_limit: int = Field(default=4, env="CPU_LIMIT", description="Лимит CPU ядер")
    
    # Настройки отказоустойчивости
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    retry_delay: int = Field(default=60, env="RETRY_DELAY", description="Задержка между повторами в секундах")
    circuit_breaker_failure_threshold: int = Field(default=5, env="CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    circuit_breaker_recovery_timeout: int = Field(default=300, env="CIRCUIT_BREAKER_RECOVERY_TIMEOUT")
    
    # Настройки кэширования
    cache_ttl: int = Field(default=3600, env="CACHE_TTL", description="TTL кэша в секундах")
    enable_result_caching: bool = Field(default=True, env="ENABLE_RESULT_CACHING")
    
    # Настройки алгоритма укладки
    exclude_isolated_vertices: bool = Field(default=True, env="EXCLUDE_ISOLATED_VERTICES", description="Исключить изолированные вершины из укладки")
    validate_topo_order: bool = Field(default=False, env="VALIDATE_TOPO_ORDER", description="Проверять корректность топологического порядка")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Глобальный экземпляр настроек
settings = Settings()


def get_neo4j_config() -> dict:
    """Возвращает конфигурацию для Neo4j драйвера"""
    return {
        "uri": settings.neo4j_uri,
        "auth": (settings.neo4j_user, settings.neo4j_password),
        "database": settings.neo4j_database,
        "max_connection_pool_size": settings.neo4j_pool_size,
        "connection_timeout": settings.neo4j_connection_timeout,
        "max_transaction_retry_time": 300,
        "encrypted": False,  # Для локальной разработки
    }


def get_celery_config() -> dict:
    """Возвращает конфигурацию для Celery"""
    return {
        "broker_url": settings.celery_broker_url,
        "result_backend": settings.celery_result_backend,
        "task_serializer": settings.celery_task_serializer,
        "result_serializer": settings.celery_result_serializer,
        "accept_content": settings.celery_accept_content,
        "timezone": settings.celery_timezone,
        "enable_utc": settings.celery_enable_utc,
        "task_routes": {
            "distributed_layout_worker.tasks.process_graph_chunk": {"queue": "graph_processing"},
            "distributed_layout_worker.tasks.optimize_layout": {"queue": "optimization"},
            "distributed_layout_worker.tasks.save_results": {"queue": "persistence"},
        },
        "worker_prefetch_multiplier": 1,
        "task_acks_late": True,
        "worker_max_tasks_per_child": 1000,
        "task_soft_time_limit": 3600,  # 1 час
        "task_time_limit": 7200,  # 2 часа
    }


def get_redis_config() -> dict:
    """Возвращает конфигурацию для Redis"""
    return {
        "url": settings.redis_url,
        "max_connections": settings.redis_max_connections,
        "retry_on_timeout": True,
        "socket_keepalive": True,
        "socket_keepalive_options": {},
        "health_check_interval": 30,
    }
