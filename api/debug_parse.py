"""Debug script to test JSON parsing from LLM response."""
import sys
import json

sys.path.insert(0, ".")

from services.llm_triplet_extraction_service import (
    LLMTripletExtractionService,
    _UNIFIED_BLOCK_TYPE_MAP,
)

gt = open("debug_response.txt", "r", encoding="utf-8").read()
print(f"Generated text: {len(gt)} chars")

# Step 1: extract JSON
data = LLMTripletExtractionService._extract_json(gt)
print(f"Step 1 - _extract_json: type={type(data)}")
if data is None:
    print("  data is None - extraction failed")
    sys.exit(1)
print(f"  keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}")

# Step 2: get blocks list
blocks = data.get("blocks") if isinstance(data, dict) else None
if blocks is None:
    blocks = data.get("data") if isinstance(data.get("data"), list) else None
print(f"Step 2 - blocks: type={type(blocks)} len={len(blocks) if blocks else 0}")

if blocks:
    first = blocks[0]
    print(f"  first block type: {type(first)}")
    if isinstance(first, dict):
        print(f"  first block keys: {list(first.keys())}")
        bt = first.get("blockType", "MISSING")
        print(f"  blockType raw: '{bt}' (type={type(bt).__name__})")
        if isinstance(bt, str):
            mapped = _UNIFIED_BLOCK_TYPE_MAP.get(bt, "NOT_FOUND")
            print(f"  blockType mapped: {mapped}")

# Step 3: parse_response
svc = LLMTripletExtractionService()
parsed = svc.parse_response(gt)
print(f"Step 3 - parse_response: {len(parsed)} blocks")
if parsed:
    for i, b in enumerate(parsed[:3]):
        print(f"  [{i}] blockType={b['blockType']} data_keys={list(b.get('data',{}).keys())[:5]}")

# Step 4: _parse_unified_json
raw = svc._parse_unified_json(gt)
print(f"Step 4 - _parse_unified_json: {len(raw)} blocks")
if raw:
    for i, b in enumerate(raw[:3]):
        print(f"  [{i}] blockType={b['blockType']} tag={b.get('tag','')} data_keys={list(b.get('data',{}).keys())[:5]}")
