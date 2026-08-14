"""
Layer: Frameworks & Drivers — Web
Package: web.routers.plans
"""
from typing import List

from fastapi import APIRouter, Depends

from application.plans.list_plans import ListPlans
from web.dependencies import get_list_plans

router = APIRouter(prefix="/billing/plans", tags=["plans"])


@router.get("")
async def list_plans(use_case: ListPlans = Depends(get_list_plans)) -> List[dict]:
    return [
        {
            "code": plan.code,
            "name": plan.name,
            "price": plan.price_kopecks / 100,
            "price_kopecks": plan.price_kopecks,
            "currency": plan.currency,
            "period": plan.period,
            "credit_limit": plan.credit_limit,
            "sort_order": plan.sort_order,
        }
        for plan in use_case.execute()
    ]
