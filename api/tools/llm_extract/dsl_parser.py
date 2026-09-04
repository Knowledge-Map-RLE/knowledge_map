"""Парсер собственного DSL извлечения блоков → JSON-структура {blockType, tag, data}.

Синтаксис DSL (построчный, одна строка = один блок):
    B <TYPEKEY> <TAG> | key=value | key=value ...

Пример:
    B T4 B1 | sub=A. russatus | pred=has | obj=higher health span | epi=direct_statement | src=...
    B T57 B9 | param=serum IL-6 | dir=decreased | sig=significant | exp=B8 | grp=[B5] | src=...
    B T58 B20 | src=clusterin | tgt=inflammaging | rel=inhibits | conf=high | ev=...
    B T1 B1 | doi=https://doi.org/10.1126/sciadv.aec9991 | title=... | authors=[Heidi, Bob]

Парсер переводит DSL-строки в словари, идентичные тем, что возвращает
`LLMTripletExtractionService._parse_unified_json`, то есть:
    {"blockType": int, "tag": "{Bn}", "data": {ключ_JSON: значение}}
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.llm_triplet_extraction_prompt_dsl import DSL_TYPEKEY_TO_BLOCKTYPE  # noqa: E402

# Поле-маппинг «короткий DSL-ключ → JSON-поле».
# Заполнено для типов, используемых в минимальном промпте (и расширяемо).
_FIELD_MAP: dict[int, dict[str, str]] = {
    1: {"doi": "doi", "title": "title", "authors": "authors"},
    2: {"sub": "subject", "pred": "predicate", "obj": "object"},
    4: {"sub": "subject", "pred": "predicate", "obj": "object",
        "epi": "epistemicStatus", "src": "source", "ctx": "context",
        "refs": "sourceRefs"},
    7: {"hyp": "hypothesis", "disproof": "disproofExplanation"},
    14: {"name": "experimentName", "type": "experimentType",
         "grp": "experimentalPairs", "ctrl": "controlPairs",
         "steps": "steps", "findings": "findings", "duration": "duration",
         "src": "source"},
    18: {"type": "interventionType", "mechanism": "mechanism", "target": "target",
         "dosage": "dosage", "regimen": "dosageRegimen", "route": "route",
         "duration": "duration", "purpose": "purpose", "src": "source"},
    19: {"species": "species", "timeline": "timeline", "conditions": "conditions"},
    22: {"sub": "subject", "pred": "predicate", "obj": "object",
         "aliases": "aliases", "canonical": "canonicalName"},
    23: {"term": "term", "definition": "definition"},
    27: {"p": "pValue"},
    37: {"stat": "statProcessing", "expect": "expectationsComparison",
         "p": "pValue", "eff": "effectSize", "ci": "confidenceInterval",
         "n": "sampleSize", "src": "source"},
    38: {"sub": "claimSubject", "pred": "claimPredicate", "obj": "claimObject",
         "conf": "confidenceNotes", "neg": "isNegated", "src": "source"},
    39: {"limitations": "limitations", "type": "type", "src": "source"},
    40: {"finding": "finding", "context": "context", "src": "source"},
    44: {"novelty": "novelty", "src": "source"},
    46: {"future": "futureResearch", "src": "source"},
    47: {"references": "references", "src": "source"},
    51: {"funding": "funding", "src": "source"},
    54: {"sub": "subject", "pred": "predicate", "obj": "object", "src": "source"},
    55: {"name": "groupName", "n": "n", "cond": "conditions", "purpose": "purpose"},
    56: {"name": "stepName", "details": "details", "duration": "duration",
         "src": "source"},
    57: {"param": "parameter", "dir": "direction", "sig": "significance",
         "detail": "detail", "figure": "figureRef", "exp": "experimentRef",
         "grp": "groupRefs", "interv": "interventionRef",
         "cond": "conditionRef", "stat": "statisticRefs",
         "outc": "outcomeClass", "src": "source"},
    58: {"src": "source", "tgt": "target", "srcRef": "sourceRef",
         "tgtRef": "targetRef", "rel": "relationType", "conf": "confidence",
         "ev": "evidence"},
    59: {"earlier": "earlier", "later": "later", "rel": "relationType"},
}

# Поля, значения которых — массив тегов/строк (преобразуются из [..] в JSON-список).
_ARRAY_FIELDS: set[int] = set()
for _bt, _fm in _FIELD_MAP.items():
    for _k, _v in _fm.items():
        if _v in ("authors", "aliases", "sourceRefs", "experimentalPairs",
                  "controlPairs", "steps", "findings", "groupRefs",
                  "statisticRefs"):
            _ARRAY_FIELDS.add((_bt, _v))

_BOOL_FIELDS = {(38, "isNegated")}

# Числовые поля: значение приводится к int/float, если это возможно.
_NUMERIC_FIELDS = {
    (55, "n"), (27, "pValue"), (37, "pValue"), (37, "effectSize"),
    (37, "sampleSize"),
}

# Тип-ключи, для которых маппинг 'B' строки распознаётся
_DSL_LINE_RE = re.compile(r"^\s*B\s+(\w+)\s+(B\d+)\s*(?:\|\s*(.*))?$", re.IGNORECASE)


def _split_fields(text: str) -> List[str]:
    """Делит строку по |, но не внутри [...] (списки)."""
    out: List[str] = []
    cur: List[str] = []
    depth = 0
    for ch in (text or ""):
        if ch == "[":
            depth += 1
            cur.append(ch)
        elif ch == "]":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == "|" and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return out


def _parse_value(raw: str, block_type: int, json_field: str) -> Any:
    raw = raw.strip()
    if not raw:
        return None

    # Логические поля
    if (block_type, json_field) in _BOOL_FIELDS:
        return raw.lower() in ("true", "1", "yes")

    # Числовые поля
    if (block_type, json_field) in _NUMERIC_FIELDS:
        try:
            if re.fullmatch(r"-?\d+", raw):
                return int(raw)
            return float(raw)
        except ValueError:
            pass

    # Массив-поля
    if (block_type, json_field) in _ARRAY_FIELDS:
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1]
            items = [x.strip() for x in inner.split(",") if x.strip()]
        else:
            items = [x.strip() for x in raw.split(",") if x.strip()]
        return [_tag_or_str(x) for x in items]

    # Ссылка-тег или число
    return _tag_or_str(raw)


def _tag_or_str(value: str) -> Any:
    if re.fullmatch(r"B\d+", value):
        return "{" + value + "}"
    return value


def _nested_pairs(value: str) -> list[dict[str, Any]]:
    """Переводит 'B5' или '[{B5}]' в experimentalPairs/controlPairs формат."""
    pairs = []
    raw = value
    if raw.startswith("["):
        raw = raw[1:-1]
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        mat = re.fullmatch(r"(?:grp:)?(B\d+)", item)
        if mat:
            pairs.append({"groupRef": "{" + mat.group(1) + "}"})
    return pairs


def parse_dsl_text(generated_text: str) -> List[dict[str, Any]]:
    """Разбирает полный вывод модели в DSL-формате в список {blockType, tag, data}."""
    blocks: List[dict[str, Any]] = []
    for line in (generated_text or "").splitlines():
        line = line.rstrip("\r")
        if not line.strip():
            continue
        if line.lstrip().startswith(("#", "//", "/*", "--", "B ", "B\t")):
            # B-строки обрабатываются ниже; комментарии пропускаем
            pass
        m = _DSL_LINE_RE.match(line)
        if not m:
            # не DSL-строка (проза/комментарий) — пропускаем
            continue
        type_key_raw, tag_raw, fields_raw = m.group(1), m.group(2), m.group(3)
        type_key = type_key_raw.upper()
        block_type = DSL_TYPEKEY_TO_BLOCKTYPE.get(type_key)
        if block_type is None:
            continue

        data: dict[str, Any] = {}
        fm = _FIELD_MAP.get(block_type, {})
        for segment in _split_fields(fields_raw or ""):
            if "=" not in segment:
                continue
            key, _, val = segment.partition("=")
            key = key.strip().lower()
            val = val.strip()
            if not key or not val:
                continue
            json_field = fm.get(key)
            if json_field is None:
                continue
            if json_field in ("experimentalPairs", "controlPairs"):
                data[json_field] = _nested_pairs(val)
            else:
                parsed = _parse_value(val, block_type, json_field)
                if parsed is not None:
                    data[json_field] = parsed

        blocks.append({
            "blockType": block_type,
            "tag": "{" + tag_raw + "}",
            "data": data,
        })
    return blocks
