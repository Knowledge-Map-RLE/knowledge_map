# Сервис хранения прогресса загрузки моделей Marker и по документам
import asyncio
import logging
from typing import Dict, Any, Optional
from .status_storage import status_storage

logger = logging.getLogger(__name__)


class MarkerProgressStore:
    """Потокобезопасное хранилище прогресса загрузки моделей Marker и задач по документам."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._models_ready_event = asyncio.Event()
        self._warmup_running: bool = False
        # Всегда начинаем с готового статуса моделей - они загрузятся при первом использовании в PDF to MD сервисе
        self._models: Dict[str, Any] = {
            "status": "ready",  # idle | loading | ready | failed
            "percent": 100,
            "phase": "ready",
            "last_message": "PDF to MD service will load models on first use",
        }
        self._by_doc: Dict[str, Dict[str, Any]] = {}
        # Устанавливаем событие готовности моделей
        self._models_ready_event.set()

    async def set_models_progress(self, percent: int, phase: str = "", last_message: str = "") -> None:
        """Обновляет прогресс загрузки моделей"""
        async with self._lock:
            self._models["status"] = "loading" if percent < 100 else "ready"
            self._models["percent"] = max(0, min(100, int(percent)))
            if phase:
                self._models["phase"] = phase
            if last_message:
                self._models["last_message"] = last_message
            logger.info(f"[marker] Models progress: {percent}% - {phase} - {last_message}")

    async def set_models_status(self, status: str, last_message: str = "") -> None:
        """Устанавливает статус моделей"""
        async with self._lock:
            self._models["status"] = status
            if last_message:
                self._models["last_message"] = last_message
            if status == "ready":
                self._models["percent"] = 100
                self._models_ready_event.set()
                self._warmup_running = False
                logger.info("[marker] Models ready!")
            elif status in ("failed", "idle"):
                self._models_ready_event.clear()
                self._warmup_running = False
                logger.warning(f"[marker] Models status: {status} - {last_message}")

    async def reset_models_status(self) -> None:
        """Сбрасывает статус моделей"""
        async with self._lock:
            self._models = {
                "status": "idle",
                "percent": 0,
                "phase": "",
                "last_message": "",
            }
            self._models_ready_event.clear()
            self._warmup_running = False
            logger.info("[marker] Models status reset")

    async def get_models_progress(self) -> Dict[str, Any]:
        """Возвращает текущий прогресс моделей"""
        async with self._lock:
            return dict(self._models)

    async def start_warmup_if_needed(self) -> bool:
        """Помечает, что прогрев запущен, если модели не готовы и прогрев ещё не идёт.
        Возвращает True, если нужно запускать прогрев; False — если уже идёт или модели готовы.
        """
        async with self._lock:
            if self._models.get("status") == "ready":
                self._models_ready_event.set()
                logger.info("[marker] Models already ready, skipping warmup")
                return False
            if self._warmup_running:
                logger.info("[marker] Warmup already running, skipping")
                return False
            self._warmup_running = True
            # ставим статус loading, если не стоял
            if self._models.get("status") in ("idle", "failed"):
                self._models["status"] = "loading"
                self._models["percent"] = max(0, int(self._models.get("percent") or 0))
            logger.info("[marker] Starting models warmup")
            return True

    async def wait_models_ready(self, timeout_sec: int) -> bool:
        """Дождаться готовности моделей. True — готовы, False — таймаут."""
        if self._models.get("status") == "ready":
            return True
        try:
            await asyncio.wait_for(self._models_ready_event.wait(), timeout=timeout_sec)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"[marker] Models not ready after {timeout_sec}s timeout")
            return False

    async def init_doc(self, doc_id: str) -> None:
        """Инициализирует документ для отслеживания прогресса"""
        async with self._lock:
            self._by_doc[doc_id] = {
                "status": "processing",  # processing | ready | failed
                "percent": 0,
                "phase": "",
                "last_message": "",
            }
            # Сохраняем в S3 для персистентности
            await status_storage.save_doc_status(doc_id, self._by_doc[doc_id])
            logger.info(f"[marker] Initialized doc tracking: {doc_id}")

    async def update_doc(self, doc_id: str, percent: Optional[int] = None, phase: str = "", last_message: str = "") -> None:
        """Обновляет прогресс обработки документа"""
        async with self._lock:
            state = self._by_doc.setdefault(doc_id, {
                "status": "processing",
                "percent": 0,
                "phase": "",
                "last_message": "",
            })
            if percent is not None:
                state["percent"] = max(0, min(100, int(percent)))
            if phase:
                state["phase"] = phase
            if last_message:
                state["last_message"] = last_message
            
            # Сохраняем в S3 для персистентности
            await status_storage.save_doc_status(doc_id, state)
            logger.info(f"[marker] Doc {doc_id} progress: {percent}% - {phase} - {last_message}")

    async def complete_doc(self, doc_id: str, success: bool) -> None:
        """Завершает обработку документа"""
        async with self._lock:
            state = self._by_doc.setdefault(doc_id, {
                "status": "processing",
                "percent": 0,
                "phase": "",
                "last_message": "",
            })
            state["status"] = "ready" if success else "failed"
            if success:
                state["percent"] = 100
                state["phase"] = "completed"
                state["last_message"] = "Processing completed successfully"
            else:
                state["phase"] = "failed"
                state["last_message"] = "Processing failed"
            
            # Сохраняем в S3 для персистентности
            await status_storage.save_doc_status(doc_id, state)
            logger.info(f"[marker] Doc {doc_id} completed: {'success' if success else 'failed'}")

    async def get_doc(self, doc_id: str) -> Dict[str, Any]:
        """Возвращает прогресс документа"""
        async with self._lock:
            # Сначала проверяем в памяти
            if doc_id in self._by_doc:
                return dict(self._by_doc[doc_id])
            
            # Если нет в памяти, загружаем из S3
            status = await status_storage.load_doc_status(doc_id)
            if status:
                self._by_doc[doc_id] = status
                return dict(status)
            
            return {}

    async def get_all(self) -> Dict[str, Any]:
        """Возвращает весь прогресс"""
        async with self._lock:
            # Возвращаем shallow-копии
            return {
                "models": dict(self._models),
                "by_doc": {k: dict(v) for k, v in self._by_doc.items()}
            }


# Глобальный синглтон
marker_progress_store = MarkerProgressStore()
