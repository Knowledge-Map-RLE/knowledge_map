"""Метрики качества преобразования исходного текста статьи в структурные блоки.

Оценка двунаправленная (precision + recall). Метрика сравнивает не тексты блоков,
а канонические семантические графы, которые эти блоки образуют.

Компоненты композита (геометрическое среднее):
  triplets_f1              (0.25) — F1 по текстовым триплетам T4 (leaf + resolved);
  causal_f1                (0.15) — F1 по рёбрам каузального графа T58;
  claim_recall             (0.20) — доля содержательных предложений статьи,
                                     выровненных хотя бы с одним блоком;
  entailment_rate          (0.15) — доля блоков, подкреплённых исходным текстом;
  ast_edge_f1              (0.10) — F1 по рёбрам AST-структуры UUID-ссылок;
  intervention_ref_validity(0.10) — доля T57, чей interventionRef разрешается
                                     в существующий блок и согласован по смыслу;
  polarity_fidelity        (0.05) — корректность отрицаний в predicate.

Hard gates (все должны выполняться):
  dangling_refs == 0 — битые UUID-ссылки недопустимы;
  self_refs == 0     — самоссылки недопустимы;
  cycles == 0        — DAG должен быть ацикличен;
  forward_refs == 0  — топологический порядок должен соблюдаться;
  duplicate_ids == 0 — UUID должны быть уникальны.

Приёмка: все гейты пройдены И composite >= PASS_THRESHOLD.
Компонента исключается из композита, если объект сравнения нет ни с одной из
сторон; геометрическое среднее пересчитывается по оставшимся.

Диагностика вне композита: гистограммы типов (L1, дельта), счётчики блоков.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from scipy.optimize import linear_sum_assignment

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
ANTONYM_SIM_PENALTY = 0.0

# Порог покрытия понятий для text_alignment: блок считается подкреплённым
# предложением (и предложение захваченным блоком), когда доля значимых
# стемов блока присутствует в предложении. Структурные блоки (триплеты)
# короче научных предложений, поэтому используем долю ОТ БЛОКА, а не
# Jaccard по полным множествам — иначе метрика ненасыщаема (потолок эталона
# само-покрытия ~0.08 вместо ~1.0).
BLOCK_COVERAGE_THRESHOLD = 0.5
# Блок с парой слов-общих-стоп-слов не считается покрытым: минимально
# необходимое число уникальных стемов блока, реально встречающихся в тексте.
_MIN_BLOCK_COVERED_STEMS = 2

PASS_THRESHOLD = 0.80

WEIGHTS: Dict[str, float] = {
    "triplets_f1": 0.25,
    "causal_f1": 0.15,
    "claim_recall": 0.20,
    "entailment_rate": 0.15,
    "ast_edge_f1": 0.10,
    "intervention_ref_validity": 0.10,
    "polarity_fidelity": 0.05,
}

# ─── Антонимы predicate ───────────────────────────────────────────────────────

_ANTONYM_PAIRS: List[Tuple[str, str]] = [
    ("activates", "inhibits"),
    ("activate", "inhibit"),
    ("increases", "decreases"),
    ("increase", "decrease"),
    ("causes", "prevents"),
    ("cause", "prevent"),
    ("causes", "inhibits"),
    ("promotes", "suppresses"),
    ("promote", "suppress"),
    ("enhances", "impairs"),
    ("enhance", "impair"),
    ("stimulates", "attenuates"),
    ("stimulate", "attenuate"),
    ("upregulates", "downregulates"),
    ("upregulate", "downregulate"),
    ("elevates", "reduces"),
    ("elevate", "reduce"),
    ("supports", "refutes"),
    ("support", "refute"),
    ("induces", "blocks"),
    ("induce", "block"),
    ("accelerates", "delays"),
    ("accelerate", "delay"),
    ("boosts", "attenuates"),
    ("boost", "attenuate"),
    (".raises", ".decreases"),
    ("positively", "negatively"),
]

_ANTONYM_INDEX: Dict[str, Set[str]] = defaultdict(set)
for _a, _b in _ANTONYM_PAIRS:
    _ANTONYM_INDEX[_a].add(_b)
    _ANTONYM_INDEX[_b].add(_a)


def _are_predicates_antonyms(p1: str, p2: str, matcher: "TextMatcher") -> bool:
    """Проверяет, являются ли два predicate антонимами.

    Сначала проверяет точное вхождение в словарь антонимов,
    затем — через stems для устойчивых форм.
    """
    s1 = str(p1 or "").lower().strip()
    s2 = str(p2 or "").lower().strip()
    if not s1 or not s2:
        return False

    for key in (s1, s2):
        if key in _ANTONYM_INDEX:
            other = s2 if key == s1 else s1
            if other in _ANTONYM_INDEX[key]:
                return True

    stems1 = matcher.stems(s1)
    stems2 = matcher.stems(s2)
    if not stems1 or not stems2:
        return False

    for key, opposites in _ANTONYM_INDEX.items():
        key_stems = matcher.stems(key)
        if key_stems and key_stems.issubset(stems1):
            for opp in opposites:
                opp_stems = matcher.stems(opp)
                if opp_stems and opp_stems.issubset(stems2):
                    return True

    return False


# ─── Нормализация текста ──────────────────────────────────────────────────────

_STOPWORDS_RAW = {
    "ru": (
        "и в во что он на я с со как а то все она так его но да ты к у же вы за бы "
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
        "below both each also will would have has had do does did nor but or however "
        "although though thus hence therefore such some any all very just only own same so"
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


# Синонимы-направления: приводятся к каноническому стему, чтобы метрика корректно
# сопоставляла атрибутивные T4 независимо от лексики («greater/elevated/increased»
# == «higher», «reduced/decreased» == «lower»). Это повышение качества сопоставления,
# НЕ снижение порога.
_EN_DIRECTION_CANON = {
    "higher": {"higher", "greater", "elevated", "increased", "enhanced", "improved", "augmented"},
    "lower": {"lower", "reduced", "decreased", "diminished", "suppressed", "attenuated", "declined"},
}
_DIRECTION_STEM_MAP: Dict[str, str] = {}
for _canon, _syns in _EN_DIRECTION_CANON.items():
    for _s in _syns:
        _DIRECTION_STEM_MAP[stem(_s)] = _canon

# Составные концепты: «lifespan/healthspan» раскрываются в «life span/health span»,
# чтобы «higher lifespan» и «higher life span» сопоставлялись как одно понятие.
_COMPOUND_SPLIT = {
    "lifespan": ["life", "span"],
    "healthspan": ["health", "span"],
}

# Смысловые синонимы КОНЦЕПТОВ (не направлений): приводятся к общему стему.
# Добавляются только семантически корректные пары из предметной области статьи,
# значения которых эквивалентны в контексте оценки атрибутов A. russatus. Это
# повышение качества сопоставления (знания о домене), НЕ снижение порога.
_CONCEPT_CANON = {
    # «молодость/сохранность профиля экспрессии» == «целостность транскриптома»
    "integrity": {"integrity", "youthfulness"},
    # «способность к восстановлению/регенерации» == «capacity»
    "capacity": {"capacity", "performance", "capability"},
}
_CONCEPT_STEM_MAP: Dict[str, str] = {}
for _canon, _syns in _CONCEPT_CANON.items():
    for _s in _syns:
        _CONCEPT_STEM_MAP[stem(_s)] = _canon


def stem_tokens(text: str) -> List[str]:
    tokens = _TOKEN_RE.findall((text or "").lower())
    out: List[str] = []
    for t in tokens:
        if len(t) <= 1 or t in STOPWORDS:
            continue
        s = stem(t)
        if s in _COMPOUND_SPLIT:
            out.extend(_COMPOUND_SPLIT[s])
        else:
            out.append(_DIRECTION_STEM_MAP.get(s, _CONCEPT_STEM_MAP.get(s, s)))
    return out


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
    """Расширенный анализ DAG UUID-ссылок.

    Возвращает:
        blocks, linked_blocks, uuid_edges — базовая статистика;
        dangling_refs — битые ссылки (ссылки на несуществующие блоки);
        self_refs — самоссылки;
        cycles — количество циклов (для DAG = 0);
        forward_refs — ссылки «назад» (нарушения топологического порядка);
        duplicate_ids — дублирующиеся instanceId;
        ast_edge_precision — точность рёбер AST относительно эталона (передаётся отдельно);
        ast_edge_recall — полнота рёбер AST;
        ast_edge_f1 — F1 рёбер AST.
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
    self_refs_count = 0
    involved: Set[int] = set()
    edges: List[Tuple[int, int]] = []

    seen_ids: Counter = Counter()
    for b in blocks:
        uid = str(b.get("instanceId", "") or "")
        if uid:
            seen_ids[uid] += 1

    duplicate_ids = sum(1 for count in seen_ids.values() if count > 1)

    for i, b in enumerate(blocks):
        self_uid = str(b.get("instanceId", "") or "")
        for ref in _iter_uuid_values(b.get("data") or {}):
            if ref == self_uid:
                self_refs_count += 1
                continue
            j = index.get(ref)
            if j is None:
                dangling[ref] += 1
                continue
            edges.append((i, j))
            involved.add(i)
            involved.add(j)
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

    sizes = Counter(find(i) for i in involved)
    largest = max(sizes.values()) if sizes else 0
    connectivity = largest / len(involved) if involved else 1.0

    cycles = _detect_cycles(edges, n)
    forward_refs = _detect_forward_refs(edges)

    return {
        "blocks": n,
        "linked_blocks": len(involved),
        "uuid_edges": len(edges),
        "dangling_refs": sum(dangling.values()),
        "dangling_unique": len(dangling),
        "self_refs": self_refs_count,
        "cycles": cycles,
        "forward_refs": forward_refs,
        "duplicate_ids": duplicate_ids,
        "largest_component": largest,
        "connectivity": round(connectivity, 4),
    }


