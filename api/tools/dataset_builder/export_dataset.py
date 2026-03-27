#!/usr/bin/env python3
"""
Dataset Export Tool

Export document, annotations, annotation relations, and action graph from Neo4j/S3
to test dataset format (CSV).

Usage:
    poetry run python tools/dataset_builder/export_dataset.py --doc-id <doc_id>
"""

import asyncio
import argparse
import csv
import json
import logging
import sys
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

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
    """Export data from Neo4j and S3 to CSV dataset format"""

    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.s3_client = get_s3_client()

        now = datetime.now()
        timestamp = now.strftime("%Y.%m.%d_%H.%M.%S")
        random_hash = secrets.token_hex(3)

        self.sample_id = f"{self.doc_id}_{timestamp}_{random_hash}"
        self.dataset_dir = DATASETS_DIR / self.sample_id

    def _write_csv(self, path: Path, rows: List[Dict], fieldnames: List[str]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def create_directories(self):
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory {self.sample_id}")

    async def export_document(self) -> Dict[str, Any]:
        """Export document metadata and files from Neo4j and S3"""
        logger.info(f"Exporting document {self.doc_id}...")

        document = PDFDocument.nodes.get_or_none(uid=self.doc_id)
        if not document:
            raise ValueError(f"Document {self.doc_id} not found in Neo4j")

        # metadata.csv — single row
        metadata_row = {
            "doc_id": self.doc_id,
            "title": document.title or "",
            "authors": json.dumps(document.authors or [], ensure_ascii=False),
            "abstract": document.abstract or "",
            "original_filename": document.original_filename or "",
            "upload_date": document.upload_date.isoformat() if document.upload_date else "",
        }
        self._write_csv(
            self.dataset_dir / "metadata.csv",
            [metadata_row],
            ["doc_id", "title", "authors", "abstract", "original_filename", "upload_date"],
        )
        logger.info("Exported metadata.csv")

        # Markdown (priority: user_md -> formatted_md -> raw_md -> legacy)
        bucket = settings.S3_BUCKET_NAME
        markdown = None

        for key_attr, label in [
            ("user_md_s3_key", "user-edited"),
            ("formatted_md_s3_key", "AI-formatted"),
            ("docling_raw_md_s3_key", "raw"),
        ]:
            key = getattr(document, key_attr, None)
            if key and await self.s3_client.object_exists(bucket, key):
                markdown = await self.s3_client.download_text(bucket, key)
                logger.info(f"Using {label} markdown from {key}")
                break

        if not markdown:
            legacy_key = f"documents/{self.doc_id}/{self.doc_id}.md"
            if await self.s3_client.object_exists(bucket, legacy_key):
                markdown = await self.s3_client.download_text(bucket, legacy_key)
                logger.info(f"Using legacy markdown from {legacy_key}")

        if markdown:
            (self.dataset_dir / "document.md").write_text(markdown, encoding="utf-8")
            logger.info("Exported document.md")
        else:
            logger.warning(f"Markdown not found for document {self.doc_id}")

        # PDF (mandatory)
        pdf_key = f"documents/{self.doc_id}/{self.doc_id}.pdf"
        if await self.s3_client.object_exists(bucket, pdf_key):
            pdf_bytes = await self.s3_client.download_bytes(bucket, pdf_key)
            (self.dataset_dir / "document.pdf").write_bytes(pdf_bytes)
            logger.info(f"Exported document.pdf ({len(pdf_bytes)} bytes)")
        else:
            raise ValueError(f"PDF not found in S3: {pdf_key}")

        return metadata_row

    def export_annotations(self) -> List[Dict]:
        """Export annotations to annotations.csv"""
        logger.info(f"Exporting annotations for {self.doc_id}...")

        results, _ = db.cypher_query(
            """
            MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(a:MarkdownAnnotation)
            RETURN a.uid, a.text, a.annotation_type, a.start_offset, a.end_offset,
                   a.color, a.source, a.confidence, a.processor_version, a.created_date, a.metadata
            ORDER BY a.start_offset
            """,
            {"doc_id": self.doc_id},
        )

        fieldnames = [
            "uid", "text", "annotation_type", "start_offset", "end_offset",
            "color", "source", "confidence", "processor_version", "created_date", "metadata",
        ]
        rows = []
        for r in results:
            meta = r[10]
            rows.append({
                "uid": r[0] or "",
                "text": r[1] or "",
                "annotation_type": r[2] or "",
                "start_offset": r[3] if r[3] is not None else "",
                "end_offset": r[4] if r[4] is not None else "",
                "color": r[5] or "",
                "source": r[6] or "",
                "confidence": r[7] if r[7] is not None else "",
                "processor_version": r[8] or "",
                "created_date": str(r[9]) if r[9] else "",
                "metadata": json.dumps(meta, ensure_ascii=False) if meta else "",
            })

        self._write_csv(self.dataset_dir / "annotations.csv", rows, fieldnames)
        logger.info(f"Exported {len(rows)} annotations to annotations.csv")
        return rows

    def export_annotation_relations(self) -> List[Dict]:
        """Export annotation relations to annotation_relations.csv"""
        logger.info(f"Exporting annotation relations for {self.doc_id}...")

        results, _ = db.cypher_query(
            """
            MATCH (d:PDFDocument {uid: $doc_id})-[:HAS_MARKDOWN_ANNOTATION]->(src:MarkdownAnnotation)
            MATCH (src)-[r:RELATES_TO]->(tgt:MarkdownAnnotation)
            RETURN r.uid, src.uid, tgt.uid, r.relation_type, r.created_date, r.metadata
            """,
            {"doc_id": self.doc_id},
        )

        fieldnames = ["relation_uid", "source_uid", "target_uid", "relation_type", "created_date", "metadata"]
        rows = []
        for r in results:
            meta = r[5]
            rows.append({
                "relation_uid": r[0] or "",
                "source_uid": r[1] or "",
                "target_uid": r[2] or "",
                "relation_type": r[3] or "",
                "created_date": str(r[4]) if r[4] else "",
                "metadata": json.dumps(meta, ensure_ascii=False) if meta else "",
            })

        if rows:
            self._write_csv(self.dataset_dir / "annotation_relations.csv", rows, fieldnames)
            logger.info(f"Exported {len(rows)} annotation relations to annotation_relations.csv")
        else:
            logger.info("No annotation relations found")
        return rows

    def export_action_graph(self) -> tuple[List[Dict], List[Dict]]:
        """Export Action nodes and LEADS_TO edges to CSV"""
        logger.info(f"Exporting action graph for {self.doc_id}...")

        nodes_result, _ = db.cypher_query(
            """
            MATCH (a:Action {doc_id: $doc_id})
            RETURN a.uid, a.verb, a.verb_text, a.object, a.full_phrase,
                   a.sentence_text, a.action_class, a.char_start
            ORDER BY a.char_start
            """,
            {"doc_id": self.doc_id},
        )

        edges_result, _ = db.cypher_query(
            """
            MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO]->(t:Action {doc_id: $doc_id})
            RETURN s.uid, t.uid, r.relation_subtype, r.confidence, r.status
            """,
            {"doc_id": self.doc_id},
        )

        node_rows = [
            {
                "uid": r[0] or "",
                "verb": r[1] or "",
                "verb_text": r[2] or "",
                "object": r[3] or "",
                "full_phrase": r[4] or "",
                "sentence_text": r[5] or "",
                "action_class": r[6] or "action",
                "char_start": r[7] if r[7] is not None else "",
            }
            for r in nodes_result
        ]
        edge_rows = [
            {
                "src_uid": r[0] or "",
                "tgt_uid": r[1] or "",
                "relation_subtype": r[2] or "",
                "confidence": r[3] if r[3] is not None else "",
                "status": r[4] or "",
            }
            for r in edges_result
        ]

        self._write_csv(
            self.dataset_dir / "action_graph_nodes.csv",
            node_rows,
            ["uid", "verb", "verb_text", "object", "full_phrase", "sentence_text", "action_class", "char_start"],
        )
        self._write_csv(
            self.dataset_dir / "action_graph_edges.csv",
            edge_rows,
            ["src_uid", "tgt_uid", "relation_subtype", "confidence", "status"],
        )
        logger.info(f"Exported {len(node_rows)} action nodes and {len(edge_rows)} edges")
        return node_rows, edge_rows

    async def export_all(self) -> Dict[str, Any]:
        """Export complete dataset to CSV files"""
        logger.info(f"=== Exporting dataset for document {self.doc_id} to {self.sample_id} ===")

        result: Dict[str, Any] = {
            "success": True,
            "sample_id": self.sample_id,
            "doc_id": self.doc_id,
            "exported_files": [],
            "errors": [],
            "counts": {
                "annotations": 0,
                "annotation_relations": 0,
                "action_nodes": 0,
                "action_edges": 0,
            },
        }

        try:
            self.create_directories()

            await self.export_document()
            result["exported_files"].extend([
                f"{self.sample_id}/metadata.csv",
                f"{self.sample_id}/document.md",
                f"{self.sample_id}/document.pdf",
            ])

            annotations = self.export_annotations()
            result["counts"]["annotations"] = len(annotations)
            result["exported_files"].append(f"{self.sample_id}/annotations.csv")

            relations = self.export_annotation_relations()
            result["counts"]["annotation_relations"] = len(relations)
            if relations:
                result["exported_files"].append(f"{self.sample_id}/annotation_relations.csv")

            node_rows, edge_rows = self.export_action_graph()
            result["counts"]["action_nodes"] = len(node_rows)
            result["counts"]["action_edges"] = len(edge_rows)
            result["exported_files"].extend([
                f"{self.sample_id}/action_graph_nodes.csv",
                f"{self.sample_id}/action_graph_edges.csv",
            ])

            # export_summary.csv
            summary_row = {
                "sample_id": self.sample_id,
                "doc_id": self.doc_id,
                "export_date": datetime.now().isoformat(),
                "annotations": result["counts"]["annotations"],
                "annotation_relations": result["counts"]["annotation_relations"],
                "action_nodes": result["counts"]["action_nodes"],
                "action_edges": result["counts"]["action_edges"],
            }
            self._write_csv(
                self.dataset_dir / "export_summary.csv",
                [summary_row],
                ["sample_id", "doc_id", "export_date", "annotations", "annotation_relations", "action_nodes", "action_edges"],
            )
            result["exported_files"].append(f"{self.sample_id}/export_summary.csv")

            logger.info(f"=== Export complete: {json.dumps(result['counts'])} ===")

        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            result["success"] = False
            result["errors"].append(str(e))

        return result


async def main():
    parser = argparse.ArgumentParser(description="Export dataset from Neo4j and S3 to CSV")
    parser.add_argument("--doc-id", required=True, help="Document ID to export")
    args = parser.parse_args()

    try:
        exporter = DatasetExporter(doc_id=args.doc_id)
        result = await exporter.export_all()
        if result["success"]:
            logger.info("Dataset export successful!")
            return 0
        else:
            logger.error(f"Export failed: {result.get('errors')}")
            return 1
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
