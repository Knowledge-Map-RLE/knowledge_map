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
from pathlib import Path
from typing import Dict, Any, List, Optional

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


class DatasetExporter:
    """Export data from Neo4j and S3 to dataset format"""

    def __init__(self, doc_id: str, output_sample: str, include_pdf: bool = False):
        self.doc_id = doc_id
        self.sample_id = output_sample
        self.include_pdf = include_pdf
        self.s3_client = get_s3_client()

        # Output directories
        self.doc_dir = DATASETS_DIR / "documents" / self.sample_id
        self.ann_dir = DATASETS_DIR / "annotations" / self.sample_id
        self.exp_dir = DATASETS_DIR / "expected" / self.sample_id

    def create_directories(self):
        """Create output directories if they don't exist"""
        self.doc_dir.mkdir(parents=True, exist_ok=True)
        self.ann_dir.mkdir(parents=True, exist_ok=True)
        self.exp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directories for sample {self.sample_id}")

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

        metadata_path = self.doc_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"Exported metadata to {metadata_path}")

        # Export markdown from S3
        bucket = settings.S3_BUCKET_NAME
        md_key = f"documents/{self.doc_id}/{self.doc_id}.md"

        if await self.s3_client.object_exists(bucket, md_key):
            markdown = await self.s3_client.download_text(bucket, md_key)
            md_path = self.doc_dir / "document.md"
            md_path.write_text(markdown, encoding="utf-8")
            logger.info(f"Exported markdown to {md_path}")
        else:
            logger.warning(f"Markdown not found in S3: {md_key}")

        # Export PDF if requested
        if self.include_pdf:
            pdf_key = f"documents/{self.doc_id}/{self.doc_id}.pdf"
            if await self.s3_client.object_exists(bucket, pdf_key):
                pdf_bytes = await self.s3_client.download_bytes(bucket, pdf_key)
                pdf_path = self.doc_dir / "document.pdf"
                pdf_path.write_bytes(pdf_bytes)
                logger.info(f"Exported PDF to {pdf_path} ({len(pdf_bytes)} bytes)")
            else:
                logger.warning(f"PDF not found in S3: {pdf_key}")

        return metadata

    def export_annotations(self) -> List[Dict[str, Any]]:
        """Export annotations from Neo4j"""
        logger.info(f"Exporting annotations for document {self.doc_id}...")

        # Get document
        document = PDFDocument.nodes.get_or_none(uid=self.doc_id)
        if not document:
            return []

        # Query annotations
        query = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
        RETURN a
        ORDER BY a.start_offset
        """

        results, _ = db.cypher_query(query, {"doc_id": self.doc_id})

        annotations = []
        for row in results:
            ann_node = MarkdownAnnotation.inflate(row[0])
            annotations.append({
                "uid": ann_node.uid,
                "text": ann_node.text,
                "annotation_type": ann_node.annotation_type,
                "start_offset": ann_node.start_offset,
                "end_offset": ann_node.end_offset,
                "confidence": ann_node.confidence,
                "color": ann_node.color,
                "metadata": ann_node.metadata or {},
                "source": ann_node.source,
                "processor_version": ann_node.processor_version,
                "created_date": ann_node.created_date.isoformat() if ann_node.created_date else None,
            })

        # Save to file
        linguistic_path = self.ann_dir / "linguistic.json"
        with open(linguistic_path, "w", encoding="utf-8") as f:
            json.dump({"annotations": annotations}, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported {len(annotations)} annotations to {linguistic_path}")
        return annotations

    def export_relations(self) -> List[Dict[str, Any]]:
        """Export relations between annotations from Neo4j"""
        logger.info(f"Exporting relations for document {self.doc_id}...")

        query = """
        MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a1:MarkdownAnnotation)
        MATCH (a1)-[r:RELATES_TO]->(a2:MarkdownAnnotation)
        RETURN a1.uid as source_uid, a2.uid as target_uid,
               r.relation_type as relation_type, r.metadata as metadata
        """

        results, _ = db.cypher_query(query, {"doc_id": self.doc_id})

        relations = []
        for row in results:
            relations.append({
                "source_uid": row[0],
                "target_uid": row[1],
                "relation_type": row[2],
                "metadata": row[3] or {},
            })

        # Save to file
        if relations:
            relations_path = self.ann_dir / "relations.json"
            with open(relations_path, "w", encoding="utf-8") as f:
                json.dump({"relations": relations}, f, ensure_ascii=False, indent=2)
            logger.info(f"Exported {len(relations)} relations to {relations_path}")
        else:
            logger.info("No relations found")

        return relations

    def export_patterns(self) -> List[Dict[str, Any]]:
        """Export patterns from Neo4j (if they exist for this document)"""
        logger.info(f"Exporting patterns for document {self.doc_id}...")

        query = """
        MATCH (p:Pattern {doc_id: $doc_id})
        MATCH (p)-[:HAS_TEXT]->(t:PatternProperty {type: 'text'})
        OPTIONAL MATCH (p)-[:HAS_POS]->(pos:PatternProperty {type: 'pos'})
        OPTIONAL MATCH (p)-[:HAS_LEMMA]->(lemma:PatternProperty {type: 'lemma'})
        OPTIONAL MATCH (p)-[:HAS_CONFIDENCE]->(conf:PatternProperty {type: 'confidence'})
        RETURN p.pattern_id as pattern_id, t.value as text,
               pos.value as pos, lemma.value as lemma,
               conf.value as confidence,
               p.sent_idx as sent_idx, p.token_idx as token_idx
        ORDER BY p.sent_idx, p.token_idx
        """

        results, _ = db.cypher_query(query, {"doc_id": self.doc_id})

        patterns = []
        for row in results:
            patterns.append({
                "pattern_id": row[0],
                "text": row[1],
                "pos": row[2],
                "lemma": row[3],
                "confidence": float(row[4]) if row[4] else None,
                "doc_id": self.doc_id,
                "sent_idx": row[5],
                "token_idx": row[6],
            })

        # Save to file
        if patterns:
            patterns_path = self.ann_dir / "patterns.json"
            with open(patterns_path, "w", encoding="utf-8") as f:
                json.dump({"patterns": patterns}, f, ensure_ascii=False, indent=2)
            logger.info(f"Exported {len(patterns)} patterns to {patterns_path}")
        else:
            logger.info("No patterns found for this document")

        return patterns

    def export_action_chains(self) -> List[Dict[str, Any]]:
        """Export action chains from Neo4j patterns"""
        logger.info(f"Exporting action chains for document {self.doc_id}...")

        # Query for action sequences
        query = """
        MATCH (p1:Pattern {doc_id: $doc_id})-[r:ACTION_SEQUENCE]->(p2:Pattern)
        MATCH (p1)-[:HAS_TEXT]->(t1:PatternProperty {type: 'text'})
        MATCH (p2)-[:HAS_TEXT]->(t2:PatternProperty {type: 'text'})
        OPTIONAL MATCH (p1)<-[:LINGUISTIC_RELATION {relation_type: 'nsubj'}]-(s1:Pattern)-[:HAS_TEXT]->(st1:PatternProperty {type: 'text'})
        OPTIONAL MATCH (p1)<-[ro1:LINGUISTIC_RELATION]-(o1:Pattern)-[:HAS_TEXT]->(ot1:PatternProperty {type: 'text'})
        WHERE ro1.relation_type IN ['obj', 'dobj']
        RETURN t1.value as verb1, t2.value as verb2,
               st1.value as subject1, ot1.value as object1,
               r.sequence_type as sequence_type, r.confidence as confidence,
               r.evidence as evidence
        """

        results, _ = db.cypher_query(query, {"doc_id": self.doc_id})

        # Build chains from sequences
        chains = []
        for row in results:
            chains.append({
                "verbs": [row[0], row[1]],
                "verb_data": [
                    {
                        "verb": row[0],
                        "subject": row[2],
                        "object": row[3],
                    }
                ],
                "sequence_type": row[4],
                "confidence": float(row[5]) if row[5] else 0.0,
                "evidence": row[6] if row[6] else [],
            })

        # Save to file
        if chains:
            chains_path = self.ann_dir / "chains.json"
            with open(chains_path, "w", encoding="utf-8") as f:
                json.dump({"chains": chains}, f, ensure_ascii=False, indent=2)
            logger.info(f"Exported {len(chains)} action chains to {chains_path}")
        else:
            logger.info("No action chains found for this document")

        return chains

    async def export_all(self):
        """Export complete dataset"""
        logger.info(f"=== Exporting dataset for document {self.doc_id} to {self.sample_id} ===")

        self.create_directories()

        # Export document
        await self.export_document()

        # Export annotations and relations
        annotations = self.export_annotations()
        relations = self.export_relations()

        # Export patterns and chains (if they exist)
        patterns = self.export_patterns()
        chains = self.export_action_chains()

        # Create summary
        summary = {
            "sample_id": self.sample_id,
            "doc_id": self.doc_id,
            "exported_at": asyncio.get_event_loop().time(),
            "counts": {
                "annotations": len(annotations),
                "relations": len(relations),
                "patterns": len(patterns),
                "chains": len(chains),
            }
        }

        logger.info(f"=== Export complete ===")
        logger.info(f"Summary: {json.dumps(summary, indent=2)}")

        # Save summary
        summary_path = DATASETS_DIR / f"{self.sample_id}_export_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        return summary


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Export dataset from Neo4j and S3")
    parser.add_argument("--doc-id", required=True, help="Document ID to export")
    parser.add_argument("--output", required=True, help="Output sample name (e.g., sample_001)")
    parser.add_argument("--include-pdf", action="store_true", help="Include PDF file in export")

    args = parser.parse_args()

    try:
        exporter = DatasetExporter(
            doc_id=args.doc_id,
            output_sample=args.output,
            include_pdf=args.include_pdf
        )
        await exporter.export_all()

        logger.info("✓ Dataset export successful!")
        return 0

    except Exception as e:
        logger.error(f"✗ Export failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
