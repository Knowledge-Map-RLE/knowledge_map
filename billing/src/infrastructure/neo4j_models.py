"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.neo4j_models
Responsibility: Neo4j-модели (neomodel) микросервиса billing.

Принадлежит слою Infrastructure. Доменные датаклассы (domain.models) —
источник истины; эти узлы — их персистентное представление.
"""
from datetime import datetime, timezone

from neomodel import (
    BooleanProperty,
    DateTimeProperty,
    IntegerProperty,
    JSONProperty,
    StringProperty,
    StructuredNode,
    UniqueIdProperty,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PlanNode(StructuredNode):
    __label__ = "Plan"

    code = StringProperty(required=True, unique_index=True)
    name = StringProperty(required=True)
    price_kopecks = IntegerProperty(required=True)
    currency = StringProperty(default="RUB")
    period = StringProperty(default="month")
    credit_limit = IntegerProperty(default=0)
    sort_order = IntegerProperty(default=0)
    is_active = BooleanProperty(default=True)


class SubscriptionNode(StructuredNode):
    __label__ = "Subscription"

    uid = UniqueIdProperty(primary_key=True)
    user_id = StringProperty(required=True, index=True)
    plan_code = StringProperty(required=True)
    status = StringProperty(required=True, index=True)
    started_at = DateTimeProperty(default=_utcnow)
    current_period_start = DateTimeProperty(default=_utcnow)
    current_period_end = DateTimeProperty(default=_utcnow)
    cancel_at_period_end = BooleanProperty(default=False)
    created_at = DateTimeProperty(default=_utcnow)


class PaymentNode(StructuredNode):
    __label__ = "Payment"

    uid = UniqueIdProperty(primary_key=True)
    user_id = StringProperty(required=True, index=True)
    subscription_uid = StringProperty(index=True)
    provider = StringProperty(default="yookassa")
    provider_payment_id = StringProperty(index=True)
    amount_kopecks = IntegerProperty(required=True)
    currency = StringProperty(default="RUB")
    status = StringProperty(required=True, index=True)
    confirmation_url = StringProperty()
    description = StringProperty()
    metadata = JSONProperty()
    created_at = DateTimeProperty(default=_utcnow)
    updated_at = DateTimeProperty(default=_utcnow)


class PaymentEventNode(StructuredNode):
    __label__ = "PaymentEvent"

    uid = UniqueIdProperty(primary_key=True)
    provider = StringProperty(required=True)
    external_event_id = StringProperty(required=True, unique_index=True)
    event_type = StringProperty(required=True)
    payload = JSONProperty()
    created_at = DateTimeProperty(default=_utcnow)
    processed_at = DateTimeProperty()


class RefundNode(StructuredNode):
    __label__ = "Refund"

    uid = UniqueIdProperty(primary_key=True)
    payment_uid = StringProperty(required=True, index=True)
    provider_refund_id = StringProperty(index=True)
    amount_kopecks = IntegerProperty(required=True)
    currency = StringProperty(default="RUB")
    status = StringProperty(required=True)
    created_at = DateTimeProperty(default=_utcnow)


class CreditAccountNode(StructuredNode):
    __label__ = "CreditAccount"

    uid = UniqueIdProperty(primary_key=True)
    user_id = StringProperty(required=True, unique_index=True)
    balance = IntegerProperty(default=0)
    created_at = DateTimeProperty(default=_utcnow)


class CreditTransactionNode(StructuredNode):
    __label__ = "CreditTransaction"

    uid = UniqueIdProperty(primary_key=True)
    account_uid = StringProperty(required=True, index=True)
    user_id = StringProperty(required=True, index=True)
    amount = IntegerProperty(required=True)
    type = StringProperty(required=True)
    reference_id = StringProperty(index=True)
    description = StringProperty()
    created_at = DateTimeProperty(default=_utcnow)
