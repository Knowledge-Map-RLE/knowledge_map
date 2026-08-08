"""Временный смоук-пробинг двухстадийного извлечения на одном чанке."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.article_editor_service import strip_references  # noqa: E402
from services.llm_triplet_extraction_service import LLMTripletExtractionService  # noqa: E402
from tools.llm_extract.run import ARTICLE_DIR, EN_MD, TITLE_EN, TITLE_RU  # noqa: E402

CHUNK_IDX = int(sys.argv[1]) if len(sys.argv) > 1 else 2
LANG = sys.argv[2] if len(sys.argv) > 2 else "ru"


def main() -> None:
    md = EN_MD if LANG == "en" else ARTICLE_DIR / "Immunometabolic resistors of aging in long-lived golden spiny mice.ru.md"
    title = TITLE_EN if LANG == "en" else TITLE_RU
    text = strip_references(md.read_text(encoding="utf-8-sig"))
    svc = LLMTripletExtractionService()
    chunks = svc.split_into_chunks(text, max_chars=7000)
    print(f"Всего чанков: {len(chunks)}", file=sys.stderr)
    chunk = chunks[CHUNK_IDX]
    print(f"Чанк {CHUNK_IDX}: {len(chunk)} chars", file=sys.stderr)

    res_s = svc.call_llm_structure(chunk, title, lang=LANG)
    print(f"STAGE1 ok={res_s.get('success')} in={res_s.get('input_tokens')} out={res_s.get('output_tokens')}",
          file=sys.stderr)
    raw_s = res_s.get("generated_text", "")
    Path(__file__).resolve().parent.joinpath(f"probe_raw_structure_chunk{CHUNK_IDX}_{LANG}.txt").write_text(raw_s, encoding="utf-8")
    containers = svc._parse_structure_json(raw_s)
    print(f"containers={len(containers)}", file=sys.stderr)
    for c in containers:
        print(f"  {c['blockType']} tag={c['tag']} keys={sorted(c['data'].keys())}", file=sys.stderr)

    containers_json = json.dumps(svc._compact_containers(containers), ensure_ascii=False)
    res_a = svc.call_llm_atomize(chunk, title, containers_json, lang=LANG)
    print(f"STAGE2 ok={res_a.get('success')} in={res_a.get('input_tokens')} out={res_a.get('output_tokens')}",
          file=sys.stderr)
    raw_a = res_a.get("generated_text", "")
    Path(__file__).resolve().parent.joinpath(f"probe_raw_atomize_chunk{CHUNK_IDX}_{LANG}.txt").write_text(raw_a, encoding="utf-8")
    t4s, sequences = svc._parse_atomize_json(raw_a)
    print(f"t4={len(t4s)} sequence_keys={len(sequences)}", file=sys.stderr)

    blocks = svc.postprocess_two_stage([(containers, t4s, sequences)])
    hist = {}
    for b in blocks:
        hist[b["blockType"]] = hist.get(b["blockType"], 0) + 1
    containers_n = len(containers)
    print(f"\nИтог: {len(blocks)} блоков; hist={hist}", file=sys.stderr)
    print(f"ratio T4/nonT4 = {len(t4s)}/{containers_n} = {len(t4s)/containers_n:.2f}", file=sys.stderr)

    from tools.llm_extract.metrics import dead_sequence_refs, sequence_uuids
    alive = {b["instanceId"] for b in blocks}
    dead = dead_sequence_refs(blocks)
    with_seq = sum(1 for b in blocks if sequence_uuids(b))
    seq_total = sum(1 for b in blocks if int(b["blockType"]) in {7, 16, 22, 23, 37, 38, 39, 40, 44, 46, 47, 56, 57})
    print(f"dead_seq_refs={dead} seq_coverage={with_seq}/{seq_total}={with_seq/max(seq_total,1):.2f}", file=sys.stderr)
    print(f"t4 uuidref rate: ",
          sum(1 for b in blocks if b["blockType"] == 4 and
              any(str(b["data"].get(k, "")).startswith("0006") for k in ("subject", "predicate", "object"))) / max(len(t4s), 1),
          file=sys.stderr)

    out = Path(__file__).resolve().parent / f"probe_twostage_chunk{CHUNK_IDX}_{LANG}.json"
    out.write_text(json.dumps({
        "chunk_idx": CHUNK_IDX, "lang": LANG, "chunk_chars": len(chunk), "blocks": blocks,
        "summary": svc._summary(blocks),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
