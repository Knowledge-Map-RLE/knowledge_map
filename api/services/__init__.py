# Services package — TRANSITIONAL (удалить в Фазе 5)
# Перенаправляет импорты в infrastructure/ для обратной совместимости.
from infrastructure.config import settings
from infrastructure.s3.s3_storage import get_s3_client
from .layout_client import get_layout_client, LayoutOptions, LayoutConfig
from infrastructure.grpc_clients.auth_grpc_client import auth_client
from .data_download_service import get_data_download_service, DATA_SOURCES
from .citation_graph_service import get_citation_graph_service, CITATION_SOURCES_CONFIG

__all__ = [
    "settings",
    "get_s3_client",
    "get_layout_client",
    "LayoutOptions",
    "LayoutConfig",
    "auth_client",
    "get_data_download_service",
    "DATA_SOURCES",
    "get_citation_graph_service",
    "CITATION_SOURCES_CONFIG",
]
