"""
Обертка над aiobreaker для совместимости с существующим кодом
"""

from datetime import timedelta
from typing import Any, Callable, Optional, Union, Type
from aiobreaker import CircuitBreaker as AioCircuitBreaker  # type: ignore
from aiobreaker import CircuitBreakerError  # type: ignore
import structlog  # type: ignore

logger = structlog.get_logger(__name__)


class CircuitBreakerState:
    """Состояния Circuit Breaker для совместимости"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Обертка над aiobreaker для совместимости с существующим кодом
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
        
        # Создаем aiobreaker
        self._breaker = AioCircuitBreaker(
            fail_max=failure_threshold,
            reset_timeout=timedelta(seconds=recovery_timeout),
            exclude=self._convert_exceptions(expected_exception)
        )
        
        # Добавляем слушатель для логирования
        self._breaker.add_listener(self._on_state_change)
    
    def _convert_exceptions(self, expected_exception: Union[Type[Exception], tuple]) -> list:
        """Конвертирует исключения в формат aiobreaker"""
        if isinstance(expected_exception, tuple):
            return list(expected_exception)
        elif expected_exception == Exception:
            return []  # aiobreaker по умолчанию ловит все исключения
        else:
            return [expected_exception]
    
    def _on_state_change(self, old_state, new_state):
        """Обработчик изменения состояния"""
        logger.info(
            f"Circuit breaker state changed from {old_state} to {new_state}",
            old_state=old_state,
            new_state=new_state
        )
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        # aiobreaker автоматически обрабатывает исключения
        return False
        
    async def __call__(self, func: Callable, *args, **kwargs) -> Any:
        """Выполняет функцию с защитой Circuit Breaker"""
        try:
            return await self._breaker.call(func, *args, **kwargs)
        except CircuitBreakerError as e:
            raise CircuitBreakerOpenException(str(e))
    
    @property
    def state(self) -> str:
        """Возвращает текущее состояние"""
        state_map = {
            'CLOSED': CircuitBreakerState.CLOSED,
            'OPEN': CircuitBreakerState.OPEN,
            'HALF_OPEN': CircuitBreakerState.HALF_OPEN
        }
        return state_map.get(self._breaker.current_state, CircuitBreakerState.CLOSED)
    
    @property
    def failure_count(self) -> int:
        """Возвращает количество ошибок"""
        return self._breaker.fail_counter
    
    @property
    def last_failure_time(self) -> Optional[float]:
        """Возвращает время последней ошибки"""
        if hasattr(self._breaker, 'last_failure_time') and self._breaker.last_failure_time:
            return self._breaker.last_failure_time.timestamp()
        return None
    
    def reset(self):
        """Принудительный сброс circuit breaker"""
        self._breaker.reset()
        logger.info("Circuit breaker manually reset")
    
    def get_status(self) -> dict:
        """Возвращает текущий статус circuit breaker"""
        return {
            "state": self.state,
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
