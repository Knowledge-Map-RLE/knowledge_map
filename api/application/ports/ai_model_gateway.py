"""
Layer: Application (Use Cases) — Ports
Package: application.ports.ai_model_gateway
Responsibility: Контракт сервиса AI-моделей (генерация текста).

Реализация находится в infrastructure/grpc_clients/ai_model_grpc_client.py.

Allowed imports: typing, стандартная библиотека
Forbidden imports: grpc, fastapi, neomodel
"""
from __future__ import annotations

from typing import Protocol, List, Dict, Any, AsyncIterator


class AIModelGatewayProtocol(Protocol):
    """Асинхронный интерфейс AI-модели."""

    async def generate(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> Dict[str, Any]: ...

    async def list_models(self) -> List[Dict[str, Any]]: ...

    async def health_check(self) -> bool: ...
