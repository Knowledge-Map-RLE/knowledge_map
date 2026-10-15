"""Неизменяемая фиксация кандидатов; публикация каталога атомарным rename."""
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from domain.article_maps import fingerprint, require


class FilePredictionStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, run_id):
        require(bool(re.fullmatch(r"[a-f0-9]{64}", run_id)), "Invalid prediction identifier")
        return self.root / run_id

    @staticmethod
    def encode(value):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")

    def read_seal(self, run_id):
        folder = self.path(run_id)
        if not folder.exists():
            return None
        require((folder / "seal.json").exists(), "Incomplete prediction seal")
        result = json.loads((folder / "predictions.json").read_text(encoding="utf-8"))
        proof = json.loads((folder / "seal.json").read_text(encoding="utf-8"))
        require(proof["prediction_sha256"] == fingerprint(result) and result["run_id"] == run_id, "Prediction seal changed")
        return result

    def seal(self, run_id, artifact):
        destination = self.path(run_id)
        if destination.exists():
            require(fingerprint(self.read_seal(run_id)) == fingerprint(artifact), "Immutable prediction differs")
            return
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / (".staging-" + str(uuid4()))
        staging.mkdir()
        try:
            for name, value in (("predictions.json", artifact), ("seal.json", {"run_id": run_id, "prediction_sha256": fingerprint(artifact)})):
                with (staging / name).open("xb") as stream:
                    stream.write(self.encode(value)); stream.flush(); os.fsync(stream.fileno())
            try:
                staging.rename(destination)
            except FileExistsError:
                require(fingerprint(self.read_seal(run_id)) == fingerprint(artifact), "Concurrent prediction seal differs")
        finally:
            if staging.exists():
                for name in ("predictions.json", "seal.json"):
                    (staging / name).unlink(missing_ok=True)
                staging.rmdir()

    def save_evaluation(self, run_id, evaluation_id, result):
        require(self.read_seal(run_id) is not None, "Missing prediction seal")
        require(bool(re.fullmatch(r"[a-f0-9]{64}", evaluation_id)), "Invalid evaluation identifier")
        folder = self.path(run_id) / "evaluations"
        folder.mkdir(exist_ok=True)
        path = folder / (evaluation_id + ".json")
        data = self.encode(result)
        if path.exists():
            require(path.read_bytes() == data, "Immutable evaluation differs")
        else:
            # Временный файл остаётся внутри явно заданного каталога эксперимента.
            temp = folder / (".staging-" + str(uuid4()))
            try:
                with temp.open("xb") as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                os.link(temp, path)
            except FileExistsError:
                require(path.read_bytes() == data, "Concurrent evaluation differs")
            finally:
                temp.unlink(missing_ok=True)
