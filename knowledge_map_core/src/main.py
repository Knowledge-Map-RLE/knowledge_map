from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

# Let asyncio/Python handle Ctrl+C instead of Intel's Fortran runtime aborting
# the process before gRPC and its clients can shut down cleanly on Windows.
os.environ["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"

# Ensure project root is on sys.path (for python src/main.py without -m)
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import grpc

from src.config import settings

logger = logging.getLogger(__name__)


def _ensure_proto_generated():
    proto_dir = Path(__file__).resolve().parent.parent / "proto"
    src_dir = Path(__file__).resolve().parent

    pb2 = src_dir / "knowledge_language_pb2.py"
    pb2_grpc = src_dir / "knowledge_language_pb2_grpc.py"

    if pb2.exists() and pb2_grpc.exists():
        _fix_proto_imports(src_dir)
        return

    logger.info("Generating protobuf stubs...")
    proto_file = proto_dir / "knowledge_language.proto"

    result = subprocess.run(
        [
            sys.executable, "-m", "grpc_tools.protoc",
            f"-I{proto_dir}",
            f"--python_out={src_dir}",
            f"--grpc_python_out={src_dir}",
            str(proto_file),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error("Protobuf generation failed: %s", result.stderr)
        raise RuntimeError(f"Protobuf generation failed: {result.stderr}")

    _fix_proto_imports(src_dir)


def _fix_proto_imports(src_dir: Path) -> None:
    # Fix knowledge_language_pb2_grpc.py
    _fix_pb2_grpc(src_dir / "knowledge_language_pb2_grpc.py", "knowledge_language_pb2")

    # Fix ai_model_pb2_grpc.py
    _fix_pb2_grpc(src_dir / "llm" / "ai_model_pb2_grpc.py", "ai_model_pb2")

    # Fix nlp_pb2_grpc.py
    _fix_pb2_grpc(src_dir / "parser" / "nlp_pb2_grpc.py", "nlp_pb2")

    logger.info("Proto imports fixed.")


def _fix_pb2_grpc(grpc_file: Path, pb2_module: str) -> None:
    if not grpc_file.exists():
        return
    content = grpc_file.read_text(encoding="utf-8")
    old_import = f"import {pb2_module} as"
    new_import = f"from . import {pb2_module} as"
    if old_import in content and new_import not in content:
        content = content.replace(old_import, new_import)
        grpc_file.write_text(content, encoding="utf-8")


def _is_port_available(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


async def serve() -> None:
    from src import knowledge_language_pb2_grpc
    from src.config import settings
    from src.services.grpc_server import KnowledgeLanguageServicer
    from src.services.pipeline import Pipeline
    from src.services.uniqueness_pipeline import UniquenessPipeline
    from src.infrastructure.qdrant_store import QdrantVectorStore
    from src.infrastructure.embedder import SentenceTransformerEmbedder
    from src.infrastructure.subgraph_matcher import SubgraphMatcherVF2
    from src.infrastructure.frequent_miner import GastonMiner
    from src.infrastructure.wl_hasher import compute_wl_hash
    from src.neo4j.writer import Neo4jWriter

    if not _is_port_available(settings.grpc_port):
        raise RuntimeError(
            f"gRPC port {settings.grpc_port} is already in use. "
            "Stop the process that owns this configured port before starting the service."
        )

    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", 256 * 1024 * 1024),
            ("grpc.max_receive_message_length", 256 * 1024 * 1024),
        ],
    )

    address = f"{settings.grpc_host}:{settings.grpc_port}"
    vector_store = None
    uniqueness_pipeline = None
    server_started = False
    try:
        pipeline = Pipeline()

        # Embeddings are only needed by semantic uniqueness operations. Keep the
        # model unloaded here so ordinary gRPC startup does not import PyTorch or
        # synchronously load model artifacts.
        embedder = SentenceTransformerEmbedder(settings.embedding_model)

        vector_store = QdrantVectorStore(
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            embedding_dimension=settings.embedding_dimension,
        )
        await vector_store.connect()

        subgraph_matcher = SubgraphMatcherVF2()
        frequent_miner = GastonMiner(
            min_support=settings.uniqueness_fsg_min_support,
            max_size=settings.uniqueness_fsg_max_size,
        )
        uniqueness_pipeline = UniquenessPipeline(
            embedder=embedder,
            vector_store=vector_store,
            subgraph_matcher=subgraph_matcher,
            frequent_miner=frequent_miner,
            wl_hasher=compute_wl_hash,
        )

        servicer = KnowledgeLanguageServicer(
            pipeline=pipeline,
            uniqueness_pipeline=uniqueness_pipeline,
        )
        knowledge_language_pb2_grpc.add_KnowledgeLanguageServiceServicer_to_server(
            servicer, server,
        )

        bound_port = server.add_insecure_port(address)
        if bound_port == 0:
            raise RuntimeError(f"Could not bind gRPC server to configured address {address}")
        logger.info("Knowledge Language gRPC server starting on %s", address)

        # Ensure Neo4j indexes for uniqueness.
        try:
            async with Neo4jWriter() as writer:
                await writer.ensure_indexes()
                logger.info("Neo4j uniqueness indexes ensured")
        except Exception as e:
            logger.warning("Failed to ensure Neo4j indexes: %s", e)

        await server.start()
        server_started = True
        logger.info("Knowledge Language gRPC server is ready on %s", address)
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("gRPC shutdown requested; draining active calls")
        raise
    finally:
        try:
            await server.stop(grace=5.0 if server_started else 0)
        finally:
            try:
                if vector_store is not None:
                    await vector_store.close()
            finally:
                if uniqueness_pipeline is not None:
                    await uniqueness_pipeline.close()


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _ensure_proto_generated()
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        # asyncio.run translates the cancellation caused by Ctrl+C into this
        # exception after serve() has completed its asynchronous cleanup.
        logger.info("Knowledge Language gRPC server stopped")


if __name__ == "__main__":
    main()
