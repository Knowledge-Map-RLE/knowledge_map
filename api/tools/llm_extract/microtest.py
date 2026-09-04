"""Микро-тест LLM-промпта извлечения блоков на маленьком фрагменте.

Цель — дешёвая итерация промпта (~1-5₽) ДО полного прогона (chunk_size=4000).
Использует реальные компоненты продакшена:
  - build_unified_chunk_prompt_en   (промпт чанка, формат JSON)
  - build_dsl_prompt                (лёгкий DSL-промпт, режим --dsl)
  - AIModelClient.generate_text     (HTTP к AI-микросервису 127.0.0.1:50059)
  - ai_pricing                      (оценка цены до запуска)

Режимы:
  Dry-run (БЕЗ вызова LLM, только оценка цены + показ промпта):
      python tools/llm_extract/microtest.py [--dsl] [--section abstract-intro]
  Реальный прогон (стоит денег, ~1-5₽):
      python tools/llm_extract/microtest.py [--dsl] --go
  Вариант фрагмента:
      --section abstract|intro|abstract-intro|results1|discussion
  Метрика-проверка по эталонным листовым T4 абстрактных атрибутов:
      (печатается автоматически при --go)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.ai_model_client import AIModelClient  # noqa: E402
from services.llm_triplet_extraction_prompt_en import build_unified_chunk_prompt_en  # noqa: E402
from services.llm_triplet_extraction_prompt_dsl import build_dsl_prompt  # noqa: E402
from services.llm_triplet_extraction_service import LLMTripletExtractionService  # noqa: E402
from tools.llm_extract.dsl_parser import parse_dsl_text  # noqa: E402
from tools.llm_extract import metrics as m  # noqa: E402
from infrastructure.config import settings  # noqa: E402
from domain.rules import ai_pricing as pricing  # noqa: E402

ARTICLE_MD = Path(
    "D:/Knowledge_Map/eval/gold/"
    "immunometabolic-resistors-of-aging-in-long-lived-golden-spiny-mice/article.md"
)
REFERENCE_JSON = Path(__file__).resolve().parent / "reference_blocks_immuno.json"
TITLE = "Immunometabolic resistors of aging in long-lived golden spiny mice"

# Границы секций (без учёта ссылок) — заголовки в article.md
_SECTIONS = {
    "abstract": (1962, 2948),
    "intro": (2958, 8626),
    "abstract-intro": (1962, 8626),
    "results1": (8639, 16717),
    "results2": (16717, 23130),
    "results3": (23130, 31723),
    "results4": (31723, 40695),
    "results5": (40695, 49485),
    "discussion": (49485, 57521),
}


def _load_text() -> str:
    return ARTICLE_MD.read_text(encoding="utf-8-sig")


def _load_reference_leaf_t4() -> list[tuple[str, str, str]]:
    data = json.loads(REFERENCE_JSON.read_text(encoding="utf-8-sig"))
    ref_blocks = data["blocks"] if isinstance(data, dict) else data
    return m.extract_leaf_triplets(ref_blocks)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="abstract-intro", choices=list(_SECTIONS))
    ap.add_argument("--dsl", action="store_true", help="Использовать лёгкий DSL-промпт")
    ap.add_argument("--go", action="store_true", help="Реально вызвать LLM (стоит денег)")
    ap.add_argument("--max-chars", type=int, default=settings.LLM_MAX_CHUNK_CHARS)
    ap.add_argument("--chunk", type=int, default=None,
                    help="Запустить только один чанк (1-индексный) — стабильнее/дешевле")
    ap.add_argument("--show-prompt", action="store_true")
    args = ap.parse_args()

    text = _load_text()
    start, end = _SECTIONS[args.section]
    frag = text[start:end].strip()

    svc = LLMTripletExtractionService()
    frag_chunks = svc.split_into_chunks(frag, args.max_chars)
    if args.chunk is not None:
        if not (1 <= args.chunk <= len(frag_chunks)):
            print(f"Ошибка: --chunk {args.chunk} вне диапазона 1..{len(frag_chunks)}")
            sys.exit(2)
        frag_chunks = [frag_chunks[args.chunk - 1]]

    print(f"Секция [{args.section}] chars={len(frag)}, чанков: {len(frag_chunks)}")
    print(f"Режим: {'DSL' if args.dsl else 'JSON (unified)'}")
    print(f"Модель: {settings.LLM_EXTRACT_MODEL}")
    print(f"max_tokens={settings.LLM_MAX_TOKENS}, temperature={settings.LLM_TEMPERATURE}")
    print("=" * 70)

    ipt = 0
    prompts = []
    for ci, ch in enumerate(frag_chunks):
        if args.dsl:
            prompt = build_dsl_prompt(article_title=TITLE, fragment_text=ch)
        else:
            prompt = build_unified_chunk_prompt_en(
                article_title=TITLE, chunk_text=ch, prior_blocks=[], next_b_tag=1
            )
        prompts.append(prompt)
        ipt += len(prompt)
        print(f"--- чанк {ci + 1}: {len(ch)} симв., промпт {len(prompt)} симв. ---")

    # Оценка токенов (грубо: символы/3) и цены ДО запуска
    est_in = ipt // 3
    est_out = _guess_output(frag)
    print("\n[ДО ЗАПУСКА — оценка цены]")
    print(f"  входных ~{est_in} токенов; выход ~{est_out} (оценка)")
    no_cache = pricing.estimate_usage_cost(
        estimated_input_tokens=est_in, estimated_output_tokens=est_out
    )
    print(f"  БЕЗ промпт-кэша: ~{pricing.cost_to_kopecks(no_cache.total) / 100:6.2f} ₽")
    if args.dsl:
        print("  (DSL: промпт короткий, кэш-префикса почти нет — вход дешёвый)")
    else:
        boiler = (len(prompts[0]) // 3) if prompts else 0
        cached = min(est_in, boiler * (len(frag_chunks) - 1)) if len(frag_chunks) > 1 else 0
        with_cache = pricing.estimate_usage_cost(
            estimated_input_tokens=est_in, estimated_output_tokens=est_out,
            cached_input_tokens=cached,
        )
        print(f"  С промпт-кэшем (~{cached} ток.): ~{pricing.cost_to_kopecks(with_cache.total) / 100:6.2f} ₽")

    if not args.go:
        print("\nТолько оценка цены (--go не указан). LLM НЕ вызывался.")
        if args.show_prompt and prompts:
            print("\n=== Промпт (чанк 1) ===\n")
            print(prompts[0])
        return

    client = AIModelClient()
    total_in = total_out = 0
    all_blocks: list[dict] = []

    for ci, (ch, prompt) in enumerate(zip(frag_chunks, prompts)):
        print(f"\n=== LLM чанк {ci + 1}/{len(frag_chunks)} (вызов...) ===")
        res = client.generate_text(
            model_id=settings.LLM_EXTRACT_MODEL,
            prompt=prompt,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            enable_chunking=True,
            timeout=1200,
        )
        if not res.get("success"):
            print("  ОШИБКА:", res.get("message"))
            continue
        total_in += res.get("input_tokens", 0)
        total_out += res.get("output_tokens", 0)
        gen = res.get("generated_text", "")
        cost = pricing.calculate_usage_cost(
            input_tokens=res.get("input_tokens", 0) + res.get("cached_input_tokens", 0),
            cached_input_tokens=res.get("cached_input_tokens", 0),
            output_tokens=res.get("output_tokens", 0),
        )
        print(f"  вход={res.get('input_tokens')} выход={res.get('output_tokens')} "
              f"кэш={res.get('cached_input_tokens', 0)} ЦЕНА=~{pricing.cost_to_kopecks(cost.total) / 100:.3f}₽")

        if args.dsl:
            blocks = parse_dsl_text(gen)
        else:
            blocks = svc._parse_unified_json(gen)
        all_blocks.extend(blocks)
        print(f"  блоков распознано: {len(blocks)}")
        _report_blocks(blocks)
        # сохраняем сырой вывод чанка (уникальный по секции+чанку, чтобы не перезаписывать)
        Path(f"microtest_{'dsl' if args.dsl else 'json'}_{args.section}_chunk{ci + 1}.txt").write_text(gen, encoding="utf-8")

    total = pricing.calculate_usage_cost(input_tokens=total_in, output_tokens=total_out)
    print("\n=== ИТОГО ===")
    print(f"  вход={total_in} выход={total_out} ЦЕНА=~{pricing.cost_to_kopecks(total.total) / 100:.3f}₽")

    # Метрика-проверка: recall эталонных листовых T4 абстрактных атрибутов
    if all_blocks:
        _metric_check(all_blocks)


def _guess_output(frag: str) -> int:
    """Грубая оценка выходных токенов ~ блоков на фрагмент."""
    return max(1000, int(len(frag) / 2))


def _report_blocks(blocks: list[dict]) -> None:
    t4 = []
    for b in blocks:
        if b.get("blockType") != 4:
            continue
        d = b.get("data") or {}
        t4.append((str(d.get("subject", "")), str(d.get("predicate", "")),
                   str(d.get("object", ""))))
    print(f"  T4-триплетов: {len(t4)}")
    for t in t4:
        if str(t[0]).startswith("A.") and str(t[1]) in ("has", "shows", "maintains", "resists"):
            print(f"     - {t}")


def _metric_check(blocks: list[dict]) -> None:
    """Сравнивает извлечённые блоки с эталонными листовыми T4 (смысловое совпадение)."""
    matcher = m.TextMatcher()
    ref_leaf = _load_reference_leaf_t4()
    ext_leaf = m.extract_leaf_triplets(blocks)

    print("\n=== МЕТРИКА vs ЭТАЛОН (листовые T4) ===")
    print(f"  эталонных листовых T4: {len(ref_leaf)}; извлечено листовых T4: {len(ext_leaf)}")
    if not ext_leaf:
        print("  Извлечено 0 листовых T4 — recall 0.")
        return

    res = m.evaluate_triplets(ref_leaf, ext_leaf, matcher)
    print(f"  triplets_f1 (leaf): precision={res['precision']:.3f} "
          f"recall={res['recall']:.3f} f1={res['f1']:.3f} matched={len(res['pairs'])}")
    print("  Совпавшие пары:")
    for p in res["pairs"]:
        print(f"    {p['score']:.2f} | REF {p['reference'][1:] if len(p['reference'])>=3 else p['reference']}")

    # Особый акцент: recall абстрактных атрибутов 'A. russatus has higher/lower X'
    ref_attr = [t for t in ref_leaf if str(t[0]).startswith("A.") and t[1] == "has"]
    ext_attr = [t for t in ext_leaf if str(t[0]).startswith("A.") and t[1] == "has"]
    if ref_attr:
        res_attr = m.evaluate_triplets(ref_attr, ext_attr, matcher)
        print(f"\n  [атрибутивные 'A. has X'] эталон={len(ref_attr)} извлечено={len(ext_attr)} "
              f"f1={res_attr['f1']:.3f} recall={res_attr['recall']:.3f} matched={len(res_attr['pairs'])}")
        if not res_attr["pairs"]:
            print("    НЕ СОВПАЛО НИ ОДНОГО абстрактного атрибута — вероятная причина: "
                  "промпт не заставляет эмитить 'has higher/lower X' листовые T4.")
    else:
        print("\n  [атрибутивные 'A. has X'] в эталоне нет (нечего сверять)")


if __name__ == "__main__":
    main()
