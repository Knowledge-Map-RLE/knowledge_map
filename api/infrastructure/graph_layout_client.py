"""
Layer: Infrastructure
Package: infrastructure.graph_layout_client
Responsibility: gRPC клиент к Rust-воркеру GraphLayoutService (порт 50051).

Принимает любой граф в виде рёбер (source_id, target_id) и возвращает
координаты (x, y) для каждой вершины — без привязки к типам нод в БД.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import grpc

from utils.generated import graph_layout_pb2, graph_layout_pb2_grpc

logger = logging.getLogger(__name__)

_GRAPH_LAYOUT_HOST = os.getenv("GRAPH_LAYOUT_HOST", "localhost")
_GRAPH_LAYOUT_PORT = int(os.getenv("GRAPH_LAYOUT_PORT", "50051"))


class GraphLayoutClient:
    """
    Тонкий gRPC клиент к Rust GraphLayoutService.

    Входные данные: список рёбер [{source_id, target_id}]
    Выходные данные: {node_id: (x, y)}
    """

    def __init__(self, host: str = _GRAPH_LAYOUT_HOST, port: int = _GRAPH_LAYOUT_PORT) -> None:
        self._address = f"{host}:{port}"

    async def compute_layout(
        self,
        edges: list[dict[str, str]],
        block_width: float = 200.0,
        block_height: float = 80.0,
        horizontal_gap: float = 40.0,
        vertical_gap: float = 50.0,
        reduce_crossings: bool = False,
    ) -> dict[str, tuple[float, float]]:
        """
        Отправляет рёбра в Rust-воркер, получает координаты вершин.

        Args:
            edges: список {"source_id": str, "target_id": str}
            block_width, block_height, horizontal_gap, vertical_gap: параметры размещения

        Returns:
            {node_id: (x, y)} — координаты для каждой вершины из ответа

        Raises:
            grpc.RpcError: если воркер недоступен или вернул ошибку
        """
        proto_edges = [
            graph_layout_pb2.GraphEdge(
                source_id=e["source_id"],
                target_id=e["target_id"],
                weight=1.0,
            )
            for e in edges
        ]

        options = graph_layout_pb2.LayoutOptions(
            block_width=block_width,
            block_height=block_height,
            horizontal_gap=horizontal_gap,
            vertical_gap=vertical_gap,
            exclude_isolated_vertices=True,
            optimize_layout=reduce_crossings,
        )

        request = graph_layout_pb2.LayoutRequest(
            task_id="api_request",
            edges=proto_edges,
            options=options,
        )

        async with grpc.aio.insecure_channel(self._address) as channel:
            stub = graph_layout_pb2_grpc.GraphLayoutServiceStub(channel)
            response: Any = await stub.ComputeLayout(request)

        if not response.success:
            raise RuntimeError(f"GraphLayoutService error: {response.error_message}")

        return {
            pos.article_id: (float(pos.x), float(pos.y))
            for pos in response.positions
        }

    async def health_check(self) -> bool:
        """Проверяет доступность Rust-воркера."""
        try:
            async with grpc.aio.insecure_channel(self._address) as channel:
                stub = graph_layout_pb2_grpc.GraphLayoutServiceStub(channel)
                resp = await stub.GetHealth(graph_layout_pb2.HealthRequest())
            return resp.status == graph_layout_pb2.HealthResponse.SERVING
        except grpc.RpcError:
            return False


_client: GraphLayoutClient | None = None


def get_graph_layout_client() -> GraphLayoutClient:
    """Синглтон клиента (создаётся при первом вызове)."""
    global _client
    if _client is None:
        _client = GraphLayoutClient()
    return _client
