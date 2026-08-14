"""
Layer: Frameworks & Drivers — Web
Package: web.routers.credits
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from application.credits.credit_operations import CreditOperations
from domain.exceptions import NotEnoughCreditsError, UnauthorizedError
from web.dependencies import Actor, get_actor, get_credit_operations

router = APIRouter(prefix="/billing/credits", tags=["credits"])


class DeductRequest(BaseModel):
    amount: int = Field(gt=0)
    reference_id: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=255)


@router.get("")
async def credits_balance(
    actor: Actor = Depends(get_actor),
    use_case: CreditOperations = Depends(get_credit_operations),
) -> dict:
    account = use_case.get_account(user_id=actor.user_id)
    return {"balance": account.balance}


@router.post("/deduct")
async def deduct_credits(
    req: DeductRequest,
    actor: Actor = Depends(get_actor),
    use_case: CreditOperations = Depends(get_credit_operations),
) -> dict:
    """Списание кредитов за AI-запрос (идемпотентно по reference_id).

    Доступен только внутреннему сервису (api) через X-Internal-Token.
    Повторный вызов с тем же reference_id не списывает повторно.
    """
    if actor.source != "internal":
        raise UnauthorizedError("Deduct endpoint is internal-only")
    try:
        account = use_case.deduct_idempotent(
            user_id=actor.user_id,
            amount=req.amount,
            reference_id=req.reference_id,
            description=req.description,
        )
    except NotEnoughCreditsError:
        raise HTTPException(status_code=402, detail="not_enough_credits")
    return {
        "balance": account.balance,
        "deducted": req.amount,
        "idempotent": True,
    }


@router.get("/transactions")
async def credit_transactions(
    actor: Actor = Depends(get_actor),
    use_case: CreditOperations = Depends(get_credit_operations),
) -> List[dict]:
    return [
        {
            "uid": tx.uid,
            "amount": tx.amount,
            "type": tx.type,
            "reference_id": tx.reference_id,
            "description": tx.description,
            "created_at": tx.created_at.isoformat(),
        }
        for tx in use_case.list_transactions(user_id=actor.user_id)
    ]
