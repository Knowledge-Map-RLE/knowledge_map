"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.ai_chat_repository
Responsibility: neomodel-реализация AIChatRepositoryProtocol.

Принадлежит слою Interface Adapters: транслирует между доменными dataclass-ами
(domain.models.ai_chat) и ORM-моделями (infrastructure.neo4j.orm_models).
Удовлетворяет протоколу structural subtyping.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.ai_chat
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from neomodel import db

from infrastructure.neo4j.orm_models import AIChat as OrmAIChat
from infrastructure.neo4j.orm_models import AIMessage as OrmAIMessage
from infrastructure.neo4j.orm_models import AIUsage as OrmAIUsage
from domain.models.ai_chat import AIChat, AIMessage, AIUsage

logger = logging.getLogger(__name__)


def _ts_to_datetime(value):
    """neomodel хранит DateTimeProperty в Neo4j как unix-число;
    при raw cypher-чтении конвертируем в naive UTC datetime (как возвращает ORM)."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)


def _chat_to_domain(orm: OrmAIChat) -> AIChat:
    return AIChat(
        uid=orm.uid,
        user_uid=orm.user_uid,
        title=orm.title or "",
        model=orm.model or "",
        created_at=orm.created_at,
        updated_at=orm.updated_at,
    )


def _message_to_domain(orm: OrmAIMessage) -> AIMessage:
    return AIMessage(
        uid=orm.uid,
        chat_uid=orm.chat.single().uid if orm.chat.single() else "",
        role=orm.role,
        content=orm.content,
        order=orm.order or 0,
        created_at=orm.created_at,
    )


def _usage_to_domain(orm: OrmAIUsage) -> AIUsage:
    return AIUsage(
        uid=orm.uid,
        message_uid=orm.message_uid,
        chat_uid=orm.chat_uid,
        user_uid=orm.user_uid,
        model=orm.model or "",
        provider_request_id=orm.provider_request_id,
        estimated_input_tokens=orm.estimated_input_tokens or 0,
        estimated_output_tokens=orm.estimated_output_tokens or 0,
        estimated_cached_tokens=orm.estimated_cached_tokens,
        estimated_cost=orm.estimated_cost or "0",
        actual_input_tokens=orm.actual_input_tokens or 0,
        actual_cached_tokens=orm.actual_cached_tokens or 0,
        actual_output_tokens=orm.actual_output_tokens or 0,
        actual_tool_tokens=orm.actual_tool_tokens or 0,
        actual_cost=orm.actual_cost or "0",
        currency=orm.actual_currency or "RUB",
        created_at=orm.created_at,
    )


class AIChatRepository:
    """neomodel-реализация репозитория AI-чатов."""

    def get_chat(self, chat_uid: str) -> Optional[AIChat]:
        orm = OrmAIChat.nodes.get_or_none(uid=chat_uid)
        return _chat_to_domain(orm) if orm else None

    def list_chats(self, user_uid: str, limit: int = 50) -> List[AIChat]:
        orms = (
            OrmAIChat.nodes.filter(user_uid=user_uid)
            .order_by("-updated_at")[:limit]
        )
        return [_chat_to_domain(o) for o in orms]

    def create_chat(self, chat: AIChat) -> AIChat:
        orm = OrmAIChat(
            uid=chat.uid,
            user_uid=chat.user_uid,
            title=chat.title,
            model=chat.model,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )
        orm.save()
        return _chat_to_domain(orm)

    def touch_chat(self, chat_uid: str) -> None:
        orm = OrmAIChat.nodes.get_or_none(uid=chat_uid)
        if orm:
            orm.updated_at = datetime.utcnow()
            orm.save()

    def list_messages(self, chat_uid: str, limit: int = 100) -> List[AIMessage]:
        result, _ = db.cypher_query(
            "MATCH (c:AIChat)-[:HAS_MESSAGE]->(m:AIMessage) "
            "WHERE c.uid = $cid "
            "RETURN m ORDER BY m.order LIMIT $limit",
            {"cid": chat_uid, "limit": limit},
        )
        messages: List[AIMessage] = []
        for row in result:
            node = row[0]
            messages.append(
                AIMessage(
                    uid=str(node.get("uid", "")),
                    chat_uid=chat_uid,
                    role=str(node.get("role", "")),
                    content=str(node.get("content", "")),
                    order=int(node.get("order") or 0),
                    created_at=_ts_to_datetime(node.get("created_at")),
                )
            )
        return messages

    def add_message(self, message: AIMessage) -> AIMessage:
        orm = OrmAIMessage(
            uid=message.uid,
            role=message.role,
            content=message.content,
            order=message.order,
            created_at=message.created_at,
        )
        orm.save()
        db.cypher_query(
            "MATCH (c:AIChat) WHERE c.uid = $cid "
            "MATCH (m:AIMessage) WHERE m.uid = $mid "
            "MERGE (c)-[:HAS_MESSAGE]->(m)",
            {"cid": message.chat_uid, "mid": message.uid},
        )
        return AIMessage(
            uid=orm.uid,
            chat_uid=message.chat_uid,
            role=orm.role,
            content=orm.content,
            order=orm.order or 0,
            created_at=orm.created_at,
        )

    def save_usage(self, usage: AIUsage) -> AIUsage:
        orm = OrmAIUsage(
            uid=usage.uid,
            message_uid=usage.message_uid,
            chat_uid=usage.chat_uid,
            user_uid=usage.user_uid,
            model=usage.model,
            provider_request_id=usage.provider_request_id,
            estimated_input_tokens=usage.estimated_input_tokens,
            estimated_output_tokens=usage.estimated_output_tokens,
            estimated_cached_tokens=usage.estimated_cached_tokens,
            estimated_cost=usage.estimated_cost,
            estimated_currency=usage.currency,
            actual_input_tokens=usage.actual_input_tokens,
            actual_cached_tokens=usage.actual_cached_tokens,
            actual_output_tokens=usage.actual_output_tokens,
            actual_tool_tokens=usage.actual_tool_tokens,
            actual_cost=usage.actual_cost,
            actual_currency=usage.currency,
            created_at=usage.created_at,
        )
        orm.save()
        db.cypher_query(
            "MATCH (m:AIMessage) WHERE m.uid = $mid "
            "MATCH (u:AIUsage) WHERE u.uid = $uid "
            "MERGE (m)-[:HAS_USAGE]->(u)",
            {"mid": usage.message_uid, "uid": usage.uid},
        )
        return _usage_to_domain(orm)

    def get_usage_by_provider_id(self, provider_request_id: str) -> Optional[AIUsage]:
        orm = OrmAIUsage.nodes.get_or_none(provider_request_id=provider_request_id)
        return _usage_to_domain(orm) if orm else None

    def list_usage_for_chat(self, chat_uid: str, limit: int = 100) -> List[AIUsage]:
        query = "MATCH (u:AIUsage) WHERE u.chat_uid = $chat_uid"
        params: dict = {"chat_uid": chat_uid, "limit": limit}
        query += " RETURN u ORDER BY u.created_at ASC LIMIT $limit"
        result, _ = db.cypher_query(query, params)
        usages: List[AIUsage] = []
        for row in result:
            node = row[0]
            usages.append(
                AIUsage(
                    uid=str(node.get("uid", "")),
                    message_uid=str(node.get("message_uid", "")),
                    chat_uid=str(node.get("chat_uid", "")),
                    user_uid=str(node.get("user_uid", "")),
                    model=str(node.get("model", "")),
                    provider_request_id=str(node.get("provider_request_id", "")),
                    estimated_input_tokens=int(node.get("estimated_input_tokens") or 0),
                    estimated_output_tokens=int(node.get("estimated_output_tokens") or 0),
                    estimated_cached_tokens=node.get("estimated_cached_tokens"),
                    estimated_cost=str(node.get("estimated_cost") or "0"),
                    actual_input_tokens=int(node.get("actual_input_tokens") or 0),
                    actual_cached_tokens=int(node.get("actual_cached_tokens") or 0),
                    actual_output_tokens=int(node.get("actual_output_tokens") or 0),
                    actual_tool_tokens=int(node.get("actual_tool_tokens") or 0),
                    actual_cost=str(node.get("actual_cost") or "0"),
                    currency=str(node.get("actual_currency") or "RUB"),
                    created_at=_ts_to_datetime(node.get("created_at")),
                )
            )
        return usages

    def list_usage_for_user(
        self,
        user_uid: str,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 100,
    ) -> List[AIUsage]:
        query = "MATCH (u:AIUsage) WHERE u.user_uid = $user_uid"
        params: dict = {"user_uid": user_uid, "limit": limit}
        if since:
            query += " AND u.created_at >= $since"
            params["since"] = since
        if until:
            query += " AND u.created_at <= $until"
            params["until"] = until
        query += " RETURN u ORDER BY u.created_at DESC LIMIT $limit"
        result, _ = db.cypher_query(query, params)
        usages: List[AIUsage] = []
        for row in result:
            node = row[0]
            usages.append(
                AIUsage(
                    uid=str(node.get("uid", "")),
                    message_uid=str(node.get("message_uid", "")),
                    chat_uid=str(node.get("chat_uid", "")),
                    user_uid=str(node.get("user_uid", "")),
                    model=str(node.get("model", "")),
                    provider_request_id=str(node.get("provider_request_id", "")),
                    estimated_input_tokens=int(node.get("estimated_input_tokens") or 0),
                    estimated_output_tokens=int(node.get("estimated_output_tokens") or 0),
                    estimated_cached_tokens=node.get("estimated_cached_tokens"),
                    estimated_cost=str(node.get("estimated_cost") or "0"),
                    actual_input_tokens=int(node.get("actual_input_tokens") or 0),
                    actual_cached_tokens=int(node.get("actual_cached_tokens") or 0),
                    actual_output_tokens=int(node.get("actual_output_tokens") or 0),
                    actual_tool_tokens=int(node.get("actual_tool_tokens") or 0),
                    actual_cost=str(node.get("actual_cost") or "0"),
                    currency=str(node.get("actual_currency") or "RUB"),
                    created_at=_ts_to_datetime(node.get("created_at")),
                )
            )
        return usages
