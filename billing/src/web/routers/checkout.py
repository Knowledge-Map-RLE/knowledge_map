"""
Layer: Frameworks & Drivers — Web
Package: web.routers.checkout
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from application.checkout.create_checkout import CreateCheckout
from config import settings
from domain.exceptions import CheckoutError
from web.dependencies import Actor, get_actor, get_checkout

router = APIRouter(prefix="/billing", tags=["checkout"])


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=16)


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest,
    actor: Actor = Depends(get_actor),
    use_case: CreateCheckout = Depends(get_checkout),
) -> dict:
    result = await use_case.execute(
        user_id=actor.user_id,
        plan_code=body.plan_code.upper(),
        return_url=settings.YOOKASSA_RETURN_URL,
    )
    if not result.confirmation_url:
        raise CheckoutError("Provider did not return confirmation URL")
    return {
        "payment_uid": result.payment_uid,
        "confirmation_url": result.confirmation_url,
    }
