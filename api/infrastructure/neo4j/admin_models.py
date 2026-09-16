"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.neo4j.admin_models
Responsibility: neomodel ORM-классы для admin-панели экономики.

Содержит модели для:
  - AI-провайдеров и версий тарифов
  - Расходов (ручных и автоматических)
  - Финансового плана
  - Журнала действий администратора
  - Сценариев запуска
  - Стадий развития

Allowed imports: neomodel, datetime, стандартная библиотека
Forbidden imports: fastapi, grpc, aioboto3, domain, application, adapters, web
"""
from datetime import datetime

from neomodel import (
    StructuredNode,
    StructuredRel,
    StringProperty,
    IntegerProperty,
    BooleanProperty,
    DateTimeProperty,
    FloatProperty,
    JSONProperty,
    RelationshipTo,
    RelationshipFrom,
    UniqueIdProperty,
)


# =============================================================================
# AI-провайдеры и версии тарифов
# =============================================================================


class AIProviderNode(StructuredNode):
    """AI-провайдер (cloudru, deepseek, sber, ...)."""

    uid = UniqueIdProperty(primary_key=True)
    name = StringProperty(required=True, unique_index=True)
    display_name = StringProperty(required=True)
    base_url = StringProperty()
    is_active = BooleanProperty(default=True)
    created_at = DateTimeProperty(default=datetime.utcnow)
    updated_at = DateTimeProperty(default=datetime.utcnow)

    price_versions = RelationshipTo(
        "ProviderPriceVersionNode", "HAS_PRICE_VERSION"
    )


class ProviderPriceVersionRel(StructuredRel):
    """Связь провайдера с версией тарифа."""
    pass


class ProviderPriceVersionNode(StructuredNode):
    """Версия тарифа AI-провайдера (ценовая история).

    Цены хранятся за 1M токенов в рублях (Decimal-строки).
    Каждый AIUsage event ссылается на price_version_uid — это гарантирует,
    что прошлые расходы не пересчитываются при изменении тарифа.
    """

    uid = UniqueIdProperty(primary_key=True)
    provider_uid = StringProperty(required=True, index=True)
    model = StringProperty(required=True, index=True)

    input_price_per_million = StringProperty(required=True)
    output_price_per_million = StringProperty(required=True)
    cache_input_price_per_million = StringProperty()
    currency = StringProperty(default="RUB")

    valid_from = DateTimeProperty(required=True, index=True)
    valid_to = DateTimeProperty()
    is_active = BooleanProperty(default=True, index=True)

    created_at = DateTimeProperty(default=datetime.utcnow)

    provider = RelationshipFrom(
        "AIProviderNode", "HAS_PRICE_VERSION", model=ProviderPriceVersionRel
    )


# =============================================================================
# Расходы
# =============================================================================


class ExpenseNode(StructuredNode):
    """Расход проекта (ручной или автоматический).

    category: infrastructure | ai_tokens | acquiring | advertising | tax | other
    is_fixed: True = постоянный (домен, S3, Compute), False = переменный (AI, эквайринг)
    """

    uid = UniqueIdProperty(primary_key=True)
    category = StringProperty(required=True, index=True)
    subcategory = StringProperty(default="")
    description = StringProperty(required=True)
    amount_kopecks = IntegerProperty(required=True)
    currency = StringProperty(default="RUB")
    period_start = DateTimeProperty(required=True, index=True)
    period_end = DateTimeProperty(required=True)
    is_recurring = BooleanProperty(default=False)
    is_fixed = BooleanProperty(default=False)
    source = StringProperty(default="manual")  # manual | auto
    created_by_uid = StringProperty(required=True, index=True)
    created_at = DateTimeProperty(default=datetime.utcnow)
    updated_at = DateTimeProperty(default=datetime.utcnow)


# =============================================================================
# Финансовый план
# =============================================================================


class FinancialPlanNode(StructuredNode):
    """Финансовый план проекта (плановые значения метрик).

    data_json хранит все плановые значения:
    {
      "period": "month",
      "target_users": 100,
      "target_paying_users": 10,
      "conversion_rate": 0.1,
      "avg_tokens_per_user": 50000000,
      "input_share": 0.6,
      "output_share": 0.3,
      "cache_share": 0.1,
      "input_price_per_million": 18.53,
      "output_price_per_million": 37.08,
      "cache_price_per_million": 5.56,
      "avg_check_rubles": 2000,
      "infrastructure_cost_rubles": 15000,
      "tax_rate": 0.06,
      "acquiring_rate": 0.02,
      "cac": 500,
      "advertising_cost_rubles": 10000,
      "target_revenue": 20000,
      "target_profit": 5000,
      "target_margin": 0.25
    }
    """

    uid = UniqueIdProperty(primary_key=True)
    version = IntegerProperty(required=True)
    name = StringProperty(required=True)
    data_json = StringProperty(required=True)
    is_active = BooleanProperty(default=True, index=True)
    created_by_uid = StringProperty(required=True)
    created_at = DateTimeProperty(default=datetime.utcnow)
    updated_at = DateTimeProperty(default=datetime.utcnow)


# =============================================================================
# Журнал действий администратора
# =============================================================================


class AdminAuditLogNode(StructuredNode):
    """Журнал действий администратора (аудит).

    Записывается при каждом изменении:
    - тарифов провайдеров
    - пакетов токенов
    - расходов
    - финансового плана
    """

    uid = UniqueIdProperty(primary_key=True)
    admin_uid = StringProperty(required=True, index=True)
    action = StringProperty(required=True, index=True)
    entity_type = StringProperty(required=True, index=True)
    entity_uid = StringProperty(index=True)
    old_value = StringProperty()
    new_value = StringProperty()
    created_at = DateTimeProperty(default=datetime.utcnow, index=True)


# =============================================================================
# Стадии развития и сценарии запуска
# =============================================================================


class StrategyStageNode(StructuredNode):
    """Стадия развития проекта (по количеству пользователей).

    user_count: 0, 1, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000
    data_json хранит расчётные показатели для стадии.
    """

    uid = UniqueIdProperty(primary_key=True)
    user_count = IntegerProperty(required=True, unique_index=True)
    stage_name = StringProperty(required=True)
    data_json = StringProperty(default="{}")
    created_by_uid = StringProperty(required=True)
    created_at = DateTimeProperty(default=datetime.utcnow)
    updated_at = DateTimeProperty(default=datetime.utcnow)


class LaunchScenarioNode(StructuredNode):
    """Сценарий запуска (Telegram-публикация).

    params_json хранит параметры расчёта:
    {
      "audience_size": 20000,
      "view_rate": 0.3,
      "click_rate": 0.05,
      "registration_rate": 0.5,
      "conversion_rates": [0.0, 0.0001, 0.0003, 0.0005, 0.001, 0.005, 0.01, 0.02, 0.05],
      "avg_check_rubles": 2000,
      "ai_cost_per_user_rubles": 100,
      "cac_rubles": 0,
      "advertising_cost_rubles": 0
    }
    """

    uid = UniqueIdProperty(primary_key=True)
    name = StringProperty(required=True)
    params_json = StringProperty(required=True)
    created_by_uid = StringProperty(required=True)
    created_at = DateTimeProperty(default=datetime.utcnow)
    updated_at = DateTimeProperty(default=datetime.utcnow)
