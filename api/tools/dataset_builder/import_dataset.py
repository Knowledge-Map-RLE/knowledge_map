#!/usr/bin/env python3
"""
Dataset Import Tool

Import test dataset into Neo4j for testing purposes.

Usage:
    poetry run python tools/dataset_builder/import_dataset.py --sample sample_001
    poetry run python tools/dataset_builder/import_dataset.py --sample sample_001 --clean
"""

import asyncio
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services import settings, get_s3_client
from src.models import PDFDocument, MarkdownAnnotation
from neomodel import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Paths
API_ROOT = Path(__file__).parent.parent.parent
PROJECT_ROOT = API_ROOT.parent  # Knowledge_Map/
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"


class DatasetImporter:
    """Import dataset from test files into Neo4j"""

    def __init__(self, sample_id: str, clean: bool = False):
        self.sample_id = sample_id
        self.clean = clean
        self.s3_client = get_s3_client()

        # Input directories
        self.doc_dir = DATASETS_DIR / "documents" / self.sample_id
        self.ann_dir = DATASETS_DIR / "annotations" / self.sample_id

        # Storage for created objects
        self.annotation_map: Dict[str, MarkdownAnnotation] = {}  # uid -> annotation

    def load_metadata(self) -> Dict[str, Any]:
        """Load document metadata"""
        metadata_path = self.doc_dir / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found: {metadata_path}")

        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_markdown(self) -> str:
        """Load markdown content"""
        md_path = self.doc_dir / "document.md"
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown not found: {md_path}")

        return md_path.read_text(encoding="utf-8")

    async def import_document(self, metadata: Dict[str, Any], markdown: str) -> PDFDocument:
        """Import document to Neo4j and S3"""
        doc_id = metadata["doc_id"]
        logger.info(f"Importing document {doc_id}...")

        # Clean existing document if requested
        if self.clean:
            existing_doc = PDFDocument.nodes.get_or_none(uid=doc_id)
            if existing_doc:
                logger.info(f"Cleaning existing document {doc_id}...")
                # Delete annotations
                query = """
                MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
                DETACH DELETE a
                """
                db.cypher_query(query, {"doc_id": doc_id})
                # Delete document
                existing_doc.delete()

        # Create document in Neo4j
        document = PDFDocument(
            uid=doc_id,
            original_filename=metadata.get("original_filename", f"{doc_id}.pdf"),
            md5_hash=doc_id,
            title=metadata.get("title"),
            authors=metadata.get("authors", []),
            abstract=metadata.get("abstract"),
            processing_status="annotated",
            is_processed=True,
        ).save()

        logger.info(f"Created document {doc_id} in Neo4j")

        # Upload markdown to S3
        bucket = settings.S3_BUCKET_NAME
        md_key = f"documents/{doc_id}/{doc_id}.md"

        await self.s3_client.upload_bytes(
            markdown.encode("utf-8"),
            bucket,
            md_key,
            content_type="text/markdown; charset=utf-8"
        )
        logger.info(f"Uploaded markdown to S3: {md_key}")

        # Upload PDF if exists
        pdf_path = self.doc_dir / "document.pdf"
        if pdf_path.exists():
            pdf_key = f"documents/{doc_id}/{doc_id}.pdf"
            await self.s3_client.upload_bytes(
                pdf_path.read_bytes(),
                bucket,
                pdf_key,
                content_type="application/pdf"
            )
            logger.info(f"Uploaded PDF to S3: {pdf_key}")

        return document

    def import_annotations(self, document: PDFDocument) -> List[MarkdownAnnotation]:
        """Import annotations to Neo4j"""
        linguistic_path = self.ann_dir / "linguistic.json"
        if not linguistic_path.exists():
            logger.info("No linguistic annotations to import")
            return []

        with open(linguistic_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        annotations_data = data.get("annotations", [])
        logger.info(f"Importing {len(annotations_data)} annotations...")

        created_annotations = []

        for ann_data in annotations_data:
            # Create annotation
            annotation = MarkdownAnnotation(
                uid=ann_data.get("uid"),  # Use provided UID or generate new
                text=ann_data["text"],
                annotation_type=ann_data["annotation_type"],
                start_offset=ann_data["start_offset"],
                end_offset=ann_data["end_offset"],
                confidence=ann_data.get("confidence", 1.0),
                color=ann_data.get("color", "#3B82F6"),
                metadata=ann_data.get("metadata", {}),
                source=ann_data.get("source", "dataset_import"),
                processor_version=ann_data.get("processor_version", "1.0"),
            ).save()

            # Connect to document
            annotation.document.connect(document)

            # Store for relations
            self.annotation_map[annotation.uid] = annotation
            created_annotations.append(annotation)

        logger.info(f"Created {len(created_annotations)} annotations in Neo4j")
        return created_annotations

    def import_relations(self):
        """Import relations between annotations to Neo4j"""
        relations_path = self.ann_dir / "relations.json"
        if not relations_path.exists():
            logger.info("No relations to import")
            return []

        with open(relations_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        relations_data = data.get("relations", [])
        logger.info(f"Importing {len(relations_data)} relations...")

        created_relations = []

        for rel_data in relations_data:
            source_uid = rel_data["source_uid"]
            target_uid = rel_data["target_uid"]

            # Get annotations
            source_ann = self.annotation_map.get(source_uid)
            target_ann = self.annotation_map.get(target_uid)

            if not source_ann or not target_ann:
                logger.warning(f"Skipping relation: annotation not found (source={source_uid}, target={target_uid})")
                continue

            # Create relation
            rel = source_ann.relations_to.connect(
                target_ann,
                {
                    "relation_type": rel_data["relation_type"],
                    "metadata": rel_data.get("metadata", {}),
                    "created_date": datetime.utcnow()
                }
            )

            created_relations.append(rel)

        logger.info(f"Created {len(created_relations)} relations in Neo4j")
        return created_relations

    def import_patterns(self, doc_id: str):
        """Import patterns to Neo4j"""
        patterns_path = self.ann_dir / "patterns.json"
        if not patterns_path.exists():
            logger.info("No patterns to import")
            return []

        with open(patterns_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        patterns_data = data.get("patterns", [])
        logger.info(f"Importing {len(patterns_data)} patterns...")

        # Use Cypher to create patterns with properties as separate nodes
        for pattern_data in patterns_data:
            pattern_id = pattern_data["pattern_id"]

            # Create Pattern node
            query = """
            MERGE (p:Pattern {pattern_id: $pattern_id})
            SET p.doc_id = $doc_id,
                p.sent_idx = $sent_idx,
                p.token_idx = $token_idx
            """
            db.cypher_query(query, {
                "pattern_id": pattern_id,
                "doc_id": doc_id,
                "sent_idx": pattern_data.get("sent_idx"),
                "token_idx": pattern_data.get("token_idx"),
            })

            # Create property nodes
            if pattern_data.get("text"):
                query = """
                MATCH (p:Pattern {pattern_id: $pattern_id})
                MERGE (prop:PatternProperty {type: 'text', value: $value})
                MERGE (p)-[:HAS_TEXT]->(prop)
                """
                db.cypher_query(query, {"pattern_id": pattern_id, "value": pattern_data["text"]})

            if pattern_data.get("pos"):
                query = """
                MATCH (p:Pattern {pattern_id: $pattern_id})
                MERGE (prop:PatternProperty {type: 'pos', value: $value})
                MERGE (p)-[:HAS_POS]->(prop)
                """
                db.cypher_query(query, {"pattern_id": pattern_id, "value": pattern_data["pos"]})

            if pattern_data.get("lemma"):
                query = """
                MATCH (p:Pattern {pattern_id: $pattern_id})
                MERGE (prop:PatternProperty {type: 'lemma', value: $value})
                MERGE (p)-[:HAS_LEMMA]->(prop)
                """
                db.cypher_query(query, {"pattern_id": pattern_id, "value": pattern_data["lemma"]})

            if pattern_data.get("confidence") is not None:
                query = """
                MATCH (p:Pattern {pattern_id: $pattern_id})
                MERGE (prop:PatternProperty {type: 'confidence', value: $value})
                MERGE (p)-[:HAS_CONFIDENCE]->(prop)
                """
                db.cypher_query(query, {"pattern_id": pattern_id, "value": str(pattern_data["confidence"])})

        logger.info(f"Created {len(patterns_data)} patterns in Neo4j")
        return patterns_data

    async def import_all(self):
        """Import complete dataset"""
        logger.info(f"=== Importing dataset {self.sample_id} ===")

        # Load data
        metadata = self.load_metadata()
        markdown = self.load_markdown()

        # Import document
        document = await self.import_document(metadata, markdown)

        # Import annotations
        annotations = self.import_annotations(document)

        # Import relations
        relations = self.import_relations()

        # Import patterns (if exist)
        patterns = self.import_patterns(metadata["doc_id"])

        # Summary
        summary = {
            "sample_id": self.sample_id,
            "doc_id": metadata["doc_id"],
            "imported_at": datetime.utcnow().isoformat(),
            "counts": {
                "annotations": len(annotations),
                "relations": len(relations),
                "patterns": len(patterns),
            }
        }

        logger.info(f"=== Import complete ===")
        logger.info(f"Summary: {json.dumps(summary, indent=2)}")

        return summary


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Import dataset to Neo4j and S3")
    parser.add_argument("--sample", required=True, help="Sample ID to import (e.g., sample_001)")
    parser.add_argument("--clean", action="store_true", help="Clean existing data before import")

    args = parser.parse_args()

    try:
        importer = DatasetImporter(sample_id=args.sample, clean=args.clean)
        await importer.import_all()

        logger.info("✓ Dataset import successful!")
        return 0

    except Exception as e:
        logger.error(f"✗ Import failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
