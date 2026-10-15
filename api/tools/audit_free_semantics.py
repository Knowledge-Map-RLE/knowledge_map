"""Запускает локальный аудит только перечисленных пяти источников, без AI и сети."""
import argparse
import json
from pathlib import Path
from application.audit_free_semantics import AuditFreeSemantics
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


def main():
    p=argparse.ArgumentParser();p.add_argument("--corpus",required=True);p.add_argument("--output",required=True)
    args=p.parse_args();disable_network()
    config=json.loads(Path(args.corpus).read_text(encoding="utf-8"));maps=FileForecastMaps(config["sources"])
    result=AuditFreeSemantics(maps).execute([e["reference"] for e in config["sources"]],maps.owner)
    result["reads"]=maps.reads
    write_immutable(Path(args.output),json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False).encode())
    print(json.dumps({k:result[k] for k in ("audit_id","pair_categories","attribute_inventory")},ensure_ascii=False))


if __name__=="__main__":main()
