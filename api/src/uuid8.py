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
