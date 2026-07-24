# TRANSITIONAL — src/models.py перенаправляет в infrastructure/neo4j/orm_models.py (удалить в Фазе 5).
# Классы объявлены ТОЛЬКО в infrastructure/neo4j/orm_models.py.
# Этот файл — чистый реэкспорт для обратной совместимости.
from infrastructure.neo4j.orm_models import (  # noqa: F401
    LinkRel, Tag, LinkMetadata, Block, Document,
    PDFAnnotation, AnnotationRelationRel, MarkdownAnnotation, LabelStudioProject,
)
