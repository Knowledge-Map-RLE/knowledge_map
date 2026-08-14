"""
Layer: Frameworks & Drivers — Web
Package: web.exception_handlers
Responsibility: Маппинг доменных исключений в HTTP-ответы.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from domain.exceptions import (
    DomainError,
    NotEnoughCreditsError,
    PlanNotFoundError,
    ProviderConfigurationError,
    ProviderError,
    SubscriptionNotFoundError,
    UnauthorizedError,
    WebhookError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnauthorizedError)
    async def _unauthorized(request: Request, exc: UnauthorizedError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(PlanNotFoundError)
    async def _plan_not_found(request: Request, exc: PlanNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SubscriptionNotFoundError)
    async def _subscription_not_found(request: Request, exc: SubscriptionNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(NotEnoughCreditsError)
    async def _not_enough_credits(request: Request, exc: NotEnoughCreditsError) -> JSONResponse:
        return JSONResponse(status_code=402, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def _provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        logger.error("Provider error: %s", exc)
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(ProviderConfigurationError)
    async def _provider_configuration_error(request: Request, exc: ProviderConfigurationError) -> JSONResponse:
        logger.warning("Provider not configured: %s", exc)
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(WebhookError)
    async def _webhook_error(request: Request, exc: WebhookError) -> JSONResponse:
        logger.warning("Webhook rejected: %s", exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        logger.warning("Domain error: %s", exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})
