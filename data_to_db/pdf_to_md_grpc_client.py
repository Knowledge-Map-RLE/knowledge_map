"""gRPC клиент для pdf_to_md сервиса (Docling конвертация PDF в Markdown)."""
import logging
import os
from typing import Optional

import grpc

logger = logging.getLogger(__name__)

PDF_TO_MD_HOST = os.getenv("PDF_TO_MD_HOST", "127.0.0.1")
PDF_TO_MD_PORT = os.getenv("PDF_TO_MD_PORT", "8001")

_client = None


class PDFToMdClient:
    """gRPC клиент для pdf_to_md сервиса."""

    def __init__(self, host: str = None, port: str = None):
        self.host = host or PDF_TO_MD_HOST
        self.port = port or PDF_TO_MD_PORT
        self.channel = None
        self.stub = None
        self._connect()

    def _connect(self):
        """Установить соединение с gRPC сервером."""
        try:
            import pdf_to_md_pb2
            import pdf_to_md_pb2_grpc
            
            self.channel = grpc.insecure_channel(f"{self.host}:{self.port}")
            self.stub = pdf_to_md_pb2_grpc.PDFToMarkdownServiceStub(self.channel)
            logger.info(f"[pdf_to_md_client] Создан gRPC клиент: {self.host}:{self.port}")
        except ImportError as e:
            logger.warning(f"[pdf_to_md_client] Proto файлы не найдены: {e}")
            self.stub = None

    def convert_pdf(self, pdf_bytes: bytes, doc_id: str = None) -> Optional[dict]:
        """Конвертирует PDF в Markdown через Docling.
        
        Args:
            pdf_bytes: Содержимое PDF файла
            doc_id: ID документа (опционально)
            
        Returns:
            dict с ключами: success, doc_id, markdown_content, message, 
                           docling_raw_s3_key, formatted_s3_key
        """
        if self.stub is None:
            logger.warning("[pdf_to_md_client] gRPC недоступен")
            return {"success": False, "error": "gRPC client not initialized"}

        try:
            import pdf_to_md_pb2
            
            request = pdf_to_md_pb2.ConvertPDFRequest(
                pdf_content=pdf_bytes,
                doc_id=doc_id or "",
            )
            
            response = self.stub.ConvertPDF(request)
            
            result = {
                "success": response.success,
                "doc_id": response.doc_id,
                "markdown_content": response.markdown_content,
                "message": response.message,
                "docling_raw_s3_key": response.docling_raw_s3_key if response.docling_raw_s3_key else None,
                "formatted_s3_key": response.formatted_s3_key if response.formatted_s3_key else None,
            }
            
            logger.info(f"[pdf_to_md_client] Конвертация завершена: {response.success}")
            return result
            
        except grpc.RpcError as e:
            logger.warning(f"[pdf_to_md_client] gRPC ошибка: {e.code()} — {e.details()}")
            return {"success": False, "error": f"gRPC error: {e.code()} - {e.details()}"}
        except ImportError as e:
            logger.warning(f"[pdf_to_md_client] Ошибка импорта: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"[pdf_to_md_client] Ошибка конвертации PDF: {e}")
            return {"success": False, "error": str(e)}

    def close(self):
        """Закрыть соединение."""
        if self.channel:
            self.channel.close()


def get_pdf_to_md_client() -> PDFToMdClient:
    """Lazy singleton для pdf_to_md клиента."""
    global _client
    if _client is None:
        _client = PDFToMdClient()
    return _client