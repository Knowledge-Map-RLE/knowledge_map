"""Тесты машины состояний платежа."""
import pytest

from domain.exceptions import InvalidPaymentTransitionError
from domain.models.payment import PaymentStatus
from domain.rules.payment_state import can_transition, transition


@pytest.mark.parametrize(
    "current,target,expected",
    [
        (PaymentStatus.CREATED, PaymentStatus.PENDING, True),
        (PaymentStatus.CREATED, PaymentStatus.FAILED, True),
        (PaymentStatus.CREATED, PaymentStatus.SUCCEEDED, False),
        (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED, True),
        (PaymentStatus.PENDING, PaymentStatus.FAILED, True),
        (PaymentStatus.PENDING, PaymentStatus.CREATED, False),
        (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, True),
        (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED, False),
        (PaymentStatus.FAILED, PaymentStatus.SUCCEEDED, False),
        (PaymentStatus.REFUNDED, PaymentStatus.PENDING, False),
    ],
)
def test_can_transition(current, target, expected):
    assert can_transition(current, target) is expected


def test_transition_success():
    assert transition(PaymentStatus.PENDING, PaymentStatus.SUCCEEDED) == PaymentStatus.SUCCEEDED


def test_transition_rejects_invalid():
    with pytest.raises(InvalidPaymentTransitionError):
        transition(PaymentStatus.CREATED, PaymentStatus.SUCCEEDED)
