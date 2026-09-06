"""
Layer: Domain — Citation Source Collectors
Package: services.citation_sources
Responsibility: Абстракции и реализации сбора данных о цитированиях
                из 4 открытых источников: OpenCitations, OpenAlex, Crossref, DataCite.
"""

from .base import CitationEdge, CitationSource
from .opencitations_source import OpenCitationsSource
from .openalex_source import OpenAlexSource
from .crossref_source import CrossrefSource
from .datacite_source import DataCiteSource

__all__ = [
    "CitationEdge",
    "CitationSource",
    "OpenCitationsSource",
    "OpenAlexSource",
    "CrossrefSource",
    "DataCiteSource",
]

ALL_SOURCES: dict[str, type[CitationSource]] = {
    "opencitations": OpenCitationsSource,
    "openalex": OpenAlexSource,
    "crossref": CrossrefSource,
    "datacite": DataCiteSource,
}
