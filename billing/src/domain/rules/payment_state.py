"""
Layer: Domain
Package: domain.rules.payment_state
Responsibility: Машина состояний платежа.
"""
from ..exceptions import InvalidPaymentTransitionError
from ..models.payment import PaymentStatus

_TRANSITIONS = {
    PaymentStatus.CREATED: {PaymentStatus.PENDING, PaymentStatus.FAILED},
    PaymentStatus.PENDING: {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED},
    PaymentStatus.SUCCEEDED: {PaymentStatus.REFUNDED},
    PaymentStatus.FAILED: set(),
    PaymentStatus.REFUNDED: set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, set())


def transition(current: str, target: str) -> str:
    if not can_transition(current, target):
        raise InvalidPaymentTransitionError(current, target)
    return target
