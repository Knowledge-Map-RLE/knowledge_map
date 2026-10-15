"""Читает явный логический корпус и подтверждает его сохранённые хеши."""
from hashlib import sha256
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.whole_map_input_audit import audit_source_coverage
from infrastructure.development_prediction_store import FilePredictionStore


class FileCategoricalCandidateInputs:
    def __init__(self, run_dir):
        self.run_dir = Path(run_dir).resolve()

    def load(self):
        base_id = self.run_dir.name
        base = FilePredictionStore(self.run_dir.parent).read_seal(base_id)
        require(base is not None and base["canonical_blocks"] == 943, "Expected sealed complete corpus run")
        manifest_path = self.run_dir / "source-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        sources = manifest["sources"]
        refs = base["binding"]["sources"]
        map_hashes = base["binding"]["map_hashes"]
        require(len(sources) == len(refs) == len(map_hashes) == 11, "Whole-map source manifest differs")
        require(not any(source["pmcid"].lower() == "pmc10000452" for source in sources),
                "Target article must not enter logical candidate discovery")
        maps = []
        for source, reference, expected_map_hash in zip(sources, refs, map_hashes):
            path = Path(source["path"])
            raw = path.read_bytes()
            require(sha256(raw).hexdigest() == source["file_sha256"], "Source map bytes differ")
            m = json.loads(raw)
            require(fingerprint(m["graph"]) == source["graph_sha256"], "Source graph hash differs")
            require(m["article_id"] == source["reference"]["article_id"] == reference["article_id"]
                    and m["run_id"] == source["reference"]["run_id"] == reference["run_id"]
                    and m["pipeline_id"] == reference["pipeline_id"] == "text_reified"
                    and m["source"]["sha256"] == source["source_sha256"],
                    "Map, source manifest and forecast reference disagree")
            # Шесть карт исходного запуска включали проверенное покрытие, добавленное в памяти.
            # Воспроизводим это точное дополнение из сохранённого артефакта, не ослабляя хеш-проверку.
            if "coverage_artifact" in source:
                coverage_path = self.run_dir / "source-coverage" / (reference["article_id"] + ".json")
                coverage_raw = coverage_path.read_bytes()
                coverage_sha256 = sha256(coverage_raw).hexdigest()
                require(coverage_sha256 == source["coverage_artifact"]["sha256"],
                        "Bound coverage artifact bytes differ")
                m["forecast_input_coverage"] = audit_source_coverage(
                    m, json.loads(coverage_raw), coverage_sha256
                )
            require(fingerprint(m) == expected_map_hash, "Reconstructed bound input map differs")
            maps.append(m)
        require(len({m["article_id"] for m in maps}) == 11, "Duplicate source article")
        return {
            "base_run_id": base_id,
            "base_prediction_sha256": fingerprint(base),
            "manifest_sha256": sha256(manifest_bytes).hexdigest(),
            "manifest": manifest,
            "maps": maps,
        }
