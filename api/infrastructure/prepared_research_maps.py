"""Изолированный корпус опыта: только перечисленные снимки, без доступа к общей Neo4j."""
from domain.article_maps import require, ArticleMapAccessDenied, fingerprint
from domain.research_semantics import project_map
from domain.research_context_revision import apply_context_revision
from hashlib import sha256
from pathlib import Path


class PreparedResearchMaps:
    def __init__(self, bundles, owner, purpose):
        require(purpose in {"training", "evaluation"} and bool(bundles), "Explicit nonempty research corpus required")
        self.owner, self.data, self.reads = owner, {}, []
        for bundle in bundles:
            require(set(bundle) == {"map", "registry", "annotation", "origin"}, "Research bundle fields differ")
            require(bundle["origin"]["purpose"] == purpose, "Target bundle cannot enter training corpus")
            result = bundle["map"]
            revision = bundle["origin"].get("context_revision")
            if revision:
                require(set(revision) == {"audit", "original_annotation"}, "Context revision origin fields differ")
                baseline = {**bundle, "annotation": revision["original_annotation"]}
                require(apply_context_revision(baseline, revision["audit"]) == bundle["annotation"], "Prepared context revision differs from verified audit")
                for table in revision["audit"]["tables"]:
                    require(sha256(Path(table["local_path"]).read_bytes()).hexdigest() == table["sha256"], "Context table bytes changed")
            require(result["article_id"] not in self.data, "Duplicate prepared research source")
            project_map(result, bundle["registry"], bundle["annotation"])
            self.data[result["article_id"]] = result
        self.bundle_sha256 = fingerprint(bundles)

    def authorize(self, article, user):
        if user != self.owner: raise ArticleMapAccessDenied("Prepared research belongs to another owner")
        require(article in self.data, "Unlisted prepared research article")

    def get(self, article, pipeline, user, run):
        self.authorize(article, user)
        result = self.data[article]
        require(pipeline == "text_reified" and run == result["run_id"], "Prepared research run differs")
        self.reads.append({"article_id": article, "run_id": run})
        return result
