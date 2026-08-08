"""Метрика структурного совпадения извлечённых блоков с эталоном.

Сравнивает структуру блоков, извлечённых LLM-функцией, с эталонной структурой
статьи «Immunometabolic resistors of aging in long-lived golden spiny mice»
(docId 000657ba-aec6-8a11-9c5c-986526539651, кэш reference_blocks.json).

Компоненты композитного балла (0..1):
  hist    (0.35) — нормализованная L1 по гистограмме типов блоков T1..T57;
  seq     (0.20) — доля контейнерных блоков (13 sequence-типов) с непустым
                    sequence-списком (эталон: все контейнеры имеют sequence);
  atom    (0.20) — симметричная близость отношения T4 / не-T4 к эталонному;
  types   (0.15) — доля типов эталона, присутствующих в извлечении;
  uuidref (0.10) — близость доли T4-блоков с UUID-референсом к эталонной.

Приёмка: composite >= 0.80. Диагностика (не влияет на приёмку): fuzzy-покрытие
контента триплетов, таблица дельт по типам, число битых sequence-ссылок.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Типы блоков, у которых есть поле sequence (контейнеры для T4-триплетов).
CONTAINER_TYPES = {7, 16, 22, 23, 37, 38, 39, 40, 44, 46, 47, 56, 57}

# Типы, НЕ производящие атомарных T4 (кроме самих T4 и контейнеров не
# учитываем в знаменателе атомизации; знаменатель — всё, что не T4).
ALL_TYPES = set(range(1, 58))

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def is_uuid(value: Any) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def type_histogram(blocks: Sequence[Dict[str, Any]]) -> Dict[int, int]:
    hist: Dict[int, int] = {}
    for b in blocks:
        t = int(b.get("blockType", 0))
        hist[t] = hist.get(t, 0) + 1
    return hist


def sequence_uuids(block: Dict[str, Any]) -> List[str]:
    """Возвращает список UUID из поля data.sequence блока-контейнера."""
    raw = (block.get("data") or {}).get("sequence")
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            items = parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            items = []
    else:
        items = []
    return [str(x).strip() for x in items if x and is_uuid(x)]


def t4_has_uuid_ref(block: Dict[str, Any]) -> bool:
    """T4-триплет содержит хотя бы один UUID-референс в S/P/O."""
    data = block.get("data") or {}
    for key in ("subject", "predicate", "object"):
        if is_uuid(data.get(key)):
            return True
    return False


def load_blocks(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("blocks", []))
    return list(data)


def hist_similarity(ref_hist: Dict[int, int], ext_hist: Dict[int, int]) -> float:
    """1 - 0.5 * L1 нормализованных распределений типов."""
    ref_n = sum(ref_hist.values())
    ext_n = sum(ext_hist.values())
    if ref_n == 0 or ext_n == 0:
        return 0.0
    total = 0.0
    for t in ALL_TYPES:
        total += abs(ext_hist.get(t, 0) / ext_n - ref_hist.get(t, 0) / ref_n)
    return max(0.0, 1.0 - total / 2)


def ratio_closeness(actual: float, reference: float) -> float:
    """Симметричная близость отношения: min/max."""
    if reference <= 0:
        return 1.0 if actual <= 0 else 0.0
    return min(actual, reference) / max(actual, reference)


def seq_coverage(blocks: Sequence[Dict[str, Any]]) -> float:
    """Доля контейнерных блоков с непустым sequence (эталон 1.0)."""
    containers = [b for b in blocks if int(b.get("blockType", 0)) in CONTAINER_TYPES]
    if not containers:
        return 0.0
    with_seq = sum(1 for b in containers if sequence_uuids(b))
    return with_seq / len(containers)


def type_presence(ref_hist: Dict[int, int], ext_hist: Dict[int, int]) -> float:
    """Доля типов эталона, присутствующих в извлечении."""
    ref_types = {t for t, n in ref_hist.items() if n > 0}
    ext_types = {t for t, n in ext_hist.items() if n > 0}
    if not ref_types:
        return 0.0
    return len(ref_types & ext_types) / len(ref_types)


def uuidref_rate(blocks: Sequence[Dict[str, Any]]) -> float:
    t4 = [b for b in blocks if int(b.get("blockType", 0)) == 4]
    if not t4:
        return 0.0
    return sum(1 for b in t4 if t4_has_uuid_ref(b)) / len(t4)


def atomization_ratio(hist: Dict[int, int]) -> float:
    non_t4 = sum(n for t, n in hist.items() if t != 4)
    if non_t4 <= 0:
        return float(hist.get(4, 0))
    return hist.get(4, 0) / non_t4


def dead_sequence_refs(blocks: Sequence[Dict[str, Any]]) -> int:
    """Число sequence-ссылок на несуществующие блоки."""
    alive = {str(b.get("instanceId", "")) for b in blocks}
    dead = 0
    for b in blocks:
        for u in sequence_uuids(b):
            if u not in alive:
                dead += 1
    return dead


# ── Fuzzy-покрытие контента (диагностика, не входит в приёмку) ─────────────
def _words_match(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) > 2 and a == b + "s":
        return True
    if len(b) > 2 and a + "s" == b:
        return True
    if len(a) > 3 and a.endswith("ies") and a[:-3] + "y" == b:
        return True
    if len(b) > 3 and b.endswith("ies") and b[:-3] + "y" == a:
        return True
    return False


def _contained_in(needle: str, haystack: str) -> bool:
    n_words = [w for w in needle.lower().split()]
    h_words = [w for w in haystack.lower().split()]
    i = 0
    for word in h_words:
        if i < len(n_words) and _words_match(word, n_words[i]):
            i += 1
    return i == len(n_words)


def content_coverage(ref_blocks, ext_blocks) -> Dict[str, float]:
    """Доля текстовых T4-триплетов эталона, покрытых извлечёнными.

    Диагностика: никак не влияет на композитный балл приёмки. Для каждого
    текстового T4 эталона (без UUID-рефов) ищем извлечённый текстовый T4 с
    тем же предикатом и субъ/объект-совпадением (subsequence либо в одну,
    либо в другую сторону).
    """
    def textual_triplets(blocks):
        out = []
        for b in blocks:
            if int(b.get("blockType", 0)) != 4:
                continue
            d = b.get("data") or {}
            s, p, o = d.get("subject", ""), d.get("predicate", ""), d.get("object", "")
            if is_uuid(s) or is_uuid(p) or is_uuid(o):
                continue
            out.append((s.lower().strip(), p.lower().strip(), o.lower().strip()))
        return out

    refs = textual_triplets(ref_blocks)
    exts = textual_triplets(ext_blocks)
    if not refs:
        return {"coverage": 0.0, "ref_textual": 0, "ext_textual": len(exts)}
    matched = 0
    for rs, rp, ro in refs:
        for es, ep, eo in exts:
            if ep != rp:
                continue
            subj_ok = rs == es or _contained_in(rs, es) or _contained_in(es, rs)
            obj_ok = ro == eo or _contained_in(ro, eo) or _contained_in(eo, ro)
            if subj_ok and obj_ok:
                matched += 1
                break
    return {
        "coverage": matched / len(refs),
        "ref_textual": len(refs),
        "ext_textual": len(exts),
    }


WEIGHTS = {"hist": 0.35, "seq": 0.20, "atom": 0.20, "types": 0.15, "uuidref": 0.10}
PASS_THRESHOLD = 0.80


def compute_metrics(
    reference_blocks: Sequence[Dict[str, Any]],
    extracted_blocks: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Полный отчёт сравнения структуры извлечённых блоков с эталоном."""
    ref_hist = type_histogram(reference_blocks)
    ext_hist = type_histogram(extracted_blocks)

    ref_atom = atomization_ratio(ref_hist)
    ext_atom = atomization_ratio(ext_hist)
    ref_uuid = uuidref_rate(reference_blocks)
    ext_uuid = uuidref_rate(extracted_blocks)
    ref_seq = seq_coverage(reference_blocks)
    ext_seq = seq_coverage(extracted_blocks)

    components = {
        "hist": hist_similarity(ref_hist, ext_hist),
        "seq": ratio_closeness(ext_seq, ref_seq),
        "atom": ratio_closeness(ext_atom, ref_atom),
        "types": type_presence(ref_hist, ext_hist),
        "uuidref": ratio_closeness(ext_uuid, ref_uuid),
    }
    composite = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)

    delta = {}
    for t in sorted(set(ref_hist) | set(ext_hist)):
        d = ext_hist.get(t, 0) - ref_hist.get(t, 0)
        if d:
            delta[t] = d

    return {
        "composite": round(composite, 4),
        "passed": composite >= PASS_THRESHOLD,
        "threshold": PASS_THRESHOLD,
        "components": {k: round(v, 4) for k, v in components.items()},
        "weights": WEIGHTS,
        "counts": {
            "ref": len(reference_blocks),
            "ext": len(extracted_blocks),
        },
        "atomization": {
            "ref": round(ref_atom, 4),
            "ext": round(ext_atom, 4),
        },
        "uuidref_rate": {"ref": round(ref_uuid, 4), "ext": round(ext_uuid, 4)},
        "seq_coverage": {"ref": round(ref_seq, 4), "ext": round(ext_seq, 4)},
        "dead_sequence_refs": dead_sequence_refs(extracted_blocks),
        "type_delta": delta,
        "content": content_coverage(reference_blocks, extracted_blocks),
    }


def load_reference(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = path or Path(__file__).resolve().parent / "reference_blocks.json"
    return load_blocks(path)


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Сравнение извлечённых блоков с эталоном")
    parser.add_argument("extracted", type=Path, help="JSON-файл извлечённых блоков")
    parser.add_argument("--ref", type=Path, default=None, help="Путь к эталону")
    args = parser.parse_args()

    ref = load_reference(args.ref)
    ext = load_blocks(args.extracted)
    report = compute_metrics(ref, ext)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
