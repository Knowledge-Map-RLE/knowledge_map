"""CLI-прогон LLM-извлечения блоков из статьи + метрика vs эталон.

Примеры:
    python tools/llm_extract/run.py extract --out extracted_baseline.json
    python tools/llm_extract/run.py extract --out extracted.json --model qwen/qwen3-4b
    python tools/llm_extract/run.py extract --out extracted_en.json --lang en
    python tools/llm_extract/run.py metrics extracted.json
    python tools/llm_extract/run.py full --out extracted.json   # extract + metrics

    # С явным указанием статьи:
    python tools/llm_extract/run.py full --out hallmarks.json --lang en \\
        --article-dir "D:\\...\\Hallmarks of cancer and hallmarks of aging" \\
        --article-title "Hallmarks of cancer and hallmarks of aging"
"""

from __future__ import annotations

import argparse
import hashlib
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

DEFAULT_OUT = Path(__file__).resolve().parent / "extracted_blocks.json"
ARTICLES_DIR = Path(__file__).resolve().parents[3] / "data" / "articles"


def _doc_id_from_dir(article_dir: Path) -> str:
    return hashlib.md5(article_dir.name.encode()).hexdigest()


def load_text(article_dir: Path | None = None) -> str:
    if article_dir:
        md_files = sorted(article_dir.glob("*.md"))
        if not md_files:
            sys.exit(f"Нет .md файлов в {article_dir}")
        md = md_files[0]
    else:
        sys.exit("Не указана --article-dir и нет дефолтной статьи")
    if not md.exists():
        sys.exit(f"Файл не найден: {md}")
    return strip_references(md.read_text(encoding="utf-8-sig"))


