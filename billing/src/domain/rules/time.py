from datetime import datetime, timezone


def utcnow() -> datetime:
    """Наивное UTC-время (соглашение хранения в Neo4j)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
