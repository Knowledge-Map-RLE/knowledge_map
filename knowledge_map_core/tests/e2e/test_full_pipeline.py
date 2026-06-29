"""End-to-end test for the full gRPC pipeline.

Requires the following services running:
  - knowledge_map_core:50056  (required)
  - nlp:50055                 (required)
  - ai:50054                  (required only for use_llm=True tests)
"""

from __future__ import annotations

import pytest
import grpc

pytestmark = pytest.mark.e2e

CORE_HOST = "localhost"
CORE_PORT = 50056


def _channel() -> grpc.aio.Channel:
    return grpc.aio.insecure_channel(
        f"{CORE_HOST}:{CORE_PORT}",
        options=[
            ("grpc.max_send_message_length", 256 * 1024 * 1024),
            ("grpc.max_receive_message_length", 256 * 1024 * 1024),
        ],
    )


@pytest.fixture(scope="module")
def event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_health_check():
    from src import knowledge_language_pb2_grpc, knowledge_language_pb2

    async with _channel() as channel:
        stub = knowledge_language_pb2_grpc.KnowledgeLanguageServiceStub(channel)
        response = await stub.HealthCheck(
            knowledge_language_pb2.HealthCheckRequest(service="knowledge_language")
        )
        assert response.status == "SERVING"
        assert response.service == "knowledge_language"


@pytest.mark.asyncio
async def test_process_text_simple():
    from src import knowledge_language_pb2_grpc, knowledge_language_pb2

    async with _channel() as channel:
        stub = knowledge_language_pb2_grpc.KnowledgeLanguageServiceStub(channel)
        response = await stub.ProcessText(
            knowledge_language_pb2.ProcessTextRequest(
                text="Dopamine is a neurotransmitter.",
                doc_id="test-doc-001",
                use_llm=False,
            )
        )
        assert response.success, f"ProcessText failed: {response.message}"
        assert response.total_statements >= 1, f"Expected >=1 statement, got {response.total_statements}"
        assert response.doc_id == "test-doc-001"
        assert len(response.concepts) >= 2

        # Verify statement structure
        stmt = response.statements[0]
        assert stmt.id
        assert stmt.predicate
        assert stmt.subject_id
        assert stmt.object_id or stmt.literal_value


@pytest.mark.asyncio
async def test_process_text_with_llm():
    from src import knowledge_language_pb2_grpc, knowledge_language_pb2

    async with _channel() as channel:
        stub = knowledge_language_pb2_grpc.KnowledgeLanguageServiceStub(channel)
        response = await stub.ProcessText(
            knowledge_language_pb2.ProcessTextRequest(
                text="Parkinson's disease involves loss of dopamine neurons. "
                     "This leads to motor symptoms.",
                doc_id="test-doc-002",
                use_llm=True,
                llm_model_id="Qwen/Qwen2.5-0.5B-Instruct",
            )
        )
        assert response.success, f"ProcessText failed: {response.message}"
        assert response.total_statements >= 1
        assert response.total_concepts >= 2


@pytest.mark.asyncio
async def test_process_text_complex_sentence():
    from src import knowledge_language_pb2_grpc, knowledge_language_pb2

    async with _channel() as channel:
        stub = knowledge_language_pb2_grpc.KnowledgeLanguageServiceStub(channel)
        response = await stub.ProcessText(
            knowledge_language_pb2.ProcessTextRequest(
                text="The hallmarks of cancer include genomic instability, "
                     "which promotes tumor diversity.",
                doc_id="test-doc-003",
                use_llm=False,
            )
        )
        assert response.success, f"ProcessText failed: {response.message}"
        assert response.total_statements >= 1
