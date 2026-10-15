"""Раздельные файловые адаптеры входов и контрольных заключений."""
import json
from pathlib import Path

from domain.article_maps import digest, require


class FileEmpiricalInputs:
    def __init__(self, path):
        self.path = Path(path)
        self.reads = []

    def read_inputs(self):
        dataset = json.loads(self.path.read_text(encoding="utf-8"))
        require(set(dataset) == {"contract_version", "metadata", "source_bindings", "evidence", "labels", "cases"}, "Unknown fields or hidden controls in inputs")
        bindings = {x["reference"]["article_id"]: x for x in dataset["source_bindings"]}
        require(len(bindings) == len(dataset["source_bindings"]), "Duplicate source binding")
        ids = set()
        for key, proof in dataset["evidence"].items():
            require(proof["article_id"] in bindings, "Evidence outside source corpus")
            require(digest(proof["text"]) == proof["text_sha256"], "Evidence bytes changed")
            require(proof["offset_encoding"] == "unicode_codepoints" and proof["end"] - proof["start"] == len(proof["text"]), "Invalid empirical offsets")
            require(proof["source_sha256"] == bindings[proof["article_id"]]["source_sha256"], "Evidence source hash differs")
            ids.add(key)
        for case in dataset["cases"]:
            for premise in (case["effect"], case["policy"]):
                require(set(premise["evidence_ids"]) <= ids, "Unknown empirical evidence")
        self.reads.append(str(self.path.resolve()))
        return dataset


class FileEmpiricalControls:
    def __init__(self, path):
        self.path = Path(path)
        self.reads = []

    def read_controls(self):
        result = json.loads(self.path.read_text(encoding="utf-8"))
        self.reads.append(str(self.path.resolve()))
        return result
