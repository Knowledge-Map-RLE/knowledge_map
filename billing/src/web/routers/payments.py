"""
Layer: Frameworks & Drivers — Web
Package: web.routers.payments
"""
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from application.payments.list_payments import ListPayments
from application.payments.refund_payment import RefundPayment
from web.dependencies import Actor, get_actor, get_list_payments, get_refund_payment

router = APIRouter(prefix="/billing/payments", tags=["payments"])


@router.get("")
async def list_payments(
    actor: Actor = Depends(get_actor),
    use_case: ListPayments = Depends(get_list_payments),
) -> List[dict]:
    return [
        {
            "uid": payment.uid,
            "amount_kopecks": payment.amount_kopecks,
            "currency": payment.currency,
            "status": payment.status,
            "description": payment.description,
            "created_at": payment.created_at.isoformat(),
        }
        for payment in use_case.execute(user_id=actor.user_id)
    ]


class RefundRequest(BaseModel):
    payment_uid: str


@router.post("/refund")
async def refund_payment(
    body: RefundRequest,
    actor: Actor = Depends(get_actor),
    use_case: RefundPayment = Depends(get_refund_payment),
) -> dict:
    result = await use_case.execute(user_id=actor.user_id, payment_uid=body.payment_uid)
    return {
        "refund_uid": result.refund_uid,
        "provider_refund_id": result.provider_refund_id,
        "status": result.status,
    }
