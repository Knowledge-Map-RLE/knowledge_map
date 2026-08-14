"""
Layer: Tests
Package: tests.conftest
Responsibility: Фейковые репозитории/гейтвей и фабрики для юнит-тестов
без Neo4j и без внешних платёжных API.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytest

from application.checkout.create_checkout import CreateCheckout
from application.ports.payment_gateway import GatewayPayment
from application.webhooks.process_provider_event import ProcessProviderEvent
from domain.models import (
    CreditAccount,
    CreditTransaction,
    Payment,
    PaymentEvent,
    Plan,
    Refund,
    Subscription,
)

FREE_PLAN = Plan(
    code="FREE",
    name="Free",
    price_kopecks=0,
    credit_limit=100,
    sort_order=0,
)
PRO_PLAN = Plan(
    code="PRO",
    name="Pro",
    price_kopecks=150000,
    credit_limit=10000,
    sort_order=1,
)
MAX_PLAN = Plan(
    code="MAX",
    name="Max",
    price_kopecks=2000000,
    credit_limit=200000,
    sort_order=2,
)


class FakePlanRepository:
    def __init__(self, plans: Optional[List[Plan]] = None):
        self.plans = {p.code: p for p in (plans or [FREE_PLAN, PRO_PLAN, MAX_PLAN])}

    def list_active(self) -> List[Plan]:
        return [p for p in self.plans.values() if p.is_active]

    def get_by_code(self, code: str) -> Optional[Plan]:
        return self.plans.get(code)


class FakeSubscriptionRepository:
    def __init__(self):
        self._by_uid: Dict[str, Subscription] = {}
        self._by_user: Dict[str, Subscription] = {}

    def get_active_by_user(self, user_id: str) -> Optional[Subscription]:
        sub = self._by_user.get(user_id)
        return _copy(sub)

    def get_by_uid(self, uid: str) -> Optional[Subscription]:
        return _copy(self._by_uid.get(uid))

    def list_by_user(self, user_id: str) -> List[Subscription]:
        sub = self._by_user.get(user_id)
        return [_copy(sub)] if sub else []

    def save(self, subscription: Subscription) -> Subscription:
        self._by_uid[subscription.uid] = _copy(subscription)
        self._by_user[subscription.user_id] = _copy(subscription)
        return _copy(subscription)


class FakePaymentRepository:
    def __init__(self):
        self._by_uid: Dict[str, Payment] = {}
        self._by_provider: Dict[str, Payment] = {}

    def create(self, payment: Payment) -> Payment:
        self._by_uid[payment.uid] = payment
        if payment.provider_payment_id:
            self._by_provider[payment.provider_payment_id] = payment
        return payment

    def save(self, payment: Payment) -> Payment:
        self._by_uid[payment.uid] = payment
        if payment.provider_payment_id:
            self._by_provider[payment.provider_payment_id] = payment
        return payment

    def get_by_uid(self, uid: str) -> Optional[Payment]:
        return self._by_uid.get(uid)

    def get_by_provider_id(self, provider_payment_id: str) -> Optional[Payment]:
        return self._by_provider.get(provider_payment_id)

    def list_by_user(self, user_id: str, limit: int = 50) -> List[Payment]:
        return [p for p in self._by_uid.values() if p.user_id == user_id][:limit]

    def list_pending_since(self, since: datetime) -> List[Payment]:
        return [
            p
            for p in self._by_uid.values()
            if p.status in ("CREATED", "PENDING") and p.created_at < since
        ]


class FakePaymentEventRepository:
    def __init__(self):
        self._by_external_id: Dict[str, PaymentEvent] = {}

    def get_by_external_event_id(self, external_event_id: str) -> Optional[PaymentEvent]:
        return self._by_external_id.get(external_event_id)

    def save(self, event: PaymentEvent) -> PaymentEvent:
        self._by_external_id[event.external_event_id] = event
        return event


class FakeRefundRepository:
    def __init__(self):
        self._by_uid: Dict[str, Refund] = {}
        self._by_provider: Dict[str, Refund] = {}

    def create(self, refund: Refund) -> Refund:
        self._by_uid[refund.uid] = refund
        if refund.provider_refund_id:
            self._by_provider[refund.provider_refund_id] = refund
        return refund

    def save(self, refund: Refund) -> Refund:
        self._by_uid[refund.uid] = refund
        if refund.provider_refund_id:
            self._by_provider[refund.provider_refund_id] = refund
        return refund

    def get_by_payment_uid(self, payment_uid: str) -> List[Refund]:
        return [r for r in self._by_uid.values() if r.payment_uid == payment_uid]

    def get_by_provider_refund_id(self, provider_refund_id: str) -> Optional[Refund]:
        return self._by_provider.get(provider_refund_id)


class FakeCreditRepository:
    def __init__(self):
        self._accounts: Dict[str, CreditAccount] = {}
        self._transactions: List[CreditTransaction] = []

    def get_or_create_account(self, user_id: str) -> CreditAccount:
        account = self._accounts.get(user_id)
        if account is None:
            account = CreditAccount(uid=f"acc-{user_id}", user_id=user_id, balance=0)
            self._accounts[user_id] = account
        return account

    def get_account(self, user_id: str) -> Optional[CreditAccount]:
        return self._accounts.get(user_id)

    def get_balance(self, user_id: str) -> int:
        account = self._accounts.get(user_id)
        return account.balance if account else 0

    def apply_transaction(self, transaction: CreditTransaction) -> CreditAccount:
        account = self._accounts.get(transaction.user_id)
        if account is None:
            account = self.get_or_create_account(transaction.user_id)
        account.balance += transaction.amount
        self._transactions.append(transaction)
        return account

    def list_transactions(self, user_id: str, limit: int = 50) -> List[CreditTransaction]:
        return [t for t in reversed(self._transactions) if t.user_id == user_id][:limit]

    def get_transaction_by_reference_id(
        self, reference_id: str
    ) -> Optional[CreditTransaction]:
        for t in reversed(self._transactions):
            if t.reference_id == reference_id:
                return t
        return None


class FakeGateway:
    """Фейковый платёжный шлюз с предсказуемым поведением."""

    def __init__(
        self,
        *,
        create_status: str = "pending",
        get_status: str = "succeeded",
        confirmation_url: str = "https://payment.example.com/confirm",
    ):
        self.create_status = create_status
        self.get_status = get_status
        self.confirmation_url = confirmation_url
        self.created: List[Dict] = []
        self.refunds: List[Dict] = []
        self._sequence = 0

    async def create_payment(
        self,
        *,
        amount_kopecks: int,
        currency: str,
        description: str,
        metadata: Dict,
        return_url: str,
        idempotency_key: str,
    ) -> GatewayPayment:
        self._sequence += 1
        provider_id = f"pmt-{self._sequence}"
        self.created.append(
            {
                "provider_id": provider_id,
                "amount_kopecks": amount_kopecks,
                "currency": currency,
                "metadata": metadata,
            }
        )
        return GatewayPayment(
            provider_payment_id=provider_id,
            status=self.create_status,
            amount_kopecks=amount_kopecks,
            currency=currency,
            confirmation_url=self.confirmation_url,
        )

    async def get_payment(self, provider_payment_id: str) -> GatewayPayment:
        last = self.created[-1] if self.created else None
        return GatewayPayment(
            provider_payment_id=provider_payment_id,
            status=self.get_status,
            amount_kopecks=last["amount_kopecks"] if last else 150000,
            currency=last["currency"] if last else "RUB",
        )

    async def create_refund(
        self,
        *,
        provider_payment_id: str,
        amount_kopecks: int,
        currency: str,
        idempotency_key: str,
    ) -> str:
        self._sequence += 1
        refund_id = f"rfd-{self._sequence}"
        self.refunds.append({"provider_payment_id": provider_payment_id, "amount_kopecks": amount_kopecks})
        return refund_id


def _copy(subscription: Optional[Subscription]) -> Optional[Subscription]:
    if subscription is None:
        return None
    import dataclasses

    return dataclasses.replace(subscription)


def make_repos(plans: Optional[List[Plan]] = None) -> Dict:
    return {
        "plans": FakePlanRepository(plans),
        "subscriptions": FakeSubscriptionRepository(),
        "payments": FakePaymentRepository(),
        "events": FakePaymentEventRepository(),
        "refunds": FakeRefundRepository(),
        "credits": FakeCreditRepository(),
    }


def make_checkout(repos: Dict, gateway: FakeGateway) -> CreateCheckout:
    return CreateCheckout(
        plan_repository=repos["plans"],
        payment_repository=repos["payments"],
        payment_gateway=gateway,
    )


def make_processor(repos: Dict, gateway: FakeGateway) -> ProcessProviderEvent:
    return ProcessProviderEvent(
        payment_event_repository=repos["events"],
        payment_repository=repos["payments"],
        refund_repository=repos["refunds"],
        subscription_repository=repos["subscriptions"],
        plan_repository=repos["plans"],
        credit_repository=repos["credits"],
        payment_gateway=gateway,
        transaction_factory=nullcontext,
    )


def make_succeeded_event(provider_id: str = "pmt-1", amount: str = "1500.00", **overrides) -> Dict:
    event = {
        "event": "payment.succeeded",
        "object": {
            "id": provider_id,
            "amount": {"value": amount, "currency": "RUB"},
            "metadata": {"user_id": "user-1", "plan_code": "PRO"},
        },
    }
    event["object"].update(overrides)
    return event


@pytest.fixture
def repos():
    return make_repos()


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
def pro_payment(repos) -> Payment:
    payment = Payment(
        uid="pay-1",
        user_id="user-1",
        amount_kopecks=150000,
        currency="RUB",
        status="PENDING",
        provider_payment_id="pmt-1",
        metadata={"user_id": "user-1", "plan_code": "PRO"},
    )
    repos["payments"].create(payment)
    return payment


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 1, 15, 12, 0, 0)
