"""Проверяет разбиения и их фрагменты без доступа к скрытым значениям."""
import json
from pathlib import Path

from domain.article_maps import digest, fingerprint, require


class FileCohortTransferInputs:
    def __init__(self, manifest):
        self.manifest = Path(manifest).resolve()
        self.reads = []

    def read_inputs(self):
        manifest=json.loads(self.manifest.read_text(encoding="utf-8"));self.reads.append(str(self.manifest))
        require(set(manifest)=={"contract_version","folds","source_bindings","metadata"},"Unknown manifest fields or leaked controls")
        require(manifest["contract_version"]==1,"Unsupported cohort-transfer contract")
        folds=[]
        bindings={b["reference"]["article_id"]:b["source_sha256"] for b in manifest["source_bindings"]}
        for entry in manifest["folds"]:
            path=(self.manifest.parent/entry["path"]).resolve()
            require(path.parent==self.manifest.parent and path.name.startswith("fold-"),"Fold path outside prepared inputs")
            fold=json.loads(path.read_text(encoding="utf-8"));self.reads.append(str(path))
            require(fingerprint(fold)==entry["sha256"] and fold["withheld_family"]==entry["withheld_family"],"Prepared fold changed")
            for proof in fold["evidence"].values():
                require(proof["article_id"] in bindings and proof["source_sha256"]==bindings[proof["article_id"]],"Evidence outside frozen corpus")
                require(proof["offset_encoding"]=="unicode_codepoints" and proof["end"]-proof["start"]==len(proof["text"]),"Invalid fold source offsets")
                require(digest(proof["text"])==proof["text_sha256"],"Evidence changed")
            for item in [*fold["training"],*fold["queries"]]:
                require(set(item["evidence_ids"])<=set(fold["evidence"]),"Unbound transfer evidence")
            folds.append(fold)
        require(len({f["withheld_family"] for f in folds})==len(folds),"Duplicate held-out group")
        return {"manifest":manifest,"folds":folds}
