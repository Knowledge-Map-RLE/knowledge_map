"""
Layer: Frameworks & Drivers — Web
Package: web.routers.health
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/billing/health")
async def billing_health():
    return JSONResponse(content={"status": "ok", "service": "billing"})
