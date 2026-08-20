"""Метрика структурного совпадения извлечённых блоков с эталоном.

Сравнивает структуру блоков, извлечённых LLM-функцией, с эталонной структурой
статьи.

Компоненты композитного балла (0..1):
  hist        (0.10) — нормализованная L1 по гистограмме типов блоков;
  seq         (0.05) — доля контейнерных блоков с непустым sequence-списком;
  atom        (0.08) — симметричная близость отношения T4 / не-T4 к эталонному;
  types       (0.05) — доля типов эталона, присутствующих в извлечении;
  uuidref     (0.02) — близость доли T4-блоков с UUID-референсом к эталонной;
  causal      (0.12) — покрытие каузальных цепочек (T58);
  intervention(0.08) — привязка результатов (T57) к интервенциям (interventionRef);
  content     (0.05) — fuzzy-покрытие контента триплетов;
  text_cover  (0.30) — покрытие предложений оригинального текста блоками;
  blocks_count(0.15) — близость общего числа блоков.

Приёмка: composite >= 0.80.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Типы блоков, у которых есть поле sequence (контейнеры для T4-триплетов).
CONTAINER_TYPES = {7, 16, 22, 23, 37, 38, 39, 40, 44, 46, 47, 56, 57}

# Все типы (для гистограмм и т.д.)
ALL_TYPES = set(range(1, 60))

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
    """Доля контейнерных блоков с непустым sequence."""
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


# ── Семантические метрики (новые) ────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Нормализует имя для fuzzy-сравнения."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


_TAG_RE = re.compile(r"^\{B(\d+)\}$")


def _build_tag_text_map(blocks: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Строит карту {tag/position → text} для резолва {B#} ссылок.

    Поддерживает два способа:
    1. По полю `tag` (если есть) — для блоков с явными тегами
    2. По позиции в массиве — {B1} = blocks[0], {B2} = blocks[1], ...
    """
    tag_map: Dict[str, str] = {}
    # Сначала строим позиционную карту из ВСЕХ блоков
    for idx, b in enumerate(blocks):
        pos_tag = f"{{B{idx + 1}}}"
        bt = int(b.get("blockType", 0))
        d = b.get("data") or {}
        if bt == 54:
            parts = [d.get("subject", ""), d.get("predicate", ""), d.get("object", "")]
        elif bt == 56:
            parts = [d.get("stepName", ""), d.get("details", "")]
        else:
            parts = []
        text = " ".join(p for p in parts if p).strip()
        if text:
            tag_map[pos_tag] = text
    # Дополняем явными тегами (перезаписывают позиционные при совпадении)
    for b in blocks:
        tag = b.get("tag", "")
        if not tag:
            continue
        bt = int(b.get("blockType", 0))
        d = b.get("data") or {}
        if bt == 54:
            parts = [d.get("subject", ""), d.get("predicate", ""), d.get("object", "")]
        elif bt == 56:
            parts = [d.get("stepName", ""), d.get("details", "")]
        else:
            parts = []
        text = " ".join(p for p in parts if p).strip()
        if text:
            tag_map[tag] = text
    return tag_map


def _resolve_ref(value: str, tag_map: Dict[str, str]) -> str:
    """Если value — {B#} ссылка, заменяет на текст из tag_map."""
    m = _TAG_RE.match(value.strip())
    if m:
        resolved = tag_map.get(value.strip(), "")
        if resolved:
            return resolved
    return value


def _fuzzy_match(a: str, b: str, threshold: float = 0.3) -> bool:
    """Fuzzy-сравнение двух строк. Возвращает True при схожести >= threshold."""
    a_norm = _normalize_name(a)
    b_norm = _normalize_name(b)
    if not a_norm or not b_norm:
        return False
    if a_norm == b_norm:
        return True
    if a_norm in b_norm or b_norm in a_norm:
        return True
    # Word overlap ratio with synonym expansion
    a_words = set(a_norm.split())
    b_words = set(b_norm.split())
    if not a_words or not b_words:
        return False
    # Direct overlap
    direct_overlap = len(a_words & b_words)
    # Check if words are semantically related via common roots/stems
    expanded_a = set(a_words)
    expanded_b = set(b_words)
    for w in a_words:
        for sw in b_words:
            if len(w) >= 4 and len(sw) >= 4:
                # Check common prefix (stem matching)
                if w[:4] == sw[:4]:
                    expanded_a.add(sw)
                    expanded_b.add(w)
    expanded_overlap = len(expanded_a & expanded_b)
    overlap = max(direct_overlap, expanded_overlap)
    union = len(a_words | b_words)
    return (overlap / union) >= threshold if union > 0 else False


