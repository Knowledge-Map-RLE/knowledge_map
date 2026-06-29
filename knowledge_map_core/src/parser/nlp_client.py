from __future__ import annotations

import logging

import grpc

from src.config import settings
from src.parser.dep_tree import DependencyTree

logger = logging.getLogger(__name__)

NLP_PROCESS_TEXT_TEMPLATE = """
syntax = "proto3";
package nlp;
service NLPService {
    rpc AnalyzeText(AnalyzeTextRequest) returns (AnalyzeTextResponse);
}
"""


class NLPClient:
    def __init__(self, host: str | None = None, port: int | None = None):
        self._host = host or settings.nlp_grpc_host
        self._port = port or settings.nlp_grpc_port
        self._channel: grpc.aio.Channel | None = None

    async def __aenter__(self) -> NLPClient:
        self._channel = grpc.aio.insecure_channel(
            f"{self._host}:{self._port}",
            options=[
                ("grpc.max_send_message_length", 256 * 1024 * 1024),
                ("grpc.max_receive_message_length", 256 * 1024 * 1024),
            ],
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._channel:
            await self._channel.close()

    async def get_dependency_trees(self, text: str) -> list[DependencyTree]:
        from src.parser import nlp_pb2_grpc, nlp_pb2

        stub = nlp_pb2_grpc.NLPServiceStub(self._channel)

        request = nlp_pb2.AnalyzeTextRequest(
            text=text,
            enable_voting=False,
        )

        try:
            response = await stub.AnalyzeText(request)
        except grpc.RpcError as e:
            logger.error("NLP gRPC call failed: %s", e)
            raise

        if not response.success:
            logger.warning("NLP analysis unsuccessful: %s", response.message)
            return []

        doc = response.document
        sentences = doc.sentences if doc else []
        trees = []

        for sent in sentences:
            sent_dict = _sentence_to_dict(sent)
            tree = DependencyTree.from_unified_sentence(sent_dict)
            trees.append(tree)

        return trees


def _sentence_to_dict(sentence) -> dict:
    tokens = []
    for tok in (sentence.tokens or []):
        tokens.append({
            "idx": tok.idx,
            "text": tok.text,
            "lemma": tok.lemma,
            "pos": tok.pos,
            "pos_fine": tok.pos_fine,
            "morph": dict(tok.morph or {}),
            "is_stop": tok.is_stop,
            "is_punct": tok.is_punct,
            "is_space": tok.is_space,
        })

    deps = []
    for dep in (sentence.dependencies or []):
        deps.append({
            "head_idx": dep.head_idx,
            "dependent_idx": dep.dependent_idx,
            "relation": dep.relation,
        })

    return {"tokens": tokens, "dependencies": deps}
