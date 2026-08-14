"""Тесты идемпотентной обработки событий провайдера (ProcessProviderEvent)."""
import pytest

from application.webhooks.process_provider_event import ProcessingResult, ProcessingStatus
from domain.exceptions import WebhookError
from domain.models import Refund
from domain.models.payment import PaymentStatus
from tests.conftest import make_processor, make_succeeded_event


@pytest.mark.asyncio
async def test_payment_succeeded_activates_subscription(repos, gateway, pro_payment):
    processor = make_processor(repos, gateway)

    result = await processor.execute(make_succeeded_event())

    assert result.status == ProcessingStatus.PROCESSED
    payment = repos["payments"].get_by_uid(pro_payment.uid)
    assert payment.status == PaymentStatus.SUCCEEDED
    assert repos["events"].get_by_external_event_id("pmt-1:payment.succeeded") is not None

    sub = repos["subscriptions"].get_active_by_user("user-1")
    assert sub is not None
    assert sub.plan_code == "PRO"

    assert repos["credits"].get_balance("user-1") == 10000


@pytest.mark.asyncio
async def test_duplicate_event_idempotent(repos, gateway, pro_payment):
    processor = make_processor(repos, gateway)
    event = make_succeeded_event()

    first = await processor.execute(event)
    second = await processor.execute(event)

    assert first.status == ProcessingStatus.PROCESSED
    assert second.status == ProcessingStatus.ALREADY_PROCESSED
    assert repos["credits"].get_balance("user-1") == 10000
    assert repos["subscriptions"].get_active_by_user("user-1").plan_code == "PRO"


@pytest.mark.asyncio
async def test_unsupported_event_ignored(repos, gateway, pro_payment):
    processor = make_processor(repos, gateway)

    result = await processor.execute(
        {"event": "payment.some_unknown", "object": {"id": "pmt-1"}}
    )

    assert result.status == ProcessingStatus.IGNORED
    assert repos["payments"].get_by_uid(pro_payment.uid).status == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_missing_fields_ignored(repos, gateway):
    processor = make_processor(repos, gateway)

    result = await processor.execute({})

    assert result.status == ProcessingStatus.IGNORED


@pytest.mark.asyncio
async def test_amount_mismatch_with_provider_rejected(repos, gateway, pro_payment):
    processor = make_processor(repos, gateway)

    event = make_succeeded_event(amount="100.00")

    with pytest.raises(WebhookError):
        await processor.execute(event)
    assert repos["payments"].get_by_uid(pro_payment.uid).status == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_stored_payment_amount_mismatch_rejected(repos, gateway, pro_payment):
    pro_payment.amount_kopecks = 100000
    repos["payments"].save(pro_payment)
    processor = make_processor(repos, gateway)

    result = await processor.execute(make_succeeded_event())

    assert result.status == ProcessingStatus.REJECTED
    assert repos["payments"].get_by_uid(pro_payment.uid).status == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_provider_verification_failure(repos, gateway, pro_payment):
    gateway.get_status = "canceled"
    processor = make_processor(repos, gateway)

    with pytest.raises(Exception):
        await processor.execute(make_succeeded_event())

    assert repos["payments"].get_by_uid(pro_payment.uid).status == PaymentStatus.PENDING


@pytest.mark.asyncio
async def test_payment_canceled(repos, gateway, pro_payment):
    processor = make_processor(repos, gateway)

    result = await processor.execute(
        {"event": "payment.canceled", "object": {"id": "pmt-1"}}
    )

    assert result.status == ProcessingStatus.PROCESSED
    assert repos["payments"].get_by_uid(pro_payment.uid).status == PaymentStatus.FAILED


@pytest.mark.asyncio
async def test_refund_succeeded(repos, gateway, pro_payment):
    pro_payment.status = PaymentStatus.SUCCEEDED
    repos["payments"].save(pro_payment)
    repos["refunds"].create(
        Refund(
            uid="ref-1",
            payment_uid=pro_payment.uid,
            amount_kopecks=150000,
            currency="RUB",
            status="PENDING",
            provider_refund_id="rfd-1",
        )
    )
    processor = make_processor(repos, gateway)

    result = await processor.execute(
        {"event": "refund.succeeded", "object": {"id": "rfd-1"}}
    )

    assert result.status == ProcessingStatus.PROCESSED
    refund = repos["refunds"].get_by_provider_refund_id("rfd-1")
    assert refund.status == "SUCCEEDED"
    assert repos["payments"].get_by_uid(pro_payment.uid).status == PaymentStatus.REFUNDED


@pytest.mark.asyncio
async def test_refund_unknown_ignored(repos, gateway):
    processor = make_processor(repos, gateway)

    result = await processor.execute(
        {"event": "refund.succeeded", "object": {"id": "no-such-refund"}}
    )

    assert result.status == ProcessingStatus.IGNORED


@pytest.mark.asyncio
async def test_reconstructs_payment_from_event_when_missing(repos, gateway):
    processor = make_processor(repos, gateway)

    result = await processor.execute(make_succeeded_event(provider_id="pmt-new"))

    assert result.status == ProcessingStatus.PROCESSED
    payment = repos["payments"].get_by_provider_id("pmt-new")
    assert payment is not None
    assert repos["credits"].get_balance("user-1") == 10000


def test_processing_result_statuses():
    assert ProcessingResult(ProcessingStatus.PROCESSED).status == "processed"
