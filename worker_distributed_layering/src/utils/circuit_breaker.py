"""
Circuit Breaker для повышения надёжности соединений
"""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, Union
import structlog

logger = structlog.get_logger(__name__)


class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Нормальная работа
    OPEN = "open"          # Блокировка вызовов
    HALF_OPEN = "half_open"  # Тестирование восстановления


class CircuitBreaker:
    """
    Реализация паттерна Circuit Breaker для обработки отказов
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Union[Exception, tuple] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        
    async def __aenter__(self):
        """
        Асинхронный контекстный менеджер - вход
        """
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Асинхронный контекстный менеджер - выход
        """
        if exc_type and issubclass(exc_type, self.expected_exception):
            self._record_failure()
        return False  # Не подавляем исключения
        
    async def __call__(self, func: Callable, *args, **kwargs) -> Any:
        """
        Выполняет функцию с защитой Circuit Breaker
        """
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker entering half-open state")
            else:
                raise CircuitBreakerOpenException(
                    f"Circuit breaker is open. Last failure: {self.last_failure_time}"
                )
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # Успешное выполнение - сбрасываем состояние
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.CLOSED
                logger.info("Circuit breaker closed after successful recovery")
            
            self.failure_count = 0
            return result
            
        except self.expected_exception as e:
            self._record_failure()
            raise e
    
    def _record_failure(self):
        """
        Записывает ошибку и обновляет состояние
        """
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures",
                failure_count=self.failure_count,
                threshold=self.failure_threshold
            )
    
    def _should_attempt_reset(self) -> bool:
        """
        Проверяет, можно ли попытаться восстановить соединение
        """
        if self.last_failure_time is None:
            return True
        
        return (time.time() - self.last_failure_time) >= self.recovery_timeout
    
    def reset(self):
        """
        Принудительный сброс circuit breaker
        """
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        logger.info("Circuit breaker manually reset")
    
    def get_status(self) -> dict:
        """
        Возвращает текущий статус circuit breaker
        """
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "recovery_timeout": self.recovery_timeout
        }


class CircuitBreakerOpenException(Exception):
    """
    Исключение, выбрасываемое когда circuit breaker открыт
    """
    pass