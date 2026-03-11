"""
Layer: Application (Use Cases)
Package: application.annotations.batch_update_offsets
Responsibility: Массово обновляет позиции (offsets) аннотаций.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import List, Dict, Tuple

from application.ports.repositories import AnnotationRepositoryProtocol


def batch_update_offsets(
    repo: AnnotationRepositoryProtocol,
    updates: List[Dict],
) -> Tuple[int, List[str]]:
    """
    Массово обновляет start_offset / end_offset аннотаций.

    Args:
        updates: [{"annotation_id": str, "start_offset": int, "end_offset": int}, ...]

    Returns:
        (updated_count, errors)
    """
    return repo.batch_update_offsets(updates)
