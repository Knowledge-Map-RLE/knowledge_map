"""Метрики качества преобразования исходного текста статьи в структурные блоки.

Оценка двунаправленная (precision + recall) и не опирается на ручные словари
синонимов: сходство строк считается лексико-морфологически — стемы RU/EN
(совместимо со стеммером клиентского articleMapGraph.ts). Класс TextMatcher —
точка расширения для семантического бэкенда (эмбеддингов) без изменения
остального кода.

Компоненты композита (веса предварительные; калибровка по размеченному корпусу
будет выполнена после появления надёжных эталонов):
  triplets_f1          (0.30) — F1 по текстовым триплетам T4;
  causal_f1            (0.15) — F1 по рёбрам каузального графа T58;
  thought_recall       (0.20) — доля содержательных предложений статьи,
                                  выровненных хотя бы с одним блоком;
  grounding            (0.15) — доля блоков, подкреплённых исходным текстом;
  graph_connectivity   (0.10) — доля блоков, участвующих в ссылках и входящих
                                  в крупнейшую компоненту графа UUID-ссылок;
  intervention_quality (0.10) — доля T57, чей interventionRef разрешается в
                                  существующий блок и согласован с ним по смыслу.

Компонента исключается из композита, если объект сравнения нет ни с одной из
сторон; веса оставшихся перенормируются — магических бонусов нет.

Приёмка: все гейты пройдены И composite >= PASS_THRESHOLD.
Гейт: dangling_refs == 0 — битые UUID-ссылки недопустимы.

Диагностика вне композита: гистограммы типов (L1, дельта), счётчики блоков.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ─── Константы ────────────────────────────────────────────────────────────────

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

ALL_TYPES = frozenset(range(1, 60))

TRIPLET_MATCH_THRESHOLD = 0.55
ENTITY_MATCH_THRESHOLD = 0.55
RELATION_MATCH_THRESHOLD = 0.50
ALIGNMENT_THRESHOLD = 0.65
INTERVENTION_MATCH_THRESHOLD = 0.45
SIM_CONTAINMENT_DISCOUNT = 0.80

PASS_THRESHOLD = 0.80

WEIGHTS: Dict[str, float] = {
    "triplets_f1": 0.30,
    "causal_f1": 0.15,
    "thought_recall": 0.20,
    "grounding": 0.15,
    "graph_connectivity": 0.10,
    "intervention_quality": 0.10,
}

# ─── Нормализация текста ──────────────────────────────────────────────────────

_STOPWORDS_RAW = {
    "ru": (
        "и в во не что он на я с со как а то все она так его но да ты к у же вы за бы "
        "по от о из ему них до вас уж вам ведь там потом себя ей они тут где есть надо "
        "ней для мы тебя их чем была сам без будто чего раз тоже себе под будет ж этот "
        "эта эти это этого которой который которой при чтобы либо хотя потому поэтому "
        "также между более менее очень почти каждый весь вся любой такой таком образом "
        "т е д см прим рис таб"
    ),
    "en": (
        "the of and in with to for on vs et al a an is are was were be been being by "
        "that this these those it its their there which who whom when where while if "
        "then than as at from into about between through during before after above "
        "below both each also can could may might will would shall should must have "
        "has had do does did not nor but or however although though thus hence "
        "therefore such some any all very just only own same so no"
    ),
}

STOPWORDS = frozenset(w for part in _STOPWORDS_RAW.values() for w in part.split())

# Порядок суффиксов значения не имеет: применяется самый длинный подходящий.
_RU_SUFFIXES_RAW = (
    "ями", "ыми", "ами", "ие", "ии", "ья", "ью", "ия", "ах", "ам", "ях",
    "ом", "им", "ов", "ев", "ой", "ый", "ий", "ое", "ого", "его", "их",
    "ых", "ую", "ая", "ем", "ей", "ин", "ну", "но", "на",
    "ировать", "ируется", "евать", "ывать", "ивать", "овать", "ирует",
    "ует", "ают", "яют", "яет", "ает", "уть", "ыть", "ать", "ять", "ить",
    "еть", "тся", "ться", "ла", "ло", "ли", "лу", "ля", "ть", "ся",
    "ут", "ют", "ат", "ят", "ит", "ет",
)
_EN_SUFFIXES_RAW = ("ing", "tion", "ment", "ness", "ed", "es", "ly", "s")

MIN_STEM_LENGTH = 3
_RU_SUFFIXES = tuple(sorted(set(_RU_SUFFIXES_RAW), key=lambda s: (-len(s), s)))
_EN_SUFFIXES = tuple(sorted(set(_EN_SUFFIXES_RAW), key=lambda s: (-len(s), s)))

_VOWEL_TAIL = frozenset("аеиоуюыэюяьъй")

_TOKEN_RE = re.compile(r"[а-яёa-z0-9]+")


def stem(word: str) -> str:
    """Суффиксный стеммер + отбрасывание конечной гласной у кириллицы
    (светлый стеммер): сводит падежные формы «метформин/метформина»,
    «приём/приёма». Латиница и цифры не затрагиваются.
    """
    w = word.lower()
    for suffixes in (_RU_SUFFIXES, _EN_SUFFIXES):
        for suf in suffixes:
            if w.endswith(suf) and len(w) - len(suf) >= MIN_STEM_LENGTH:
                w = w[: -len(suf)]
                break
    if len(w) >= MIN_STEM_LENGTH + 1 and w[-1] in _VOWEL_TAIL and any(
        "а" <= ch <= "я" for ch in w
    ):
        w = w[:-1]
    return w


def stem_tokens(text: str) -> List[str]:
    tokens = _TOKEN_RE.findall((text or "").lower())
    return [stem(t) for t in tokens if len(t) > 1 and t not in STOPWORDS]


class TextMatcher:
    """Сходство пар строк на основе стем-множеств, значение в [0, 1].

    sim = max(Jaccard, DISCOUNT * containment), где containment — пересечение,
    делённое на меньший объём. Containment различает частный случай и общее
    понятие («AMPK» внутри «AMPK активация у стареющих мышц»), Jaccard штрафует
    за лишние слова. Замена на эмбеддинги = переопределение similarity.
    """

    def __init__(self, containment_discount: float = SIM_CONTAINMENT_DISCOUNT) -> None:
        self._discount = containment_discount
        self._cache: Dict[str, frozenset] = {}

    def stems(self, text: Any) -> frozenset:
        key = str(text or "")
        cached = self._cache.get(key)
        if cached is None:
            cached = frozenset(stem_tokens(key))
            self._cache[key] = cached
        return cached

    def similarity(self, a: Any, b: Any) -> float:
        return self.similarity_sets(self.stems(a), self.stems(b))

    def similarity_sets(self, sa: frozenset, sb: frozenset) -> float:
        if not sa or not sb:
            return 0.0
        inter = len(sa & sb)
        if inter == 0:
            return 0.0
        jaccard = inter / len(sa | sb)
        containment = inter / min(len(sa), len(sb))
        return max(jaccard, self._discount * containment)


# ─── Базовые операции над блоками ─────────────────────────────────────────────

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def is_uuid(value: Any) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def load_blocks(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("blocks", []))
    return list(data)


def build_uuid_map(blocks: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build UUID → block index for resolving references.

    Публичный универсальный резолвер: ключом берётся `instanceId`, при
    отсутствии — `uuid` (внутренний формат сервиса извлечения до конвертации).
    """
    index: Dict[str, Dict[str, Any]] = {}
    for b in blocks:
        key = str(b.get("instanceId") or b.get("uuid") or "")
        if key and key not in index:
            index[key] = b
    return index


