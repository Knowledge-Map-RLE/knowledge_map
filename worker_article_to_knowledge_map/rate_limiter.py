"""Async token bucket rate limiter for NCBI API calls."""
import asyncio
import time


class NCBIRateLimiter:
    """
    Token bucket rate limiter.
    Without API key: 3 requests/sec (NCBI policy).
    With API key: 10 requests/sec.
    """

    def __init__(self, has_api_key: bool = False):
        self._rate = 10.0 if has_api_key else 3.0
        self._tokens = self._rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0