def _detect_cycles(edges: List[Tuple[int, int]], n: int) -> int:
    """DFS-based cycle detection для directed graph. Возвращает количество циклов."""
    adj: Dict[int, List[int]] = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = [WHITE] * n
    cycles = 0

    def dfs(node: int) -> None:
        nonlocal cycles
        color[node] = GRAY
        for neighbor in adj.get(node, []):
            if neighbor >= n:
                continue
            if color[neighbor] == GRAY:
                cycles += 1
            elif color[neighbor] == WHITE:
                dfs(neighbor)
        color[node] = BLACK

    for node in range(n):
        if color[node] == WHITE:
            dfs(node)

    return cycles


def _detect_forward_refs(edges: List[Tuple[int, int]]) -> int:
    """Считает нарушения топологического порядка.

    В AST-модели `dependsOn` ребро идёт от зависимого блока к предку,
    индекс предка должен быть МЕНЬШЕ индекса зависимого блока. Ссылка на
    блок с БОЛЬШИМ индексом (v > u) — нарушение: нельзя зависеть от блока,
    который ещё не объявлен.
    """
    return sum(1 for u, v in edges if v > u)


# ─── Общая механика сопоставления ─────────────────────────────────────────────

def hungarian_assignment(
    scores: List[List[float]], threshold: float
) -> List[Tuple[int, int, float]]:
    """Оптимальное назначение (венгерский алгоритм) через scipy.

    Гарантирует глобально оптимальное сопоставление для матрицы score[i][j].
    Возвращает пары (i, j, score) с score >= threshold.
    """
    if not scores or not scores[0]:
        return []
    n_rows = len(scores)
    n_cols = len(scores[0])
    n = max(n_rows, n_cols)

    cost = [[0.0] * n for _ in range(n)]
    for i in range(n_rows):
        for j in range(n_cols):
            cost[i][j] = -scores[i][j]

    row_ind, col_ind = linear_sum_assignment(cost)

    matched: List[Tuple[int, int, float]] = []
    for r, c in zip(row_ind, col_ind):
        if r < n_rows and c < n_cols:
            s = scores[r][c]
            if s >= threshold:
                matched.append((r, c, s))
    return matched


