"""
Упрощенная реализация Circuit Breaker без внешних зависимостей
Альтернатива aiobreaker для случаев, когда установка не удается
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Any, Callable, Optional, Union, Type

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Нормальная работа
    OPEN = "open"          # Блокировка вызовов
    HALF_OPEN = "half_open"  # Тестирование восстановления


class SimpleCircuitBreaker:
    """
    Упрощенная реализация Circuit Breaker без внешних зависимостей
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Union[Type[Exception], tuple] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        
        logger.info(f"SimpleCircuitBreaker initialized: threshold={failure_threshold}, timeout={recovery_timeout}")
        
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        if exc_type and self._is_expected_exception(exc_type):
            self._record_failure()
        return False  # Не подавляем исключения
        
    async def __call__(self, func: Callable, *args, **kwargs) -> Any:
        """Выполняет функцию с защитой Circuit Breaker"""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker entering half-open state")
            else:
                raise CircuitBreakerOpenException(
                    f"Circuit breaker is open. Last failure: {self.last_failure_time}"
                )
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Успешное выполнение - сбрасываем состояние
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.CLOSED
                logger.info("Circuit breaker closed after successful recovery")
            
            self.failure_count = 0
            return result
            
        except self.expected_exception as e:
            self._record_failure()
            raise e
    
    def _is_expected_exception(self, exc_type: Type[Exception]) -> bool:
        """Проверяет, является ли исключение ожидаемым"""
        if isinstance(self.expected_exception, tuple):
            return issubclass(exc_type, self.expected_exception)
        else:
            return issubclass(exc_type, self.expected_exception)
    
    def _record_failure(self):
        """Записывает ошибку и обновляет состояние"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures",
                extra={
                    "failure_count": self.failure_count,
                    "threshold": self.failure_threshold
                }
            )
    
    def _should_attempt_reset(self) -> bool:
        """Проверяет, можно ли попытаться восстановить соединение"""
        if self.last_failure_time is None:
            return True
        
        return (time.time() - self.last_failure_time) >= self.recovery_timeout
    
    def reset(self):
        """Принудительный сброс circuit breaker"""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
        logger.info("Circuit breaker manually reset")
    
    def get_status(self) -> dict:
        """Возвращает текущий статус circuit breaker"""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "recovery_timeout": self.recovery_timeout
        }


class CircuitBreakerOpenException(Exception):
    """Исключение, выбрасываемое когда circuit breaker открыт"""
    pass


# Алиас для совместимости
CircuitBreaker = SimpleCircuitBreaker
