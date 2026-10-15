"""Порт карт читает только явный перечень неизменяемых локальных снимков."""
import json
from pathlib import Path
from hashlib import sha256

from domain.article_maps import require, ArticleMapAccessDenied, fingerprint
from domain.development_prediction import validate_visible_dag
from domain.whole_map_input_audit import audit_source_coverage


class FileForecastMaps:
    def __init__(self, entries, owner="offline-authorized-corpus"):
        self.owner, self.entries, self.reads = owner, {}, []
        for entry in entries:
            key = (entry["reference"]["article_id"], entry["reference"]["pipeline_id"], entry["reference"]["run_id"])
            require(key not in self.entries, "Duplicate snapshot reference")
            self.entries[key] = entry

    def authorize(self, article, owner):
        if owner != self.owner or article not in {k[0] for k in self.entries}:
            raise ArticleMapAccessDenied("Snapshot corpus access denied")

    def get(self, article, pipeline, owner, run):
        self.authorize(article, owner)
        entry = self.entries.get((article, pipeline, run))
        if entry is None:
            return None
        path = Path(entry["path"]).resolve()
        raw = path.read_bytes()
        require(sha256(raw).hexdigest() == entry["file_sha256"], "Snapshot bytes changed")
        result = json.loads(raw)
        require(result["article_id"] == article and result["pipeline_id"] == pipeline and result["run_id"] == run,
                "Snapshot identity differs")
        require(result["graph"]["schema_version"] == 6, "Free forecast requires schema 6")
        require(fingerprint(result["graph"]) == entry["graph_sha256"], "Snapshot graph changed")
        source = result["source"]
        require(sha256(source["text"].encode("utf-8")).hexdigest() == source["sha256"] == entry["source_sha256"], "Source text changed")
        require(source["offset_encoding"] == "unicode_codepoints", "Source offsets must use Unicode code points")
        units = {u["id"]: u for u in source["units"]}
        require(len(units) == len(source["units"]), "Duplicate source unit")
        validate_visible_dag(result["graph"])
        for k in result["graph"]["knowledge"]:
            for s in k["semantic_frame"]["statements"]:
                require(bool(s["provenance"]["unit_ids"]), "Statement lacks source provenance")
                for uid in s["provenance"]["unit_ids"]:
                    require(uid in units, "Unknown provenance source unit")
                    u = units[uid]
                    require(0 <= u["start"] < u["end"] <= source["content_end"] <= len(source["text"]), "Provenance outside source content")
                    require(source["text"][u["start"]:u["end"]] == u["text"], "Provenance text differs")
        read = {"article_id": article, "run_id": run, "file_sha256": entry["file_sha256"]}
        if "coverage_artifact" in entry:
            artifact = entry["coverage_artifact"]
            coverage_raw = Path(artifact["path"]).resolve().read_bytes()
            require(sha256(coverage_raw).hexdigest() == artifact["sha256"], "Coverage artifact bytes changed")
            result["forecast_input_coverage"] = audit_source_coverage(result, json.loads(coverage_raw), artifact["sha256"])
            read["coverage_artifact"] = artifact
        self.reads.append(read)
        return result
