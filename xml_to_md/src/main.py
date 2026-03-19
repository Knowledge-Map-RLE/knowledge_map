#!/usr/bin/env python3
"""gRPC сервер для XML to Markdown конвертации."""
import asyncio
import logging
import os
import platform
import socket
import subprocess
import sys
from concurrent import futures
from pathlib import Path
from xml.etree import ElementTree as ET

import grpc

# Добавляем путь к proto файлам
sys.path.append(str(Path(__file__).parent))

# Импортируем сгенерированные proto файлы
try:
    import xml_to_md_pb2
    import xml_to_md_pb2_grpc
except ImportError:
    proto_path = Path(__file__).parent.parent / "proto"
    src_path = Path(__file__).parent

    subprocess.run([
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={proto_path}",
        f"--python_out={src_path}",
        f"--grpc_python_out={src_path}",
        str(proto_path / "xml_to_md.proto")
    ], check=True)

    import xml_to_md_pb2
    import xml_to_md_pb2_grpc

# Настройка логирования
os.makedirs('logs', exist_ok=True)

stream_handler = logging.StreamHandler()
if hasattr(stream_handler.stream, 'reconfigure'):
    stream_handler.stream.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/xml_to_md.log', encoding='utf-8'),
        stream_handler
    ]
)
logger = logging.getLogger(__name__)

from converters.pmc import PmcXmlConverter
from converters.pubmed import parse_pubmed_article

GRPC_PORT = int(os.getenv("XML_TO_MD_GRPC_PORT", "50054"))

_pmc_converter = PmcXmlConverter()


def is_port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('localhost', port))
            return result != 0
    except Exception:
        return False


def get_process_using_port(port: int):
    try:
        if platform.system() == "Windows":
            result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if f':{port}' in line and 'LISTENING' in line:
                        parts = line.split()
                        if len(parts) >= 5:
                            return int(parts[-1])
        else:
            result = subprocess.run(['lsof', '-ti', f':{port}'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
    except Exception as e:
        logger.warning(f"[grpc] Ошибка при поиске процесса на порту {port}: {e}")
    return None


def kill_process_on_port(port: int) -> bool:
    pid = get_process_using_port(port)
    if pid is None:
        return True
    try:
        if platform.system() == "Windows":
            subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True, timeout=10)
        else:
            subprocess.run(['kill', '-9', str(pid)], capture_output=True, timeout=10)
        import time
        time.sleep(2)
        return is_port_available(port)
    except Exception as e:
        logger.error(f"[grpc] Ошибка при завершении процесса PID {pid}: {e}")
        return False


def ensure_port_available(port: int) -> bool:
    if is_port_available(port):
        return True
    logger.warning(f"[grpc] Порт {port} занят, освобождаем...")
    return kill_process_on_port(port)


class XmlToMarkdownServicer(xml_to_md_pb2_grpc.XmlToMarkdownServiceServicer):
    """gRPC сервис для конвертации XML в Markdown."""

    async def ConvertPmcXml(self, request, context):
        """Конвертация PMC XML в Markdown."""
        try:
            logger.info(f"[grpc] ConvertPmcXml: {len(request.xml_bytes)} байт XML")
            image_urls = dict(request.image_urls) if request.image_urls else {}
            markdown = _pmc_converter.convert(request.xml_bytes, image_urls=image_urls)
            if markdown:
                logger.info(f"[grpc] ConvertPmcXml: успешно, {len(markdown)} символов Markdown")
                return xml_to_md_pb2.ConvertXmlResponse(
                    success=True,
                    markdown_content=markdown,
                    message="Конвертация завершена успешно",
                )
            else:
                logger.warning("[grpc] ConvertPmcXml: пустой результат")
                return xml_to_md_pb2.ConvertXmlResponse(
                    success=False,
                    markdown_content="",
                    message="Конвертация вернула пустой результат",
                )
        except Exception as e:
            logger.error(f"[grpc] ConvertPmcXml ошибка: {e}")
            return xml_to_md_pb2.ConvertXmlResponse(
                success=False,
                markdown_content="",
                message=f"Ошибка: {str(e)}",
            )

    async def ParsePubmedMetadata(self, request, context):
        """Парсинг PubMed efetch XML → список метаданных статей."""
        try:
            logger.info(f"[grpc] ParsePubmedMetadata: {len(request.xml_bytes)} байт XML")
            root = ET.fromstring(request.xml_bytes)
            articles = []
            for article_el in root.findall("PubmedArticle"):
                meta = parse_pubmed_article(article_el)
                if not meta.get("pmid"):
                    continue
                articles.append(xml_to_md_pb2.ArticleMetadata(
                    pmid=meta.get("pmid", ""),
                    title=meta.get("title", ""),
                    authors=meta.get("authors", []),
                    journal=meta.get("journal", ""),
                    pub_date=meta.get("pub_date", ""),
                    abstract=meta.get("abstract", ""),
                    doi=meta.get("doi") or "",
                ))
            logger.info(f"[grpc] ParsePubmedMetadata: распарсено {len(articles)} статей")
            return xml_to_md_pb2.ParseMetadataResponse(
                success=True,
                articles=articles,
                message=f"Распарсено {len(articles)} статей",
            )
        except ET.ParseError as e:
            logger.error(f"[grpc] ParsePubmedMetadata XML ошибка: {e}")
            return xml_to_md_pb2.ParseMetadataResponse(
                success=False,
                articles=[],
                message=f"Ошибка парсинга XML: {str(e)}",
            )
        except Exception as e:
            logger.error(f"[grpc] ParsePubmedMetadata ошибка: {e}")
            return xml_to_md_pb2.ParseMetadataResponse(
                success=False,
                articles=[],
                message=f"Ошибка: {str(e)}",
            )


async def serve():
    """Запуск gRPC сервера."""
    logger.info("[grpc] Инициализация xml_to_md gRPC сервера")

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=4))
    xml_to_md_pb2_grpc.add_XmlToMarkdownServiceServicer_to_server(
        XmlToMarkdownServicer(), server
    )

    listen_addr = f'0.0.0.0:{GRPC_PORT}'

    if not ensure_port_available(GRPC_PORT):
        raise RuntimeError(f"Не удалось освободить порт {GRPC_PORT}")

    server.add_insecure_port(listen_addr)
    logger.info(f"[grpc] Запуск сервера на {listen_addr}")

    await server.start()
    logger.info("[grpc] Сервер запущен и готов к приёму запросов")
    await server.wait_for_termination()


if __name__ == '__main__':
    asyncio.run(serve())
