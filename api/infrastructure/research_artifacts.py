"""Неизменяемые контрольные артефакты; публикация одним атомарным связыванием файла."""
import os
import re
from pathlib import Path
from uuid import uuid4

from domain.article_maps import require
from infrastructure.development_prediction_store import FilePredictionStore


class FileResearchArtifacts:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def audit(self, artifact_id, artifact):
        require(bool(re.fullmatch(r"[a-f0-9]{64}", artifact_id)), "Invalid scientific artifact id")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (artifact_id + ".json")
        data = FilePredictionStore.encode(artifact)
        if path.exists():
            require(path.read_bytes() == data, "Immutable scientific artifact differs")
            return
        staging = self.root / (".staging-" + str(uuid4()))
        try:
            with staging.open("xb") as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            try:
                os.link(staging, path)
            except FileExistsError:
                require(path.read_bytes() == data, "Concurrent scientific artifact differs")
        finally:
            staging.unlink(missing_ok=True)
