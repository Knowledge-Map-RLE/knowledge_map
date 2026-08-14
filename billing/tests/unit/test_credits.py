"""Тесты операций с кредитами."""
import pytest

from application.credits.credit_operations import CreditOperations
from domain.exceptions import NotEnoughCreditsError


@pytest.fixture
def credit_ops(repos):
    return CreditOperations(credit_repository=repos["credits"])


def test_grant_and_balance(credit_ops):
    credit_ops.grant(user_id="user-1", amount=1000)
    assert credit_ops.get_balance(user_id="user-1") == 1000


def test_grant_twice(credit_ops):
    credit_ops.grant(user_id="user-1", amount=100)
    credit_ops.grant(user_id="user-1", amount=200)
    assert credit_ops.get_balance(user_id="user-1") == 300


def test_grant_rejects_non_positive(credit_ops):
    with pytest.raises(ValueError):
        credit_ops.grant(user_id="user-1", amount=0)


def test_deduct_success(credit_ops):
    credit_ops.grant(user_id="user-1", amount=100)
    credit_ops.deduct(user_id="user-1", amount=40)
    assert credit_ops.get_balance(user_id="user-1") == 60


def test_deduct_not_enough(credit_ops):
    credit_ops.grant(user_id="user-1", amount=10)
    with pytest.raises(NotEnoughCreditsError):
        credit_ops.deduct(user_id="user-1", amount=20)


def test_deduct_rejects_non_positive(credit_ops):
    with pytest.raises(ValueError):
        credit_ops.deduct(user_id="user-1", amount=0)


def test_list_transactions(credit_ops):
    credit_ops.grant(user_id="user-1", amount=100)
    credit_ops.deduct(user_id="user-1", amount=40)
    transactions = credit_ops.list_transactions(user_id="user-1")
    assert len(transactions) == 2
    assert transactions[0].amount == -40
    assert transactions[1].amount == 100


def test_deduct_idempotent_single_charge(credit_ops):
    credit_ops.grant(user_id="user-1", amount=100)
    credit_ops.deduct_idempotent(
        user_id="user-1", amount=30, reference_id="req-1", description="ai"
    )
    assert credit_ops.get_balance(user_id="user-1") == 70
    assert len(credit_ops.list_transactions(user_id="user-1")) == 2


def test_deduct_idempotent_repeat_no_double_charge(credit_ops):
    credit_ops.grant(user_id="user-1", amount=100)
    first = credit_ops.deduct_idempotent(
        user_id="user-1", amount=30, reference_id="req-1"
    )
    second = credit_ops.deduct_idempotent(
        user_id="user-1", amount=30, reference_id="req-1"
    )
    assert first.balance == 70
    assert second.balance == 70
    assert credit_ops.get_balance(user_id="user-1") == 70
    assert len(credit_ops.list_transactions(user_id="user-1")) == 2


def test_deduct_idempotent_different_references_charge_twice(credit_ops):
    credit_ops.grant(user_id="user-1", amount=100)
    credit_ops.deduct_idempotent(user_id="user-1", amount=30, reference_id="req-1")
    credit_ops.deduct_idempotent(user_id="user-1", amount=30, reference_id="req-2")
    assert credit_ops.get_balance(user_id="user-1") == 40


def test_deduct_idempotent_requires_reference(credit_ops):
    with pytest.raises(ValueError):
        credit_ops.deduct_idempotent(user_id="user-1", amount=10, reference_id="")