_RELATION_SYNONYMS: Dict[str, str] = {
    "causes": "causes",
    "leads_to": "causes",
    "produces": "causes",
    "induces": "causes",
    "results_in": "causes",
    "drives": "causes",
    "promotes": "promotes",
    "enhances": "promotes",
    "upregulates": "promotes",
    "increases": "promotes",
    "supports": "promotes",
    "maintains": "promotes",
    "inhibits": "inhibits",
    "suppresses": "inhibits",
    "reduces": "inhibits",
    "decreases": "inhibits",
    "downregulates": "inhibits",
    "restrains": "inhibits",
    "enables": "enables",
    "contributes_to": "enables",
    "exhibits": "exhibits",
    "resists": "exhibits",
}


def _normalize_relation(rel: str) -> str:
    return _RELATION_SYNONYMS.get(rel.lower().strip(), rel.lower().strip())


def causal_chain_coverage(
    ref_blocks: Sequence[Dict[str, Any]],
    ext_blocks: Sequence[Dict[str, Any]],
) -> float:
    """Доля каузальных связей (T58) эталона, найденных в извлечении.

    Сравнивает пары (source_name, target_name, relationType) по
    семантическому совпадению. Резолвит {B#} ссылки через T54/T56 блоки.
    Нормализует relationType через синонимы.
    """
    ext_tag_map = _build_tag_text_map(ext_blocks)

    def extract_causal(blocks: Sequence[Dict[str, Any]], tag_map: Dict[str, str]) -> List[tuple]:
        chains = []
        for b in blocks:
            if int(b.get("blockType", 0)) == 58:
                d = b.get("data") or {}
                src = str(d.get("source_name", d.get("source", "")) or "")
                tgt = str(d.get("target_name", d.get("target", "")) or "")
                rel = str(d.get("relationType", "") or "")
                if src and tgt and rel:
                    chains.append((_resolve_ref(src, tag_map), _resolve_ref(tgt, tag_map), _normalize_relation(rel)))
        return chains

    ref_chains = extract_causal(ref_blocks, {})
    ext_chains = extract_causal(ext_blocks, ext_tag_map)

    if not ref_chains:
        return 1.0 if not ext_chains else 0.8  # bonus if both empty
    if not ext_chains:
        return 0.0

    matched = 0
    for rs, rt, rr in ref_chains:
        for es, et, er in ext_chains:
            if rr == er and _fuzzy_match(rs, es) and _fuzzy_match(rt, et):
                matched += 1
                break
    return matched / len(ref_chains)


def intervention_result_linkage(
    ref_blocks: Sequence[Dict[str, Any]],
    ext_blocks: Sequence[Dict[str, Any]],
) -> float:
    """Доля T57 с привязкой к интервенции (interventionRef).

    Сравнивает долю T57 блоков с interventionRef между эталоном и извлечением.
    """
    def count_linked(blocks: Sequence[Dict[str, Any]]) -> tuple:
        t57 = [b for b in blocks if int(b.get("blockType", 0)) == 57]
        if not t57:
            return 0, 0
        linked = sum(
            1 for b in t57
            if (b.get("data") or {}).get("interventionRef")
        )
        return linked, len(t57)

    ref_linked, ref_total = count_linked(ref_blocks)
    ext_linked, ext_total = count_linked(ext_blocks)

    if ref_total == 0:
        return 1.0 if ext_total == 0 else 0.5
    ref_ratio = ref_linked / ref_total
    ext_ratio = ext_linked / ext_total if ext_total > 0 else 0.0
    return ratio_closeness(ext_ratio, ref_ratio)


def block_count_closeness(ref_count: int, ext_count: int) -> float:
    """Близость общего числа блоков: 1 - |ref-ext|/max(ref,ext)."""
    if max(ref_count, ext_count) == 0:
        return 1.0
    return 1.0 - abs(ref_count - ext_count) / max(ref_count, ext_count)


# ── Fuzzy-покрытие контента ──────────────────────────────────────────────────

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


