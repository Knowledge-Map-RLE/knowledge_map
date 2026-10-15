"""Аудит имеет только источниковый порт; входа для целевой статьи нет."""
from application.ports.article_comparisons import ComparisonMaps
from domain.article_maps import fingerprint, require
from domain.free_semantic_audit import audit, VERSION


class AuditFreeSemantics:
    def __init__(self,maps:ComparisonMaps):self.maps=maps

    def execute(self,references,owner):
        require(len({r["article_id"] for r in references})==len(references),"Duplicate audit source")
        maps=[self.maps.get(r["article_id"],r["pipeline_id"],owner,r["run_id"]) for r in references]
        require(all(m is not None for m in maps),"Audit source missing")
        binding={"references":references,"maps_sha256":[fingerprint(m) for m in maps],"audit_version":VERSION}
        return {"audit_id":fingerprint(binding),"binding":binding,**audit(maps)}
