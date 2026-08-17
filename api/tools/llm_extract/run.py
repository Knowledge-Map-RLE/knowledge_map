"""CLI-прогон LLM-извлечения блоков из статьи + метрика vs эталон.

Примеры:
    python tools/llm_extract/run.py extract --out extracted_baseline.json
    python tools/llm_extract/run.py extract --out extracted.json --model qwen/qwen3-4b
    python tools/llm_extract/run.py extract --out extracted_en.json --lang en
    python tools/llm_extract/run.py metrics extracted.json
    python tools/llm_extract/run.py full --out extracted.json   # extract + metrics
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.article_editor_service import strip_references  # noqa: E402
from services.llm_triplet_extraction_service import (  # noqa: E402
    DEFAULT_MODEL,
    LLMTripletExtractionService,
)
from tools.llm_extract import metrics as m  # noqa: E402

ARTICLE_DIR = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "articles"
    / "Immunometabolic resistors of aging in long-lived golden spiny mice"
)
RU_MD = ARTICLE_DIR / "Immunometabolic resistors of aging in long-lived golden spiny mice.ru.md"
EN_MD = ARTICLE_DIR / "Immunometabolic resistors of aging in long-lived golden spiny mice.md"
TITLE_RU = "Иммуно-метаболические резисторы старения у долгоживущих золотых колючих мышей"
TITLE_EN = "Immunometabolic resistors of aging in long-lived golden spiny mice"
DEFAULT_OUT = Path(__file__).resolve().parent / "extracted_blocks.json"


def load_text(lang: str) -> str:
    md = RU_MD if lang == "ru" else EN_MD
    if not md.exists():
        sys.exit(f"Файл не найден: {md}")
    return strip_references(md.read_text(encoding="utf-8-sig"))


def cmd_extract(args: argparse.Namespace) -> None:
    text = load_text(args.lang)
    title = TITLE_EN if args.lang == "en" else TITLE_RU
    out_path = Path(args.out)

    previous_blocks = []
    previous_raw = []
    done_indices = set()
    if args.resume and out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            if prev.get("blocks"):
                previous_blocks = prev["blocks"]
            done_indices = {
                c.get("index")
                for c in (prev.get("chunks") or [])
                if isinstance(c, dict) and "error" not in c and c.get("index") is not None
            }
            print(
                f"Resume: {len(previous_blocks)} блоков, {len(done_indices)} готовых чанков",
                file=sys.stderr,
            )
        except Exception as exc:  # pragma: no cover
            print(f"resume parse failed: {exc}", file=sys.stderr)
        raw_path = out_path.with_suffix(".raw.json")
        if args.save_raw and raw_path.exists():
            try:
                previous_raw = json.loads(raw_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover
                print(f"raw parse failed: {exc}", file=sys.stderr)

    print(f"Текст: {len(text)} символов после strip_references", file=sys.stderr)
    service = LLMTripletExtractionService()

    def _checkpoint(_idx: int, _reports) -> None:
        pass

    result = service.extract(
        "000657ba-aec6-8a11-9c5c-986526539651",
        text,
        article_title=title,
        model_id=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        max_chunk_chars=args.max_chunk,
        chunk_offset=args.offset,
        max_chunks=args.max_chunks,
        progress_cb=_checkpoint,
        lang=args.lang,
    )
    if not result.get("success"):
        sys.exit(f"Ошибка извлечения: {result.get('message')}")
    blocks = previous_blocks + (result.get("blocks") or [])
    payload = {
        "doc_id": result["doc_id"],
        "model": args.model,
        "lang": args.lang,
        "summary": result["summary"],
        "chunks": result["chunks"],
        "blocks": blocks,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.save_raw:
        raw = previous_raw + (result.get("raw_chunks") or [])
        raw_path = out_path.with_suffix(".raw.json")
        raw_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"Raw-чанки сохранены: {raw_path} ({len(raw)})", file=sys.stderr)
    print(f"Блоки сохранены: {out_path} ({len(blocks)})", file=sys.stderr)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


def cmd_metrics(args: argparse.Namespace) -> None:
    extracted = m.load_blocks(Path(args.extracted))
    ref = m.load_reference()
    report = m.compute_metrics(ref, extracted)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.explain:
        print("\n--- Расшифровка дельт по типам ---", file=sys.stderr)
        for t, d in report["type_delta"].items():
            sign = "+" if d > 0 else ""
            print(f"  T{t}: {sign}{d} (извлечено-эталон)", file=sys.stderr)
    sys.exit(0 if report["passed"] else 1)


def cmd_full(args: argparse.Namespace) -> None:
    cmd_extract(args)
    print("\n=== МЕТРИКА ===\n", file=sys.stderr)
    extracted = m.load_blocks(Path(args.out))
    report = m.compute_metrics(m.load_reference(), extracted)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="llm_extract", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="Извлечь блоки и сохранить JSON")
    p_extract.add_argument("--out", default=str(DEFAULT_OUT))
    p_extract.add_argument("--model", default=DEFAULT_MODEL)
    p_extract.add_argument("--temperature", type=float, default=0.2)
    p_extract.add_argument("--max-tokens", type=int, default=20000)
    p_extract.add_argument("--timeout", type=int, default=900)
    p_extract.add_argument("--max-chunk", type=int, default=7000)
    p_extract.add_argument("--offset", type=int, default=0)
    p_extract.add_argument("--max-chunks", type=int, default=None)
    p_extract.add_argument("--lang", choices=["ru", "en"], default="ru")
    p_extract.add_argument("--resume", action="store_true")
    p_extract.add_argument("--save-raw", action="store_true")
    p_extract.set_defaults(func=cmd_extract)

    p_metrics = sub.add_parser("metrics", help="Посчитать метрику извлечённых блоков")
    p_metrics.add_argument("extracted")
    p_metrics.add_argument("--explain", action="store_true")
    p_metrics.set_defaults(func=cmd_metrics)

    p_full = sub.add_parser("full", help="Извлечь + посчитать метрику")
    p_full.add_argument("--out", default=str(DEFAULT_OUT))
    p_full.add_argument("--model", default=DEFAULT_MODEL)
    p_full.add_argument("--temperature", type=float, default=0.2)
    p_full.add_argument("--max-tokens", type=int, default=20000)
    p_full.add_argument("--timeout", type=int, default=900)
    p_full.add_argument("--max-chunk", type=int, default=7000)
    p_full.add_argument("--offset", type=int, default=0)
    p_full.add_argument("--max-chunks", type=int, default=None)
    p_full.add_argument("--lang", choices=["ru", "en"], default="ru")
    p_full.set_defaults(func=cmd_full)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
