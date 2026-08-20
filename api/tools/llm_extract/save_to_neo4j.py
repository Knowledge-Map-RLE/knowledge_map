"""Save extracted v3 blocks to Neo4j.

Usage:
    poetry run python api/tools/llm_extract/save_to_neo4j.py
"""
import json
import sys
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("ERROR: neo4j module not found. Run with api venv:")
    print("  api/.venv/Scripts/python.exe api/tools/llm_extract/save_to_neo4j.py")
    sys.exit(1)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

EXTRACTIONS = [
    {
        "file": Path(__file__).parent / "extracted_hallmarks_v7.json",
        "doc_id": "f8e0c6a4a0237d72aa04b5e3638ed50f",
        "label": "Hallmarks of cancer and hallmarks of aging",
    },
    {
        "file": Path(__file__).parent / "extracted_immuno_v7.json",
        "doc_id": "000657ba-aec6-8a11-9c5c-986526539651",
        "label": "Immunometabolic resistors of aging in long-lived golden spiny mice",
    },
]

BATCH_SIZE = 500


def load_blocks(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("blocks", []))
    return list(data)


def save_blocks_to_neo4j(driver, doc_id: str, blocks: list[dict]):
    """Delete old blocks for doc, create new ArticleBlock nodes + HAS_BLOCK edges."""
    with driver.session() as session:
        # Delete old blocks
        result = session.run(
            "MATCH (d:Document {uid: $doc_id}) "
            "OPTIONAL MATCH (d)-[r:HAS_BLOCK]->(b:ArticleBlock) "
            "DELETE r, b",
            doc_id=doc_id,
        )
        summary = result.consume()
        print(f"  Deleted {summary.counters.nodes_deleted} old blocks")

        # Batch create
        batch = []
        for i, block in enumerate(blocks):
            block_uid = block.get("instanceId") or f"gen-{doc_id[:8]}-{i}"
            batch.append({
                "uid": block_uid,
                "bt": int(block.get("blockType", 0)),
                "data": json.dumps(block.get("data", {}), ensure_ascii=False),
                "order": int(block.get("order", i)),
            })

        created = 0
        for chunk_start in range(0, len(batch), BATCH_SIZE):
            chunk = batch[chunk_start : chunk_start + BATCH_SIZE]
            session.run(
                "MATCH (d:Document {uid: $doc_id}) "
                "UNWIND $batch AS item "
                "CREATE (b:ArticleBlock {"
                "  uid: item.uid, block_type: item.bt, data: item.data, "
                "  order: item.order"
                "}) "
                "CREATE (d)-[:HAS_BLOCK]->(b)",
                {"batch": chunk, "doc_id": doc_id},
            )
            created += len(chunk)

        # Update edit_date
        from datetime import datetime, timezone
        session.run(
            "MATCH (d:Document {uid: $doc_id}) "
            "SET d.edit_date = datetime($now)",
            {"doc_id": doc_id, "now": datetime.now(timezone.utc).isoformat()},
        )

        print(f"  Created {created} ArticleBlock nodes")


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        for ext in EXTRACTIONS:
            print(f"\n{'='*60}")
            print(f"  {ext['label']}")
            print(f"  doc_id: {ext['doc_id']}")
            print(f"{'='*60}")

            # Verify document exists
            with driver.session() as session:
                result = session.run(
                    "MATCH (d:Document {uid: $doc_id}) RETURN d.uid AS uid, d.title AS title",
                    doc_id=ext["doc_id"],
                )
                record = result.single()
                if not record:
                    print(f"  ERROR: Document {ext['doc_id']} not found in Neo4j!")
                    continue
                print(f"  Found document: {record['title']}")

            blocks = load_blocks(ext["file"])
            print(f"  Loaded {len(blocks)} blocks from {ext['file'].name}")

            save_blocks_to_neo4j(driver, ext["doc_id"], blocks)

        print(f"\n{'='*60}")
        print("  Done!")
        print(f"{'='*60}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
