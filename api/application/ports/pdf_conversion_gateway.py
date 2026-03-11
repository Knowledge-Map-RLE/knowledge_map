"""
Layer: Application (Use Cases) — Ports
Package: application.ports.pdf_conversion_gateway
Responsibility: Контракт сервиса конвертации PDF в Markdown.

Реализация находится в infrastructure/grpc_clients/pdf_to_md_grpc_client.py.

Allowed imports: typing, стандартная библиотека
Forbidden imports: grpc, fastapi, neomodel
"""
from __future__ import annotations

from typing import Protocol, Dict, Any


class PDFConversionGatewayProtocol(Protocol):
    """Асинхронный интерфейс сервиса PDF → Markdown."""

    async def convert_pdf(
        self,
        pdf_content: bytes,
        doc_id: str,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """
        Конвертирует PDF в Markdown.

        Returns:
            dict с ключами: success, markdown, images (dict имя→bytes), error
        """
        ...
