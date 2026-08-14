"""
Интеграционные тесты API billing через TestClient.

Используют DI-override на фейковые репозитории/гейтвей, чтобы не требовать
Neo4j и внешних сервисов. TestClient создаётся без контекста lifespan —
сид тарифов и фоновая сверка здесь не нужны.
"""
import pytest
from contextlib import nullcontext

from fastapi.testclient import TestClient
from tests.conftest import FakeGateway, make_repos
from web.app import app
from web.dependencies import (
    get_cancel_subscription,
    get_check_access,
    get_checkout,
    get_credit_operations,
    get_list_payments,
    get_list_plans,
    get_process_provider_event,
    get_refund_payment,
    get_subscription_state,
)


@pytest.fixture
def client():
    repos = make_repos()
    gateway = FakeGateway()

    from application.access.check_access import CheckAccess
    from application.checkout.create_checkout import CreateCheckout
    from application.credits.credit_operations import CreditOperations
    from application.payments.list_payments import ListPayments
    from application.payments.refund_payment import RefundPayment
    from application.plans.list_plans import ListPlans
    from application.subscriptions.cancel_subscription import CancelSubscription
    from application.subscriptions.get_subscription import GetSubscription
    from application.webhooks.process_provider_event import ProcessProviderEvent

    def _override_use_case(factory):
        return lambda: factory

    app.dependency_overrides[get_list_plans] = _override_use_case(
        ListPlans(plan_repository=repos["plans"])
    )
    app.dependency_overrides[get_checkout] = _override_use_case(
        CreateCheckout(
            plan_repository=repos["plans"],
            payment_repository=repos["payments"],
            payment_gateway=gateway,
        )
    )
    app.dependency_overrides[get_subscription_state] = _override_use_case(
        GetSubscription(
            subscription_repository=repos["subscriptions"],
            credit_repository=repos["credits"],
            plan_repository=repos["plans"],
        )
    )
    app.dependency_overrides[get_cancel_subscription] = _override_use_case(
        CancelSubscription(subscription_repository=repos["subscriptions"])
    )
    app.dependency_overrides[get_list_payments] = _override_use_case(
        ListPayments(payment_repository=repos["payments"])
    )
    app.dependency_overrides[get_refund_payment] = _override_use_case(
        RefundPayment(
            payment_repository=repos["payments"],
            refund_repository=repos["refunds"],
            payment_gateway=gateway,
        )
    )
    app.dependency_overrides[get_credit_operations] = _override_use_case(
        CreditOperations(credit_repository=repos["credits"])
    )
    app.dependency_overrides[get_check_access] = _override_use_case(
        CheckAccess(subscription_repository=repos["subscriptions"])
    )
    app.dependency_overrides[get_process_provider_event] = _override_use_case(
        ProcessProviderEvent(
            payment_event_repository=repos["events"],
            payment_repository=repos["payments"],
            refund_repository=repos["refunds"],
            subscription_repository=repos["subscriptions"],
            plan_repository=repos["plans"],
            credit_repository=repos["credits"],
            payment_gateway=gateway,
            transaction_factory=nullcontext,
        )
    )

    test_client = TestClient(app)
    yield test_client, repos, gateway

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _patch_internal_token(monkeypatch):
    monkeypatch.setattr("web.dependencies.settings.INTERNAL_TOKEN", "test-internal-token")


def _auth_headers() -> dict:
    return {"X-Internal-Token": "test-internal-token"}


def _get(client, path, user_id="user-1"):
    return client.get(path, headers=_auth_headers(), params={"user_id": user_id})


def _post(client, path, json, user_id="user-1"):
    return client.post(path, json=json, headers=_auth_headers(), params={"user_id": user_id})


def test_health(client):
    test_client, _, _ = client
    response = test_client.get("/billing/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_plans(client):
    test_client, _, _ = client
    response = test_client.get("/billing/plans")
    assert response.status_code == 200
    plans = response.json()
    assert {p["code"] for p in plans} == {"FREE", "PRO", "MAX"}
    pro = next(p for p in plans if p["code"] == "PRO")
    assert pro["price_kopecks"] == 150000


def test_checkout_requires_auth(client):
    test_client, _, _ = client
    response = test_client.post("/billing/checkout", json={"plan_code": "PRO"})
    assert response.status_code == 401


def test_checkout_flow(client):
    test_client, repos, _ = client
    response = _post(test_client, "/billing/checkout", {"plan_code": "PRO"})
    assert response.status_code == 200
    body = response.json()
    assert body["confirmation_url"].startswith("https://")
    assert repos["payments"].get_by_uid(body["payment_uid"]) is not None


def test_checkout_free_plan_returns_error(client):
    test_client, _, _ = client
    response = _post(test_client, "/billing/checkout", {"plan_code": "FREE"})
    assert response.status_code == 400


def test_subscription_state_free(client):
    test_client, _, _ = client
    response = _get(test_client, "/billing/subscription")
    assert response.status_code == 200
    body = response.json()
    assert body["plan_code"] == "FREE"
    assert body["active"] is False
    assert body["credits"]["limit"] == 100


def test_access_denied_without_subscription(client):
    test_client, _, _ = client
    response = _get(test_client, "/billing/access", user_id="user-1")
    response = test_client.get(
        "/billing/access",
        headers=_auth_headers(),
        params={"user_id": "user-1", "required_plan": "PRO"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason"] == "PLAN_REQUIRED:PRO"


def test_webhook_full_flow(client):
    test_client, repos, _ = client
    checkout = _post(test_client, "/billing/checkout", {"plan_code": "PRO"})
    payment = repos["payments"].get_by_uid(checkout.json()["payment_uid"])

    response = test_client.post(
        "/billing/webhooks/yookassa",
        json={
            "event": "payment.succeeded",
            "object": {
                "id": payment.provider_payment_id,
                "amount": {"value": "1500.00", "currency": "RUB"},
                "metadata": {"user_id": "user-1", "plan_code": "PRO"},
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processed"

    sub_response = _get(test_client, "/billing/subscription")
    assert sub_response.json()["plan_code"] == "PRO"
    assert sub_response.json()["credits"]["balance"] == 10000


def test_webhook_idempotent(client):
    test_client, repos, _ = client
    payload = {
        "event": "payment.succeeded",
        "object": {
            "id": "pmt-ext",
            "amount": {"value": "1500.00", "currency": "RUB"},
            "metadata": {"user_id": "user-1", "plan_code": "PRO"},
        },
    }
    first = test_client.post("/billing/webhooks/yookassa", json=payload)
    second = test_client.post("/billing/webhooks/yookassa", json=payload)
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "already_processed"