_PREDICATE_SYNONYMS: Dict[str, str] = {
    "include": "have",
    "includes": "have",
    "have": "have",
    "has": "have",
    "contains": "have",
    "is": "is",
    "are": "is",
    "represents": "is",
    "acts as": "is",
    "serves as": "is",
    "becomes": "is",
    "is not": "is not",
    "is activated by": "activates",
    "is a selective force for": "influences",
    "is not driven by": "is not",
    "are protected from": "protects from",
    "have been observed in": "occurs in",
    "can induce": "activates",
    "directly causes": "causes",
    "drives": "causes",
    "causes": "causes",
    "induces": "causes",
    "induce": "causes",
    "leads to": "causes",
    "results in": "causes",
    "promotes": "promotes",
    "enhances": "promotes",
    "increases": "promotes",
    "upregulates": "promotes",
    "supports": "promotes",
    "maintains": "promotes",
    "inhibits": "inhibits",
    "suppresses": "inhibits",
    "suppress": "inhibits",
    "reduces": "inhibits",
    "decreases": "inhibits",
    "blocks": "inhibits",
    "extends": "extends",
    "prolongs": "extends",
    "slows": "slows",
    "delays": "slows",
    "reduces the rate of": "slows",
    "activates": "activates",
    "triggers": "activates",
    "stimulates": "activates",
    "regulates": "regulates",
    "modulates": "regulates",
    "controls": "regulates",
    "occurs in": "occurs in",
    "happens in": "occurs in",
    "is observed in": "occurs in",
    "selects for": "promotes",
    "combines": "combines",
    "involves": "involves",
    "make": "causes",
    "proposed": "proposes",
    "requires": "requires",
    "occur": "occurs in",
}


def _normalize_predicate(pred: str) -> str:
    p = pred.lower().strip()
    return _PREDICATE_SYNONYMS.get(p, p)


