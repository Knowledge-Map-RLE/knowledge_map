"""Сохраняет точные файлы реализации, объявленные в источниковой фиксации."""
import argparse
import json
from pathlib import Path
from hashlib import sha256
from domain.article_maps import fingerprint,require
from infrastructure.immutable_files import write_immutable


def main():
    p=argparse.ArgumentParser();p.add_argument("--run-folder",required=True);args=p.parse_args()
    folder=Path(args.run_folder).resolve();sealed=json.loads((folder/"predictions.json").read_text(encoding="utf-8"))
    proof=json.loads((folder/"seal.json").read_text(encoding="utf-8"))
    require(fingerprint(sealed)==proof["prediction_sha256"],"Seal changed")
    root=Path(__file__).resolve().parents[1]
    for name,expected in sealed["binding"]["corpus_metadata"]["implementation_sha256"].items():
        path=(root/name).resolve();require(path.is_relative_to(root),"Implementation path escaped API root")
        raw=path.read_bytes();require(sha256(raw).hexdigest()==expected,"Frozen implementation already changed: "+name)
        write_immutable(folder/"implementation"/name,raw)
    print(json.dumps({"files":len(sealed["binding"]["corpus_metadata"]["implementation_sha256"]),"run_id":sealed["run_id"]}))


if __name__=="__main__":main()
