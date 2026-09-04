"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.feedback_repository
 Responsibility: neomodel-реализация FeedbackRepositoryProtocol.

Принадлежит слою Interface Adapters: транслирует между доменными dataclass-ами
(domain.models.feedback) и ORM-моделями (infrastructure.neo4j.orm_models).
Удовлетворяет протоколу structural subtyping.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.feedback
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from neomodel import db

from infrastructure.neo4j.orm_models import (
    FeedbackTicket as OrmTicket,
    FeedbackMessage as OrmMessage,
    FeedbackDraft as OrmDraft,
)
from domain.models.feedback import FeedbackDraft, FeedbackMessage, FeedbackTicket
from src.uuid8 import uuid8_str

logger = logging.getLogger(__name__)


def _now() -> float:
    import time
    return time.time()


def _ticket_to_domain(orm: OrmTicket) -> FeedbackTicket:
    return FeedbackTicket(
        uid=orm.uid,
        user_uid=orm.user_uid,
        status=orm.status or "new",
        browser_info=json.loads(orm.browser_info) if orm.browser_info else {},
        app_version=orm.app_version or "",
        created_at=orm.created_at or 0.0,
        updated_at=orm.updated_at or 0.0,
    )


def _message_to_domain(orm: OrmMessage) -> FeedbackMessage:
    return FeedbackMessage(
        uid=orm.uid,
        ticket_uid=orm.ticket_uid,
        sender_uid=orm.sender_uid,
        sender_type=orm.sender_type,
        text=orm.text or "",
        image_s3_keys=json.loads(orm.image_s3_keys) if orm.image_s3_keys else [],
        created_at=orm.created_at or 0.0,
    )


def _draft_to_domain(orm: OrmDraft) -> FeedbackDraft:
    return FeedbackDraft(
        user_uid=orm.user_uid,
        text=orm.text or "",
        updated_at=orm.updated_at or 0.0,
    )


