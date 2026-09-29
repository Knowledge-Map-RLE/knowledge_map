from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from typing import Any

from src.domain.interfaces import GraphSerializer
from src.domain.models import Statement, StatementID, StatementType, SubjectType, ObjectType, Concept, Literal


class Serializer(GraphSerializer):
    def serialize_statements(self, statements: list[Statement], concepts: dict[str, Concept]) -> list[dict[str, Any]]:
        result = []
        for stmt in statements:
            result.append(self._statement_to_dict(stmt))
        return result

    def to_proto(self, statements: list[Statement], concepts: dict[str, Concept]) -> tuple[list, list]:
        stmt_protos = []
        concept_map: dict[str, Concept] = dict(concepts)

        for stmt in statements:
            proto = self._statement_to_proto(stmt)
            stmt_protos.append(proto)

            if isinstance(stmt.subject, Concept):
                concept_map[stmt.subject.id] = stmt.subject
            if isinstance(stmt.object, Concept):
                concept_map[stmt.object.id] = stmt.object

        concept_protos = []
        for c in concept_map.values():
            concept_protos.append(self._concept_to_proto(c))

        return stmt_protos, concept_protos

    def _statement_to_dict(self, stmt: Statement) -> dict[str, Any]:
        obj_val = stmt.object_id
        if isinstance(stmt.object, Literal):
            obj_val = stmt.object.value

        return {
            "id": str(stmt.id),
            "type": stmt.type.value,
            "subject_id": stmt.subject_id,
            "subject_type": stmt.subject_type.value,
            "predicate": stmt.predicate,
            "object_id": obj_val,
            "object_type": stmt.object_type.value,
            "status": stmt.status, "arity": stmt.arity, "negated": stmt.negated,
            "modality": stmt.modality, "context": stmt.context, "provenance": stmt.provenance,
            "metadata": stmt.metadata, "object_absent": stmt.object is None,
            "confidence": stmt.confidence,
            "sentence_text": stmt.sentence_text,
            "created_at": int(stmt.created_at.timestamp() * 1000),
        }

    def _statement_to_proto(self, stmt: Statement):
        from src import knowledge_language_pb2

        obj_val = stmt.object_id
        literal_value = ""
        if isinstance(stmt.object, Literal):
            obj_val = stmt.object.value
            literal_value = stmt.object.value

        return knowledge_language_pb2.StatementProto(
            id=str(stmt.id),
            type=self._proto_statement_type(stmt.type),
            subject_id=stmt.subject_id,
            subject_type=self._proto_subject_type(stmt.subject_type),
            predicate=stmt.predicate,
            object_id=obj_val,
            object_type=self._proto_object_type(stmt.object_type),
            literal_value=literal_value,
            status=stmt.status, arity=stmt.arity, negated=stmt.negated,
            modality=stmt.modality, context_json=json.dumps(stmt.context),
            provenance_json=json.dumps(stmt.provenance), metadata_json=json.dumps(stmt.metadata),
            object_absent=stmt.object is None,
            confidence=stmt.confidence,
            sentence_text=stmt.sentence_text,
            created_at=int(stmt.created_at.timestamp() * 1000),
        )

    def _concept_to_proto(self, concept: Concept):
        from src import knowledge_language_pb2

        return knowledge_language_pb2.ConceptProto(
            id=concept.id,
            text=concept.text,
            normalized_text=concept.normalized_text or "",
        )

    def from_proto(self, statement_protos, concept_protos):
        """Two-pass deserialization preserves forward and recursive references."""
        concepts = {c.id: Concept(c.id,c.text,c.normalized_text or None) for c in concept_protos}
        statements = {}
        for p in statement_protos:
            statements[p.id] = Statement(
                id=StatementID(uuid.UUID(p.id)),
                type=StatementType.FACT if p.type == 1 else StatementType.META,
                subject=Concept("", ""),predicate=p.predicate,object=None,
                status=p.status or "hypothesized",arity=p.arity or 2,
                negated=p.negated,modality=p.modality or "asserted",
                context=json.loads(p.context_json or "{}"),provenance=json.loads(p.provenance_json or "[]"),
                metadata=json.loads(p.metadata_json or "{}"),confidence=p.confidence,
                sentence_text=p.sentence_text,
                created_at=datetime.fromtimestamp(p.created_at/1000,tz=timezone.utc))
        for p in statement_protos:
            stmt=statements[p.id]
            stmt.subject=concepts[p.subject_id] if p.subject_type==1 else statements[p.subject_id]
            if p.object_absent:
                stmt.object=None
            elif p.object_type==1:
                stmt.object=concepts[p.object_id]
            elif p.object_type==2:
                stmt.object=statements[p.object_id]
            elif p.object_type==3:
                stmt.object=Literal(p.literal_value)
            else:
                raise ValueError("Unknown object type")
            if (stmt.object is None)!=(stmt.arity==1):
                raise ValueError("Predicate arity mismatch")
        return list(statements.values()),concepts

    def artifacts_to_proto(self, result):
        from src import knowledge_language_pb2
        from knowledge_contracts.validation import validate_linguistic, validate_structural, validate_map
        validate_linguistic(result["linguistic_profile"],result["source"])
        validate_structural(result["blocks"], result["source"], result["linguistic_profile"]["sentences"])
        validate_map(result["graph"],result["blocks"])
        return knowledge_language_pb2.KnowledgeGraphResponse(
            success=True,doc_id=result["article_id"],schema_version=2,
            extraction_json=json.dumps(result,ensure_ascii=False))

    def artifacts_from_proto(self, response):
        if response.schema_version != 2:
            raise ValueError("Not a canonical extraction envelope")
        result=json.loads(response.extraction_json)
        self.artifacts_to_proto(result)
        return result

    @staticmethod
    def _proto_statement_type(t: StatementType):
        from src import knowledge_language_pb2

        mapping = {
            StatementType.FACT: knowledge_language_pb2.FACT,
            StatementType.META: knowledge_language_pb2.META,
        }
        return mapping.get(t, knowledge_language_pb2.STATEMENT_TYPE_UNSPECIFIED)

    @staticmethod
    def _proto_subject_type(t: SubjectType):
        from src import knowledge_language_pb2

        mapping = {
            SubjectType.CONCEPT: knowledge_language_pb2.SUBJECT_CONCEPT,
            SubjectType.STATEMENT: knowledge_language_pb2.SUBJECT_STATEMENT,
        }
        return mapping.get(t, knowledge_language_pb2.SUBJECT_TYPE_UNSPECIFIED)

    @staticmethod
    def _proto_object_type(t: ObjectType):
        from src import knowledge_language_pb2

        mapping = {
            ObjectType.CONCEPT: knowledge_language_pb2.OBJECT_CONCEPT,
            ObjectType.STATEMENT: knowledge_language_pb2.OBJECT_STATEMENT,
            ObjectType.LITERAL: knowledge_language_pb2.OBJECT_LITERAL,
        }
        return mapping.get(t, knowledge_language_pb2.OBJECT_TYPE_UNSPECIFIED)
