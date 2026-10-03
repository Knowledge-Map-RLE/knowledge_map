"""Единый парсер DSL структурных строк — `B T<код> B<тег> | поле=значение | ... | unit=S<n>`.

Канонический источник полей — `knowledge_contracts.block_dsl.DSL_FIELDS`
(короткий DSL-ключ → JSON-поле блока, kind). Парсер строгий: неизвестный
код/поле или битая строка — ошибка, чтобы прямая типизация никогда не была
молча потерянной (lossy).

Выход парсера — список строк:
``[{"blockType": BlockType.XXX, "tag": "B5", "data": {...}}]``
где `data` содержит JSON-поля блока (по kind) плюс служебные `tag` и `unit`.
Дальнейшая материализация (`provenance`, `source`, `instanceId`, `order`)
происходит в pipeline.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from knowledge_contracts.block_dsl import DSL_FIELDS, FieldSpec, required_dsl_fields
from knowledge_contracts.block_types import LEGACY_INT_TO_KEY
from knowledge_contracts.dsl_tags import sanitize_value, split_list_value
from knowledge_contracts.validation import ValidationError, require

_CODE_MAJOR_RE = re.compile(r"^\s*B\s*T(?P<code>\d{1,2})\s*B(?P<tag>\d{1,6})(?:\s*\|\s*(?P<fields>.*))?\s*$", re.IGNORECASE)
_TAG_MAJOR_RE = re.compile(r"^\s*B(?P<tag>\d{1,6})\s*T(?P<code>\d{1,2})(?:\s*\|\s*(?P<fields>.*))?\s*$", re.IGNORECASE)
# LLM иногда нумерует строки: "B1 T1 B1 | ..." вместо "B T1 B1 | ...".
# Лидирующий индекс отбрасывается, остальное разбирается как код-мажор.
_INDEX_MAJOR_RE = re.compile(r"^\s*B(?P<index>\d{1,6})\s*T(?P<code>\d{1,2})\s*B(?P<tag>\d{1,6})(?:\s*\|\s*(?P<fields>.*))?\s*$", re.IGNORECASE)
_UNIT_RE = re.compile(r"^S([1-9][0-9]*)$")
_TAG_RE = re.compile(r"\bB(\d{1,6})\b")
_FENCE_RE = re.compile(r"^\s*(```|~~~|dsl\b)")

_COMMENT_STARTS = ("#", "//", "--", "/*", "*", "=")
_RIGHT_ASSERT = "<≤>≥"


def escape_dsl_value(value: str) -> str:
    """Encode structural text without losing DSL separators or line breaks."""
    return (str(value).replace("\\", "\\\\").replace("\r", "\\r")
            .replace("\n", "\\n").replace("|", "\\|"))


def _unescape_dsl_value(value: str) -> str:
    """Decode only the escape sequences defined by :func:`escape_dsl_value`."""
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            escaped = value[index + 1]
            if escaped == "n":
                result.append("\n")
                index += 2
                continue
            if escaped == "r":
                result.append("\r")
                index += 2
                continue
            if escaped in ("|", "\\"):
                result.append(escaped)
                index += 2
                continue
        result.append(char)
        index += 1
    return "".join(result)


def _match_line(line: str):
    """Заголовок DSL-строки: код-мажор ``B T<code> B<tag>``, тег-мажор
    ``B<tag> T<code>`` или префикс-индекс ``B<index> T<code> B<tag>``.

    Все три реальные формы встречаются у LLM; лидирующий индекс отбрасывается,
    остальное нормализуется в код-мажор. Проверка идёт в порядке убывания
    специфичности, чтобы тег-мажор ``B3 T4`` не перехватывался индекс-мажором.
    """
    match = _CODE_MAJOR_RE.match(line)
    if match:
        return match
    match = _TAG_MAJOR_RE.match(line)
    if match:
        return match
    match = _INDEX_MAJOR_RE.match(line)
    if match:
        return match
    return None


def _split_segments(fields_text: str) -> List[str]:
    """Разделяет содержимое строки по ``|``.

    Скобки экранируют разделитель только у значения, которое начинается
    непосредственно после ``=``: ``grp=[B1|B2]``.  Квадратные скобки —
    обычный символ в текстовых полях (например, незавершённая citation
    ``obj=multimorbidity [35``), поэтому они не должны скрывать ``unit=``.
    """
    segments: List[str] = []
    current: List[str] = []
    depth = 0
    escaped = False
    for char in fields_text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        current_field = "".join(current).strip()
        opens_list_value = bool(re.fullmatch(r"[^=|]+\s*=\s*", current_field))
        if char == "[" and (depth > 0 or opens_list_value):
            depth += 1
            current.append(char)
        elif char == "]":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "|" and depth == 0:
            segments.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        segments.append("".join(current))
    return [s.strip() for s in segments if s.strip()]


def _coerce_int(raw: str) -> int:
    return int(str(raw).strip())


def _coerce_float(raw: str) -> Any:
    value = str(raw).strip()
    comparator = value[:1] if value[:1] in _RIGHT_ASSERT else ""
    stripped = value[len(comparator):].strip()
    try:
        numeric = float(stripped)
        return value if comparator else numeric
    except ValueError:
        return value


def _coerce_bool(raw: str) -> bool:
    value = str(raw).strip().lower()
    require(value in ("true", "false", "1", "0", "yes", "no"),
            f"Invalid boolean value {raw!r}")
    return value in ("true", "1", "yes")


def _coerce_strs(raw: str) -> List[str]:
    items = split_list_value(raw)
    if items is None:
        candidates = [p.strip() for p in raw.split(",") if p.strip()]
        items = candidates if len(candidates) > 1 else ([candidates[0]] if candidates else [])
    return [sanitize_value(item) for item in items]


def missing_required_fields(row: Dict[str, Any]) -> List[str]:
    """Обязательные поля строки, отсутствие которых валидируется.

    Для ``text`` поле ``content`` восстанавливается детерминированно из
    verbatim-текста unit при материализации, поэтому пропущенным не считается.
    """
    reconstructible = {"content"} if row["blockType"] == "text" else set()
    required = required_dsl_fields(row["blockType"])
    return [f"{dsl_key} (JSON: {json_field})"
            for json_field, dsl_key in required.items()
            if json_field not in reconstructible and not row["data"].get(json_field)]


def _coerce_ref(value: str) -> str:
    value = value.strip()
    if value in ("[]", "{}", "-", "none", "n/a", ""):
        return ""
    tags = _TAG_RE.findall(value)
    require(bool(tags), f"Reference field has no B<tag>: {value!r}")
    return f"B{tags[0]}"


def _coerce_refs(raw: str) -> List[str]:
    raw = raw.strip()
    if raw in ("[]", "{}", "-", "none", "n/a", ""):
        return []
    tags = _TAG_RE.findall(raw)
    require(bool(tags), f"Reference list has no B<tag>: {raw!r}")
    return list(dict.fromkeys(f"B{t}" for t in tags))


def _coerce_ref_groups(raw: str) -> List[List[str]]:
    """Parse alternative B-tag groups, e.g. ``[[B1,B2],[B3]]``."""
    value = raw.strip()
    if value in ("[]", "{}", "-", "none", "n/a", ""):
        return []
    group = r"\[\s*B[0-9]{1,6}(?:\s*,\s*B[0-9]{1,6})*\s*\]"
    require(bool(re.fullmatch(rf"\[\s*(?:{group}(?:\s*,\s*{group})*)?\s*\]", value)),
            f"Alternative reference groups must use [[B1,B2],[B3]] syntax: {raw!r}")
    groups = re.findall(r"\[([^\[\]]+)\]", value[1:-1])
    parsed = []
    for group_value in groups:
        tags = _TAG_RE.findall(group_value)
        require(bool(tags), f"Alternative reference group has no B<tag>: {group_value!r}")
        parsed.append(list(dict.fromkeys(f"B{tag}" for tag in tags)))
    return parsed


def _coerce(value: str, spec: FieldSpec, block_type: str, tag: str, line: int) -> Any:
    kind = spec.kind
    try:
        if kind == "int":
            return _coerce_int(value)
        if kind == "float":
            return _coerce_float(value)
        if kind == "bool":
            return _coerce_bool(value)
        if kind == "strs":
            return _coerce_strs(value)
        if kind == "ref":
            return _coerce_ref(value)
        if kind == "refs":
            return _coerce_refs(value)
        if kind == "ref_groups":
            return _coerce_ref_groups(value)
        return sanitize_value(value)
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 - любой сбой значения = ошибка строки
        raise ValidationError(f"Bad value {value!r} for {block_type}/{spec.json_field} "
                              f"(line {line}, {tag}): {exc}") from exc


def parse_dsl_rows(dsl_text: str, unit_ids: List[str], *,
                   allow_duplicate_tags: bool = False) -> List[Dict[str, Any]]:
    """Разбирает DSL-ответ в структурные строки.

    Args:
        dsl_text: текст DSL (может быть обёрнут в Markdown-фенсы — они пропускаются).
        unit_ids: допустимые source unit id (``"S<n>"``) — обычно все предложения статьи.
        allow_duplicate_tags: permits repeated candidate tags only for targeted-repair
            parsing; the repair validator must select at most one accepted row per tag.

    Returns:
        Список строк: ``[{"blockType", "tag", "data"}]`` (data включает `tag` и `unit`).
    """
    allowed_units = {u.strip().upper() for u in unit_ids}
    rows: List[Dict[str, Any]] = []
    seen_tags: List[str] = []
    for number, raw_line in enumerate((dsl_text or "").splitlines(), 1):
        line = raw_line.strip()
        if not line or _FENCE_RE.match(line) or line.startswith(_COMMENT_STARTS):
            continue
        match = _match_line(line)
        if not match:
            raise ValidationError(
                f"DSL line {number} is not a structural row: {line[:120]!r}")
        code, tag = int(match.group("code")), f"B{int(match.group('tag'))}"
        field_text = match.group("fields")
        require(code in LEGACY_INT_TO_KEY,
                f"Unknown DSL code T{code} (line {number})")
        block_type = LEGACY_INT_TO_KEY[code]
        require(allow_duplicate_tags or tag not in seen_tags,
                f"Duplicate DSL tag {tag} (line {number})")
        seen_tags.append(tag)
        field_map = DSL_FIELDS.get(block_type, {})
        by_short = {short.casefold(): (short, spec) for short, spec in field_map.items()}
        data: Dict[str, Any] = {"tag": tag}
        unit: Optional[str] = None
        segments = _split_segments(field_text or "")
        dsl_keys = set(by_short) | {"unit"}
        for segment in segments:
            key, separator, raw_value = segment.partition("=")
            key, raw_value = key.strip().lower(), _unescape_dsl_value(raw_value.strip())
            if not key or not raw_value:
                continue
            if separator:
                joined_key = re.search(
                    r"(?<!\w)([a-z_][a-z0-9_]*)\s*=",
                    raw_value,
                    re.IGNORECASE,
                )
                if joined_key and joined_key.group(1).casefold() in dsl_keys:
                    raise ValidationError(
                        f"Row {tag} (T{code}) has non-pipe-delimited fields before "
                        f"{joined_key.group(1)}=; separate every DSL field with ` | `"
                    )
            require(key != "tag", f"'tag' key is part of the DSL header (line {number})")
            if key == "unit":
                require(unit is None, f"Duplicate field 'unit' (line {number})")
                unit = raw_value.upper()
                continue
            # Historical DSL may contain model-generated map dependencies.
            # Read and discard them; new map edges come from deterministic rules.
            if key in {"req", "anyreq"}:
                continue
            require(key in by_short or key != "_extra",
                    f"Reserved field {key!r} (line {number})")
            if key not in by_short:
                # Модель иногда добавляет поля вне утверждённого вокабуляра;
                # сохраняем их без потерь, не прерывая обработку всей строки.
                data.setdefault("_extra", {})[key] = sanitize_value(raw_value)
                continue
            require(key not in data, f"Duplicate field {key!r} (line {number})")
            short, spec = by_short[key]
            if spec.json_field == "subjectStatementRef":
                require(bool(re.fullmatch(r"B[1-9][0-9]*", raw_value)),
                        f"subref= must be exactly one B-tag (line {number})")
            data[spec.json_field] = _coerce(raw_value, spec, block_type, tag, number)
        require(unit is not None, f"Row {tag} (T{code}) lacks unit=S<n>")
        require(bool(_UNIT_RE.match(unit)), f"Row {tag} has invalid unit {unit!r}")
        require(unit in allowed_units, f"Row {tag} references unknown unit {unit}")
        data["unit"] = unit
        rows.append({"blockType": block_type, "tag": tag, "data": data})
    require(bool(rows), "DSL response has no structural rows")
    return rows
