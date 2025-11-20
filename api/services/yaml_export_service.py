"""
Сервис для экспорта и импорта данных в формате YAML.

Этот модуль предоставляет общую логику для экспорта/импорта аннотаций,
связей и других данных в формате YAML, избегая дублирования кода.
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import yaml

from src.models import PDFDocument, MarkdownAnnotation
from services.annotation_service import AnnotationService
from neomodel import db

logger = logging.getLogger(__name__)


class YAMLExportService:
    """Сервис для экспорта/импорта данных в YAML"""

    def __init__(self):
        self.annotation_service = AnnotationService()

    @staticmethod
    def export_to_yaml(data: Any, file_path: Path) -> None:
        """
        Экспортирует данные в YAML файл.

        Args:
            data: Данные для экспорта
            file_path: Путь к файлу для сохранения
        """
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                indent=2
            )
        logger.info(f"Exported data to {file_path}")

    @staticmethod
    def import_from_yaml(file_path: Path) -> Any:
        """
        Импортирует данные из YAML файла.

        Args:
            file_path: Путь к файлу для загрузки

        Returns:
            Загруженные данные
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        logger.info(f"Imported data from {file_path}")
        return data

    def export_annotations_to_yaml(self, doc_id: str) -> Dict[str, Any]:
        """
        Экспортирует аннотации документа в формат YAML.

        Args:
            doc_id: ID документа

        Returns:
            Dict с аннотациями и связями
        """
        logger.info(f"Exporting annotations for document {doc_id}...")

        # Получить документ
        document = PDFDocument.nodes.get_or_none(uid=doc_id)
        if not document:
            return {"annotations": [], "relations": []}

        # Query annotations
        query = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
        RETURN a
        ORDER BY a.start_offset
        """

        results, _ = db.cypher_query(query, {"doc_id": doc_id})

        annotations = []
        for row in results:
            ann_node = MarkdownAnnotation.inflate(row[0])
            annotation_data = {
                "uid": ann_node.uid,
                "text": ann_node.text,
                "annotation_type": ann_node.annotation_type,
                "start_offset": ann_node.start_offset,
                "end_offset": ann_node.end_offset,
                "color": ann_node.color,
                "source": ann_node.source,
            }

            # Добавляем опциональные поля только если они не пустые
            if ann_node.confidence is not None:
                annotation_data["confidence"] = ann_node.confidence
            if ann_node.processor_version:
                annotation_data["processor_version"] = ann_node.processor_version
            if ann_node.created_date:
                annotation_data["created_date"] = ann_node.created_date.isoformat()
            if ann_node.metadata:
                annotation_data["metadata"] = ann_node.metadata

            annotations.append(annotation_data)

        # Export relations
        relations = self.export_relations_to_dict(doc_id)

        return {
            "document_id": doc_id,
            "document_title": document.title,
            "document_filename": document.original_filename,
            "annotations": annotations,
            "relations": relations
        }

    def export_relations_to_dict(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Экспортирует связи документа в словарь.

        Args:
            doc_id: ID документа

        Returns:
            List связей
        """
        query = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a1:MarkdownAnnotation)
        MATCH (a1)-[r:RELATES_TO]->(a2:MarkdownAnnotation)
        RETURN a1.uid as source_uid, a2.uid as target_uid,
               r.relation_type as relation_type, r.metadata as metadata,
               r.uid as relation_uid, r.created_date as created_date
        """

        results, _ = db.cypher_query(query, {"doc_id": doc_id})

        relations = []
        for row in results:
            relation_data = {
                "source_uid": row[0],
                "target_uid": row[1],
                "relation_type": row[2],
            }

            # Добавляем опциональные поля только если они не пустые
            if row[3]:  # metadata
                relation_data["metadata"] = row[3]
            if row[4]:  # relation_uid
                relation_data["relation_uid"] = row[4]
            if row[5]:  # created_date
                relation_data["created_date"] = row[5].isoformat() if hasattr(row[5], 'isoformat') else str(row[5])

            relations.append(relation_data)

        return relations

    async def import_annotations_from_dict(
        self,
        doc_id: str,
        data: Dict[str, Any],
        text_length: int
    ) -> Dict[str, Any]:
        """
        Импортирует аннотации из словаря в Neo4j.

        Args:
            doc_id: ID документа
            data: Данные с аннотациями и связями
            text_length: Длина текста документа для валидации

        Returns:
            Статистика импорта
        """
        annotations = data.get("annotations", [])
        relations = data.get("relations", [])

        created_annotations = 0
        created_relations = 0
        errors = []

        # Создаём аннотации
        for ann_data in annotations:
            try:
                start_offset = int(ann_data["start_offset"])
                end_offset = int(ann_data["end_offset"])

                # Валидация офсетов
                if start_offset < 0 or end_offset > text_length or start_offset >= end_offset:
                    logger.warning(f"Skipping annotation with invalid offsets: {start_offset}-{end_offset}")
                    errors.append(f"Invalid offsets: {start_offset}-{end_offset}")
                    continue

                result = await self.annotation_service.create_annotation(
                    doc_id=doc_id,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    text=ann_data.get("text", ""),
                    annotation_type=ann_data.get("annotation_type", ""),
                    color=ann_data.get("color", "#ffeb3b"),
                    source="file",  # Всегда устанавливаем source="file"
                    confidence=ann_data.get("confidence"),
                    metadata=ann_data.get("metadata", {})
                )
                created_annotations += 1

            except Exception as e:
                logger.warning(f"Error creating annotation: {e}")
                errors.append(f"Annotation error: {str(e)}")

        # Создаём связи
        for rel_data in relations:
            try:
                await self.annotation_service.create_relation(
                    source_id=rel_data["source_uid"],
                    target_id=rel_data["target_uid"],
                    relation_type=rel_data.get("relation_type", ""),
                    metadata=rel_data.get("metadata", {})
                )
                created_relations += 1

            except Exception as e:
                logger.warning(f"Error creating relation: {e}")
                errors.append(f"Relation error: {str(e)}")

        return {
            "success": True,
            "created_annotations": created_annotations,
            "created_relations": created_relations,
            "total_in_file": {
                "annotations": len(annotations),
                "relations": len(relations)
            },
            "errors": errors
        }
