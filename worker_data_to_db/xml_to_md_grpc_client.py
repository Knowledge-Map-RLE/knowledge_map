"""Синхронный gRPC клиент для xml_to_md сервиса.

Используется в воркере pmc_oa_bulk_to_db.py (синхронный многопоточный код).
"""
import logging
import os

import grpc

import xml_to_md_pb2
import xml_to_md_pb2_grpc

logger = logging.getLogger(__name__)

_client = None


class XmlToMdClient:
    """Синхронный gRPC клиент для xml_to_md сервиса.

    Thread-safe: gRPC stub не хранит состояния, один channel на процесс.
    """

    def __init__(self):
        host = os.getenv("XML_TO_MD_SERVICE_HOST", "127.0.0.1")
        port = os.getenv("XML_TO_MD_SERVICE_PORT", "50054")
        self.channel = grpc.insecure_channel(f"{host}:{port}")
        self.stub = xml_to_md_pb2_grpc.XmlToMarkdownServiceStub(self.channel)
        logger.info(f"[xml_to_md_client] Создан синхронный клиент: {host}:{port}")

    def convert_pmc_xml(self, xml_bytes: bytes, timeout: int = 60) -> str:
        """Конвертирует PMC XML в Markdown через gRPC.

        Args:
            xml_bytes: XML байты статьи (весь <article> элемент)
            timeout: таймаут запроса в секундах

        Returns:
            Markdown-строка или "" при ошибке/недоступности сервиса
        """
        try:
            request = xml_to_md_pb2.ConvertPmcXmlRequest(
                xml_bytes=xml_bytes,
                image_urls={},
                provider=xml_to_md_pb2.PMC,
            )
            response = self.stub.ConvertPmcXml(request, timeout=timeout)
            if response.success:
                return response.markdown_content
            else:
                logger.warning(f"[xml_to_md_client] Сервис вернул ошибку: {response.message}")
                return ""
        except grpc.RpcError as e:
            logger.warning(f"[xml_to_md_client] gRPC ошибка: {e.code()} — {e.details()}")
            return ""
        except Exception as e:
            logger.warning(f"[xml_to_md_client] Ошибка convert_pmc_xml: {e}")
            return ""


def get_xml_to_md_client() -> XmlToMdClient:
    """Lazy singleton для синхронного xml_to_md клиента."""
    global _client
    if _client is None:
        _client = XmlToMdClient()
    return _client
