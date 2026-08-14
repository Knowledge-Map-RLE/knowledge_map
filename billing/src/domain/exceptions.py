"""
Layer: Domain
Package: domain.exceptions
Responsibility: Доменные исключения микросервиса billing.
"""
from typing import Optional


class DomainError(Exception):
    """Базовое доменное исключение."""


class UnauthorizedError(DomainError):
    """Пользователь не аутентифицирован или токен невалиден."""


class PlanNotFoundError(DomainError):
    """Тариф не найден."""


class PaymentNotFoundError(DomainError):
    """Платёж не найден."""


class SubscriptionNotFoundError(DomainError):
    """Подписка не найдена."""


class InvalidPaymentTransitionError(DomainError):
    """Недопустимый переход состояния платежа."""

    def __init__(self, current: str, target: str):
        super().__init__(f"Invalid payment transition: {current} -> {target}")
        self.current = current
        self.target = target


class NotEnoughCreditsError(DomainError):
    """Недостаточно кредитов."""


class CheckoutError(DomainError):
    """Ошибка создания чекаута."""


class ProviderError(DomainError):
    """Ошибка внешнего платёжного провайдера."""

    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


class ProviderConfigurationError(ProviderError):
    """Провайдер не сконфигурирован (пустые shop_id/secret_key)."""


class WebhookError(DomainError):
    """Ошибка обработки вебхука провайдера."""
