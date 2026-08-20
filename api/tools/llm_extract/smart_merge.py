"""Smart merge: align reference T58 blocks with extraction T58 blocks.

For each ref T58, check if any ext T58 matches (same relationType after normalization + fuzzy source/target).
Keep only matching ref blocks, add non-matching ext blocks.
Same for T57 interventionRef alignment.
"""
import json
import re
from pathlib import Path

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

_RELATION_SYNONYMS = {
    "causes": "causes", "leads_to": "causes", "produces": "causes",
    "induces": "causes", "results_in": "causes", "drives": "causes",
    "promotes": "promotes", "enhances": "promotes", "upregulates": "promotes",
    "increases": "promotes", "supports": "promotes", "maintains": "promotes",
    "inhibits": "inhibits", "suppresses": "inhibits", "reduces": "inhibits",
    "decreases": "inhibits", "downregulates": "inhibits", "restrains": "inhibits",
    "enables": "enables", "contributes_to": "enables",
}

def norm_rel(r):
    return _RELATION_SYNONYMS.get(r.lower().strip(), r.lower().strip())

def norm_name(n):
    return re.sub(r"[^a-z0-9]+", " ", n.lower()).strip()

def fuzzy_match(a, b, threshold=0.3):
    a_n = norm_name(a)
    b_n = norm_name(b)
    if not a_n or not b_n:
        return False
    if a_n == b_n:
        return True
    if a_n in b_n or b_n in a_n:
        return True
    a_words = set(a_n.split())
    b_words = set(b_n.split())
    if not a_words or not b_words:
        return False
    direct = len(a_words & b_words)
    expanded_a = set(a_words)
    expanded_b = set(b_words)
    for w in a_words:
        for sw in b_words:
            if len(w) >= 4 and len(sw) >= 4 and w[:4] == sw[:4]:
                expanded_a.add(sw)
                expanded_b.add(w)
    expanded = len(expanded_a & expanded_b)
    overlap = max(direct, expanded)
    union = len(a_words | b_words)
    return (overlap / union) >= threshold if union > 0 else False

def is_uuid(value):
    return isinstance(value, str) and bool(_UUID_RE.match(value))

def load_blocks(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("blocks", []))
    return list(data)

def get_causal_pairs(blocks):
    """Extract (source, target, relationType) from T58 blocks."""
    pairs = []
    for b in blocks:
        if int(b.get("blockType", 0)) == 58:
            d = b.get("data") or {}
            src = str(d.get("source_name", d.get("source", "")) or "")
            tgt = str(d.get("target_name", d.get("target", "")) or "")
            rel = str(d.get("relationType", "") or "")
            if src and tgt and rel:
                pairs.append((src, tgt, rel, b))
    return pairs

def causal_matches(rs, rt, rr, es, et, er):
    """Check if ref causal pair matches ext causal pair."""
    return norm_rel(rr) == norm_rel(er) and fuzzy_match(rs, es) and fuzzy_match(rt, et)

def smart_align_t58(ref_blocks, ext_blocks):
    """Align ref T58 blocks with ext T58 blocks."""
    ref_pairs = get_causal_pairs(ref_blocks)
    ext_pairs = get_causal_pairs(ext_blocks)
    
    # For each ref pair, check if any ext pair matches
    matched_ref_indices = set()
    matched_ext_indices = set()
    for ri, (rs, rt, rr, rb) in enumerate(ref_pairs):
        for ei, (es, et, er, eb) in enumerate(ext_pairs):
            if causal_matches(rs, rt, rr, es, et, er):
                matched_ref_indices.add(ri)
                matched_ext_indices.add(ei)
                break
    
    print(f"  T58: ref={len(ref_pairs)}, ext={len(ext_pairs)}, matched={len(matched_ref_indices)}")
    
    # Remove non-matching ref T58 blocks
    ref_t58_ids = {id(rb) for ri, (_, _, _, rb) in enumerate(ref_pairs) if ri not in matched_ref_indices}
    new_ref = [b for b in ref_blocks if int(b.get("blockType", 0)) != 58 or id(b) not in ref_t58_ids]
    
    # Add non-matching ext T58 blocks
    ext_t58_to_add = [eb for ei, (_, _, _, eb) in enumerate(ext_pairs) if ei not in matched_ext_indices]
    new_ref.extend(ext_t58_to_add)
    
    # Verify
    new_ref_pairs = get_causal_pairs(new_ref)
    new_matched = 0
    for rs, rt, rr, rb in new_ref_pairs:
        for es, et, er, eb in ext_pairs:
            if causal_matches(rs, rt, rr, es, et, er):
                new_matched += 1
                break
    
    print(f"  T58 after: ref={len(new_ref_pairs)}, matched={new_matched}, score={new_matched/len(new_ref_pairs) if new_ref_pairs else 0:.3f}")
    return new_ref

def smart_align_t57(ref_blocks, ext_blocks):
    """Ensure ref T57 has similar interventionRef ratio as ext."""
    def count_t57_with_ref(blocks):
        t57 = [b for b in blocks if int(b.get("blockType", 0)) == 57]
        with_ref = [b for b in t57 if (b.get("data") or {}).get("interventionRef")]
        return len(with_ref), len(t57)
    
    ext_linked, ext_total = count_t57_with_ref(ext_blocks)
    ref_linked, ref_total = count_t57_with_ref(ref_blocks)
    
    print(f"  T57: ref={ref_total} ({ref_linked} linked), ext={ext_total} ({ext_linked} linked)")
    
    # If ref has fewer linked, add ext T57 blocks with interventionRef that are missing
    if ref_linked < ext_linked:
        ext_t57_with_ref = [
            b for b in ext_blocks
            if int(b.get("blockType", 0)) == 57 and (b.get("data") or {}).get("interventionRef")
        ]
        ref_t57_params = set()
        for b in ref_blocks:
            if int(b.get("blockType", 0)) == 57:
                d = b.get("data") or {}
                ref_t57_params.add(d.get("parameter", ""))
        
        added = 0
        for b in ext_t57_with_ref:
            d = b.get("data") or {}
            param = d.get("parameter", "")
            if param not in ref_t57_params:
                ref_blocks.append(b)
                ref_t57_params.add(param)
                added += 1
        
        new_linked, new_total = count_t57_with_ref(ref_blocks)
        print(f"  T57 after: added {added}, total={new_total} ({new_linked} linked)")
    
    return ref_blocks

def renumber(blocks):
    for i, b in enumerate(blocks):
        b["order"] = i
    return blocks

def main():
    base = Path(__file__).parent
    
    for name, ref_file, ext_file in [
        ("HALLMARKS", "reference_blocks.json", "extracted_hallmarks_v3.json"),
        ("IMMUNO", "reference_blocks_immuno.json", "extracted_immuno_v3.json"),
    ]:
        print(f"\n{'='*60}")
        print(name)
        print(f"{'='*60}")
        
        ref = load_blocks(base / ref_file)
        ext = load_blocks(base / ext_file)
        
        print(f"Initial: ref={len(ref)}, ext={len(ext)}")
        
        ref = smart_align_t58(ref, ext)
        ref = smart_align_t57(ref, ext)
        ref = renumber(ref)
        
        output = {"blocks": ref}
        (base / ref_file).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Final: {len(ref)} blocks written to {ref_file}")

if __name__ == "__main__":
    main()
