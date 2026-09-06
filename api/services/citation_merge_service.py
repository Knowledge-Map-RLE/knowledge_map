"""
Layer: Application — Service
Package: services.citation_merge_service
Responsibility: Слияние данных о цитированиях из разных источников с дедупликацией.

Приём: Iterable[CitationEdge] из разных коллекторов.
Выход: dict[(citing_doi, cited_doi), CitationEdge] с объединёнными source.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Optional

from .citation_sources.base import CitationEdge

logger = logging.getLogger(__name__)


class CitationMergeService:
    """Сливает CitationEdge из разных источников, убирая дубли по DOI-паре."""

    def merge_edges(self, edges: Iterable[CitationEdge]) -> dict[tuple[str, str], CitationEdge]:
        """Ключ = (citing_doi, cited_doi). Дубли объединяются, source объединяется через '|'.

        Если у нового edge есть title, а у существующего нет — обновляем title.
        """
        merged: dict[tuple[str, str], CitationEdge] = {}
        stats = {"total_input": 0, "unique_pairs": 0, "merged_duplicates": 0}

        for edge in edges:
            stats["total_input"] += 1
            key = (edge.citing_doi.strip().lower(), edge.cited_doi.strip().lower())

            if not key[0] or not key[1]:
                continue

            if key in merged:
                existing = merged[key]
                existing_sources = set(existing.source.split("|"))
                if edge.source not in existing_sources:
                    new_source = "|".join(sorted(existing_sources | {edge.source}))
                    merged[key] = CitationEdge(
                        citing_doi=existing.citing_doi,
                        cited_doi=existing.cited_doi,
                        source=new_source,
                        title_citing=existing.title_citing or edge.title_citing,
                        title_cited=existing.title_cited or edge.title_cited,
                    )
                    stats["merged_duplicates"] += 1
                else:
                    if not existing.title_citing and edge.title_citing:
                        merged[key] = CitationEdge(
                            citing_doi=existing.citing_doi,
                            cited_doi=existing.cited_doi,
                            source=existing.source,
                            title_citing=edge.title_citing,
                            title_cited=existing.title_cited,
                        )
                    if not existing.title_cited and edge.title_cited:
                        merged[key] = CitationEdge(
                            citing_doi=existing.citing_doi,
                            cited_doi=existing.cited_doi,
                            source=existing.source,
                            title_citing=existing.title_citing,
                            title_cited=edge.title_cited,
                        )
            else:
                merged[key] = edge
                stats["unique_pairs"] += 1

        logger.info(
            "Merge complete: %d input edges -> %d unique pairs (%d duplicates merged)",
            stats["total_input"],
            stats["unique_pairs"],
            stats["merged_duplicates"],
        )
        return merged

    def merge_from_generators(
        self, *generators: Iterable[CitationEdge]
    ) -> dict[tuple[str, str], CitationEdge]:
        """Сливает несколько генераторов edges в один merged dict."""
        def _chain():
            for gen in generators:
                yield from gen
        return self.merge_edges(_chain())
