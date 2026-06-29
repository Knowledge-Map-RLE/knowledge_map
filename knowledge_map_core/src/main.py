from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

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


def _kill_process_on_port(port: int) -> None:
    import subprocess
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True,
        )
        lines = result.stdout.split("\n")
        for line in lines:
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pid = parts[-1]
                    logger.warning("Killing process %s on port %s", pid, port)
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    except Exception:
        pass


async def serve() -> None:
    from src import knowledge_language_pb2_grpc
    from src.services.grpc_server import KnowledgeLanguageServicer
    from src.services.pipeline import Pipeline

    # Always kill any previous instance on the port first
    _kill_process_on_port(settings.grpc_port)
    await asyncio.sleep(1)

    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", 256 * 1024 * 1024),
            ("grpc.max_receive_message_length", 256 * 1024 * 1024),
        ],
    )

    pipeline = Pipeline()
    servicer = KnowledgeLanguageServicer(pipeline=pipeline)

    knowledge_language_pb2_grpc.add_KnowledgeLanguageServiceServicer_to_server(
        servicer, server,
    )

    address = f"{settings.grpc_host}:{settings.grpc_port}"
    server.add_insecure_port(address)
    logger.info("Knowledge Language gRPC server starting on %s", address)

    await server.start()
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        await server.stop(0)


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _ensure_proto_generated()
    asyncio.run(serve())


if __name__ == "__main__":
    main()
