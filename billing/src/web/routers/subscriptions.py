"""
Layer: Frameworks & Drivers — Web
Package: web.routers.subscriptions
"""
from fastapi import APIRouter, Depends

from application.subscriptions.cancel_subscription import CancelSubscription
from application.subscriptions.get_subscription import GetSubscription
from domain.rules.time import utcnow
from web.dependencies import Actor, get_actor, get_cancel_subscription, get_subscription_state

router = APIRouter(prefix="/billing/subscription", tags=["subscriptions"])


@router.get("")
async def subscription_state(
    actor: Actor = Depends(get_actor),
    use_case: GetSubscription = Depends(get_subscription_state),
) -> dict:
    state = use_case.execute(user_id=actor.user_id, now=utcnow())
    return {
        "active": state.active,
        "plan_code": state.plan_code,
        "status": state.status,
        "current_period_start": state.current_period_start,
        "current_period_end": state.current_period_end,
        "cancel_at_period_end": state.cancel_at_period_end,
        "credits": {
            "balance": state.credits_balance,
            "limit": state.credits_limit,
        },
    }


@router.post("/cancel")
async def cancel_subscription(
    actor: Actor = Depends(get_actor),
    use_case: CancelSubscription = Depends(get_cancel_subscription),
) -> dict:
    use_case.execute(user_id=actor.user_id, now=utcnow())
    return {"status": "cancelled_at_period_end"}
