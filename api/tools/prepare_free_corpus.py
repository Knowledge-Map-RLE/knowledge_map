"""Фиксирует только явно указанные локальные карты; не ищет статьи в общей базе."""
import argparse
import json
from datetime import date
from hashlib import sha256
from pathlib import Path
import xml.etree.ElementTree as ET

from domain.article_maps import fingerprint, require
from infrastructure.immutable_files import write_immutable


def entry(folder, cutoff):
    path = folder / "map.json"
    raw = path.read_bytes()
    m = json.loads(raw)
    root = ET.fromstring((folder / "article.xml").read_bytes())
    dates = []
    for d in root.findall(".//article-meta/pub-date"):
        if (d.get("pub-type") is not None or d.get("publication-format") is not None) and d.get("pub-type") not in {"epub", "ppub"} and d.get("publication-format") not in {"electronic", "print"}:
            continue
        year = d.findtext("year")
        if year:
            dates.append(date(int(year), int(d.findtext("month") or 1), int(d.findtext("day") or 1)))
    require(bool(dates), "Publication date required")
    available = min(dates)
    require(available <= date.fromisoformat(cutoff), "Source published after corpus cutoff")
    title = root.find(".//article-meta/title-group/article-title")
    require(title is not None, "XML article title required")
    return {"reference": {n: m[n] for n in ("article_id", "pipeline_id", "run_id")},
            "path": str(path.resolve()), "file_sha256": sha256(raw).hexdigest(),
            "graph_sha256": fingerprint(m["graph"]), "source_sha256": m["source"]["sha256"],
            "pmcid": folder.name, "published_on": str(available), "title": "".join(title.itertext()),
            "family": "publication-provenance-" + folder.name,
            "support_note": "Different publications are provenance groups, not proven independent primary evidence"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--maps-root", required=True)
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--cutoff", required=True)
    p.add_argument("--target", action="store_true")
    args = p.parse_args()
    require(len(set(args.ids)) == len(args.ids), "Duplicate PMCID")
    entries = [entry(Path(args.maps_root) / pmc, args.cutoff) for pmc in args.ids]
    if args.target:
        require(len(entries) == 1, "Exactly one evaluation target required")
        result = entries[0]
    else:
        result = {"sources": entries, "metadata": {"training_cutoff": args.cutoff,
            "question": None, "selection": "Five previously approved GOLD source runs; fixed before this forecast",
            "topic": "Aging and cognitive impairment", "expert_validated": False,
            "family_definition": "Publication provenance only; overlapping cited studies can remain",
            "known_target_debugging_case": True}}
    data = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    write_immutable(Path(args.output), data)
    print(json.dumps({"sources": len(entries), "output": args.output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