def cmd_extract(args: argparse.Namespace) -> None:
    article_dir = Path(args.article_dir) if args.article_dir else None
    text = load_text(article_dir)
    title = args.article_title or (article_dir.name if article_dir else "")
    doc_id = _doc_id_from_dir(article_dir) if article_dir else "unknown"
    out_path = Path(args.out)

    previous_blocks = []
    previous_raw = []
    done_indices = set()
    if getattr(args, "resume", False) and out_path.exists():
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
        except Exception as exc:
            print(f"resume parse failed: {exc}", file=sys.stderr)
        raw_path = out_path.with_suffix(".raw.json")
        if getattr(args, "save_raw", False) and raw_path.exists():
            try:
                previous_raw = json.loads(raw_path.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"raw parse failed: {exc}", file=sys.stderr)

    print(f"Статья: {title}", file=sys.stderr)
    print(f"Текст: {len(text)} символов после strip_references", file=sys.stderr)
    print(f"Модель: {args.model}", file=sys.stderr)
    service = LLMTripletExtractionService()

    def _checkpoint(_idx: int, _reports) -> None:
        pass

    result = service.extract(
        doc_id,
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
    )
    if not result.get("success"):
        sys.exit(f"Ошибка извлечения: {result.get('message')}")
    blocks = previous_blocks + (result.get("blocks") or [])
    payload = {
        "doc_id": result["doc_id"],
        "model": args.model,
        "article_title": title,
        "summary": result["summary"],
        "chunks": result["chunks"],
        "blocks": blocks,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    if getattr(args, "save_raw", False):
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
    ref = m.load_reference(Path(args.ref) if args.ref else None)
    original_text = Path(args.text).read_text(encoding="utf-8-sig") if args.text else None
    report = m.compute_metrics(ref, extracted, original_text)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.explain:
        print("\n--- Расшифровка дельт по типам ---", file=sys.stderr)
        for t, d in report["type_delta"].items():
            sign = "+" if d > 0 else ""
            print(f"  T{t}: {sign}{d} (извлечено-эталон)", file=sys.stderr)
    sys.exit(0 if report["passed"] else 1)


def cmd_multi_metrics(args: argparse.Namespace) -> None:
    pairs = []
    text_files = args.text or []
    for i, item in enumerate(args.articles):
        parts = item.split("::")
        if len(parts) != 3:
            sys.exit(f"Неверный формат: {item} (ожидается extracted.json::reference.json::label)")
        ext_path, ref_path, label = parts
        ext = m.load_blocks(Path(ext_path))
        ref = m.load_blocks(Path(ref_path))
        text_path = text_files[i] if i < len(text_files) else None
        original_text = Path(text_path).read_text(encoding="utf-8-sig") if text_path else None
        report = m.compute_metrics(ref, ext, original_text)
        pairs.append({"label": label, "report": report, "ext_count": len(ext), "ref_count": len(ref)})
        print(f"\n=== {label} ({len(ext)} ext / {len(ref)} ref) ===", file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False, indent=2))

    total_ext = sum(p["ext_count"] for p in pairs)
    total_ref = sum(p["ref_count"] for p in pairs)
    weighted_composite = 0.0
    for p in pairs:
        weight = p["ext_count"] / total_ext if total_ext > 0 else 1.0 / len(pairs)
        weighted_composite += p["report"]["composite"] * weight

    summary = {
        "articles": len(pairs),
        "weighted_composite": round(weighted_composite, 4),
        "passed": weighted_composite >= m.PASS_THRESHOLD,
        "threshold": m.PASS_THRESHOLD,
        "total_ext_blocks": total_ext,
        "total_ref_blocks": total_ref,
        "per_article": [
            {"label": p["label"], "composite": p["report"]["composite"], "ext": p["ext_count"], "ref": p["ref_count"]}
            for p in pairs
        ],
    }
    print("\n=== КОМБИНИРОВАННАЯ МЕТРИКА ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.exit(0 if summary["passed"] else 1)


def cmd_full(args: argparse.Namespace) -> None:
    cmd_extract(args)
    print("\n=== МЕТРИКА ===\n", file=sys.stderr)
    extracted = m.load_blocks(Path(args.out))
    ref = m.load_reference(Path(args.ref) if args.ref else None)
    original_text = load_text(Path(args.article_dir) if args.article_dir else None)
    report = m.compute_metrics(ref, extracted, original_text)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


def _add_article_args(parser) -> None:
    parser.add_argument("--article-dir", required=True, help="Путь к папке со статьёй (.md)")
    parser.add_argument("--article-title", default=None, help="Заголовок статьи")


def main() -> None:
    parser = argparse.ArgumentParser(prog="llm_extract", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_extract = sub.add_parser("extract", help="Извлечь блоки и сохранить JSON")
    p_extract.add_argument("--out", default=str(DEFAULT_OUT))
    p_extract.add_argument("--model", default=DEFAULT_MODEL)
    p_extract.add_argument("--temperature", type=float, default=0.1)
    p_extract.add_argument("--max-tokens", type=int, default=80000)
    p_extract.add_argument("--timeout", type=int, default=900)
    p_extract.add_argument("--max-chunk", type=int, default=7000)
    p_extract.add_argument("--offset", type=int, default=0)
    p_extract.add_argument("--max-chunks", type=int, default=None)
    p_extract.add_argument("--resume", action="store_true")
    p_extract.add_argument("--save-raw", action="store_true")
    _add_article_args(p_extract)
    p_extract.set_defaults(func=cmd_extract)

    p_metrics = sub.add_parser("metrics", help="Посчитать метрику извлечённых блоков")
    p_metrics.add_argument("extracted")
    p_metrics.add_argument("--ref", type=str, default=None, help="Путь к reference_blocks.json")
    p_metrics.add_argument("--text", type=str, default=None, help="Путь к .md файлу оригинала")
    p_metrics.add_argument("--explain", action="store_true")
    p_metrics.set_defaults(func=cmd_metrics)

    p_multi = sub.add_parser("multi-metrics", help="Метрика на нескольких статьях")
    p_multi.add_argument(
        "--articles",
        nargs="+",
        required=True,
        help="extracted.json::reference.json::label для каждой статьи",
    )
    p_multi.add_argument("--text", nargs="+", default=None, help="Пути к .md файлам оригиналов (в том же порядке)")
    p_multi.set_defaults(func=cmd_multi_metrics)

    p_full = sub.add_parser("full", help="Извлечь + посчитать метрику")
    p_full.add_argument("--out", default=str(DEFAULT_OUT))
    p_full.add_argument("--model", default=DEFAULT_MODEL)
    p_full.add_argument("--temperature", type=float, default=0.1)
    p_full.add_argument("--max-tokens", type=int, default=80000)
    p_full.add_argument("--timeout", type=int, default=900)
    p_full.add_argument("--max-chunk", type=int, default=7000)
    p_full.add_argument("--offset", type=int, default=0)
    p_full.add_argument("--max-chunks", type=int, default=None)
    p_full.add_argument("--ref", type=str, default=None, help="Путь к reference_blocks.json")
    _add_article_args(p_full)
    p_full.set_defaults(func=cmd_full)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
