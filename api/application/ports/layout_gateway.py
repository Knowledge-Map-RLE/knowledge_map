"""
Layer: Application (Use Cases) — Ports
Package: application.ports.layout_gateway
Responsibility: Контракт сервиса расчёта укладки графа.

Реализация находится в infrastructure/grpc_clients/layout_grpc_client.py.

Allowed imports: typing, стандартная библиотека
Forbidden imports: grpc, fastapi, neomodel
"""
from __future__ import annotations

from typing import Protocol, List, Dict, Any


class LayoutGatewayProtocol(Protocol):
    """Асинхронный интерфейс сервиса укладки графа."""

    async def calculate_layout(
        self,
        blocks: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
    ) -> Dict[str, Any]: ...

    async def health_check(self) -> bool: ...
