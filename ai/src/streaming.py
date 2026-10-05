"""HTTP-ответ, закрывающий источник SSE при отключении клиента."""
import anyio
from starlette.responses import StreamingResponse
from starlette.types import Send


class ClosingStreamingResponse(StreamingResponse):
    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            # Разрыв во время send оставляет генератор приостановленным на yield.
            # Закрываем его в этой же задаче до завершения ASGI-обработчика.
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()
