"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_download_ws
Responsibility: WebSocket endpoint для real-time обновлений прогресса загрузки.

Allowed imports: fastapi, services.data_download_service
Forbidden imports: application (напрямую)
"""
import asyncio
import logging
import json
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from services.data_download_service import get_data_download_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-download-ws"])

active_connections: Set[WebSocket] = set()


class ConnectionManager:
    """Менеджер WebSocket соединений для broadcast обновлений."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Отправляет сообщение всем подключенным клиентам."""
        if not self.active_connections:
            return
        message_json = json.dumps(message, ensure_ascii=False)
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to connection: {e}")
                disconnected.add(connection)
        for conn in disconnected:
            self.active_connections.discard(conn)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для получения обновлений прогресса загрузки."""
    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket connected to data download status"
        })
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")
                if action == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def notify_progress(
    source: str,
    downloaded: int,
    total: int,
    percent: float,
    status: str,
):
    """Уведомляет всех подключенных клиентов о прогрессе."""
    await manager.broadcast({
        "type": "progress",
        "source": source,
        "downloaded": downloaded,
        "total": total,
        "percent": percent,
        "status": status,
    })


async def notify_status_change(source: str, status: str, message: str = ""):
    """Уведомляет всех подключенных клиентов об изменении статуса."""
    await manager.broadcast({
        "type": "status_change",
        "source": source,
        "status": status,
        "message": message,
    })


async def notify_error(source: str, error: str):
    """Уведомляет всех подключенных клиентов об ошибке."""
    await manager.broadcast({
        "type": "error",
        "source": source,
        "error": error,
    })