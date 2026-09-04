"""
Layer: Application (Use Cases)
Package: application.ports.feedback_repository
 Responsibility: Protocol для репозитория обратной связи.

Принадлежит слою Application — зависит только от domain.models.
"""
from __future__ import annotations

from typing import Optional, Protocol

from domain.models.feedback import FeedbackDraft, FeedbackMessage, FeedbackTicket


class FeedbackRepositoryProtocol(Protocol):
    """Протокол репозитория обратной связи (structural subtyping)."""

    async def create_ticket(
        self,
        user_uid: str,
        browser_info: dict,
        app_version: str,
    ) -> FeedbackTicket: ...

    async def get_ticket(self, uid: str) -> Optional[FeedbackTicket]: ...

    async def list_tickets(
        self,
        *,
        user_uid: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FeedbackTicket]: ...

    async def update_ticket_status(
        self,
        uid: str,
        status: str,
    ) -> FeedbackTicket: ...

    async def add_message(
        self,
        ticket_uid: str,
        sender_uid: str,
        sender_type: str,
        text: str,
        image_s3_keys: list[str],
    ) -> FeedbackMessage: ...

    async def get_messages(
        self,
        ticket_uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeedbackMessage]: ...

    async def get_draft(self, user_uid: str) -> Optional[FeedbackDraft]: ...

    async def upsert_draft(
        self,
        user_uid: str,
        text: str,
    ) -> FeedbackDraft: ...

    async def delete_draft(self, user_uid: str) -> None: ...

    async def count_tickets(
        self,
        *,
        status: Optional[str] = None,
        user_uid: Optional[str] = None,
    ) -> int: ...