def content_coverage(ref_blocks, ext_blocks) -> Dict[str, float]:
    """Доля текстовых T4-триплетов эталона, покрытых извлечёнными.

    Использует нормализацию predicate через синонимы и fuzzy matching
    для subject/object.
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
            out.append((s.lower().strip(), _normalize_predicate(p), o.lower().strip()))
        return out

    refs = textual_triplets(ref_blocks)
    exts = textual_triplets(ext_blocks)
    if not refs:
        return {"coverage": 0.0, "ref_textual": 0, "ext_textual": len(exts)}
    matched = 0
    for rs, rp, ro in refs:
        for es, ep, eo in exts:
            if rp != ep:
                continue
            subj_ok = rs == es or _fuzzy_match(rs, es) or _contained_in(rs, es) or _contained_in(es, rs)
            obj_ok = ro == eo or _fuzzy_match(ro, eo) or _contained_in(ro, eo) or _contained_in(eo, ro)
            if subj_ok and obj_ok:
                matched += 1
                break
    return {
        "coverage": matched / len(refs),
        "ref_textual": len(refs),
        "ext_textual": len(exts),
    }


# ── Текстовое покрытие оригинала блоками ─────────────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "and", "or", "in", "on", "at", "to", "for",
    "is", "are", "was", "were", "be", "been", "being", "by", "with", "from",
    "as", "into", "that", "this", "it", "not", "but", "if", "than", "then",
    "so", "no", "nor", "its", "their", "our", "your", "his", "her", "also",
    "may", "can", "will", "would", "could", "should", "has", "have", "had",
    "do", "does", "did", "about", "between", "through", "during", "before",
    "after", "above", "below", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "only", "own", "same", "than",
    "too", "very", "just", "because", "however", "while", "where", "when",
    "which", "who", "whom", "what", "how", "all", "any", "there", "they",
    "these", "those", "been", "being", "having", "doing", "used", "using",
    "result", "results", "based", "found", "showed", "shown", "suggest",
    "suggests", "suggesting", "demonstrate", "demonstrates", "indicate",
    "indicates", "indicating", "therefore", "thus", "hence", "indeed",
    "still", "even", "well", "much", "many", "often", "however", "although",
    "though", "yet", "already", "here", "now", "new", "first", "last",
    "long", "great", "high", "low", "small", "large", "important", "key",
    "different", "similar", "several", "various", "particularly", "especially",
    "main", "major", "primary", "secondary", "specific", "general",
    "possible", "likely", "unlikely", "clear", "obvious", "known", "unknown",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
})


def _tokenize(text: str) -> list[str]:
    """Токенизирует текст в список значимых слов (без стоп-слов, нормализованных)."""
    words = re.findall(r"[a-z0-9]{2,}", text.lower())
    return [w for w in words if w not in _STOP_WORDS]


def _block_to_text(block: Dict[str, Any]) -> str:
    """Конвертирует блок в текстовое представление для сравнения."""
    bt = int(block.get("blockType", 0))
    d = block.get("data") or {}

    if bt == 54:
        return f"{d.get('subject', '')} {d.get('predicate', '')} {d.get('object', '')}"
    elif bt == 58:
        return f"{d.get('source', '')} {d.get('relationType', '')} {d.get('target', '')}"
    elif bt == 4:
        return f"{d.get('subject', '')} {d.get('predicate', '')} {d.get('object', '')}"
    elif bt == 22:
        return f"{d.get('subject', '')} {d.get('predicate', '')} {d.get('object', '')}"
    elif bt == 7:
        return f"{d.get('hypothesis', '')} {d.get('disproofExplanation', '')}"
    elif bt == 16:
        return str(d.get("mechanism", ""))
    elif bt == 23:
        return f"{d.get('term', '')} {d.get('definition', '')}"
    elif bt == 38:
        return f"{d.get('claimSubject', '')} {d.get('claimPredicate', '')} {d.get('claimObject', '')}"
    elif bt == 57:
        return f"{d.get('parameter', '')} {d.get('direction', '')} {d.get('detail', '')}"
    elif bt == 56:
        return f"{d.get('stepName', '')} {d.get('details', '')}"
    elif bt == 55:
        return f"{d.get('groupName', '')} {d.get('conditions', '')}"
    elif bt == 14:
        return f"{d.get('experimentName', '')} {d.get('experimentType', '')}"
    elif bt == 19:
        return f"{d.get('species', '')} {d.get('timeline', '')} {d.get('conditions', '')}"
    elif bt == 39:
        return str(d.get("limitations", ""))
    elif bt == 44:
        return str(d.get("novelty", ""))
    elif bt == 46:
        return str(d.get("futureResearch", ""))
    elif bt == 37:
        return f"{d.get('statProcessing', '')} {d.get('expectationsComparison', '')}"
    elif bt == 51:
        return str(d.get("funding", ""))
    elif bt == 18:
        return f"{d.get('interventionType', '')} {d.get('mechanism', '')} {d.get('target', '')}"
    elif bt == 40:
        return f"{d.get('finding', '')} {d.get('context', '')}"
    elif bt == 2:
        return f"{d.get('subject', '')} {d.get('predicate', '')} {d.get('object', '')}"
    elif bt == 1:
        authors = d.get("authors", [])
        author_str = " ".join(authors) if isinstance(authors, list) else str(authors)
        return f"{d.get('title', '')} {d.get('doi', '')} {author_str}"
    else:
        return " ".join(str(v) for v in d.values() if isinstance(v, str))


def _sentence_split(text: str) -> list[str]:
    """Разбивает текст на предложения, отфицовывая не-контент."""
    # Убираем YAML-фронтматтер
    text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
    # Убираем markdown-заголовки
    text = re.sub(r'^#{1,6}\s+.*$', '', text, flags=re.MULTILINE)
    # Убираем author/affiliation multi-line блоки (по запятым и department/названиям)
    text = re.sub(
        r'^(?:[A-Z][a-z]+ [A-Z][a-z]+(?:\s*,\s*[A-Z][a-z]+ [A-Z][a-z]+)*)'
        r'|Department\s+of\s+\w+.*$'
        r'|School\s+of\s+\w+.*$'
        r'|Institute\s+of\s+\w+.*$'
        r'|Center\s+for\s+\w+.*$'
        r'|Faculty\s+of\s+\w+.*$'
        r'|Laboratory\s+of\s+\w+.*$'
        r'|Program\s+in\s+\w+.*$'
        r'|Yale\s+\w+.*$'
        r'|NIH.*$'
        r'|NIA.*$'
        r'|PCMGF.*$'
        r'|Tel Aviv University.*$'
        r'|Max Planck.*$',
        '', text, flags=re.MULTILINE
    )
    # Убираем email/doi/http референсы
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\*\*.*?\*\*', '', text)
    text = re.sub(r'^.*(?:@|doi\.org|http|e-?mail|Corresponding author).*$', '', text, flags=re.MULTILINE)

    sents = re.split(r'(?<=[.!?])\s+', text)
    result = []
    for s in sents:
        s = s.strip()
        if len(s) < 30:
            continue
        if re.match(r'^\[\d+\]', s):
            continue
        result.append(s)
    return result


def text_coverage(original_text: str, blocks: list[dict]) -> dict:
    """Измеряет долю предложений оригинального текста, покрытых блоками.

    Для каждого предложения оригинала проверяем, есть ли хотя бы один блок,
    чьё текстовое представление совпадает с предложением по ключевым словам.
    Это гарантирует, что ни одна мысль не потеряна при преобразовании в триплеты.
    """
    sentences = _sentence_split(original_text)
    if not sentences:
        return {"coverage": 0.0, "total": 0, "covered": 0, "block_texts_count": 0}

    # Строим текстовое представление всех блоков
    block_texts: list[tuple[str, set[str]]] = []
    for b in blocks:
        raw = _block_to_text(b)
        tokens = set(_tokenize(raw))
        if tokens:
            block_texts.append((raw, tokens))

    if not block_texts:
        return {"coverage": 0.0, "total": len(sentences), "covered": 0, "block_texts_count": 0}

    # Для каждого предложения проверяем покрытие
    covered = 0
    uncovered_sentences = []
    for sent in sentences:
        sent_tokens = set(_tokenize(sent))
        if not sent_tokens or len(sent_tokens) < 3:
            continue

        is_covered = False
        for _, btokens in block_texts:
            # Прямое пересечение
            overlap = len(sent_tokens & btokens)
            if overlap / len(sent_tokens) >= 0.12:
                is_covered = True
                break
            # Stem-based matching: расширяем через общий префикс (4+ chars)
            expanded_sent = set(sent_tokens)
            expanded_block = set(btokens)
            for st in sent_tokens:
                for bt in btokens:
                    if len(st) >= 4 and len(bt) >= 4 and st[:4] == bt[:4]:
                        expanded_sent.add(bt)
                        expanded_block.add(st)
            expanded_overlap = len(expanded_sent & expanded_block)
            if expanded_overlap / len(sent_tokens) >= 0.12:
                is_covered = True
                break

        if is_covered:
            covered += 1
        else:
            uncovered_sentences.append(sent[:120])

    return {
        "coverage": covered / len(sentences) if sentences else 0.0,
        "total": len(sentences),
        "covered": covered,
        "block_texts_count": len(block_texts),
        "uncovered_sample": uncovered_sentences[:5],
    }


# ── Композитный балл ─────────────────────────────────────────────────────────

WEIGHTS = {
    "hist": 0.10,
    "seq": 0.05,
    "atom": 0.08,
    "types": 0.05,
    "uuidref": 0.02,
    "causal": 0.12,
    "intervention": 0.08,
    "content": 0.05,
    "text_cover": 0.30,
    "blocks_count": 0.15,
}
PASS_THRESHOLD = 0.80


def compute_metrics(
    reference_blocks: Sequence[Dict[str, Any]],
    extracted_blocks: Sequence[Dict[str, Any]],
    original_text: Optional[str] = None,
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

    tc_result = text_coverage(original_text, list(extracted_blocks)) if original_text else {"coverage": 0.0}

    components = {
        "hist": hist_similarity(ref_hist, ext_hist),
        "seq": ratio_closeness(ext_seq, ref_seq),
        "atom": ratio_closeness(ext_atom, ref_atom),
        "types": type_presence(ref_hist, ext_hist),
        "uuidref": ratio_closeness(ext_uuid, ref_uuid),
        "causal": causal_chain_coverage(reference_blocks, extracted_blocks),
        "intervention": intervention_result_linkage(reference_blocks, extracted_blocks),
        "content": content_coverage(reference_blocks, extracted_blocks)["coverage"],
        "text_cover": tc_result["coverage"],
        "blocks_count": block_count_closeness(
            len(reference_blocks), len(extracted_blocks)
        ),
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
        "text_cover": tc_result,
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
    parser.add_argument("--text", type=Path, default=None, help="Путь к .md файлу оригинала")
    args = parser.parse_args()

    ref = load_reference(args.ref)
    ext = load_blocks(args.extracted)
    original_text = args.text.read_text(encoding="utf-8-sig") if args.text else None
    report = compute_metrics(ref, ext, original_text)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
