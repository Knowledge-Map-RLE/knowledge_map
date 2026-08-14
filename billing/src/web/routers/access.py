"""
Layer: Frameworks & Drivers — Web
Package: web.routers.access
"""
from fastapi import APIRouter, Depends, Query

from application.access.check_access import CheckAccess
from domain.rules.time import utcnow
from web.dependencies import Actor, get_actor, get_check_access

router = APIRouter(prefix="/billing/access", tags=["access"])


@router.get("")
async def check_access(
    required_plan: str = Query(..., min_length=1, max_length=16),
    actor: Actor = Depends(get_actor),
    use_case: CheckAccess = Depends(get_check_access),
) -> dict:
    decision = use_case.execute(
        user_id=actor.user_id,
        required_plan=required_plan.upper(),
        now=utcnow(),
    )
    return {
        "allowed": decision.allowed,
        "plan_code": decision.plan_code,
        "required_plan": decision.required_plan,
        "reason": decision.reason,
    }
