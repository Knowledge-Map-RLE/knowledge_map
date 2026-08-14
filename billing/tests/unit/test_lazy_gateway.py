"""Тесты ленивого платёжного gateway (LazyPaymentGateway)."""
import pytest

from adapters.payment.lazy_gateway import LazyPaymentGateway
from domain.exceptions import ProviderConfigurationError


@pytest.mark.asyncio
async def test_lazy_gateway_raises_without_keys():
    gateway = LazyPaymentGateway(shop_id="", secret_key="", api_url="https://api.example")
    with pytest.raises(ProviderConfigurationError):
        await gateway.create_payment(
            amount_kopecks=100,
            currency="RUB",
            description="test",
            metadata={},
            return_url="http://localhost:5555/subscription",
            idempotency_key="key-1",
        )


@pytest.mark.asyncio
async def test_lazy_gateway_raises_get_payment_without_keys():
    gateway = LazyPaymentGateway(shop_id="", secret_key="", api_url="https://api.example")
    with pytest.raises(ProviderConfigurationError):
        await gateway.get_payment("pay-1")


@pytest.mark.asyncio
async def test_lazy_gateway_raises_refund_without_keys():
    gateway = LazyPaymentGateway(shop_id="", secret_key="", api_url="https://api.example")
    with pytest.raises(ProviderConfigurationError):
        await gateway.create_refund(
            provider_payment_id="pay-1",
            amount_kopecks=100,
            currency="RUB",
            idempotency_key="key-2",
        )
