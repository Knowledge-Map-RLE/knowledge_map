from __future__ import annotations

import logging

from src.domain.models import Statement, StatementType, StatementID, Concept
from src.extractor.context import ExtractionContext
from src.extractor.engine import RuleEngine
from src.llm.ai_client import AIClient
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
        ai_client: AIClient | None = None,
        rule_engine: RuleEngine | None = None,
        meta_builder: MetaBuilder | None = None,
        normalizer: ConceptNormalizerImpl | None = None,
        validator: Validator | None = None,
        serializer: Serializer | None = None,
    ):
        self._nlp = nlp_client or NLPClient()
        self._ai = ai_client or AIClient()
        self._engine = rule_engine or RuleEngine()
        self._meta = meta_builder or MetaBuilder()
        self._normalizer = normalizer or ConceptNormalizerImpl()
        self._validator = validator or Validator()
        self._serializer = serializer or Serializer()

    async def process(
        self,
        text: str,
        doc_id: str = "",
        use_llm: bool = False,
        llm_model_id: str | None = None,
    ) -> dict:
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

        if use_llm and all_statements:
            await self._enrich_with_llm(text, all_statements, concepts, llm_model_id)

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

    async def _enrich_with_llm(
        self,
        text: str,
        statements: list[Statement],
        concepts: dict[str, Concept],
        model_id: str | None,
    ) -> None:
        existing = []
        for s in statements:
            obj_val = s.object_id
            existing.append({
                "id": str(s.id),
                "subject": s.subject_id,
                "predicate": s.predicate,
                "object": obj_val,
            })

        async with self._ai as client:
            suggestions = await client.suggest_meta_statements(text, existing, model_id)

        for suggestion in suggestions:
            subject = concepts.get(suggestion["subject_id"])
            obj_ref = concepts.get(suggestion["object_id"])
            if subject and obj_ref:
                meta = Statement(
                    id=StatementID.new(),
                    type=StatementType.META,
                    subject=subject,
                    predicate=suggestion["predicate"],
                    object=obj_ref,
                    sentence_text=text,
                )
                statements.append(meta)

    def _normalize_concepts(self, statements: list[Statement], concepts: dict[str, Concept]) -> None:
        for stmt in statements:
            if isinstance(stmt.subject, Concept):
                stmt.subject.normalized_text = self._normalizer.normalize(stmt.subject.text)
            if isinstance(stmt.object, Concept):
                stmt.object.normalized_text = self._normalizer.normalize(stmt.object.text)
