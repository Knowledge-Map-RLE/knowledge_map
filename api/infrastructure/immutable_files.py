"""Атомарная запись неизменяемого артефакта, пригодная для повторного запуска после сбоя."""
import os
from pathlib import Path
from uuid import uuid4
from domain.article_maps import require


def write_immutable(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == data, "Immutable artifact differs: " + path.name)
        return
    temporary = path.parent / (".staging-" + str(uuid4()))
    try:
        with temporary.open("xb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try: os.link(temporary, path)
        except FileExistsError: require(path.read_bytes() == data, "Concurrent immutable artifact differs: " + path.name)
    finally: temporary.unlink(missing_ok=True)
