"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin
Responsibility: Агрегатор admin-роутеров — собирает все под-эндпоинты под /api/admin.

Allowed imports: fastapi, web.routers.admin.*
Forbidden imports: neomodel, domain (напрямую)
"""
from fastapi import APIRouter
from web.routers.admin.dashboard import router as dashboard_router
from web.routers.admin.users import router as users_router
from web.routers.admin.tokens import router as tokens_router
from web.routers.admin.sales import router as sales_router
from web.routers.admin.expenses import router as expenses_router
from web.routers.admin.providers import router as providers_router
from web.routers.admin.plan import router as plan_router
from web.routers.admin.strategy import router as strategy_router
from web.routers.admin.unit_economics import router as unit_economics_router
from web.routers.admin.launch import router as launch_router
from web.routers.admin.audit import router as audit_router

admin_router = APIRouter()
admin_router.include_router(dashboard_router, prefix="/dashboard", tags=["admin-dashboard"])
admin_router.include_router(users_router, prefix="/users", tags=["admin-users"])
admin_router.include_router(tokens_router, prefix="/tokens", tags=["admin-tokens"])
admin_router.include_router(sales_router, prefix="/sales", tags=["admin-sales"])
admin_router.include_router(expenses_router, prefix="/expenses", tags=["admin-expenses"])
admin_router.include_router(providers_router, prefix="/providers", tags=["admin-providers"])
admin_router.include_router(plan_router, prefix="/plan", tags=["admin-plan"])
admin_router.include_router(strategy_router, prefix="/strategy", tags=["admin-strategy"])
admin_router.include_router(unit_economics_router, prefix="/unit-economics", tags=["admin-unit-economics"])
admin_router.include_router(launch_router, prefix="/launch", tags=["admin-launch"])
admin_router.include_router(audit_router, prefix="/audit", tags=["admin-audit"])
