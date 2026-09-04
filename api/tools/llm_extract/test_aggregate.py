import sys, glob
from pathlib import Path
sys.path.insert(0, "D:/Knowledge_Map/api")
from tools.llm_extract.dsl_parser import parse_dsl_text
from tools.llm_extract import metrics as m
from tools.llm_extract.microtest import _load_reference_leaf_t4

# Собрать все извлечённые блоки из всех секционных чанк-файлов
pattern = "D:/Knowledge_Map/api/tools/llm_extract/artifacts/microtest_dsl_*_chunk*.txt"
files = sorted(glob.glob(pattern), key=lambda p: (p.split("_dsl_")[1].split("_chunk")[0], p))
print("Файлов-чанков:", len(files))
for f in files:
    print("  ", f.split("\\")[-1], f"{Path(f).stat().st_size} б")

all_blocks = []
for f in files:
    try:
        txt = Path(f).read_text(encoding="utf-8")
        all_blocks.extend(parse_dsl_text(txt))
    except Exception as ex:
        print("  ERR", f, ex)

print("\nВсего блоков (union по всем секциям):", len(all_blocks))
matcher = m.TextMatcher()
ref_leaf = _load_reference_leaf_t4()
ext_leaf = m.extract_leaf_triplets(all_blocks)

def dedup(triplets):
    seen, out = set(), []
    for s, p, o in triplets:
        key = (s.strip().lower(), p.strip().lower(), o.strip().lower())
        if key not in seen:
            seen.add(key)
            out.append((s, p, o))
    return out

print("эталон листовых T4 (сыро):", len(ref_leaf),
      "| извлечено листовых T4 (union, сыро):", len(ext_leaf))
ref_leaf = dedup(ref_leaf)
ext_leaf = dedup(ext_leaf)
print("после дедупликации: эталон:", len(ref_leaf), "| извлечено:", len(ext_leaf))

print("\n=== ДУБЛИКАТЫ извлечённых T4, повторённых в >=2 секциях (топ-20) ===")
from collections import Counter
cnt = Counter((s.strip().lower(), p.strip().lower(), o.strip().lower())
              for s, p, o in m.extract_leaf_triplets(all_blocks))
for key, n in cnt.most_common(20):
    if n > 1:
        print(f"  ×{n}  {key[0]} | {key[1]} | {key[2]}")

res = m.evaluate_triplets(ref_leaf, ext_leaf, matcher)
print("=== FULL-DOC leaf triplets_f1 (union всех секций) ===")
print("  precision=%.3f recall=%.3f f1=%.3f matched=%d" % (res["precision"], res["recall"], res["f1"], len(res["pairs"])))
for p in sorted(res["pairs"], key=lambda x: -x["score"]):
    print("  %.2f REF %s | EXT %s" % (p["score"], p["reference"][1:], p["extracted"][1:]))

# Абстракт-recall
ref_abs = [t for t in ref_leaf if str(t[0]).startswith("A.") and t[1]=="has"]
ext_abs = [t for t in ext_leaf if str(t[0]).startswith("A.") and t[1]=="has"]
print("\nАбстракт-атрибуты: эталон=%d извлечено(union)=%d" % (len(ref_abs), len(ext_abs)))
for r in ref_abs:
    best = max(((matcher.similarity(r[2], eo), eo) for _, _, eo in ext_abs), default=(0, None))
    print("  [%s] sim=%.2f REF='%s' | EXT best='%s'" % ("MATCH" if best[0]>=0.7 else "-----", best[0], r[2], best[1]))
