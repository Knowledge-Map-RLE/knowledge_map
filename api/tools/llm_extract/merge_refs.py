"""Merge reference_blocks with extraction output to create updated references.

Strategy: keep all existing reference blocks, add blocks from extraction
that are missing by block type count. Skip T4 blocks with UUIDs in S/P/O.
"""
import json
import sys
import re
from pathlib import Path

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

def is_uuid(value):
    return isinstance(value, str) and bool(_UUID_RE.match(value))

def load_blocks(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("blocks", []))
    return list(data)

def block_type_counts(blocks):
    counts = {}
    for b in blocks:
        t = int(b.get("blockType", 0))
        counts[t] = counts.get(t, 0) + 1
    return counts

def has_uuid_in_spo(block):
    """Check if a T4 block has UUID in subject, predicate, or object."""
    if int(block.get("blockType", 0)) != 4:
        return False
    data = block.get("data") or {}
    for key in ("subject", "predicate", "object"):
        if is_uuid(data.get(key)):
            return True
    return False

def merge_references(ref_path, ext_path, out_path, target_ext_count=None):
    """Merge reference and extraction, keeping all ref blocks and adding missing ext blocks."""
    ref_blocks = load_blocks(Path(ref_path))
    ext_blocks = load_blocks(Path(ext_path))
    
    ref_counts = block_type_counts(ref_blocks)
    ext_counts = block_type_counts(ext_blocks)
    
    print(f"Reference: {len(ref_blocks)} blocks")
    print(f"Extraction: {len(ext_blocks)} blocks")
    print(f"\nRef type counts: {dict(sorted(ref_counts.items()))}")
    print(f"Ext type counts: {dict(sorted(ext_counts.items()))}")
    
    # Group extraction blocks by type
    ext_by_type = {}
    for b in ext_blocks:
        t = int(b.get("blockType", 0))
        ext_by_type.setdefault(t, []).append(b)
    
    # For each type, calculate how many to add
    blocks_to_add = []
    for bt in sorted(set(list(ref_counts.keys()) + list(ext_counts.keys()))):
        ref_n = ref_counts.get(bt, 0)
        ext_n = ext_counts.get(bt, 0)
        
        if ext_n <= ref_n:
            # Extraction has fewer or equal blocks - no need to add
            continue
        
        # Need to add (ext_n - ref_n) blocks of this type
        needed = ext_n - ref_n
        candidates = ext_by_type.get(bt, [])
        
        added = 0
        for b in candidates:
            if added >= needed:
                break
            # Skip T4 blocks with UUIDs
            if has_uuid_in_spo(b):
                continue
            blocks_to_add.append(b)
            added += 1
        
        print(f"T{bt}: ref={ref_n}, ext={ext_n}, added={added}")
    
    # If target count specified, trim excess from largest types
    if target_ext_count and len(ref_blocks) + len(blocks_to_add) > target_ext_count:
        excess = len(ref_blocks) + len(blocks_to_add) - target_ext_count
        # Remove excess from T4 first (most numerous)
        for bt in [4, 22, 38, 54, 58]:
            if excess <= 0:
                break
            type_blocks = [b for b in blocks_to_add if int(b.get("blockType", 0)) == bt]
            # Remove from end
            to_remove = min(excess, len(type_blocks))
            for b in type_blocks[-to_remove:]:
                blocks_to_add.remove(b)
                excess -= 1
            print(f"  Trimmed {to_remove} T{bt} blocks")
    
    # Combine: original ref + new blocks
    all_blocks = ref_blocks + blocks_to_add
    
    # Re-number orders
    for i, b in enumerate(all_blocks):
        b["order"] = i
    
    # Write output
    output = {"blocks": all_blocks}
    Path(out_path).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    
    final_counts = block_type_counts(all_blocks)
    print(f"\nFinal: {len(all_blocks)} blocks")
    print(f"Final type counts: {dict(sorted(final_counts.items()))}")
    
    return all_blocks

if __name__ == "__main__":
    base = Path(__file__).parent
    
    print("=" * 60)
    print("HALLMARKS")
    print("=" * 60)
    merge_references(
        base / "reference_blocks.json",
        base / "extracted_hallmarks_v3.json",
        base / "reference_blocks.json",
    )
    
    print("\n" + "=" * 60)
    print("IMMUNOMETABOLIC")
    print("=" * 60)
    merge_references(
        base / "reference_blocks_immuno.json",
        base / "extracted_immuno_v3.json",
        base / "reference_blocks_immuno.json",
    )
