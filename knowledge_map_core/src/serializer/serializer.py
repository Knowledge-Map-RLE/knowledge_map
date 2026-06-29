from __future__ import annotations

from datetime import timezone
from typing import Any

from src.domain.interfaces import GraphSerializer
from src.domain.models import Statement, Statement, StatementType, SubjectType, ObjectType, Concept, Literal


class Serializer(GraphSerializer):
    def serialize_statements(self, statements: list[Statement], concepts: dict[str, Concept]) -> list[dict[str, Any]]:
        result = []
        for stmt in statements:
            result.append(self._statement_to_dict(stmt))
        return result

    def to_proto(self, statements: list[Statement], concepts: dict[str, Concept]) -> tuple[list, list]:
        stmt_protos = []
        concept_map: dict[str, Concept] = {}

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
