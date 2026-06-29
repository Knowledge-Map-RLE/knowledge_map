import time
import uuid
import os


def uuid7() -> uuid.UUID:
    timestamp_ms = int(time.time() * 1000)

    timestamp_part = timestamp_ms << 80
    ver_part = 0x7000_0000_0000_0000
    rand_part = int.from_bytes(os.urandom(10), "big")
    rand_part = (rand_part >> 2) | (0x02 << 62)
    value = timestamp_part | ver_part | rand_part

    return uuid.UUID(int=value)
