"""Entry point for the Billing microservice.

Run with: poetry run python src/main.py
"""
import uvicorn

from config import settings

if __name__ == "__main__":
    uvicorn.run(
        "web.app:app",
        host=settings.BILLING_HOST,
        port=settings.BILLING_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
