"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.provider_repository
Responsibility: neomodel-реализация репозитория AI-провайдеров и тарифов.

Принадлежит слою Interface Adapters, потому что транслирует между
доменным языком (domain.models.admin.AIProvider, PriceVersion) и
ORM-деталями (neomodel AIProviderNode, ProviderPriceVersionNode).
Знает о neomodel, но application-слой — нет.

Цены за 1M токенов хранятся в Neo4j как Decimal-строки
(StringProperty) и транслируются обратно в Decimal.
При создании новой версии тарифа предыдущая активная версия
для той же модели автоматически деактивируется.

Класс реализует интерфейс репозитория без наследования от Protocol
(structural subtyping).

Allowed imports: neomodel, infrastructure.neo4j.admin_models, domain.models.*, domain.exceptions
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from neomodel import db, DoesNotExist

from infrastructure.neo4j.admin_models import AIProviderNode, ProviderPriceVersionNode
from domain.models.admin import AIProvider, PriceVersion
from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)


def _parse_datetime(value: Any) -> datetime:
    """Преобразует ISO-строку или datetime в datetime для neomodel."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _to_decimal(value: Any) -> Decimal:
    """Строку или число в Decimal."""
    return Decimal(str(value))


def _provider_to_domain(orm_provider: AIProviderNode) -> AIProvider:
    """Транслирует ORM-объект AIProviderNode в доменный dataclass."""
    return AIProvider(
        uid=orm_provider.uid,
        name=orm_provider.name,
        display_name=orm_provider.display_name,
        base_url=orm_provider.base_url,
        is_active=orm_provider.is_active or False,
        created_at=orm_provider.created_at.isoformat(),
        updated_at=orm_provider.updated_at.isoformat(),
    )


def _price_to_domain(orm_version: ProviderPriceVersionNode) -> PriceVersion:
    """Транслирует ORM-объект ProviderPriceVersionNode в доменный dataclass."""
    return PriceVersion(
        uid=orm_version.uid,
        provider_uid=orm_version.provider_uid,
        model=orm_version.model,
        input_price_per_million=_to_decimal(orm_version.input_price_per_million),
        output_price_per_million=_to_decimal(orm_version.output_price_per_million),
        cache_input_price_per_million=(
            _to_decimal(orm_version.cache_input_price_per_million)
            if orm_version.cache_input_price_per_million is not None
            else None
        ),
        currency=orm_version.currency or "RUB",
        valid_from=orm_version.valid_from.isoformat(),
        valid_to=orm_version.valid_to.isoformat() if orm_version.valid_to else None,
        is_active=orm_version.is_active or False,
        created_at=orm_version.created_at.isoformat(),
    )


class ProviderRepository:
    """
    neomodel-реализация репозитория AI-провайдеров и версий тарифов.
    Реализует интерфейс репозитория (structural subtyping).
    """

    def create_provider(self, data: dict) -> AIProvider:
        """Создаёт AI-провайдера и возвращает доменный AIProvider."""
        with db.transaction:
            orm_provider = AIProviderNode(
                name=str(data["name"]),
                display_name=str(data["display_name"]),
                base_url=str(data["base_url"]) if data.get("base_url") else None,
                is_active=bool(data.get("is_active", True)),
            )
            orm_provider.save()
            orm_provider.refresh()
            logger.info("AI-провайдер '%s' создан (%s)", orm_provider.uid, orm_provider.name)
            return _provider_to_domain(orm_provider)

    def get_provider(self, uid: str) -> Optional[AIProvider]:
        """Возвращает провайдера по uid или None."""
        try:
            orm_provider = AIProviderNode.nodes.get(uid=uid)
            return _provider_to_domain(orm_provider)
        except DoesNotExist:
            return None

    def get_all_providers(self) -> List[AIProvider]:
        """Возвращает всех AI-провайдеров."""
        providers = AIProviderNode.nodes.order_by("name")
        return [_provider_to_domain(p) for p in providers]

    def update_provider(self, uid: str, data: dict) -> Optional[AIProvider]:
        """Обновляет поля провайдера. Возвращает None, если не найден."""
        with db.transaction:
            try:
                orm_provider = AIProviderNode.nodes.get(uid=uid)
            except DoesNotExist:
                return None

            if "name" in data:
                orm_provider.name = str(data["name"])
            if "display_name" in data:
                orm_provider.display_name = str(data["display_name"])
            if "base_url" in data:
                orm_provider.base_url = str(data["base_url"]) if data["base_url"] else None
            if "is_active" in data:
                orm_provider.is_active = bool(data["is_active"])

            orm_provider.updated_at = datetime.utcnow()
            orm_provider.save()
            orm_provider.refresh()
            logger.info("AI-провайдер '%s' обновлён", orm_provider.uid)
            return _provider_to_domain(orm_provider)

    def create_price_version(self, provider_uid: str, data: dict) -> PriceVersion:
        """Создаёт версию тарифа провайдера.

        Деактивирует предыдущую активную версию для той же модели.
        """
        with db.transaction:
            try:
                orm_provider = AIProviderNode.nodes.get(uid=provider_uid)
            except DoesNotExist:
                raise NotFoundError("AIProvider", provider_uid)

            active_versions = ProviderPriceVersionNode.nodes.filter(
                provider_uid=provider_uid,
                model=str(data["model"]),
                is_active=True,
            )
            for version in active_versions:
                version.is_active = False
                version.save()
                logger.info(
                    "Тарифная версия '%s' деактивирована (модель '%s')",
                    version.uid,
                    version.model,
                )

            orm_version = ProviderPriceVersionNode(
                provider_uid=provider_uid,
                model=str(data["model"]),
                input_price_per_million=str(data["input_price_per_million"]),
                output_price_per_million=str(data["output_price_per_million"]),
                cache_input_price_per_million=(
                    str(data["cache_input_price_per_million"])
                    if data.get("cache_input_price_per_million") is not None
                    else None
                ),
                currency=str(data.get("currency", "RUB")),
                valid_from=_parse_datetime(data["valid_from"]),
                valid_to=(
                    _parse_datetime(data["valid_to"]) if data.get("valid_to") else None
                ),
                is_active=True,
            )
            orm_version.save()
            orm_version.refresh()
            orm_provider.price_versions.connect(orm_version)
            logger.info(
                "Тарифная версия '%s' создана (провайдер '%s', модель '%s')",
                orm_version.uid,
                provider_uid,
                orm_version.model,
            )
            return _price_to_domain(orm_version)

    def get_price_versions(self, provider_uid: str) -> List[PriceVersion]:
        """Возвращает все версии тарифов провайдера (новые первыми)."""
        versions = ProviderPriceVersionNode.nodes.filter(
            provider_uid=provider_uid
        ).order_by("-valid_from", "-created_at")
        return [_price_to_domain(v) for v in versions]

    def get_active_price_version(
        self, provider_uid: str, model: str
    ) -> Optional[PriceVersion]:
        """Возвращает активную версию тарифа для провайдера и модели."""
        version = (
            ProviderPriceVersionNode.nodes.filter(
                provider_uid=provider_uid,
                model=model,
                is_active=True,
            )
            .order_by("-valid_from")
            .first()
        )
        return _price_to_domain(version) if version else None

    def get_current_price_version_uid(self, model: str) -> Optional[str]:
        """Возвращает uid активной версии тарифа по имени модели."""
        query = (
            "MATCH (v:ProviderPriceVersion {model: $model, is_active: true}) "
            "RETURN v.uid AS uid ORDER BY v.valid_from DESC LIMIT 1"
        )
        result, _ = db.cypher_query(query, {"model": model})
        if not result:
            return None
        return str(result[0][0])