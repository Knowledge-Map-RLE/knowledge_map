from __future__ import annotations

import logging

from src.domain.models import Statement
from src.extractor.context import ExtractionContext
from src.extractor.rules import ALL_RULES
from src.parser.dep_tree import DependencyTree

logger = logging.getLogger(__name__)


class RuleEngine:
    def __init__(self, rules: list | None = None):
        self._rules = list(rules or ALL_RULES)

    def register_rule(self, rule) -> None:
        self._rules.append(rule)
        logger.info("Registered rule: %s", rule.name)

    def process_sentence(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        matched_rules = [r for r in self._rules if r.matches(tree)]

        if not matched_rules:
            logger.debug("No rule matched: %s", ctx.sentence_text[:80])
            return []

        statements: list[Statement] = []
        seen_hashes: set[int] = set()

        for rule in matched_rules:
            try:
                extracted = rule.extract(tree, ctx)
                for stmt in extracted:
                    h = hash((stmt.subject_id, stmt.predicate, stmt.object_id, stmt.type.value))
                    if h not in seen_hashes:
                        seen_hashes.add(h)
                        statements.append(stmt)
            except Exception:
                logger.exception("Rule %s failed on: %s", rule.name, ctx.sentence_text[:80])

        return statements
