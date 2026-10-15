"""Адресное чтение подписанного прогноза и нового контрольного источника."""
import json
from pathlib import Path

from domain.article_maps import digest, fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore


class FileControlInputs:
    def __init__(self, manifest):
        self.path = Path(manifest).resolve()
        self.reads = []

    def read_inputs(self):
        self.reads.append(str(self.path))
        manifest = json.loads(self.path.read_text(encoding="utf-8"))
        root = Path(manifest["forecast_store"]).resolve()
        frozen = FilePredictionStore(root).read_seal(manifest["forecast_run_id"])
        require(frozen is not None and fingerprint(frozen) == manifest["forecast_sha256"], "Frozen forecast changed")
        self.reads.extend(str(root / manifest["forecast_run_id"] / name) for name in ("predictions.json", "seal.json"))
        path = Path(manifest["control"]["path"]).resolve()
        self.reads.append(str(path))
        control = json.loads(path.read_text(encoding="utf-8"))
        require(fingerprint(control) == manifest["control"]["sha256"], "Control annotation changed")
        for document in control["documents"]:
            path = Path(document["path"]).resolve()
            self.reads.append(str(path))
            require(digest(path.read_text(encoding="utf-8")) == document["sha256"], "Control source text changed")
        for document in control["binary_documents"]:
            from hashlib import sha256
            path = Path(document["path"]).resolve()
            self.reads.append(str(path))
            require(sha256(path.read_bytes()).hexdigest() == document["sha256"], "Control binary source changed")
        sources = {d["id"]: d for d in control["documents"]}
        require(len(sources) == len(control["documents"]), "Duplicate control document")
        identifiers = {a["id"] for a in control["anchors"]}
        require(len(identifiers) == len(control["anchors"]), "Duplicate control anchor")
        for anchor in control["anchors"]:
            require(anchor["document_id"] in sources, "Unknown control source anchor")
            text = Path(sources[anchor["document_id"]]["path"]).read_text(encoding="utf-8")
            require(type(anchor["start"]) is int and type(anchor["end"]) is int and
                    0 <= anchor["start"] < anchor["end"] <= len(text) and
                    digest(text[anchor["start"]:anchor["end"]]) == anchor["sha256"], "Unicode source anchor changed")
        for record in control["reporting"]:
            require(record["anchors"] and set(record["anchors"]) <= identifiers, "Unknown reporting source anchor")
        for claim in control["observations"]:
            require(set(claim["provenance"]) <= identifiers, "Unknown observation source anchor")
        return {"forecast": frozen, "control": control}
