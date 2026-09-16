"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin
Responsibility: Административные эндпоинты биллинга (внутренний доступ).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from config import settings
from domain.exceptions import UnauthorizedError
from infrastructure.neo4j_models import (
    CreditAccountNode,
    CreditTransactionNode,
    PaymentNode,
    PlanNode,
    SubscriptionNode,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing/admin", tags=["admin"])


def _require_internal_token(
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
) -> None:
    if not x_internal_token or not settings.INTERNAL_TOKEN or x_internal_token != settings.INTERNAL_TOKEN:
        raise UnauthorizedError("Invalid or missing X-Internal-Token")


@router.get("/payments")
async def list_all_payments(
    offset: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    plan_code: Optional[str] = None,
    _actor: None = Depends(_require_internal_token),
) -> dict:
    filters: dict = {}
    if status:
        filters["status"] = status
    if user_id:
        filters["user_id"] = user_id

    nodes: list = list(PaymentNode.nodes.filter(**filters).order_by("-created_at"))

    if plan_code:
        sub_uids = {
            s.uid
            for s in SubscriptionNode.nodes.filter(plan_code=plan_code)
        }
        nodes = [n for n in nodes if n.subscription_uid and n.subscription_uid in sub_uids]

    total = len(nodes)
    page = nodes[offset : offset + limit]

    return {
        "payments": [
            {
                "uid": node.uid,
                "user_id": node.user_id,
                "subscription_uid": node.subscription_uid,
                "provider": node.provider,
                "provider_payment_id": node.provider_payment_id,
                "amount_kopecks": node.amount_kopecks,
                "currency": node.currency,
                "status": node.status,
                "description": node.description,
                "created_at": node.created_at.isoformat() if node.created_at else None,
                "updated_at": node.updated_at.isoformat() if node.updated_at else None,
            }
            for node in page
        ],
        "total": total,
    }


@router.get("/subscriptions")
async def list_all_subscriptions(
    status: Optional[str] = None,
    plan_code: Optional[str] = None,
    _actor: None = Depends(_require_internal_token),
) -> List[dict]:
    filters: dict = {}
    if status:
        filters["status"] = status
    if plan_code:
        filters["plan_code"] = plan_code

    nodes = list(SubscriptionNode.nodes.filter(**filters).order_by("-created_at"))

    return [
        {
            "uid": node.uid,
            "user_id": node.user_id,
            "plan_code": node.plan_code,
            "status": node.status,
            "started_at": node.started_at.isoformat() if node.started_at else None,
            "current_period_start": node.current_period_start.isoformat() if node.current_period_start else None,
            "current_period_end": node.current_period_end.isoformat() if node.current_period_end else None,
            "cancel_at_period_end": node.cancel_at_period_end,
            "created_at": node.created_at.isoformat() if node.created_at else None,
        }
        for node in nodes
    ]


@router.get("/credits/transactions")
async def list_all_credit_transactions(
    user_id: Optional[str] = None,
    type: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    _actor: None = Depends(_require_internal_token),
) -> dict:
    filters: dict = {}
    if user_id:
        filters["user_id"] = user_id
    if type:
        filters["type"] = type

    nodes = list(CreditTransactionNode.nodes.filter(**filters).order_by("-created_at"))

    total = len(nodes)
    page = nodes[offset : offset + limit]

    return {
        "transactions": [
            {
                "uid": node.uid,
                "account_uid": node.account_uid,
                "user_id": node.user_id,
                "amount": node.amount,
                "type": node.type,
                "reference_id": node.reference_id,
                "description": node.description,
                "created_at": node.created_at.isoformat() if node.created_at else None,
            }
            for node in page
        ],
        "total": total,
    }


@router.get("/users/summary")
async def user_financial_summary(
    user_id: Optional[str] = None,
    _actor: None = Depends(_require_internal_token),
) -> List[dict]:
    account_filters: dict = {}
    if user_id:
        account_filters["user_id"] = user_id

    accounts = list(CreditAccountNode.nodes.filter(**account_filters))
    target_user_ids = [a.user_id for a in accounts]

    if user_id:
        payments = list(PaymentNode.nodes.filter(user_id=user_id))
        subscriptions = list(SubscriptionNode.nodes.filter(user_id=user_id))
    else:
        payments = list(PaymentNode.nodes.all())
        subscriptions = list(SubscriptionNode.nodes.all())

    payments_by_user: dict[str, list] = {}
    for p in payments:
        payments_by_user.setdefault(p.user_id, []).append(p)

    active_subs_by_user: dict[str, SubscriptionNode] = {}
    for s in subscriptions:
        if s.status == "active":
            existing = active_subs_by_user.get(s.user_id)
            if existing is None or (s.current_period_end and (existing.current_period_end is None or s.current_period_end > existing.current_period_end)):
                active_subs_by_user[s.user_id] = s

    account_map = {a.user_id: a for a in accounts}

    if not target_user_ids:
        all_user_ids = {p.user_id for p in payments} | {s.user_id for s in subscriptions}
        for uid in all_user_ids:
            if uid not in account_map:
                target_user_ids.append(uid)

    summaries = []
    for uid in sorted(target_user_ids):
        user_payments = payments_by_user.get(uid, [])
        total_paid = sum(p.amount_kopecks for p in user_payments)
        account = account_map.get(uid)
        sub = active_subs_by_user.get(uid)

        summaries.append({
            "user_id": uid,
            "payments_count": len(user_payments),
            "total_paid_kopecks": total_paid,
            "total_paid": total_paid / 100,
            "credit_balance": account.balance if account else 0,
            "subscription_status": sub.status if sub else None,
            "subscription_plan": sub.plan_code if sub else None,
        })

    return summaries
