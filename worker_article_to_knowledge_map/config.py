"""Configuration for the batch article processing worker."""
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Search parameters
    query: str = field(default_factory=lambda: os.getenv("WORKER_QUERY", "aging"))
    target_count: int = field(default_factory=lambda: int(os.getenv("WORKER_TARGET_COUNT", "1000")))
    batch_size: int = field(default_factory=lambda: int(os.getenv("WORKER_BATCH_SIZE", "5")))

    # API
    api_base_url: str = field(
        default_factory=lambda: os.getenv("WORKER_API_URL", "http://localhost:8000/api/data_extraction")
    )
    api_timeout: float = field(default_factory=lambda: float(os.getenv("WORKER_API_TIMEOUT", "120")))

    # Status API
    status_port: int = field(default_factory=lambda: int(os.getenv("WORKER_STATUS_PORT", "8004")))
    status_host: str = field(default_factory=lambda: os.getenv("WORKER_STATUS_HOST", "0.0.0.0"))

    # NCBI
    ncbi_api_key: str = field(default_factory=lambda: os.getenv("NCBI_API_KEY", ""))
    ncbi_tool: str = field(default_factory=lambda: os.getenv("NCBI_TOOL", "KnowledgeMapWorker"))
    ncbi_email: str = field(default_factory=lambda: os.getenv("NCBI_EMAIL", "worker@knowledge-map.local"))

    # Timing
    annotate_wait_sec: float = field(default_factory=lambda: float(os.getenv("WORKER_ANNOTATE_WAIT", "300")))
    poll_interval_sec: float = field(default_factory=lambda: float(os.getenv("WORKER_POLL_INTERVAL", "3")))
    poll_timeout_sec: float = field(default_factory=lambda: float(os.getenv("WORKER_POLL_TIMEOUT", "300")))

    # Retry
    max_retries: int = field(default_factory=lambda: int(os.getenv("WORKER_MAX_RETRIES", "3")))
    retry_base_delay: float = field(default_factory=lambda: float(os.getenv("WORKER_RETRY_DELAY", "5")))

    # Neo4j (for state storage)
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "password"))


def load_config() -> Config:
    return Config()
