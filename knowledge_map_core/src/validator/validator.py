from __future__ import annotations

from src.domain.interfaces import GraphValidator
from src.domain.models import Statement


class Validator(GraphValidator):
    def validate(self, statements: list[Statement]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        seen_ids: set[str] = set()

        for stmt in statements:
            sid = str(stmt.id)
            if sid in seen_ids:
                errors.append(f"Duplicate statement ID: {sid}")
            seen_ids.add(sid)

            if not stmt.predicate:
                errors.append(f"Statement {sid}: empty predicate")

            if not stmt.subject_id:
                errors.append(f"Statement {sid}: empty subject")

            if not stmt.object_id:
                errors.append(f"Statement {sid}: empty object")

        return len(errors) == 0, errors
