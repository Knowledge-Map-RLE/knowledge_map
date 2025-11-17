#!/usr/bin/env python3
"""
Dataset Validation Tool

Validate test datasets against JSON schema and check consistency.

Usage:
    poetry run python tools/dataset_builder/validate_dataset.py --sample sample_001
    poetry run python tools/dataset_builder/validate_dataset.py --all
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Paths
API_ROOT = Path(__file__).parent.parent.parent
PROJECT_ROOT = API_ROOT.parent  # Knowledge_Map/
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"
SCHEMA_PATH = DATASETS_DIR / "schema.json"


class DatasetValidator:
    """Validate dataset structure and consistency"""

    def __init__(self, sample_id: str):
        self.sample_id = sample_id
        self.doc_dir = DATASETS_DIR / "documents" / self.sample_id
        self.ann_dir = DATASETS_DIR / "annotations" / self.sample_id
        self.exp_dir = DATASETS_DIR / "expected" / self.sample_id

        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_structure(self) -> bool:
        """Validate that required files and directories exist"""
        logger.info(f"Validating structure for {self.sample_id}...")

        # Check document directory
        if not self.doc_dir.exists():
            self.errors.append(f"Document directory not found: {self.doc_dir}")
            return False

        # Check required files
        required_files = [
            (self.doc_dir / "metadata.json", "Document metadata"),
            (self.doc_dir / "document.md", "Markdown document"),
        ]

        for file_path, description in required_files:
            if not file_path.exists():
                self.errors.append(f"{description} not found: {file_path}")

        # Check optional files
        optional_files = [
            (self.doc_dir / "document.pdf", "PDF document"),
            (self.ann_dir / "linguistic.json", "Linguistic annotations"),
            (self.ann_dir / "relations.json", "Relations"),
            (self.ann_dir / "chains.json", "Action chains"),
            (self.ann_dir / "patterns.json", "Patterns"),
        ]

        for file_path, description in optional_files:
            if not file_path.exists():
                self.warnings.append(f"{description} not found (optional): {file_path}")

        return len(self.errors) == 0

    def load_json_file(self, file_path: Path) -> Dict[str, Any] | None:
        """Load and parse JSON file"""
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in {file_path}: {e}")
            return None
        except Exception as e:
            self.errors.append(f"Error reading {file_path}: {e}")
            return None

    def validate_metadata(self) -> Dict[str, Any] | None:
        """Validate document metadata"""
        logger.info("Validating metadata...")

        metadata = self.load_json_file(self.doc_dir / "metadata.json")
        if not metadata:
            return None

        # Check required fields
        required_fields = ["doc_id"]
        for field in required_fields:
            if field not in metadata:
                self.errors.append(f"Missing required field in metadata: {field}")

        # Check field types
        if "doc_id" in metadata and not isinstance(metadata["doc_id"], str):
            self.errors.append("metadata.doc_id must be a string")

        if "authors" in metadata and not isinstance(metadata["authors"], list):
            self.errors.append("metadata.authors must be a list")

        return metadata

    def validate_annotations(self, markdown_text: str) -> Tuple[List[Dict], Set[str]]:
        """Validate linguistic annotations"""
        logger.info("Validating annotations...")

        data = self.load_json_file(self.ann_dir / "linguistic.json")
        if not data:
            return [], set()

        annotations = data.get("annotations", [])
        annotation_uids = set()

        for i, ann in enumerate(annotations):
            # Check required fields
            required_fields = ["uid", "text", "annotation_type", "start_offset", "end_offset"]
            for field in required_fields:
                if field not in ann:
                    self.errors.append(f"Annotation {i}: missing required field '{field}'")

            # Validate offsets
            if "start_offset" in ann and "end_offset" in ann:
                start = ann["start_offset"]
                end = ann["end_offset"]

                if not isinstance(start, int) or not isinstance(end, int):
                    self.errors.append(f"Annotation {i}: offsets must be integers")
                elif start < 0 or end < 0:
                    self.errors.append(f"Annotation {i}: offsets must be non-negative")
                elif start >= end:
                    self.errors.append(f"Annotation {i}: start_offset must be less than end_offset")
                elif end > len(markdown_text):
                    self.errors.append(
                        f"Annotation {i}: end_offset ({end}) exceeds markdown length ({len(markdown_text)})"
                    )
                else:
                    # Validate text matches offsets
                    expected_text = markdown_text[start:end]
                    actual_text = ann.get("text", "")
                    if expected_text != actual_text:
                        self.warnings.append(
                            f"Annotation {i}: text mismatch at offsets [{start}:{end}]. "
                            f"Expected: '{expected_text}', got: '{actual_text}'"
                        )

            # Validate confidence
            if "confidence" in ann:
                conf = ann["confidence"]
                if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
                    self.errors.append(f"Annotation {i}: confidence must be between 0.0 and 1.0")

            # Validate color format
            if "color" in ann:
                color = ann["color"]
                if not isinstance(color, str) or not color.startswith("#") or len(color) != 7:
                    self.warnings.append(f"Annotation {i}: color should be in hex format (#RRGGBB)")

            # Track UIDs
            if "uid" in ann:
                uid = ann["uid"]
                if uid in annotation_uids:
                    self.errors.append(f"Annotation {i}: duplicate UID '{uid}'")
                annotation_uids.add(uid)

        logger.info(f"Found {len(annotations)} annotations with {len(annotation_uids)} unique UIDs")
        return annotations, annotation_uids

    def validate_relations(self, annotation_uids: Set[str]):
        """Validate relations between annotations"""
        logger.info("Validating relations...")

        data = self.load_json_file(self.ann_dir / "relations.json")
        if not data:
            return []

        relations = data.get("relations", [])

        for i, rel in enumerate(relations):
            # Check required fields
            required_fields = ["source_uid", "target_uid", "relation_type"]
            for field in required_fields:
                if field not in rel:
                    self.errors.append(f"Relation {i}: missing required field '{field}'")

            # Validate UIDs exist
            source_uid = rel.get("source_uid")
            target_uid = rel.get("target_uid")

            if source_uid and source_uid not in annotation_uids:
                self.errors.append(f"Relation {i}: source_uid '{source_uid}' not found in annotations")

            if target_uid and target_uid not in annotation_uids:
                self.errors.append(f"Relation {i}: target_uid '{target_uid}' not found in annotations")

            # Validate self-loops
            if source_uid == target_uid:
                self.warnings.append(f"Relation {i}: self-loop detected (source == target)")

        logger.info(f"Found {len(relations)} relations")
        return relations

    def validate_chains(self):
        """Validate action chains"""
        logger.info("Validating action chains...")

        data = self.load_json_file(self.ann_dir / "chains.json")
        if not data:
            return []

        chains = data.get("chains", [])

        valid_sequence_types = ["temporal", "causal", "conditional", "sequential"]

        for i, chain in enumerate(chains):
            # Check required fields
            required_fields = ["verbs", "sequence_type"]
            for field in required_fields:
                if field not in chain:
                    self.errors.append(f"Chain {i}: missing required field '{field}'")

            # Validate sequence type
            if "sequence_type" in chain:
                seq_type = chain["sequence_type"]
                if seq_type not in valid_sequence_types:
                    self.errors.append(
                        f"Chain {i}: invalid sequence_type '{seq_type}'. "
                        f"Must be one of: {valid_sequence_types}"
                    )

            # Validate verbs list
            if "verbs" in chain:
                verbs = chain["verbs"]
                if not isinstance(verbs, list):
                    self.errors.append(f"Chain {i}: verbs must be a list")
                elif len(verbs) < 2:
                    self.warnings.append(f"Chain {i}: chain has less than 2 verbs")

            # Validate confidence
            if "confidence" in chain:
                conf = chain["confidence"]
                if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
                    self.errors.append(f"Chain {i}: confidence must be between 0.0 and 1.0")

        logger.info(f"Found {len(chains)} action chains")
        return chains

    def validate_all(self) -> bool:
        """Run all validations"""
        logger.info(f"=== Validating dataset {self.sample_id} ===")

        # Validate structure
        if not self.validate_structure():
            logger.error("Structure validation failed")
            return False

        # Load markdown for offset validation
        md_path = self.doc_dir / "document.md"
        markdown_text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""

        # Validate components
        metadata = self.validate_metadata()
        annotations, annotation_uids = self.validate_annotations(markdown_text)
        relations = self.validate_relations(annotation_uids)
        chains = self.validate_chains()

        # Print results
        logger.info(f"=== Validation Results ===")
        logger.info(f"Sample: {self.sample_id}")
        logger.info(f"Errors: {len(self.errors)}")
        logger.info(f"Warnings: {len(self.warnings)}")

        if self.errors:
            logger.error("=== ERRORS ===")
            for error in self.errors:
                logger.error(f"  ✗ {error}")

        if self.warnings:
            logger.warning("=== WARNINGS ===")
            for warning in self.warnings:
                logger.warning(f"  ⚠ {warning}")

        if not self.errors and not self.warnings:
            logger.info("✓ Dataset is valid!")
            return True
        elif not self.errors:
            logger.info("✓ Dataset is valid (with warnings)")
            return True
        else:
            logger.error("✗ Dataset validation failed")
            return False


def validate_all_samples() -> bool:
    """Validate all samples in the datasets directory"""
    logger.info("Validating all datasets...")

    documents_dir = DATASETS_DIR / "documents"
    if not documents_dir.exists():
        logger.error(f"Documents directory not found: {documents_dir}")
        return False

    samples = [d.name for d in documents_dir.iterdir() if d.is_dir()]

    if not samples:
        logger.warning("No samples found to validate")
        return True

    all_valid = True
    for sample_id in sorted(samples):
        logger.info(f"\n{'='*60}")
        validator = DatasetValidator(sample_id)
        is_valid = validator.validate_all()
        all_valid = all_valid and is_valid

    logger.info(f"\n{'='*60}")
    logger.info(f"Validated {len(samples)} samples")

    if all_valid:
        logger.info("✓ All datasets are valid!")
    else:
        logger.error("✗ Some datasets have validation errors")

    return all_valid


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Validate test datasets")
    parser.add_argument("--sample", help="Sample ID to validate (e.g., sample_001)")
    parser.add_argument("--all", action="store_true", help="Validate all samples")

    args = parser.parse_args()

    if args.all:
        success = validate_all_samples()
    elif args.sample:
        validator = DatasetValidator(args.sample)
        success = validator.validate_all()
    else:
        parser.print_help()
        return 1

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
