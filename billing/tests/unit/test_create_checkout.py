"""Тесты CreateCheckout: создание платежа у провайдера и в репозитории."""
import pytest

from domain.exceptions import CheckoutError, PlanNotFoundError
from domain.models.payment import PaymentStatus
from tests.conftest import make_checkout


@pytest.mark.asyncio
async def test_checkout_success(repos, gateway):
    checkout = make_checkout(repos, gateway)

    result = await checkout.execute(
        user_id="user-1",
        plan_code="PRO",
        return_url="http://localhost:5555/subscription",
    )

    assert result.confirmation_url == "https://payment.example.com/confirm"
    assert result.provider_payment_id == "pmt-1"

    payment = repos["payments"].get_by_uid(result.payment_uid)
    assert payment is not None
    assert payment.user_id == "user-1"
    assert payment.amount_kopecks == 150000
    assert payment.status == PaymentStatus.PENDING
    assert payment.metadata == {"user_id": "user-1", "plan_code": "PRO"}


@pytest.mark.asyncio
async def test_checkout_unknown_plan(repos, gateway):
    checkout = make_checkout(repos, gateway)

    with pytest.raises(PlanNotFoundError):
        await checkout.execute(user_id="user-1", plan_code="NOPE", return_url="http://x")


@pytest.mark.asyncio
async def test_checkout_free_plan_rejected(repos, gateway):
    checkout = make_checkout(repos, gateway)

    with pytest.raises(CheckoutError):
        await checkout.execute(user_id="user-1", plan_code="FREE", return_url="http://x")


@pytest.mark.asyncio
async def test_checkout_provider_error_wrapped(repos, gateway):
    checkout = make_checkout(repos, gateway)

    class BoomGateway:
        async def create_payment(self, **kwargs):
            raise RuntimeError("boom")

    checkout = make_checkout(repos, BoomGateway())

    with pytest.raises(CheckoutError):
        await checkout.execute(user_id="user-1", plan_code="PRO", return_url="http://x")
