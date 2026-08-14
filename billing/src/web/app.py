"""
Layer: Frameworks & Drivers — Web
Package: web.app
Responsibility: Фабрика FastAPI-приложения billing.

Точка сборки: роутеры, CORS, обработчики исключений, Neo4j,
сид тарифов и фоновая сверка платежей.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neomodel import config as neomodel_config

from config import settings
from infrastructure.seeding import seed_plans
from web.exception_handlers import register_exception_handlers

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def _configure_neo4j() -> None:
    database_url = settings.get_database_url()
    neomodel_config.DATABASE_URL = database_url
    if not settings.NEO4J_URI.startswith(("bolt+s://", "neo4j+s://")):
        neomodel_config.ENCRYPTED = False
    logger.info("Neo4j: %s", settings.NEO4J_URI)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_neo4j()

    from adapters.payment.lazy_gateway import LazyPaymentGateway

    app.state.payment_gateway = LazyPaymentGateway(
        shop_id=settings.YOOKASSA_SHOP_ID,
        secret_key=settings.YOOKASSA_SECRET_KEY,
        api_url=settings.YOOKASSA_API_URL,
    )

    try:
        seed_plans()
    except Exception:
        logger.exception("Failed to seed plans (Neo4j not ready?)")

    reconciliation_task = None
    if settings.RECONCILIATION_INTERVAL_SECONDS > 0:
        from infrastructure.reconciliation import reconciliation_loop

        from application.webhooks.process_provider_event import ProcessProviderEvent
        from adapters.repositories.credit_repository import CreditRepository
        from adapters.repositories.payment_event_repository import PaymentEventRepository
        from adapters.repositories.payment_repository import PaymentRepository
        from adapters.repositories.plan_repository import PlanRepository
        from adapters.repositories.refund_repository import RefundRepository
        from adapters.repositories.subscription_repository import SubscriptionRepository

        processor = ProcessProviderEvent(
            payment_event_repository=PaymentEventRepository(),
            payment_repository=PaymentRepository(),
            refund_repository=RefundRepository(),
            subscription_repository=SubscriptionRepository(),
            plan_repository=PlanRepository(),
            credit_repository=CreditRepository(),
            payment_gateway=app.state.payment_gateway,
        )
        reconciliation_task = asyncio.create_task(
            reconciliation_loop(
                payment_repository=PaymentRepository(),
                payment_gateway=app.state.payment_gateway,
                process_provider_event=processor,
                interval_seconds=settings.RECONCILIATION_INTERVAL_SECONDS,
            )
        )

    logger.info("Billing application started on port %s", settings.BILLING_PORT)
    try:
        yield
    finally:
        if reconciliation_task is not None:
            reconciliation_task.cancel()
        gateway = getattr(app.state, "payment_gateway", None)
        close = getattr(gateway, "close", None)
        if close:
            try:
                close()
            except Exception:
                pass


app = FastAPI(
    title="Knowledge Map Billing",
    description="Подписки, платежи (ЮKassa) и кредиты",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

from web.routers import access, checkout, credits, health, payments, plans, subscriptions, webhooks  # noqa: E402

app.include_router(health.router)
app.include_router(plans.router)
app.include_router(checkout.router)
app.include_router(subscriptions.router)
app.include_router(payments.router)
app.include_router(credits.router)
app.include_router(access.router)
app.include_router(webhooks.router)


@app.get("/")
async def root():
    return {"message": "Knowledge Map Billing", "docs": "/docs", "health": "/billing/health"}
