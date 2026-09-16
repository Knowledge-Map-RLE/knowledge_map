"""
Seed data script for the admin panel.
Creates test data for local development.

Usage:
    poetry run python scripts/seed_admin_data.py
    poetry run python scripts/seed_admin_data.py --clear
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from neomodel import config as neo_config, db

from infrastructure.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SEED_ADMIN_UID = "seed-admin-script"
PERIOD_START = "2026-09-01T00:00:00Z"
PERIOD_END = "2026-09-30T23:59:59Z"


# ═══════════════════════════════════════════════════════════════════════
# Connection
# ═══════════════════════════════════════════════════════════════════════


def connect() -> None:
    """Establish Neo4j connection via neomodel."""
    neo_config.DATABASE_URL = settings.get_database_url()
    logger.info("Connected to Neo4j: %s", settings.NEO4J_URI)


# ═══════════════════════════════════════════════════════════════════════
# AI Providers & Price Versions
# ═══════════════════════════════════════════════════════════════════════

PROVIDERS: list[dict[str, Any]] = [
    {
        "uid": "seed-prov-cloudru",
        "name": "cloudru",
        "display_name": "Cloud.ru Foundation Models",
        "prices": [
            {
                "uid": "seed-pv-cloudru-v4flash",
                "model": "deepseek-ai/DeepSeek-V4-Flash",
                "input_price": "18.53",
                "output_price": "37.08",
            },
        ],
    },
    {
        "uid": "seed-prov-deepseek",
        "name": "deepseek",
        "display_name": "DeepSeek API",
        "prices": [
            {
                "uid": "seed-pv-deepseek-v3",
                "model": "deepseek-ai/DeepSeek-V3",
                "input_price": "2.19",
                "output_price": "8.78",
            },
        ],
    },
]


def seed_providers() -> None:
    """Create AI providers and their price versions (MERGE upsert)."""
    logger.info("Seeding AI providers...")

    for prov in PROVIDERS:
        results, _ = db.cypher_query(
            "MERGE (p:AIProviderNode {name: $name}) "
            "SET p.uid = coalesce(p.uid, $uid), "
            "    p.display_name = $display_name, "
            "    p.is_active = $active, "
            "    p.updated_at = datetime() "
            "RETURN p.uid AS uid",
            {
                "name": prov["name"],
                "uid": prov["uid"],
                "display_name": prov["display_name"],
                "active": True,
            },
        )
        provider_uid: str = results[0][0]
        logger.info("  Provider: %s (uid=%s)", prov["display_name"], provider_uid)

        for price in prov["prices"]:
            db.cypher_query(
                "MERGE (v:ProviderPriceVersionNode {uid: $uid}) "
                "SET v.provider_uid = $provider_uid, "
                "    v.model = $model, "
                "    v.input_price_per_million = $input_price, "
                "    v.output_price_per_million = $output_price, "
                "    v.currency = 'RUB', "
                "    v.valid_from = datetime(), "
                "    v.is_active = true, "
                "    v.created_at = datetime() "
                "RETURN v.uid",
                {
                    "uid": price["uid"],
                    "provider_uid": provider_uid,
                    "model": price["model"],
                    "input_price": price["input_price"],
                    "output_price": price["output_price"],
                },
            )
            db.cypher_query(
                "MATCH (p:AIProviderNode {uid: $provider_uid}) "
                "MATCH (v:ProviderPriceVersionNode {uid: $version_uid}) "
                "MERGE (p)-[:HAS_PRICE_VERSION]->(v)",
                {"provider_uid": provider_uid, "version_uid": price["uid"]},
            )
            logger.info(
                "    Price: %s  input=%s RUB/1M  output=%s RUB/1M",
                price["model"],
                price["input_price"],
                price["output_price"],
            )


# ═══════════════════════════════════════════════════════════════════════
# Expenses
# ═══════════════════════════════════════════════════════════════════════


EXPENSES: list[dict[str, Any]] = [
    {
        "uid": "seed-exp-domain",
        "category": "infrastructure",
        "subcategory": "domain",
        "description": "Domain knowledge-map.ru",
        "amount_kopecks": 150_000,
        "is_recurring": True,
        "is_fixed": True,
        "source": "manual",
    },
    {
        "uid": "seed-exp-compute",
        "category": "infrastructure",
        "subcategory": "compute",
        "description": "Compute Cloud (VDS)",
        "amount_kopecks": 450_000,
        "is_recurring": True,
        "is_fixed": True,
        "source": "manual",
    },
    {
        "uid": "seed-exp-s3",
        "category": "infrastructure",
        "subcategory": "storage",
        "description": "Object Storage (S3)",
        "amount_kopecks": 120_000,
        "is_recurring": True,
        "is_fixed": True,
        "source": "manual",
    },
    {
        "uid": "seed-exp-cdn",
        "category": "infrastructure",
        "subcategory": "cdn",
        "description": "CDN (Selectel)",
        "amount_kopecks": 80_000,
        "is_recurring": True,
        "is_fixed": True,
        "source": "manual",
    },
    {
        "uid": "seed-exp-ads-telegram",
        "category": "advertising",
        "subcategory": "telegram",
        "description": "Advertising (Telegram)",
        "amount_kopecks": 1_000_000,
        "is_recurring": False,
        "is_fixed": False,
        "source": "manual",
    },
    {
        "uid": "seed-exp-ads-vk",
        "category": "advertising",
        "subcategory": "vk",
        "description": "Advertising (VK)",
        "amount_kopecks": 500_000,
        "is_recurring": False,
        "is_fixed": False,
        "source": "manual",
    },
    {
        "uid": "seed-exp-ai-tokens",
        "category": "ai_tokens",
        "subcategory": "cloudru",
        "description": "AI tokens (cloud.ru) — auto-generated",
        "amount_kopecks": 350_000,
        "is_recurring": False,
        "is_fixed": False,
        "source": "auto",
    },
    {
        "uid": "seed-exp-acquiring",
        "category": "acquiring",
        "subcategory": "tinkoff",
        "description": "Acquiring fees (Tinkoff) — auto-generated",
        "amount_kopecks": 40_000,
        "is_recurring": False,
        "is_fixed": False,
        "source": "auto",
    },
]


def seed_expenses() -> None:
    """Create expense records (MERGE upsert)."""
    logger.info("Seeding expenses...")

    for exp in EXPENSES:
        db.cypher_query(
            "MERGE (e:ExpenseNode {uid: $uid}) "
            "SET e.category = $category, "
            "    e.subcategory = $subcategory, "
            "    e.description = $description, "
            "    e.amount_kopecks = $amount_kopecks, "
            "    e.currency = 'RUB', "
            "    e.period_start = datetime($period_start), "
            "    e.period_end = datetime($period_end), "
            "    e.is_recurring = $is_recurring, "
            "    e.is_fixed = $is_fixed, "
            "    e.source = $source, "
            "    e.created_by_uid = $created_by_uid, "
            "    e.updated_at = datetime() "
            "RETURN e.uid",
            {
                "uid": exp["uid"],
                "category": exp["category"],
                "subcategory": exp["subcategory"],
                "description": exp["description"],
                "amount_kopecks": exp["amount_kopecks"],
                "period_start": PERIOD_START,
                "period_end": PERIOD_END,
                "is_recurring": exp["is_recurring"],
                "is_fixed": exp["is_fixed"],
                "source": exp["source"],
                "created_by_uid": SEED_ADMIN_UID,
            },
        )
        amount_rub = exp["amount_kopecks"] / 100
        recurring = "recurring" if exp["is_recurring"] else "one-time"
        fixed = "fixed" if exp["is_fixed"] else "variable"
        logger.info(
            "  Expense: %s — %.2f RUB (%s, %s)",
            exp["description"],
            amount_rub,
            recurring,
            fixed,
        )


# ═══════════════════════════════════════════════════════════════════════
# Financial Plan
# ═══════════════════════════════════════════════════════════════════════


FINANCIAL_PLAN_DATA: dict[str, Any] = {
    "period": "month",
    "target_users": 100,
    "target_paying_users": 10,
    "conversion_rate": 0.1,
    "avg_tokens_per_user": 50_000_000,
    "input_share": 0.6,
    "output_share": 0.3,
    "cache_share": 0.1,
    "input_price_per_million": 18.53,
    "output_price_per_million": 37.08,
    "cache_price_per_million": 5.56,
    "avg_check_rubles": 2000,
    "infrastructure_cost_rubles": 7200,
    "tax_rate": 0.06,
    "acquiring_rate": 0.02,
    "cac": 500,
    "advertising_cost_rubles": 10000,
    "target_revenue": 20000,
    "target_profit": 5000,
    "target_margin": 0.25,
}


def seed_financial_plan() -> None:
    """Create the financial plan (MERGE upsert)."""
    logger.info("Seeding financial plan...")

    data_json_str = json.dumps(FINANCIAL_PLAN_DATA, ensure_ascii=False)

    db.cypher_query(
        "MERGE (fp:FinancialPlanNode {uid: $uid}) "
        "SET fp.name = $name, "
        "    fp.version = $version, "
        "    fp.data_json = $data_json, "
        "    fp.is_active = $is_active, "
        "    fp.created_by_uid = $created_by_uid, "
        "    fp.updated_at = datetime() "
        "RETURN fp.uid",
        {
            "uid": "seed-fp-model-v1",
            "name": "Модель v1",
            "version": 1,
            "data_json": data_json_str,
            "is_active": True,
            "created_by_uid": SEED_ADMIN_UID,
        },
    )
    logger.info('  Plan: "Модель v1" (uid=seed-fp-model-v1)')


# ═══════════════════════════════════════════════════════════════════════
# Strategy Stages
# ═══════════════════════════════════════════════════════════════════════


STRATEGY_STAGE_COUNTS: list[int] = [
    0, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000,
]


def seed_strategy_stages() -> None:
    """Create strategy stages (MERGE upsert on user_count)."""
    logger.info("Seeding strategy stages...")

    for count in STRATEGY_STAGE_COUNTS:
        stage_name = f"{count} users"
        uid = f"seed-stage-{count}"
        data_json = json.dumps({"user_count": count})

        db.cypher_query(
            "MERGE (s:StrategyStageNode {user_count: $user_count}) "
            "SET s.uid = coalesce(s.uid, $uid), "
            "    s.stage_name = $stage_name, "
            "    s.data_json = $data_json, "
            "    s.created_by_uid = $created_by_uid, "
            "    s.updated_at = datetime() "
            "RETURN s.uid",
            {
                "user_count": count,
                "uid": uid,
                "stage_name": stage_name,
                "data_json": data_json,
                "created_by_uid": SEED_ADMIN_UID,
            },
        )
        logger.info("  Stage: %s (uid=%s)", stage_name, uid)


# ═══════════════════════════════════════════════════════════════════════
# Launch Scenario
# ═══════════════════════════════════════════════════════════════════════


LAUNCH_SCENARIO_PARAMS: dict[str, Any] = {
    "audience_size": 20000,
    "conversion_rates": [0, 0.0001, 0.0003, 0.0005, 0.001, 0.005, 0.01, 0.02, 0.05],
}


def seed_launch_scenario() -> None:
    """Create the launch scenario (MERGE upsert)."""
    logger.info("Seeding launch scenario...")

    params_json_str = json.dumps(LAUNCH_SCENARIO_PARAMS, ensure_ascii=False)

    db.cypher_query(
        "MERGE (ls:LaunchScenarioNode {uid: $uid}) "
        "SET ls.name = $name, "
        "    ls.params_json = $params_json, "
        "    ls.created_by_uid = $created_by_uid, "
        "    ls.updated_at = datetime() "
        "RETURN ls.uid",
        {
            "uid": "seed-launch-tg-v1",
            "name": "Telegram Launch v1",
            "params_json": params_json_str,
            "created_by_uid": SEED_ADMIN_UID,
        },
    )
    logger.info('  Scenario: "Telegram Launch v1" (uid=seed-launch-tg-v1)')


# ═══════════════════════════════════════════════════════════════════════
# Clear
# ═══════════════════════════════════════════════════════════════════════


def clear_seed_data() -> None:
    """Remove all seed data nodes (uid STARTS WITH 'seed-')."""
    logger.info("Clearing seed data...")

    labels = (
        "AIProviderNode",
        "ProviderPriceVersionNode",
        "ExpenseNode",
        "FinancialPlanNode",
        "StrategyStageNode",
        "LaunchScenarioNode",
    )
    label_filter = " OR ".join(f"n:{label}" for label in labels)

    result, _ = db.cypher_query(
        f"MATCH (n) WHERE ({label_filter}) AND n.uid STARTS WITH 'seed-' "
        "DETACH DELETE n "
        "RETURN count(n) AS deleted"
    )
    deleted = result[0][0] if result else 0
    logger.info("  Deleted %d seed nodes", deleted)


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed admin panel data for local development"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Remove all seed data and exit",
    )
    args = parser.parse_args()

    try:
        connect()
    except Exception as exc:
        logger.error("Failed to connect to Neo4j: %s", exc)
        return 1

    if args.clear:
        try:
            clear_seed_data()
        except Exception as exc:
            logger.error("Failed to clear seed data: %s", exc, exc_info=True)
            return 1
        return 0

    try:
        seed_providers()
        seed_expenses()
        seed_financial_plan()
        seed_strategy_stages()
        seed_launch_scenario()
        logger.info("Seed data creation complete.")
    except Exception as exc:
        logger.error("Seed data creation failed: %s", exc, exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
