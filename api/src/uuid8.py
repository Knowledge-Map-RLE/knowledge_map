import os
import time
import uuid


def uuid8() -> uuid.UUID:
    """Generate UUIDv8 with 64-bit microsecond-precision timestamp."""
    ts_us = int(time.time() * 1_000_000)
    rand = os.urandom(7)

    b = bytearray(16)

    for i in range(8):
        b[i] = (ts_us >> (56 - i * 8)) & 0xFF

    b[6] = (b[6] & 0x0F) | 0x80          # version = 8

    b[8] = 0x80 | (rand[0] & 0x3F)       # variant = 10 + 6 random

    b[9:16] = rand[:]

    return uuid.UUID(bytes=bytes(b))


def uuid8_str() -> str:
    return str(uuid8())


def uuid8_timestamp(uuid_str: str) -> float:
    """Извлекает unix-время (секунды) из UUIDv8.

    Первые 8 байт UUIDv8 содержат 64-битный timestamp в микросекундах; старшая
    полубайтовая часть байта 6 заменена версией (0x8), поэтому точность
    ограничена ~4 мс — для отображения времени этого достаточно.
    """
    try:
        raw = uuid.UUID(uuid_str).bytes
    except (ValueError, TypeError, AttributeError):
        return 0.0
    ts_us = 0
    for i in range(8):
        ts_us = (ts_us << 8) | raw[i]
    return ts_us / 1_000_000.0