class FeedbackRepository:
    """neomodel-реализация репозитория обратной связи."""

    # ── Tickets ────────────────────────────────────────────────────────────

    async def create_ticket(
        self,
        user_uid: str,
        browser_info: dict,
        app_version: str,
    ) -> FeedbackTicket:
        now = _now()
        orm = OrmTicket(
            uid=uuid8_str(),
            user_uid=user_uid,
            status="new",
            browser_info=json.dumps(browser_info, ensure_ascii=False),
            app_version=app_version,
            created_at=now,
            updated_at=now,
        )
        orm.save()
        logger.info(f"Feedback ticket created: {orm.uid} by {user_uid}")
        return _ticket_to_domain(orm)

    async def get_ticket(self, uid: str) -> Optional[FeedbackTicket]:
        orm = OrmTicket.nodes.get_or_none(uid=uid)
        return _ticket_to_domain(orm) if orm else None

    async def list_tickets(
        self,
        *,
        user_uid: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FeedbackTicket]:
        query = "MATCH (t:FeedbackTicket) WHERE 1=1"
        params: dict = {}

        if user_uid:
            query += " AND t.user_uid = $user_uid"
            params["user_uid"] = user_uid
        if status:
            query += " AND t.status = $status"
            params["status"] = status

        query += " RETURN t ORDER BY t.created_at DESC SKIP $skip LIMIT $limit"
        params["skip"] = offset
        params["limit"] = limit

        result, _ = db.cypher_query(query, params)
        tickets: list[FeedbackTicket] = []
        for row in result:
            node = row[0]
            tickets.append(
                FeedbackTicket(
                    uid=str(node.get("uid", "")),
                    user_uid=str(node.get("user_uid", "")),
                    status=str(node.get("status", "new")),
                    browser_info=json.loads(str(node.get("browser_info", "{}"))),
                    app_version=str(node.get("app_version", "")),
                    created_at=float(node.get("created_at") or 0.0),
                    updated_at=float(node.get("updated_at") or 0.0),
                )
            )
        return tickets

    async def update_ticket_status(
        self,
        uid: str,
        status: str,
    ) -> FeedbackTicket:
        orm = OrmTicket.nodes.get_or_none(uid=uid)
        if not orm:
            raise ValueError(f"Ticket {uid} not found")
        orm.status = status
        orm.updated_at = _now()
        orm.save()
        return _ticket_to_domain(orm)

    # ── Messages ───────────────────────────────────────────────────────────

    async def add_message(
        self,
        ticket_uid: str,
        sender_uid: str,
        sender_type: str,
        text: str,
        image_s3_keys: list[str],
    ) -> FeedbackMessage:
        orm = OrmMessage(
            uid=uuid8_str(),
            ticket_uid=ticket_uid,
            sender_uid=sender_uid,
            sender_type=sender_type,
            text=text,
            image_s3_keys=json.dumps(image_s3_keys, ensure_ascii=False),
            created_at=_now(),
        )
        orm.save()
        db.cypher_query(
            "MATCH (t:FeedbackTicket) WHERE t.uid = $tid "
            "MATCH (m:FeedbackMessage) WHERE m.uid = $mid "
            "MERGE (t)-[:HAS_MESSAGE]->(m)",
            {"tid": ticket_uid, "mid": orm.uid},
        )
        # обновляем updated_at на тикете
        ticket_orm = OrmTicket.nodes.get_or_none(uid=ticket_uid)
        if ticket_orm:
            ticket_orm.updated_at = _now()
            ticket_orm.save()
        return _message_to_domain(orm)

    async def get_messages(
        self,
        ticket_uid: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeedbackMessage]:
        result, _ = db.cypher_query(
            "MATCH (t:FeedbackTicket)-[:HAS_MESSAGE]->(m:FeedbackMessage) "
            "WHERE t.uid = $tid "
            "RETURN m ORDER BY m.created_at ASC SKIP $skip LIMIT $limit",
            {"tid": ticket_uid, "skip": offset, "limit": limit},
        )
        messages: list[FeedbackMessage] = []
        for row in result:
            node = row[0]
            messages.append(
                FeedbackMessage(
                    uid=str(node.get("uid", "")),
                    ticket_uid=ticket_uid,
                    sender_uid=str(node.get("sender_uid", "")),
                    sender_type=str(node.get("sender_type", "")),
                    text=str(node.get("text", "")),
                    image_s3_keys=json.loads(str(node.get("image_s3_keys", "[]"))),
                    created_at=float(node.get("created_at") or 0.0),
                )
            )
        return messages

    # ── Drafts ─────────────────────────────────────────────────────────────

    async def get_draft(self, user_uid: str) -> Optional[FeedbackDraft]:
        orm = OrmDraft.nodes.get_or_none(user_uid=user_uid)
        return _draft_to_domain(orm) if orm else None

    async def upsert_draft(
        self,
        user_uid: str,
        text: str,
    ) -> FeedbackDraft:
        orm = OrmDraft.nodes.get_or_none(user_uid=user_uid)
        now = _now()
        if orm:
            orm.text = text
            orm.updated_at = now
            orm.save()
        else:
            orm = OrmDraft(
                user_uid=user_uid,
                text=text,
                updated_at=now,
            )
            orm.save()
        return _draft_to_domain(orm)

    async def delete_draft(self, user_uid: str) -> None:
        orm = OrmDraft.nodes.get_or_none(user_uid=user_uid)
        if orm:
            orm.delete()

    # ── Counts ─────────────────────────────────────────────────────────────

    async def count_tickets(
        self,
        *,
        status: Optional[str] = None,
        user_uid: Optional[str] = None,
    ) -> int:
        query = "MATCH (t:FeedbackTicket) WHERE 1=1"
        params: dict = {}
        if status:
            query += " AND t.status = $status"
            params["status"] = status
        if user_uid:
            query += " AND t.user_uid = $user_uid"
            params["user_uid"] = user_uid
        query += " RETURN count(t) as cnt"
        result, _ = db.cypher_query(query, params)
        return int(result[0][0]) if result else 0
