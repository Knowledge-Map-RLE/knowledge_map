#!/usr/bin/env python3
"""
Dataset Export Tool

Export document, annotations, relations, and chains from Neo4j to test dataset format.

Usage:
    poetry run python tools/dataset_builder/export_dataset.py --doc-id <doc_id> --output sample_001
    poetry run python tools/dataset_builder/export_dataset.py --doc-id <doc_id> --output sample_001 --include-pdf
"""

import asyncio
import argparse
import json
import logging
import sys
import yaml
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services import settings, get_s3_client
from services.yaml_export_service import YAMLExportService
from src.models import PDFDocument, MarkdownAnnotation
from neomodel import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Paths
API_ROOT = Path(__file__).parent.parent.parent
PROJECT_ROOT = API_ROOT.parent  # Knowledge_Map/
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"


class DatasetExporter:
    """Export data from Neo4j and S3 to dataset format"""

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.s3_client = get_s3_client()
        self.yaml_service = YAMLExportService()

        # Генерируем уникальное имя: {md5_hash}_{YYYY}.{MM}.{DD}_{HH}.{mm}.{ss}_{random6}
        now = datetime.now()
        timestamp = now.strftime("%Y.%m.%d_%H.%M.%S")
        random_hash = secrets.token_hex(3)  # 6 символов (3 байта в hex)

        self.sample_id = f"{self.doc_id}_{timestamp}_{random_hash}"
        self.dataset_dir = DATASETS_DIR / self.sample_id

    def create_directories(self):
        """Create output directory if it doesn't exist"""
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory {self.sample_id}")

    async def export_document(self) -> Dict[str, Any]:
        """Export document metadata and markdown from Neo4j and S3"""
        logger.info(f"Exporting document {self.doc_id}...")

        # Get document from Neo4j
        document = PDFDocument.nodes.get_or_none(uid=self.doc_id)
        if not document:
            raise ValueError(f"Document {self.doc_id} not found in Neo4j")

        # Export metadata
        metadata = {
            "doc_id": self.doc_id,
            "title": document.title,
            "authors": document.authors or [],
            "abstract": document.abstract,
            "original_filename": document.original_filename,
            "upload_date": document.upload_date.isoformat() if document.upload_date else None,
        }

        metadata_path = self.dataset_dir / "metadata.yaml"
        self.yaml_service.export_to_yaml(metadata, metadata_path)
        logger.info(f"Exported metadata to {metadata_path}")

        # Export markdown from S3 (приоритет: user_md -> formatted_md -> raw_md)
        bucket = settings.S3_BUCKET_NAME
        markdown = None

        # Проверяем user_md (отредактированный пользователем)
        if document.user_md_s3_key:
            if await self.s3_client.object_exists(bucket, document.user_md_s3_key):
                markdown = await self.s3_client.download_text(bucket, document.user_md_s3_key)
                logger.info(f"Using user-edited markdown from {document.user_md_s3_key}")

        # Если нет user_md, проверяем formatted_md (AI-форматированный)
        if not markdown and document.formatted_md_s3_key:
            if await self.s3_client.object_exists(bucket, document.formatted_md_s3_key):
                markdown = await self.s3_client.download_text(bucket, document.formatted_md_s3_key)
                logger.info(f"Using AI-formatted markdown from {document.formatted_md_s3_key}")

        # Если нет formatted_md, используем raw markdown
        if not markdown and document.docling_raw_md_s3_key:
            if await self.s3_client.object_exists(bucket, document.docling_raw_md_s3_key):
                markdown = await self.s3_client.download_text(bucket, document.docling_raw_md_s3_key)
                logger.info(f"Using raw markdown from {document.docling_raw_md_s3_key}")

        # Fallback к старому формату
        if not markdown:
            md_key = f"documents/{self.doc_id}/{self.doc_id}.md"
            if await self.s3_client.object_exists(bucket, md_key):
                markdown = await self.s3_client.download_text(bucket, md_key)
                logger.info(f"Using legacy markdown from {md_key}")

        if markdown:
            md_path = self.dataset_dir / "document.md"
            md_path.write_text(markdown, encoding="utf-8")
            logger.info(f"Exported markdown to {md_path}")
        else:
            logger.warning(f"Markdown not found for document {self.doc_id}")

        # Export PDF (обязательно)
        pdf_key = f"documents/{self.doc_id}/{self.doc_id}.pdf"
        if await self.s3_client.object_exists(bucket, pdf_key):
            pdf_bytes = await self.s3_client.download_bytes(bucket, pdf_key)
            pdf_path = self.dataset_dir / "document.pdf"
            pdf_path.write_bytes(pdf_bytes)
            logger.info(f"Exported PDF to {pdf_path} ({len(pdf_bytes)} bytes)")
        else:
            raise ValueError(f"PDF file is mandatory but not found in S3: {pdf_key}")

        return metadata

    def export_annotations(self) -> List[Dict[str, Any]]:
        """Export annotations from Neo4j"""
        logger.info(f"Exporting annotations for document {self.doc_id}...")

        # Используем YAML сервис для получения аннотаций
        data = self.yaml_service.export_annotations_to_yaml(self.doc_id)
        annotations = data.get("annotations", [])

        # Save to file
        linguistic_path = self.dataset_dir / "linguistic.yaml"
        self.yaml_service.export_to_yaml({"annotations": annotations}, linguistic_path)

        logger.info(f"Exported {len(annotations)} annotations to {linguistic_path}")
        return annotations

    def export_relations(self) -> List[Dict[str, Any]]:
        """Export relations between annotations from Neo4j"""
        logger.info(f"Exporting relations for document {self.doc_id}...")

        # Используем YAML сервис для получения связей
        relations = self.yaml_service.export_relations_to_dict(self.doc_id)

        # Save to file
        if relations:
            relations_path = self.dataset_dir / "relations.yaml"
            self.yaml_service.export_to_yaml({"relations": relations}, relations_path)
            logger.info(f"Exported {len(relations)} relations to {relations_path}")
        else:
            logger.info("No relations found")

        return relations

    def export_patterns(self) -> List[Dict[str, Any]]:
        """Export patterns from Neo4j (if they exist for this document)"""
        logger.info(f"Exporting patterns for document {self.doc_id}...")

        # Паттерны связаны с документом через аннотации
        query = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
        MATCH (p:Pattern {source_token_uid: a.uid})
        MATCH (p)-[:HAS_TEXT]->(t:PatternProperty {type: 'text'})
        OPTIONAL MATCH (p)-[:HAS_POS]->(pos:PatternProperty {type: 'pos'})
        OPTIONAL MATCH (p)-[:HAS_LEMMA]->(lemma:PatternProperty {type: 'lemma'})
        OPTIONAL MATCH (p)-[:HAS_CONFIDENCE]->(conf:PatternProperty {type: 'confidence'})
        RETURN DISTINCT p.pattern_id as pattern_id, t.value as text,
               pos.value as pos, lemma.value as lemma,
               conf.value as confidence,
               p.source_token_uid as source_token_uid
        ORDER BY p.pattern_id
        """

        results, _ = db.cypher_query(query, {"doc_id": self.doc_id})

        patterns = []
        for row in results:
            pattern_data = {
                "pattern_id": row[0],
                "text": row[1],
                "source_token_uid": row[5],
            }
            # Добавляем опциональные поля
            if row[2]:  # pos
                pattern_data["pos"] = row[2]
            if row[3]:  # lemma
                pattern_data["lemma"] = row[3]
            if row[4] is not None:  # confidence
                pattern_data["confidence"] = float(row[4])

            patterns.append(pattern_data)

        # Save to file (обязательно)
        if patterns:
            patterns_path = self.dataset_dir / "patterns.yaml"
            self.yaml_service.export_to_yaml({"patterns": patterns}, patterns_path)
            logger.info(f"Exported {len(patterns)} patterns to {patterns_path}")
        else:
            raise ValueError("Patterns are mandatory but none were found for this document")

        return patterns

    def export_action_chains(self) -> List[Dict[str, Any]]:
        """Export action chains from Neo4j patterns"""
        logger.info(f"Exporting action chains for document {self.doc_id}...")

        # Query for action sequences - паттерны связаны с документом через аннотации
        query = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
        MATCH (p1:Pattern {source_token_uid: a.uid})-[r:ACTION_SEQUENCE]->(p2:Pattern)
        MATCH (p1)-[:HAS_TEXT]->(t1:PatternProperty {type: 'text'})
        MATCH (p2)-[:HAS_TEXT]->(t2:PatternProperty {type: 'text'})
        OPTIONAL MATCH (p1)<-[:LINGUISTIC_RELATION {relation_type: 'nsubj'}]-(s1:Pattern)-[:HAS_TEXT]->(st1:PatternProperty {type: 'text'})
        OPTIONAL MATCH (p1)<-[ro1:LINGUISTIC_RELATION]-(o1:Pattern)-[:HAS_TEXT]->(ot1:PatternProperty {type: 'text'})
        WHERE ro1.relation_type IN ['obj', 'dobj']
        RETURN DISTINCT t1.value as verb1, t2.value as verb2,
               st1.value as subject1, ot1.value as object1,
               r.sequence_type as sequence_type, r.confidence as confidence,
               r.evidence as evidence
        """

        results, _ = db.cypher_query(query, {"doc_id": self.doc_id})

        # Build chains from sequences
        chains = []
        for row in results:
            chain_data = {
                "verbs": [row[0], row[1]],
                "verb_data": [
                    {
                        "verb": row[0],
                    }
                ],
            }
            # Добавляем опциональные поля
            if row[2]:  # subject
                chain_data["verb_data"][0]["subject"] = row[2]
            if row[3]:  # object
                chain_data["verb_data"][0]["object"] = row[3]
            if row[4]:  # sequence_type
                chain_data["sequence_type"] = row[4]
            if row[5] is not None:  # confidence
                chain_data["confidence"] = float(row[5])
            if row[6]:  # evidence
                chain_data["evidence"] = row[6]

            chains.append(chain_data)

        # Save to file (обязательно)
        if chains:
            chains_path = self.dataset_dir / "chains.yaml"
            self.yaml_service.export_to_yaml({"chains": chains}, chains_path)
            logger.info(f"Exported {len(chains)} action chains to {chains_path}")
        else:
            raise ValueError("Action chains are mandatory but none were found for this document")

        return chains

    async def export_all(self) -> Dict[str, Any]:
        """
        Export complete dataset

        All components are mandatory: PDF, markdown, annotations, relations, patterns, chains

        Returns:
            Dict with export results including success status, files, and counts
        """
        logger.info(f"=== Exporting dataset for document {self.doc_id} to {self.sample_id} ===")

        result = {
            "success": True,
            "sample_id": self.sample_id,
            "doc_id": self.doc_id,
            "exported_files": [],
            "errors": [],
            "counts": {
                "annotations": 0,
                "relations": 0,
                "patterns": 0,
                "chains": 0,
            }
        }

        try:
            self.create_directories()

            # Export document
            await self.export_document()
            result["exported_files"].extend([
                f"{self.sample_id}/metadata.yaml",
                f"{self.sample_id}/document.md",
                f"{self.sample_id}/document.pdf",
            ])

            # Export annotations and relations
            annotations = self.export_annotations()
            result["counts"]["annotations"] = len(annotations)
            result["exported_files"].append(f"{self.sample_id}/linguistic.yaml")

            relations = self.export_relations()
            result["counts"]["relations"] = len(relations)
            if relations:
                result["exported_files"].append(f"{self.sample_id}/relations.yaml")

            # Export patterns (обязательно)
            patterns = self.export_patterns()
            result["counts"]["patterns"] = len(patterns)
            result["exported_files"].append(f"{self.sample_id}/patterns.yaml")

            # Export chains (обязательно)
            chains = self.export_action_chains()
            result["counts"]["chains"] = len(chains)
            result["exported_files"].append(f"{self.sample_id}/chains.yaml")

            logger.info(f"=== Export complete ===")
            logger.info(f"Summary: {json.dumps(result['counts'], indent=2)}")

            # Save summary (YAML внутри папки)
            summary_path = self.dataset_dir / "export_summary.yaml"
            summary_data = {
                "sample_id": self.sample_id,
                "doc_id": self.doc_id,
                "export_date": datetime.now().isoformat(),
                "exported_files": result["exported_files"],
                "counts": result["counts"],
            }
            self.yaml_service.export_to_yaml(summary_data, summary_path)

        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            result["success"] = False
            result["errors"].append(str(e))

        return result


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Export dataset from Neo4j and S3")
    parser.add_argument("--doc-id", required=True, help="Document ID to export")
    parser.add_argument("--output", required=True, help="Output sample name (e.g., sample_001)")
    parser.add_argument("--include-pdf", action="store_true", help="Include PDF file in export")
    parser.add_argument("--include-patterns", action="store_true", default=True, help="Include patterns in export")
    parser.add_argument("--include-chains", action="store_true", default=True, help="Include action chains in export")

    args = parser.parse_args()

    try:
        exporter = DatasetExporter(
            doc_id=args.doc_id,
            output_sample=args.output,
            include_pdf=args.include_pdf
        )
        result = await exporter.export_all(
            include_patterns=args.include_patterns,
            include_chains=args.include_chains
        )

        if result["success"]:
            logger.info("✓ Dataset export successful!")
            return 0
        else:
            logger.error(f"✗ Export failed: {result.get('errors')}")
            return 1

    except Exception as e:
        logger.error(f"✗ Export failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