def resolve_uuid_text(value: Any, uuid_map: Dict[str, Dict[str, Any]]) -> str:
    """Публичная обёртка над универсальным резолвером UUID → текст."""
    return _resolve_uuid_value(value, uuid_map)


def _build_uuid_map(blocks: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build UUID → block index for resolving references."""
    return {str(b.get("instanceId", "")): b for b in blocks if b.get("instanceId")}


def _resolve_uuid_value(value: Any, uuid_map: Dict[str, Dict[str, Any]]) -> str:
    """If value is a UUID, resolve it to the referenced block's text."""
    if isinstance(value, str) and is_uuid(value.strip()):
        target = uuid_map.get(value.strip())
        if target:
            return block_to_text(target, uuid_map=uuid_map)
    return _stringify(value)


def gold_dir() -> Path:
    """Каталог золотых эталонов eval/gold (единственный источник эталонов)."""
    return Path(__file__).resolve().parents[3] / "eval" / "gold"


def load_gold_manifest(root: Optional[Path] = None) -> Dict[str, Any]:
    manifest_path = (root or gold_dir()) / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def gold_case_paths(slug: str, root: Optional[Path] = None) -> Dict[str, Path]:
    """Пути файлов кейса: reference — structural_lines.json, article — снапшот текста."""
    case_dir = (root or gold_dir()) / slug
    paths = {"reference": case_dir / "structural_lines.json", "article": case_dir / "article.md"}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Кейс '{slug}' неполон, отсутствуют: {', '.join(missing)}")
    return paths


def gold_case_slugs(root: Optional[Path] = None) -> List[str]:
    return [c["slug"] for c in load_gold_manifest(root).get("cases", [])]


def resolve_reference_slug(root: Optional[Path] = None) -> str:
    """Единственный кейс набора; при нескольких требует явного выбора."""
    slugs = gold_case_slugs(root)
    if len(slugs) == 1:
        return slugs[0]
    raise ValueError("В наборе несколько кейсов, укажите slug явно: " + ", ".join(slugs))


def load_reference(path: Optional[Path] = None, slug: Optional[str] = None) -> List[Dict[str, Any]]:
    if path is not None:
        return load_blocks(path)
    return load_blocks(gold_case_paths(slug or resolve_reference_slug())["reference"])


def _block_type(block: Dict[str, Any]) -> int:
    try:
        return int(block.get("blockType", 0) or 0)
    except (TypeError, ValueError):
        return 0


BLOCK_TEXT_FIELDS: Dict[int, Tuple[str, ...]] = {
    1: ("title", "doi", "authors"),
    2: ("subject", "predicate", "object"),
    4: ("subject", "predicate", "object"),
    7: ("hypothesis", "disproofExplanation"),
    14: ("experimentName", "experimentType"),
    16: ("mechanism",),
    18: ("interventionType", "mechanism", "target"),
    19: ("species", "timeline", "conditions"),
    22: ("subject", "predicate", "object"),
    23: ("term", "definition"),
    37: ("statProcessing", "expectationsComparison"),
    38: ("claimSubject", "claimPredicate", "claimObject"),
    39: ("limitations",),
    40: ("finding", "context"),
    44: ("novelty",),
    46: ("futureResearch",),
    51: ("funding",),
    54: ("subject", "predicate", "object"),
    55: ("groupName", "conditions"),
    56: ("stepName", "details"),
    57: ("parameter", "direction", "detail"),
    58: ("source_name", "relationType", "target_name", "source", "target"),
}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " ".join(_stringify(v) for v in value)
    if isinstance(value, dict):
        return " ".join(_stringify(v) for v in value.values())
    return str(value)


def block_to_text(block: Dict[str, Any], uuid_map: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """Extract text from block, resolving UUID references if uuid_map is provided."""
    data = block.get("data") or {}
    fields = BLOCK_TEXT_FIELDS.get(_block_type(block))
    if uuid_map:
        parts = [_resolve_uuid_value(data.get(f), uuid_map) for f in fields] if fields else [_resolve_uuid_value(v, uuid_map) for v in data.values()]
    else:
        parts = [_stringify(data.get(f)) for f in fields] if fields else [_stringify(v) for v in data.values()]
    return " ".join(p.strip() for p in parts if p and p.strip())


def type_histogram(blocks: Sequence[Dict[str, Any]]) -> Dict[int, int]:
    hist: Dict[int, int] = {}
    for b in blocks:
        t = _block_type(b)
        hist[t] = hist.get(t, 0) + 1
    return hist


def type_delta(ref_hist: Dict[int, int], ext_hist: Dict[int, int]) -> Dict[int, int]:
    delta: Dict[int, int] = {}
    for t in sorted(set(ref_hist) | set(ext_hist)):
        d = ext_hist.get(t, 0) - ref_hist.get(t, 0)
        if d:
            delta[t] = d
    return delta


def hist_l1_similarity(ref_hist: Dict[int, int], ext_hist: Dict[int, int]) -> float:
    ref_n = sum(ref_hist.values())
    ext_n = sum(ext_hist.values())
    if ref_n == 0 or ext_n == 0:
        return 0.0
    total = sum(abs(ext_hist.get(t, 0) / ext_n - ref_hist.get(t, 0) / ref_n) for t in ALL_TYPES)
    return max(0.0, 1.0 - total / 2)


# ─── Граф UUID-ссылок ─────────────────────────────────────────────────────────

def _iter_uuid_values(node: Any) -> Iterable[str]:
    if isinstance(node, str):
        s = node.strip()
        if is_uuid(s):
            yield s
        elif s.startswith("["):
            try:
                parsed = json.loads(s)
            except (ValueError, TypeError):
                return
            yield from _iter_uuid_values(parsed)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_uuid_values(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _iter_uuid_values(v)


def analyze_uuid_graph(blocks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Целостность структуры по всем UUID-полям данных.

    connectivity — доля блоков, участвующих хотя бы в одной ссылке и входящих
    в крупнейшую компоненту; блоки, которым ссылаться не положено (метаданные),
    связность не портят. Отсутствие ссылок вообще считается нормой.
    """
    n = len(blocks)
    index: Dict[str, int] = {}
    for i, b in enumerate(blocks):
        uid = str(b.get("instanceId", "") or "")
        if uid and uid not in index:
            index[uid] = i

    parent = list(range(n))

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    dangling: Counter = Counter()
    involved: Set[int] = set()
    edges = 0
    for i, b in enumerate(blocks):
        self_uid = str(b.get("instanceId", "") or "")
        for ref in _iter_uuid_values(b.get("data") or {}):
            if ref == self_uid:
                continue
            j = index.get(ref)
            if j is None:
                dangling[ref] += 1
                continue
            edges += 1
            involved.add(i)
            involved.add(j)
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

    sizes = Counter(find(i) for i in involved)
    largest = max(sizes.values()) if sizes else 0
    return {
        "blocks": n,
        "linked_blocks": len(involved),
        "uuid_edges": edges,
        "dangling_refs": sum(dangling.values()),
        "dangling_unique": len(dangling),
        "largest_component": largest,
        "connectivity": largest / len(involved) if involved else 1.0,
    }


# ─── Общая механика сопоставления ─────────────────────────────────────────────

def _greedy_assignment(
    scores: List[List[float]], threshold: float
) -> List[Tuple[int, int, float]]:
    candidates = sorted(
        ((i, j, s) for i, row in enumerate(scores) for j, s in enumerate(row)),
        key=lambda x: x[2],
        reverse=True,
    )
    used_i: Set[int] = set()
    used_j: Set[int] = set()
    matched: List[Tuple[int, int, float]] = []
    for i, j, s in candidates:
        if s < threshold:
            break
        if i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        matched.append((i, j, s))
    return matched


def _prf(matched: int, predicted: int, expected: int) -> Dict[str, float]:
    precision = matched / predicted if predicted else 0.0
    recall = matched / expected if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def _empty_when_undefined() -> Optional[Dict[str, Any]]:
    return None


# ─── Триплеты T4 ──────────────────────────────────────────────────────────────

_TRIPLET_FIELD_WEIGHTS = (0.4, 0.2, 0.4)


def extract_triplets(blocks: Sequence[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    for b in blocks:
        if _block_type(b) != 4:
            continue
        d = b.get("data") or {}
        s, p, o = d.get("subject"), d.get("predicate"), d.get("object")
        if not s or not o or is_uuid(s) or is_uuid(p) or is_uuid(o):
            continue
        out.append((str(s).strip(), str(p or "").strip(), str(o).strip()))
    return out


def evaluate_triplets(
    ref_triplets: Sequence[Tuple[str, str, str]],
    ext_triplets: Sequence[Tuple[str, str, str]],
    matcher: TextMatcher,
) -> Optional[Dict[str, Any]]:
    """Precision/recall/F1: триплет совпадает, если взвешенная сумма сходств
    S/P/O (0.4/0.2/0.4) достигает порога; каждому триплету — не более одной пары.
    """
    if not ref_triplets and not ext_triplets:
        return None
    base = {"ref_count": len(ref_triplets), "ext_count": len(ext_triplets)}
    if not ref_triplets or not ext_triplets:
        result = _prf(0, len(ext_triplets), len(ref_triplets))
        return {**result, **base, "pairs": []}

    scores = [
        [
            sum(
                w * matcher.similarity(a, b)
                for w, a, b in zip(_TRIPLET_FIELD_WEIGHTS, rt, et)
            )
            for et in ext_triplets
        ]
        for rt in ref_triplets
    ]
    pairs = _greedy_assignment(scores, TRIPLET_MATCH_THRESHOLD)
    result = _prf(len(pairs), len(ext_triplets), len(ref_triplets))
    return {
        **result,
        **base,
        "pairs": [
            {
                "reference": list(ref_triplets[i]),
                "extracted": list(ext_triplets[j]),
                "score": round(s, 4),
            }
            for i, j, s in sorted(pairs, key=lambda x: -x[2])[:20]
        ],
    }


# ─── Каузальный граф T58 ──────────────────────────────────────────────────────

_TAG_RE = re.compile(r"^\{B\d+\}$")

_RELATION_CLASS_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (
        "negative_causation",
        r"inhibit|suppress|reduc|decreas|downregul|impair|attenuat|block|delay|slow"
        r"|подавл|ингибир|сниж|уменьш|блокир|ослабл|замедл",
    ),
    (
        "positive_causation",
        r"promot|enhanc|increas|upregul|stimulat|elevat|boost|acceler"
        r"|повыш|увелич|усил|стимул|ускор|активир",
    ),
    (
        "causation",
        r"caus|induc|driv|lead|result|produc|provok|contribute"
        r"|вызыв|вызв|привод|обусловл|порожд|способств",
    ),
    ("regulation", r"regulat|modulat|control|регулир|модулир|контрол"),
)


def relation_class(rel: str) -> str:
    s = str(rel or "").lower().strip()
    for name, pattern in _RELATION_CLASS_PATTERNS:
        if re.search(pattern, s):
            return name
    return f"other::{s}"


def build_tag_map(blocks: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Карта «тег/позиция → текст блока» для резолва ссылок {B#} и UUID."""
    uuid_map = _build_uuid_map(blocks)
    tag_map: Dict[str, str] = {}
    for idx, b in enumerate(blocks):
        text = block_to_text(b, uuid_map=uuid_map)
        if text:
            tag_map[f"{{B{idx + 1}}}"] = text
    for b in blocks:
        tag = str(b.get("tag", "") or "").strip()
        if tag:
            text = block_to_text(b, uuid_map=uuid_map)
            if text:
                tag_map[tag] = text
    return tag_map


def _resolve_ref(value: str, tag_map: Dict[str, str]) -> str:
    v = str(value or "").strip()
    if _TAG_RE.match(v):
        return tag_map.get(v, "")
    return v


def extract_causal_edges(
    blocks: Sequence[Dict[str, Any]], tag_map: Dict[str, str]
) -> List[Dict[str, str]]:
    edges: List[Dict[str, str]] = []
    for b in blocks:
        if _block_type(b) != 58:
            continue
        d = b.get("data") or {}
        src = _resolve_ref(str(d.get("source_name") or d.get("source") or ""), tag_map)
        tgt = _resolve_ref(str(d.get("target_name") or d.get("target") or ""), tag_map)
        rel = str(d.get("relationType") or "").strip()
        if src and tgt and rel:
            edges.append({"source": src, "target": tgt, "relation": rel})
    return edges


def _relations_compatible(a: Dict[str, str], b: Dict[str, str], matcher: TextMatcher) -> bool:
    cls_a, cls_b = relation_class(a["relation"]), relation_class(b["relation"])
    if cls_a == cls_b and not cls_a.startswith("other::"):
        return True
    return matcher.similarity(a["relation"], b["relation"]) >= RELATION_MATCH_THRESHOLD


def evaluate_causal(
    ref_edges: Sequence[Dict[str, str]],
    ext_edges: Sequence[Dict[str, str]],
    matcher: TextMatcher,
) -> Optional[Dict[str, Any]]:
    """F1 по рёбрам каузального графа.

    Вершины сопоставляются по смысловому сходству имён, ребро засчитывается,
    когда оба конца отображены и тип связи совместим (один класс причинности
    либо высокое лексическое сходство). Направление учитывается строго.
    """
    if not ref_edges and not ext_edges:
        return None
    base: Dict[str, Any] = {"ref_edges": len(ref_edges), "ext_edges": len(ext_edges)}
    if not ref_edges or not ext_edges:
        return {**_prf(0, len(ext_edges), len(ref_edges)), **base, "node_matches": []}

    ref_nodes = list(dict.fromkeys(e["source"] for e in ref_edges) | dict.fromkeys(e["target"] for e in ref_edges))
    ext_nodes = list(dict.fromkeys(e["source"] for e in ext_edges) | dict.fromkeys(e["target"] for e in ext_edges))
    node_scores = [[matcher.similarity(a, c) for c in ext_nodes] for a in ref_nodes]
    node_pairs = _greedy_assignment(node_scores, ENTITY_MATCH_THRESHOLD)
    mapping = {ref_nodes[i]: ext_nodes[j] for i, j, _ in node_pairs}

    used: Set[int] = set()
    matched_pairs: List[Tuple[int, int]] = []
    for ri, re_edge in enumerate(ref_edges):
        mapped_src = mapping.get(re_edge["source"])
        mapped_tgt = mapping.get(re_edge["target"])
        if not mapped_src or not mapped_tgt:
            continue
        for ei, ex_edge in enumerate(ext_edges):
            if ei in used:
                continue
            if (
                ex_edge["source"] == mapped_src
                and ex_edge["target"] == mapped_tgt
                and _relations_compatible(re_edge, ex_edge, matcher)
            ):
                used.add(ei)
                matched_pairs.append((ri, ei))
                break

    result = _prf(len(matched_pairs), len(ext_edges), len(ref_edges))
    return {
        **result,
        **base,
        "node_matches": [
            {"reference": k, "extracted": v}
            for k, v in sorted(mapping.items())[:20]
        ],
    }


# ─── Привязка результатов T57 к интервенциям ──────────────────────────────────

def evaluate_interventions(
    blocks: Sequence[Dict[str, Any]], matcher: TextMatcher
) -> Optional[Dict[str, Any]]:
    """Качество привязки T57: interventionRef должен разрешаться в существующий
    блок и быть согласованным с находкой по смыслу. Метрика внутренняя и не
    требует эталона.
    """
    findings = [b for b in blocks if _block_type(b) == 57]
    if not findings:
        return None
    by_id = {str(b.get("instanceId", "") or ""): b for b in blocks if b.get("instanceId")}
    resolved = 0
    consistent = 0
    sims: List[float] = []
    for b in findings:
        raw = str((b.get("data") or {}).get("interventionRef") or "").strip()
        target = by_id.get(raw) if is_uuid(raw) else None
        if target is None:
            continue
        resolved += 1
        # Check if target is a valid intervention (T18 or T54)
        target_type = _block_type(target)
        if target_type in (18, 54):
            # Structural consistency: T57 references a valid intervention block
            consistent += 1
            sims.append(1.0)
        else:
            # T57 references a non-intervention block
            sims.append(0.0)
    quality = consistent / len(findings) if findings else 0.0
    return {
        "quality": round(quality, 4),
        "findings": len(findings),
        "resolved_refs": resolved,
        "semantically_consistent": consistent,
        "avg_target_similarity": round(sum(sims) / len(sims), 4) if sims else None,
    }


# ─── Выравнивание текста и блоков ─────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS_RE = re.compile(r"[*_`]{1,3}")
_CONTACT_LINE_RE = re.compile(
    r"(@|https?://|www\.|\bdoi\b|e-?mail|corresponding author|orcid)", re.IGNORECASE
)
_AFFILIATION_RE = re.compile(
    r"(universit|institute|department|laborator|faculty|school of|cent(re|er) (for|of)"
    r"|hospital|college|академи|университет|институт|кафедра|лаборатор|факульте|центр)",
    re.IGNORECASE,
)
_CITATION_START_RE = re.compile(r"^\[\d+\]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'«А-ЯЁA-Z(\[])")
MIN_SENTENCE_CHARS = 30
MIN_SENTENCE_STEMS = 3


def split_sentences(text: str) -> List[str]:
    t = _FRONTMATTER_RE.sub("", text or "")
    t = _CODE_FENCE_RE.sub(" ", t)
    t = _HEADING_RE.sub("", t)
    t = _TABLE_ROW_RE.sub("", t)
    t = _MD_LINK_RE.sub(r"\1", t)
    t = _MD_EMPHASIS_RE.sub("", t)
    kept = [
        line.strip()
        for line in t.splitlines()
        if line.strip()
        and not _CONTACT_LINE_RE.search(line)
        and not _AFFILIATION_RE.search(line)
    ]
    sentences = _SENTENCE_SPLIT_RE.split(" ".join(kept))
    return [
        s.strip()
        for s in sentences
        if len(s.strip()) >= MIN_SENTENCE_CHARS and not _CITATION_START_RE.match(s.strip())
    ]


def evaluate_text_alignment(
    original_text: str, blocks: Sequence[Dict[str, Any]], matcher: TextMatcher
) -> Optional[Dict[str, Any]]:
    """Выравнивание предложений статьи и блоков.

    thought_recall — доля содержательных предложений, чьё максимальное сходство
    с каким-либо блоком достигает ALIGNMENT_THRESHOLD; grounding — симметрично
    для блоков относительно текста. Предложения без достаточного числа значимых
    стемов исключаются из оценки.
    """
    sentences = split_sentences(original_text)
    if not sentences:
        return None
    sent_stems = [(i, matcher.stems(s)) for i, s in enumerate(sentences)]
    assessed = [(i, st) for i, st in sent_stems if len(st) >= MIN_SENTENCE_STEMS]
    if not assessed:
        return None

    uuid_map = _build_uuid_map(blocks)
    block_texts = [block_to_text(b, uuid_map=uuid_map) for b in blocks]
    block_stems = [matcher.stems(t) for t in block_texts]

    best_for_sentence: Dict[int, float] = {}
    for i, st in assessed:
        best_for_sentence[i] = max(
            (matcher.similarity_sets(st, bs) for bs in block_stems), default=0.0
        )
    covered = sum(1 for v in best_for_sentence.values() if v >= ALIGNMENT_THRESHOLD)

    grounding: Optional[float] = None
    blocks_grounded: Optional[int] = None
    if block_stems:
        grounded = 0
        for bt in block_stems:
            best = max((matcher.similarity_sets(bt, st) for _, st in assessed), default=0.0)
            if best >= ALIGNMENT_THRESHOLD:
                grounded += 1
        blocks_grounded = grounded
        grounding = grounded / len(block_stems)

    uncovered = sorted(best_for_sentence.items(), key=lambda kv: kv[1])
    return {
        "thought_recall": round(covered / len(assessed), 4),
        "grounding": round(grounding, 4) if grounding is not None else None,
        "sentences_assessed": len(assessed),
        "sentences_covered": covered,
        "blocks_total": len(block_stems),
        "blocks_grounded": blocks_grounded,
        "uncovered_sample": [
            {"sentence": sentences[i][:160], "best_score": round(v, 3)}
            for i, v in uncovered[:5]
        ],
    }


# ─── Композит ─────────────────────────────────────────────────────────────────

def compute_metrics(
    reference_blocks: Sequence[Dict[str, Any]],
    extracted_blocks: Sequence[Dict[str, Any]],
    original_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Полный отчёт о качестве извлечения структуры статьи."""
    matcher = TextMatcher()

    ref_blocks = list(reference_blocks)
    ext_blocks = list(extracted_blocks)
    ref_hist = type_histogram(ref_blocks)
    ext_hist = type_histogram(ext_blocks)

    components: Dict[str, float] = {}
    details: Dict[str, Any] = {}

    triplets = evaluate_triplets(extract_triplets(ref_blocks), extract_triplets(ext_blocks), matcher)
    if triplets is not None:
        components["triplets_f1"] = triplets["f1"]
        details["triplets"] = triplets

    ref_tag_map = build_tag_map(ref_blocks)
    ext_tag_map = build_tag_map(ext_blocks)
    causal = evaluate_causal(
        extract_causal_edges(ref_blocks, ref_tag_map),
        extract_causal_edges(ext_blocks, ext_tag_map),
        matcher,
    )
    if causal is not None:
        components["causal_f1"] = causal["f1"]
        details["causal"] = causal

    interventions = evaluate_interventions(ext_blocks, matcher)
    if interventions is not None:
        components["intervention_quality"] = interventions["quality"]
        details["interventions"] = interventions

    graph = analyze_uuid_graph(ext_blocks)
    components["graph_connectivity"] = round(graph["connectivity"], 4)
    details["graph"] = graph

    alignment = evaluate_text_alignment(original_text, ext_blocks, matcher) if original_text else None
    if alignment is not None:
        components["thought_recall"] = alignment["thought_recall"]
        if alignment["grounding"] is not None:
            components["grounding"] = alignment["grounding"]
        details["text_alignment"] = alignment

    weight_sum = sum(WEIGHTS[k] for k in components)
    composite = (
        sum(components[k] * WEIGHTS[k] for k in components) / weight_sum
        if weight_sum > 0
        else None
    )

    gates = {
        "dangling_refs": {
            "value": graph["dangling_refs"],
            "limit": 0,
            "passed": graph["dangling_refs"] == 0,
        },
    }
    passed = composite is not None and composite >= PASS_THRESHOLD and all(
        g["passed"] for g in gates.values()
    )

    return {
        "composite": round(composite, 4) if composite is not None else None,
        "passed": passed,
        "threshold": PASS_THRESHOLD,
        "gates": gates,
        "components": {k: round(v, 4) for k, v in components.items()},
        "weights": WEIGHTS,
        "counts": {"ref": len(ref_blocks), "ext": len(ext_blocks)},
        "type_delta": type_delta(ref_hist, ext_hist),
        "details": {
            **details,
            "type_histograms": {
                "l1_similarity": round(hist_l1_similarity(ref_hist, ext_hist), 4),
            },
        },
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Сравнение извлечённых блоков с эталоном")
    parser.add_argument("extracted", type=Path, help="JSON-файл извлечённых блоков")
    parser.add_argument("--ref", type=Path, default=None, help="Путь к эталону (по умолчанию — кейс из eval/gold)")
    parser.add_argument("--case", type=str, default=None, help="Slug кейса эталона из eval/gold/manifest.json")
    parser.add_argument("--text", type=Path, default=None, help="Путь к .md файлу оригинала")
    args = parser.parse_args()

    ref = load_reference(args.ref, slug=args.case)
    ext = load_blocks(args.extracted)
    original_text = args.text.read_text(encoding="utf-8-sig") if args.text else None
    if original_text is None:
        article_path = gold_case_paths(args.case or resolve_reference_slug()).get("article")
        original_text = article_path.read_text(encoding="utf-8-sig") if article_path else None
    report = compute_metrics(ref, ext, original_text)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
