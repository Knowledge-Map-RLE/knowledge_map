from __future__ import annotations

import logging
import re

from src.domain.models import Statement, StatementType, StatementID, Concept
from src.extractor.context import ExtractionContext
from src.extractor.engine import RuleEngine
from src.meta.meta_builder import MetaBuilder
from src.normalizer.concept_normalizer import ConceptNormalizerImpl
from src.parser.dep_tree import DependencyTree
from src.parser.nlp_client import NLPClient
from src.serializer.serializer import Serializer
from src.validator.validator import Validator

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        nlp_client: NLPClient | None = None,
        rule_engine: RuleEngine | None = None,
        meta_builder: MetaBuilder | None = None,
        normalizer: ConceptNormalizerImpl | None = None,
        validator: Validator | None = None,
        serializer: Serializer | None = None,
    ):
        self._nlp = nlp_client or NLPClient()
        self._engine = rule_engine or RuleEngine()
        self._meta = meta_builder or MetaBuilder()
        self._normalizer = normalizer or ConceptNormalizerImpl()
        self._validator = validator or Validator()
        self._serializer = serializer or Serializer()

    @staticmethod
    def _preprocess_text(text: str) -> str:
        """Clean text before NLP: strip HTML, citations, references section, split on semicolons."""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\[\d+\](?:\s*\[\d+\])*', '', text)
        ref = re.search(r'\n##?\s*(?:References|Bibliography|Citations)\b', text, re.IGNORECASE)
        if ref:
            text = text[:ref.start()]
        text = re.sub(r';\s*(?=[A-Z"\'(])', '. ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    async def process(
        self,
        text: str,
        doc_id: str = "",
    ) -> dict:
        text = self._preprocess_text(text)
        trees = await self._get_dependency_trees(text)
        if not trees:
            return {
                "success": True,
                "statements": [],
                "concepts": {},
                "total_statements": 0,
                "total_concepts": 0,
                "message": "No sentences found",
            }

        all_statements: list[Statement] = []
        concepts: dict[str, Concept] = {}

        for tree in trees:
            sentence_text = tree.root and tree.subtree_text(tree.root.idx) or ""
            if not sentence_text:
                continue

            ctx = ExtractionContext(
                sentence_text=sentence_text,
                existing_concepts=concepts,
                doc_id=doc_id,
            )

            statements = self._engine.process_sentence(tree, ctx)
            all_statements.extend(statements)

        self._normalize_concepts(all_statements, concepts)

        validated, errors = self._validator.validate(all_statements)
        if not validated:
            logger.warning("Validation errors: %s", errors)

        all_statements, concepts = self._meta.process(all_statements, concepts, {"doc_id": doc_id})
        all_statements = [s for s in all_statements if s.predicate != "related_to"]

        stmt_protos, concept_protos = self._serializer.to_proto(all_statements, concepts)

        return {
            "success": True,
            "statements": stmt_protos,
            "concepts": concept_protos,
            "total_statements": len(stmt_protos),
            "total_concepts": len(concept_protos),
            "message": "",
        }

    async def _get_dependency_trees(self, text: str) -> list[DependencyTree]:
        async with self._nlp as client:
            return await client.get_dependency_trees(text)

    def _normalize_concepts(self, statements: list[Statement], concepts: dict[str, Concept]) -> None:
        for stmt in statements:
            if isinstance(stmt.subject, Concept):
                stmt.subject.normalized_text = self._normalizer.normalize(stmt.subject.text)
            if isinstance(stmt.object, Concept):
                stmt.object.normalized_text = self._normalizer.normalize(stmt.object.text)
