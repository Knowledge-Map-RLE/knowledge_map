"""Test unified whole-article extraction with cost reporting.

Usage:
    cd api
    poetry run python test_whole_article.py
"""
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, ".")

from domain.rules.ai_pricing import calculate_usage_cost, UsageCost


def format_cost(cost: UsageCost, input_tok: int, output_tok: int) -> str:
    """Форматирует отчёт о токенах и стоимости."""
    lines = []
    lines.append(f"  Input tokens:   {input_tok:>8,}")
    lines.append(f"  Output tokens:  {output_tok:>8,}")
    lines.append(f"  Total tokens:   {input_tok + output_tok:>8,}")
    lines.append(f"  ---")
    lines.append(f"  Input cost:     {cost.input_cost:>10.4f} RUB")
    lines.append(f"  Output cost:    {cost.output_cost:>10.4f} RUB")
    lines.append(f"  Total cost:     {cost.total:>10.4f} RUB")
    return "\n".join(lines)


def main():
    # 1. Read article from .md file
    article_path = Path(
        r"D:\Knowledge_Map\data\articles"
        r"\Hallmarks of cancer and hallmarks of aging"
        r"\Hallmarks of cancer and hallmarks of aging.md"
    )
    if not article_path.exists():
        print(f"Article not found: {article_path}")
        sys.exit(1)

    full_text = article_path.read_text(encoding="utf-8")

    # Extract title from first heading
    title = "Hallmarks of cancer and hallmarks of aging"
    for line in full_text.splitlines():
        if line.startswith("# ") and "Hallmarks" in line:
            title = line.lstrip("# ").strip()
            break

    # Strip YAML front matter for the prompt
    body = full_text
    if full_text.startswith("---"):
        end = full_text.find("---", 3)
        if end != -1:
            body = full_text[end + 3:].lstrip("\n")

    doc_id = "test-hallmarks-cancer-aging-001"

    print("=" * 60)
    print("UNIFIED WHOLE-ARTICLE EXTRACTION TEST")
    print("=" * 60)
    print(f"Article:  {title}")
    print(f"docId:    {doc_id}")
    print(f"Chars:    {len(body):,}")
    print()

    # 2. Run extraction
    from services.llm_triplet_extraction_service import LLMTripletExtractionService

    service = LLMTripletExtractionService()

    print("Starting extraction...")
    t0 = time.time()
    result = service.extract(
        doc_id=doc_id,
        text=body,
        article_title=title,
        lang="en",
    )
    elapsed = time.time() - t0
    print(f"Elapsed:  {elapsed:.1f}s")
    print()

    # 3. Token & cost report
    summary = result.get("summary", {})
    tokens = summary.get("tokens", {})
    input_tok = tokens.get("input", 0)
    output_tok = tokens.get("output", 0)
    attempts = summary.get("attempts", 1)

    if input_tok or output_tok:
        cost = calculate_usage_cost(
            input_tokens=input_tok,
            output_tokens=output_tok,
        )
        print("--- TOKEN & COST REPORT ---")
        print(format_cost(cost, input_tok, output_tok))
        print(f"  Attempts:       {attempts}")
        print()
    else:
        print("  [No token data returned by LLM]")
        print()

    # 4. Extraction result
    print("--- EXTRACTION RESULT ---")
    print(f"Success: {result.get('success')}")
    if result.get("message"):
        print(f"Message: {result['message']}")

    blocks = result.get("blocks", [])
    print(f"Blocks extracted: {len(blocks)}")

    if blocks:
        type_counts = {}
        for b in blocks:
            t = b.get("blockType", 0)
            type_counts[t] = type_counts.get(t, 0) + 1
        print(f"\nBlock type distribution:")
        for t in sorted(type_counts.keys()):
            print(f"  T{t:>2d}: {type_counts[t]:>3d}")

        # Show first 5 blocks
        print(f"\nFirst 5 blocks:")
        for b in blocks[:5]:
            print(json.dumps(b, indent=2, ensure_ascii=False))

    # 5. Save output
    output_path = Path("tools/llm_extract/test_output.json")
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResult saved to {output_path}")

    # 6. Metrics
    if blocks:
        from tools.llm_extract.metrics import compute_metrics, load_reference

        ref = load_reference()
        report = compute_metrics(ref, blocks)
        print(f"\n--- METRICS ---")
        print(f"Composite: {report['composite']:.4f} (threshold: {report['threshold']})")
        print(f"Passed:    {report['passed']}")
        print(f"Counts:    ref={report['counts']['ref']}, ext={report['counts']['ext']}")
        for k, v in report["components"].items():
            w = report["weights"][k]
            print(f"  {k:<15s}: {v:.4f} (weight={w:.2f})")


if __name__ == "__main__":
    main()
