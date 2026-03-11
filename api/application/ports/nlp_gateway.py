"""
Layer: Application (Use Cases) — Ports
Package: application.ports.nlp_gateway
Responsibility: Контракт NLP-микросервиса для use cases.

Реализация находится в infrastructure/grpc_clients/nlp_grpc_client.py.

Allowed imports: typing, стандартная библиотека
Forbidden imports: grpc, fastapi, neomodel, adapters, infrastructure, web
"""
from __future__ import annotations

from typing import Protocol, Optional, List, Dict, Any


class NLPGatewayProtocol(Protocol):
    """Асинхронный интерфейс NLP-микросервиса."""

    async def process_text(
        self,
        text: str,
        processor_names: Optional[List[str]] = None,
        merge_results: bool = True,
        timeout: int = 300,
    ) -> Dict[str, Any]: ...

    async def process_selection(
        self,
        text: str,
        start: int,
        end: int,
    ) -> Dict[str, Any]: ...

    async def validate_markdown(
        self,
        markdown: str,
        strict_mode: bool = False,
    ) -> Dict[str, Any]: ...

    async def get_supported_types(self) -> Dict[str, Any]: ...

    async def get_analyzer_info(self) -> Dict[str, Any]: ...