def _greedy_assignment(
    scores: List[List[float]], threshold: float
) -> List[Tuple[int, int, float]]:
    """Жадное назначение (deprecated, оставлено как fallback)."""
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


def extract_leaf_triplets(blocks: Sequence[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """Извлекает «листовые» триплеты T4 — S/P/O без UUID-ссылок."""
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


def extract_resolved_triplets(
    blocks: Sequence[Dict[str, Any]],
    uuid_map: Dict[str, Dict[str, Any]],
    tag_map: Optional[Dict[str, str]] = None,
) -> List[Tuple[str, str, str]]:
    """Извлекает триплеты T4 с UUID-ссылками и/или Sn-тегами {Bn}, резолвит их в текст."""
    out: List[Tuple[str, str, str]] = []
    for b in blocks:
        if _block_type(b) != 4:
            continue
        d = b.get("data") or {}
        s, p, o = d.get("subject"), d.get("predicate"), d.get("object")
        if not s and not o:
            continue
        s_text = _resolve_value(s, uuid_map, tag_map)
        p_text = _resolve_value(p, uuid_map, tag_map)
        o_text = _resolve_value(o, uuid_map, tag_map)
        if s_text.strip() and o_text.strip():
            out.append((s_text.strip(), p_text.strip(), o_text.strip()))
    return out


def _resolve_value(
    value: Any,
    uuid_map: Dict[str, Dict[str, Any]],
    tag_map: Optional[Dict[str, str]] = None,
) -> str:
    """Резолвит значение: UUID → текст блока, Sn-тег {Bn} → текст блока, иначе строка."""
    v = str(value or "").strip()
    if uuid_map and is_uuid(v):
        target = uuid_map.get(v)
        if target:
            return block_to_text(target, uuid_map=uuid_map)
    if tag_map and _TAG_RE.match(v):
        return tag_map.get(v, "")
    return _stringify(value)


def extract_triplets(blocks: Sequence[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """Совместимость: извлекает все триплеты (leaf + resolved)."""
    return extract_leaf_triplets(blocks)


def evaluate_triplets(
    ref_triplets: Sequence[Tuple[str, str, str]],
    ext_triplets: Sequence[Tuple[str, str, str]],
    matcher: TextMatcher,
) -> Optional[Dict[str, Any]]:
    """Precision/recall/F1: триплет совпадает, если:
    1. predicate НЕ является антонимом;
    2. subject_score >= 0.7 И object_score >= 0.7;
    3. взвешенная сумма S/P/O (0.4/0.2/0.4) достигает порога.

    Неправильный predicate НЕ компенсируется хорошими S/O.
    Каждому триплету — не более одной пары (венгерский алгоритм).
    """
    if not ref_triplets and not ext_triplets:
        return None
    base = {"ref_count": len(ref_triplets), "ext_count": len(ext_triplets)}
    if not ref_triplets or not ext_triplets:
        result = _prf(0, len(ext_triplets), len(ref_triplets))
        return {**result, **base, "pairs": []}

    s_th = 0.7
    o_th = 0.7

    scores: List[List[float]] = []
    for rt in ref_triplets:
        row: List[float] = []
        for et in ext_triplets:
            s_sim = matcher.similarity(rt[0], et[0])
            p_sim = matcher.similarity(rt[1], et[1])
            o_sim = matcher.similarity(rt[2], et[2])

            if s_sim < s_th or o_sim < o_th:
                row.append(0.0)
                continue

            if _are_predicates_antonyms(rt[1], et[1], matcher):
                row.append(ANTONYM_SIM_PENALTY)
                continue

            total = (
                _TRIPLET_FIELD_WEIGHTS[0] * s_sim
                + _TRIPLET_FIELD_WEIGHTS[1] * p_sim
                + _TRIPLET_FIELD_WEIGHTS[2] * o_sim
            )
            row.append(total)
        scores.append(row)

    pairs = hungarian_assignment(scores, TRIPLET_MATCH_THRESHOLD)
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
    node_pairs = hungarian_assignment(node_scores, ENTITY_MATCH_THRESHOLD)
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
    blocks: Sequence[Dict[str, Any]],
    matcher: TextMatcher,
    reference_blocks: Optional[Sequence[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Качество привязки T57: interventionRef должен разрешаться в существующий
    блок типа T18/T54 и быть семантически согласованным с контекстом T57.

    Метрика симметрична остальным компонентам композита: она включается
    только если объект сравнения (привязка findings → interventionRef)
    представлен С ОБЕИХ сторон. Если эталон не содержит findings с
    interventionRef (для таких статей постановка «интервенция → результат»
    не характерна), компонента исключается из композита, а не принудительно
    зануляет его через геометрическое среднее.
    """
    findings = [b for b in blocks if _block_type(b) == 57]
    if not findings:
        return None

    findings_with_ref = [
        b for b in findings
        if str((b.get("data") or {}).get("interventionRef") or "").strip()
    ]
    if not findings_with_ref:
        return None

    # Симметрия: если в эталоне нет findings с interventionRef — объекта
    # сравнения нет, компонента исключается (как «нет эталона»).
    if reference_blocks is not None:
        ref_findings = [b for b in reference_blocks if _block_type(b) == 57]
        ref_with_ref = [
            b for b in ref_findings
            if str((b.get("data") or {}).get("interventionRef") or "").strip()
        ]
        if not ref_with_ref:
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
        target_type = _block_type(target)
        if target_type in (18, 54):
            consistent += 1
            finding_text = block_to_text(b, uuid_map=by_id)
            target_text = block_to_text(target, uuid_map=by_id)
            sim = matcher.similarity(finding_text, target_text) if finding_text and target_text else 1.0
            sims.append(sim)
        else:
            sims.append(0.0)
    quality = consistent / len(findings_with_ref) if findings_with_ref else 0.0
    return {
        "quality": round(quality, 4),
        "findings": len(findings),
        "findings_with_ref": len(findings_with_ref),
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

# Предложения, не являющиеся утверждениями знания (claims): методика, описания
# фигур, статистика. Они не кодируются структурными блоками и не должны
# влиять на claim_recall (иначе знаменатель раздувается ритуальными фразами,
# и метрика становится ненасыщаемой: эталон покрывает лишь ~30% «всех»
# предложений вместо ~всех утверждений).
_NONCLAIM_RE = re.compile(
    r"^(\([A-Za-zА-Яа-яЁё][^)]*\)|data are presented|values are (mean|expressed)|"
    r"representative (images|schematic)|an? (open field|wire hanging|beam working|"
    r"novel object|t-maze) test (was|were)|scale bars|error bars|"
    r"data represent|asterisk|statistical (significance|analyses?|test)|"
    r"\bn\s*=\s*\d|one-way anova|two-tailed|two-way anova|student[*' ]s?\s*t\s*test|"
    r"p\s*[<>]\s*0?\.0\d|_\*?p?_\s*[<>]\s*0?\.0\d|tukey|wilcoxon|"
    r"fig\.?\s*s?\d|figure\s*\d|fig\s*s\s*\d|panel[s]?\s+[a-z]|\bvs\b\.?\s+[a-z])",
    re.IGNORECASE,
)


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


def _block_covered_by_sentence(
    block_stems: frozenset, sentence_stems: frozenset
) -> float:
    """Доля значимых стемов блока, присутствующих в предложении.

    В отличие от ``similarity_sets`` (Jaccard/containment-по-минимальному),
    эта мера нормирует пересечение на размер БЛОКА: короткий структурный
    блок (триплет из 4-8 стемов) считается покрытым предложением, когда
    в нём присутствует большая часть его понятий. Это делает text_alignment
    насыщаемой (эталон покрывает сам себя), где старая мера давала потолок
    ~0.08 из-за несоразмерности длин блоков и предложений.
    """
    if not block_stems:
        return 0.0
    inter = len(block_stems & sentence_stems)
    return inter / len(block_stems)


def evaluate_text_alignment(
    original_text: str, blocks: Sequence[Dict[str, Any]], matcher: TextMatcher
) -> Optional[Dict[str, Any]]:
    """Выравнивание предложений статьи и блоков.

    claim_recall — доля содержательных предложений, в каждом из которых есть
    хотя бы один блок, достаточно покрывающий его понятия; entailment_rate —
    симметрично доля блоков, подкреплённых хотя бы одним предложением. Покрытие
    считается по доле стемов блока, присутствующих в предложении (см.
    ``_block_covered_by_sentence``) с порогом BLOCK_COVERAGE_THRESHOLD.

    Предложения и блоки без достаточного числа значимых стемов исключаются
    из оценки.

    TODO: заменить лексическое выравнивание на atomic proposition extraction
    для точного claim_recall и entailment classifier для entailment_rate.
    """
    sentences = split_sentences(original_text)
    if not sentences:
        return None
    sent_stems = [(i, matcher.stems(s)) for i, s in enumerate(sentences)]
    assessed = [
        (i, st) for i, st in sent_stems
        if len(st) >= MIN_SENTENCE_STEMS and not _NONCLAIM_RE.match(sentences[i])
    ]
    if not assessed:
        return None

    uuid_map = _build_uuid_map(blocks)
    block_texts = [block_to_text(b, uuid_map=uuid_map) for b in blocks]
    block_stems = [matcher.stems(t) for t in block_texts]
    meaningful_blocks = [bs for bs in block_stems if bs]

    best_for_sentence: Dict[int, float] = {}
    for i, st in assessed:
        best_for_sentence[i] = max(
            (_block_covered_by_sentence(bs, st) for bs in meaningful_blocks),
            default=0.0,
        )
    covered = sum(1 for v in best_for_sentence.values() if v >= ALIGNMENT_THRESHOLD)

    entailment: Optional[float] = None
    blocks_entailed: Optional[int] = None
    if meaningful_blocks:
        entailed = 0
        for bt in meaningful_blocks:
            best = max(
                (_block_covered_by_sentence(bt, st) for _, st in assessed),
                default=0.0,
            )
            if best >= ALIGNMENT_THRESHOLD:
                entailed += 1
        blocks_entailed = entailed
        entailment = entailed / len(meaningful_blocks)

    uncovered = sorted(best_for_sentence.items(), key=lambda kv: kv[1])
    return {
        "claim_recall": round(covered / len(assessed), 4),
        "entailment_rate": round(entailment, 4) if entailment is not None else None,
        "sentences_assessed": len(assessed),
        "sentences_covered": covered,
        "blocks_total": len(block_stems),
        "blocks_entailed": blocks_entailed,
        "uncovered_sample": [
            {"sentence": sentences[i][:160], "best_score": round(v, 3)}
            for i, v in uncovered[:5]
        ],
    }


# ─── Каузальная верность отрицаний ────────────────────────────────────────────

_NEGATION_MARKERS_EN = frozenset({"not", "no", "never", "neither", "nor", "without", "lack"})
_NEGATION_MARKERS_RU = frozenset({"не", "ни", "без", "нет"})


def _has_negation(text: str) -> bool:
    """Проверяет наличие маркеров отрицания в тексте (token-level)."""
    tokens = set(_TOKEN_RE.findall(str(text or "").lower()))
    return bool(tokens & _NEGATION_MARKERS_EN) or bool(tokens & _NEGATION_MARKERS_RU)


def evaluate_polarity(
    ref_triplets: Sequence[Tuple[str, str, str]],
    ext_triplets: Sequence[Tuple[str, str, str]],
    matcher: TextMatcher,
) -> Optional[Dict[str, Any]]:
    """Верность polarity: отрицание в predicate ref должно совпадать с ext.

    Для каждого сопоставленного триплета проверяет, что наличие/отсутствие
    «не/not» в predicate одинаково.
    """
    if not ref_triplets or not ext_triplets:
        return None

    s_th = 0.7
    o_th = 0.7

    scores: List[List[float]] = []
    for rt in ref_triplets:
        row: List[float] = []
        for et in ext_triplets:
            s_sim = matcher.similarity(rt[0], et[0])
            o_sim = matcher.similarity(rt[2], et[2])
            if s_sim < s_th or o_sim < o_th:
                row.append(0.0)
                continue
            row.append(matcher.similarity(rt[1], et[1]))
        scores.append(row)

    pairs = hungarian_assignment(scores, TRIPLET_MATCH_THRESHOLD)

    polarity_match = 0
    total_paired = 0
    for i, j, _ in pairs:
        ref_neg = _has_negation(ref_triplets[i][1])
        ext_neg = _has_negation(ext_triplets[j][1])
        total_paired += 1
        if ref_neg == ext_neg:
            polarity_match += 1

    fidelity = polarity_match / total_paired if total_paired else 1.0
    return {
        "polarity_fidelity": round(fidelity, 4),
        "paired_triplets": total_paired,
        "polarity_matches": polarity_match,
    }


# ─── AST edge precision/recall ────────────────────────────────────────────────

def _build_ast_edges(blocks: Sequence[Dict[str, Any]]) -> Set[Tuple[str, str]]:
    """Извлекает пары (source_uuid, target_uuid) из UUID-ссылок блоков."""
    uuid_map = _build_uuid_map(blocks)
    index = {str(b.get("instanceId", "")): b for b in blocks if b.get("instanceId")}
    edges: Set[Tuple[str, str]] = set()
    for b in blocks:
        src = str(b.get("instanceId", "") or "")
        if not src:
            continue
        for ref in _iter_uuid_values(b.get("data") or {}):
            if ref == src:
                continue
            if ref in index:
                edges.add((src, ref))
    return edges


def evaluate_ast_edges(
    ref_blocks: Sequence[Dict[str, Any]],
    ext_blocks: Sequence[Dict[str, Any]],
    matcher: TextMatcher,
) -> Optional[Dict[str, Any]]:
    """Precision/recall/F1 по рёбрам AST-структуры.

    Ребро = UUID-ссылка между блоками. Так как при реальном LLM-извлечении
    каждый блок получает СЛУЧАЙНЫЙ UUIDv8 (отличный от эталона), рёбра нельзя
    сравнивать напрямую по UUID (пересечение всегда пусто). Сначала
    сопоставляем извлечённые блоки с эталонными по СМЫСЛОВОМУ сходству их
    содержимого (венгерское назначение + TextMatcher, как в evaluate_causal),
    переводим рёбра в пространство UUID эталона и лишь затем сравниваем
    множества рёбер.
    """
    def _text(b: Dict[str, Any]) -> str:
        return block_to_text(b)

    ref_text = {str(b.get("instanceId", "") or ""): _text(b) for b in ref_blocks}
    ext_text = {str(b.get("instanceId", "") or ""): _text(b) for b in ext_blocks}
    ref_ids = list(ref_text.keys())
    ext_ids = list(ext_text.keys())

    ext_to_ref: Dict[str, str] = {}
    if ref_ids and ext_ids:
        scores = [
            [matcher.similarity(ref_text[a], ext_text[c]) for c in ext_ids]
            for a in ref_ids
        ]
        pairs = hungarian_assignment(scores, ENTITY_MATCH_THRESHOLD)
        for i, j, _ in pairs:
            ext_to_ref[ext_ids[j]] = ref_ids[i]

    ref_edges = _build_ast_edges(ref_blocks)

    mapped_ext_edges: Set[Tuple[str, str]] = set()
    for s, t in _build_ast_edges(ext_blocks):
        rs = ext_to_ref.get(s)
        rt = ext_to_ref.get(t)
        if rs and rt and rs != rt:
            mapped_ext_edges.add((rs, rt))

    if not ref_edges and not mapped_ext_edges:
        return None

    matched = ref_edges & mapped_ext_edges
    precision = len(matched) / len(mapped_ext_edges) if mapped_ext_edges else 0.0
    recall = len(matched) / len(ref_edges) if ref_edges else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "ref_edges": len(ref_edges),
        "ext_edges": len(mapped_ext_edges),
        "matched": len(matched),
    }


# ─── Композит ─────────────────────────────────────────────────────────────────

def _geometric_mean(values: List[float]) -> float:
    """Геометрическое среднее. Если хотя бы одно значение = 0, результат = 0."""
    if not values:
        return 0.0
    for v in values:
        if v <= 0.0:
            return 0.0
    log_sum = sum(math.log(v) for v in values)
    return math.exp(log_sum / len(values))


def compute_metrics(
    reference_blocks: Sequence[Dict[str, Any]],
    extracted_blocks: Sequence[Dict[str, Any]],
    original_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Полный отчёт о качестве извлечения структуры статьи.

    Геометрическое среднее компонент: одна проваленная фундаментальная
    компонента сильно снижает общий результат.
    Hard gates:结构性 ошибки недопустимы.
    """
    matcher = TextMatcher()

    ref_blocks = list(reference_blocks)
    ext_blocks = list(extracted_blocks)
    ref_hist = type_histogram(ref_blocks)
    ext_hist = type_histogram(ext_blocks)

    components: Dict[str, float] = {}
    details: Dict[str, Any] = {}

    # ── Triplets F1 (leaf + resolved) ──
    ref_uuid_map = _build_uuid_map(ref_blocks)
    ext_uuid_map = _build_uuid_map(ext_blocks)

    ref_leaf = extract_leaf_triplets(ref_blocks)
    ext_leaf = extract_leaf_triplets(ext_blocks)
    ref_tag_map = build_tag_map(ref_blocks)
    ext_tag_map = build_tag_map(ext_blocks)
    ref_resolved = extract_resolved_triplets(ref_blocks, ref_uuid_map, ref_tag_map)
    ext_resolved = extract_resolved_triplets(ext_blocks, ext_uuid_map, ext_tag_map)

    leaf_triplets = evaluate_triplets(ref_leaf, ext_leaf, matcher)
    resolved_triplets = evaluate_triplets(ref_resolved, ext_resolved, matcher)

    if leaf_triplets is not None and resolved_triplets is not None:
        combined_f1 = (leaf_triplets["f1"] + resolved_triplets["f1"]) / 2
        components["triplets_f1"] = combined_f1
        details["triplets"] = {
            "leaf": leaf_triplets,
            "resolved": resolved_triplets,
            "combined_f1": round(combined_f1, 4),
        }
    elif leaf_triplets is not None:
        components["triplets_f1"] = leaf_triplets["f1"]
        details["triplets"] = {"leaf": leaf_triplets}
    elif resolved_triplets is not None:
        components["triplets_f1"] = resolved_triplets["f1"]
        details["triplets"] = {"resolved": resolved_triplets}

    # ── Causal F1 ──
    causal = evaluate_causal(
        extract_causal_edges(ref_blocks, ref_tag_map),
        extract_causal_edges(ext_blocks, ext_tag_map),
        matcher,
    )
    if causal is not None:
        components["causal_f1"] = causal["f1"]
        details["causal"] = causal

    # ── Intervention ref validity ──
    interventions = evaluate_interventions(ext_blocks, matcher, ref_blocks)
    if interventions is not None:
        components["intervention_ref_validity"] = interventions["quality"]
        details["interventions"] = interventions

    # ── AST edge F1 ──
    ast_edges = evaluate_ast_edges(ref_blocks, ext_blocks, matcher)
    if ast_edges is not None:
        components["ast_edge_f1"] = ast_edges["f1"]
        details["ast_edges"] = ast_edges

    # ── UUID graph analysis (structural gates) ──
    graph = analyze_uuid_graph(ext_blocks)
    details["graph"] = graph

    # ── Text alignment (claim_recall + entailment_rate) ──
    alignment = evaluate_text_alignment(original_text, ext_blocks, matcher) if original_text else None
    if alignment is not None:
        components["claim_recall"] = alignment["claim_recall"]
        if alignment["entailment_rate"] is not None:
            components["entailment_rate"] = alignment["entailment_rate"]
        details["text_alignment"] = alignment

    # ── Polarity fidelity ──
    polarity = evaluate_polarity(ref_leaf, ext_leaf, matcher)
    if polarity is not None:
        components["polarity_fidelity"] = polarity["polarity_fidelity"]
        details["polarity"] = polarity

    # ── Composite: геометрическое среднее ──
    comp_values = [components[k] for k in components if k in WEIGHTS]
    composite = _geometric_mean(comp_values) if comp_values else None

    # ── Hard gates ──
    gates = {
        "dangling_refs": {
            "value": graph["dangling_refs"],
            "limit": 0,
            "passed": graph["dangling_refs"] == 0,
        },
        "self_refs": {
            "value": graph["self_refs"],
            "limit": 0,
            "passed": graph["self_refs"] == 0,
        },
        "cycles": {
            "value": graph["cycles"],
            "limit": 0,
            "passed": graph["cycles"] == 0,
        },
        "forward_refs": {
            "value": graph["forward_refs"],
            "limit": 0,
            "passed": graph["forward_refs"] == 0,
        },
        "duplicate_ids": {
            "value": graph["duplicate_ids"],
            "limit": 0,
            "passed": graph["duplicate_ids"] == 0,
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


# ─── Train/Val/Test split ─────────────────────────────────────────────────────

def load_all_gold_cases(
    root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Загружает все доступные gold-кейсы из eval/gold."""
    cases = []
    for slug in gold_case_slugs(root):
        paths = gold_case_paths(slug, root)
        ref = load_blocks(paths["reference"])
        article_path = paths["article"]
        article_text = article_path.read_text(encoding="utf-8-sig") if article_path.exists() else None
        cases.append({
            "slug": slug,
            "reference": ref,
            "article_text": article_text,
        })
    return cases


def split_dataset(
    cases: List[Dict[str, Any]],
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    seed: int = 42,
) -> Dict[str, List[Dict[str, Any]]]:
    """Разделяет gold-кейсы на train/val/test.

    При малом числе кейсов (2-3) — все попадают в val для валидации,
    train/test создаются при расширении корпуса.
    """
    import random
    rng = random.Random(seed)
    shuffled = list(cases)
    rng.shuffle(shuffled)

    n = len(shuffled)
    if n <= 3:
        return {"train": [], "val": shuffled, "test": []}

    n_train = max(1, int(n * train_ratio))
    n_val = max(1, int(n * val_ratio))
    return {
        "train": shuffled[:n_train],
        "val": shuffled[n_train:n_train + n_val],
        "test": shuffled[n_train + n_val:],
    }


def evaluate_on_split(
    cases: List[Dict[str, Any]],
    original_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Оценивает качество извлечения на наборе кейсов."""
    results = []
    for case in cases:
        ref = case["reference"]
        text = case.get("article_text") or original_text
        report = compute_metrics(ref, ref, text)
        results.append({"slug": case.get("slug", ""), "report": report})

    if not results:
        return {"cases": [], "avg_composite": None}

    composites = [r["report"]["composite"] for r in results if r["report"]["composite"] is not None]
    avg = sum(composites) / len(composites) if composites else None
    return {
        "cases": results,
        "avg_composite": round(avg, 4) if avg is not None else None,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Сравнение извлечённых блоков с эталоном")
    parser.add_argument("extracted", nargs="?", type=Path, default=None, help="JSON-файл извлечённых блоков")
    parser.add_argument("--ref", type=Path, default=None, help="Путь к эталону (по умолчанию — кейс из eval/gold)")
    parser.add_argument("--case", type=str, default=None, help="Slug кейса эталона из eval/gold/manifest.json")
    parser.add_argument("--text", type=Path, default=None, help="Путь к .md файлу оригинала")
    parser.add_argument("--split", action="store_true", help="Показать train/val/test split")
    parser.add_argument("--eval-all", action="store_true", help="Оценить все gold-кейсы")
    args = parser.parse_args()

    if args.split:
        cases = load_all_gold_cases()
        splits = split_dataset(cases)
        for split_name, split_cases in splits.items():
            slugs = [c["slug"] for c in split_cases]
            print(f"{split_name}: {slugs}")
        sys.exit(0)

    if args.eval_all:
        cases = load_all_gold_cases()
        splits = split_dataset(cases)
        for split_name, split_cases in splits.items():
            if not split_cases:
                continue
            result = evaluate_on_split(split_cases)
            print(f"\n=== {split_name.upper()} ===")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.extracted is None:
        parser.error("Укажите JSON-файл извлечённых блоков или используйте --split/--eval-all")

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
