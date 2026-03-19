#!/usr/bin/env python3
"""Асинхронный gRPC клиент для взаимодействия с xml_to_md сервисом."""
import logging
import os
from typing import Any, Dict, List, Optional

import grpc
from grpc import aio

from utils.generated import xml_to_md_pb2, xml_to_md_pb2_grpc

logger = logging.getLogger(__name__)


class XmlToMdGRPCClient:
    """Асинхронный gRPC клиент для xml_to_md сервиса."""

    def __init__(self, host: str = None, port: int = None):
        env_host = os.getenv("XML_TO_MD_SERVICE_HOST", "127.0.0.1")
        env_port = os.getenv("XML_TO_MD_SERVICE_PORT", "50054")
        self.host = host or env_host
        self.port = port or int(env_port)
        self.channel = None
        self.stub = None
        self._connected = False
        logger.info(f"[xml_to_md_client] Создан клиент: {self.host}:{self.port}")

    async def connect(self):
        """Подключение к gRPC серверу."""
        if not self._connected:
            self.channel = aio.insecure_channel(f"{self.host}:{self.port}")
            self.stub = xml_to_md_pb2_grpc.XmlToMarkdownServiceStub(self.channel)
            self._connected = True
            logger.info(f"[xml_to_md_client] Подключён к {self.host}:{self.port}")

    async def disconnect(self):
        """Отключение от gRPC сервера."""
        if self.channel:
            await self.channel.close()
            self._connected = False

    async def convert_pmc_xml(
        self,
        xml_bytes: bytes,
        image_urls: Optional[Dict[str, str]] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """Конвертация PMC XML в Markdown.

        Returns:
            {"success": bool, "markdown_content": str, "message": str}
        """
        await self.connect()
        try:
            request = xml_to_md_pb2.ConvertPmcXmlRequest(
                xml_bytes=xml_bytes,
                image_urls=image_urls or {},
                provider=xml_to_md_pb2.PMC,
            )
            response = await self.stub.ConvertPmcXml(request, timeout=timeout)
            return {
                "success": response.success,
                "markdown_content": response.markdown_content,
                "message": response.message,
            }
        except Exception as e:
            logger.error(f"[xml_to_md_client] Ошибка convert_pmc_xml: {e}")
            return {"success": False, "markdown_content": "", "message": str(e)}

    async def parse_pubmed_metadata(
        self,
        xml_bytes: bytes,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Парсинг PubMed efetch XML → список метаданных статей.

        Returns:
            {"success": bool, "articles": [{"pmid":..., "title":..., ...}], "message": str}
        """
        await self.connect()
        try:
            request = xml_to_md_pb2.ParsePubmedMetadataRequest(xml_bytes=xml_bytes)
            response = await self.stub.ParsePubmedMetadata(request, timeout=timeout)
            articles = [
                {
                    "pmid": a.pmid,
                    "title": a.title,
                    "authors": list(a.authors),
                    "journal": a.journal,
                    "pub_date": a.pub_date,
                    "abstract": a.abstract,
                    "doi": a.doi or None,
                }
                for a in response.articles
            ]
            return {
                "success": response.success,
                "articles": articles,
                "message": response.message,
            }
        except Exception as e:
            logger.error(f"[xml_to_md_client] Ошибка parse_pubmed_metadata: {e}")
            return {"success": False, "articles": [], "message": str(e)}


_xml_to_md_grpc_client: Optional[XmlToMdGRPCClient] = None


def get_xml_to_md_grpc_client() -> XmlToMdGRPCClient:
    """Lazy singleton для xml_to_md gRPC клиента."""
    global _xml_to_md_grpc_client
    if _xml_to_md_grpc_client is None:
        _xml_to_md_grpc_client = XmlToMdGRPCClient()
    return _xml_to_md_grpc_client
