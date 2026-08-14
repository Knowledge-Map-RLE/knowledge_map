"""
Layer: Frameworks & Drivers — Web
Package: web.dependencies
Responsibility: FastAPI-зависимости: аутентификация и DI use cases / репозиториев.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, Request

from application.access.check_access import CheckAccess
from application.checkout.create_checkout import CreateCheckout
from application.credits.credit_operations import CreditOperations
from application.payments.list_payments import ListPayments
from application.payments.refund_payment import RefundPayment
from application.ports.payment_gateway import PaymentProviderProtocol
from application.ports.repositories import (
    CreditRepositoryProtocol,
    PaymentEventRepositoryProtocol,
    PaymentRepositoryProtocol,
    PlanRepositoryProtocol,
    RefundRepositoryProtocol,
    SubscriptionRepositoryProtocol,
)
from application.plans.list_plans import ListPlans
from application.subscriptions.cancel_subscription import CancelSubscription
from application.subscriptions.get_subscription import GetSubscription
from application.webhooks.process_provider_event import ProcessProviderEvent
from config import settings
from domain.exceptions import UnauthorizedError
from infrastructure.auth_grpc_client import AuthClient, auth_client


@dataclass(frozen=True)
class Actor:
    user_id: str
    source: str  # "bearer" | "internal"


def get_payment_gateway(request: Request) -> PaymentProviderProtocol:
    return request.app.state.payment_gateway


def get_plan_repository() -> PlanRepositoryProtocol:
    from adapters.repositories.plan_repository import PlanRepository
    return PlanRepository()


def get_subscription_repository() -> SubscriptionRepositoryProtocol:
    from adapters.repositories.subscription_repository import SubscriptionRepository
    return SubscriptionRepository()


def get_payment_repository() -> PaymentRepositoryProtocol:
    from adapters.repositories.payment_repository import PaymentRepository
    return PaymentRepository()


def get_payment_event_repository() -> PaymentEventRepositoryProtocol:
    from adapters.repositories.payment_event_repository import PaymentEventRepository
    return PaymentEventRepository()


def get_refund_repository() -> RefundRepositoryProtocol:
    from adapters.repositories.refund_repository import RefundRepository
    return RefundRepository()


def get_credit_repository() -> CreditRepositoryProtocol:
    from adapters.repositories.credit_repository import CreditRepository
    return CreditRepository()


def get_auth_client() -> AuthClient:
    return auth_client


def get_actor(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
) -> Actor:
    if x_internal_token and settings.INTERNAL_TOKEN and x_internal_token == settings.INTERNAL_TOKEN:
        user_id = request.query_params.get("user_id")
        if user_id:
            return Actor(user_id=user_id, source="internal")
        raise UnauthorizedError("Missing user_id with internal token")

    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")

    token = authorization[len("Bearer "):]
    result = auth_client.verify_token(token)
    if not result.get("valid") or not result.get("user"):
        raise UnauthorizedError("Invalid token")
    return Actor(user_id=result["user"]["uid"], source="bearer")


def get_checkout(request: Request) -> CreateCheckout:
    return CreateCheckout(
        plan_repository=get_plan_repository(),
        payment_repository=get_payment_repository(),
        payment_gateway=request.app.state.payment_gateway,
    )


def get_process_provider_event(request: Request) -> ProcessProviderEvent:
    return ProcessProviderEvent(
        payment_event_repository=get_payment_event_repository(),
        payment_repository=get_payment_repository(),
        refund_repository=get_refund_repository(),
        subscription_repository=get_subscription_repository(),
        plan_repository=get_plan_repository(),
        credit_repository=get_credit_repository(),
        payment_gateway=request.app.state.payment_gateway,
    )


def get_list_plans() -> ListPlans:
    return ListPlans(plan_repository=get_plan_repository())


def get_subscription_state() -> GetSubscription:
    return GetSubscription(
        subscription_repository=get_subscription_repository(),
        credit_repository=get_credit_repository(),
        plan_repository=get_plan_repository(),
    )


def get_cancel_subscription() -> CancelSubscription:
    return CancelSubscription(subscription_repository=get_subscription_repository())


def get_list_payments() -> ListPayments:
    return ListPayments(payment_repository=get_payment_repository())


def get_refund_payment(request: Request) -> RefundPayment:
    return RefundPayment(
        payment_repository=get_payment_repository(),
        refund_repository=get_refund_repository(),
        payment_gateway=request.app.state.payment_gateway,
    )


def get_credit_operations() -> CreditOperations:
    return CreditOperations(credit_repository=get_credit_repository())


def get_check_access() -> CheckAccess:
    return CheckAccess(subscription_repository=get_subscription_repository())
