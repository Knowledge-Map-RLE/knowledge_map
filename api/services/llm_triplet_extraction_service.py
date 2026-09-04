"""LLM-извлечение структуры блоков из научной статьи.

Сервис вызывает AI-микросервис (`ai_model_client.generate_text`) с unified
промптом для полной статьи, присваивает UUIDv8 каждому блоку и резолвит
плейсхолдеры ``{Bn}``/``{SEQn}`` → реальные UUID.

Выход: полная структура блоков `[{instanceId, blockType, data, order}]`.

Пример:
    service = LLMTripletExtractionService()
    result = service.extract(doc_id="...", text="...")
    result["blocks"]  # list[dict] готово к PUT /blocks
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.uuid8 import uuid8_str
from . import settings
from .ai_model_client import get_ai_model_client
from .llm_triplet_extraction_prompt_en import (
    build_unified_prompt_en,
    build_unified_chunk_prompt_en,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = settings.LLM_EXTRACT_MODEL
DEFAULT_MAX_CHUNK_CHARS = settings.LLM_MAX_CHUNK_CHARS
DEFAULT_MAX_TOKENS = settings.LLM_MAX_TOKENS
DEFAULT_TIMEOUT = settings.LLM_TIMEOUT
DEFAULT_TEMPERATURE = settings.LLM_TEMPERATURE
MAX_RETRIES = settings.LLM_MAX_RETRIES

# Типы, у которых есть sequence (для summary).
CONTAINER_TYPES = {7, 16, 22, 23, 37, 38, 39, 40, 44, 46, 47, 56, 57}

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\{?\s*SEQ\s*(\d+)\s*\}?")
_MISSING_OBJ_BRACE_RE = re.compile(r"(\])\s*,\s*(\{\s*\"blocks\"\s*:)", re.DOTALL)
_BTAG_RE = re.compile(r"\{?\s*B\s*(\d+)\s*\}?")
_BROKEN_QUOTE_RE = re.compile(r'">"')
_UUID_RE_SIMPLE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

_HEADING_RE = re.compile(r"^#{1,3}\s+\S")

_UNIFIED_BLOCK_TYPE_MAP: Dict[str, int] = {
    "article": 1,
    "objective": 2,
    "hypothesis": 7,
    "study": 4,
    "experiment": 14,
    "entity": 22,
    "definition": 23,
    "intervention": 18,
    "model": 19,
    "group": 55,
    "procedure_step": 56,
    "result": 57,
    "statistic": 37,
    "claim": 38,
    "mechanism": 16,
    "action": 54,
    "relation": 58,
    "action_relation": 58,
    "temporal_relation": 59,
    "limitation": 39,
    "novelty": 44,
    "future_proposal": 46,
    "reference": 47,
    "funding": 51,
    "side_finding": 40,
    "atomic_statement": 4,
    "direct_triplet": 4,
    "p_value": 27,
    "side_finding": 40,
    "conclusions": 20,
    "animal_group": 55,
    "animal_model": 19,
    "biological_mechanism": 16,
    "experiment_step": 56,
    "result_finding": 57,
    "statistical_processing": 37,
    "study_limitations": 39,
    "concept_definition": 23,
    "research_goal": 2,
    "links_to_previous_research": 47,
    "funding_sources": 51,
}


def _sequence_items(block: Dict[str, Any]) -> List[str]:
    """Возвращает элементы поля data.sequence (list или JSON-строка)."""
    raw = (block.get("data") or {}).get("sequence")
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if x and str(x).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if x and str(x).strip()]
        except (ValueError, TypeError):
            pass
    return []


class LLMTripletExtractionService:
    def __init__(self) -> None:
        self.client = get_ai_model_client()

    # ── Чанкинг ──────────────────────────────────────────────────────────────
    def split_into_chunks(
        self, text: str, max_chars: int = DEFAULT_MAX_CHUNK_CHARS
    ) -> List[str]:
        """Разбивает текст на чанки по границам абзацев/заголовков.

        Каждый чанк не превышает ``max_chars`` символов (в пределах контекста
        модели). Гигантский абзац режется по предложениям.
        """
        segments: List[str] = []
        buf: List[str] = []
        for line in (text or "").splitlines():
            if _HEADING_RE.match(line):
                if buf:
                    segments.append("\n".join(buf))
                    buf = []
                segments.append(line)
            else:
                buf.append(line)
        if buf:
            segments.append("\n".join(buf))

        chunks: List[str] = []
        cur: List[str] = []
        cur_len = 0
        for seg in segments:
            seg_len = len(seg)
            if seg_len > max_chars:
                # Абзац-переросток: режем по предложениям.
                parts = self._split_sentences(seg, max_chars)
            else:
                parts = [seg]
            for part in parts:
                if cur and cur_len + len(part) + 1 > max_chars:
                    chunks.append("\n".join(cur))
                    cur = []
                    cur_len = 0
                cur.append(part)
                cur_len += len(part) + 1
        if cur:
            chunks.append("\n".join(cur))
        return [c.strip() for c in chunks if c.strip()]

    @staticmethod
    def _split_sentences(text: str, max_chars: int) -> List[str]:
        pieces = re.split(r"(?<=[.!?])\s+", text)
        out: List[str] = []
        cur = ""
        for p in pieces:
            if len(cur) + len(p) + 1 > max_chars and cur:
                out.append(cur)
                cur = ""
            cur = (cur + " " + p).strip()
        if cur:
            out.append(cur)
        return out

    # ── LLM ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _repair_common_json(text: str) -> str:
        """Чинит типичные глитчи модели, ломающие JSON.

        Модель иногда вставляет ``">"`` (закрывающая кавычка + символ > +
        открывающая кавычка) внутрь строкового значения, разрывая строку
        (``"...golden">"russian spiny mice"``). Заменяем на пробел —
        строка склеивается обратно, JSON становится валидным.
        """
        if not text:
            return text
        return _BROKEN_QUOTE_RE.sub(" ", text)

    @staticmethod
    def _find_first_json_object_end(text: str, start: int) -> int:
        """Возвращает индекс закрывающей `}` первого объекта от `start`.

        Модель иногда выдаёт несколько ``{"blocks": [...]}`` объектов подряд
        (или повторяет вывод при обрыве/чанкинге на стороне провайдера), порой
        даже без запятой-разделителя (``]}{``). ``rfind("}")`` в такой ситуации
        захватывает все объекты разом, и ``json.loads`` падает с "Extra data".
        Поэтому ищем конец ПЕРВОГО корневого объекта балансировкой скобок.
        """
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        return -1

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        text = LLMTripletExtractionService._repair_common_json(text)
        m = _JSON_FENCE_RE.search(text)
        candidate = m.group(1) if m else text
        start = candidate.find("{")
        if start == -1:
            return None
        end = LLMTripletExtractionService._find_first_json_object_end(candidate, start)
        if end == -1 or end <= start:
            return None
        try:
            data = json.loads(candidate[start : end + 1])
            return data if isinstance(data, dict) else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_json_fragments(text: str) -> List[Dict[str, Any]]:
        """Извлекает несколько JSON-объектов из ответа модели.

        Модель 4B иногда выдаёт несколько объектов ``{"blocks": [...]}``
        подряд (по одному на контейнер) вместо одного валидного JSON.
        Разбираем по отдельности и объединяем списки ``blocks``.

        Модель часто пропускает закрывающую ``}`` перед запятой между
        фрагментами (``{"blocks": [...],{"blocks": [...]}``). Нормализуем
        такой случай до ``{"blocks": [...]},{"blocks": [...]}``.
        """
        if not text:
            return []
        m = _JSON_FENCE_RE.search(text)
        candidate = m.group(1) if m else text
        candidate = _MISSING_OBJ_BRACE_RE.sub(
            lambda mm: mm.group(1) + "}," + mm.group(2), candidate
        )
        objects: List[Dict[str, Any]] = []
        pos = 0
        while True:
            start = candidate.find("{", pos)
            if start == -1:
                break
            depth = 0
            in_str = False
            esc = False
            end = -1
            for i in range(start, len(candidate)):
                ch = candidate[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end == -1:
                break
            fragment = candidate[start : end + 1]
            try:
                data = json.loads(fragment)
                if isinstance(data, dict):
                    objects.append(data)
            except (ValueError, TypeError):
                pass
            pos = end + 1
        return objects

    def parse_response(self, generated_text: str) -> List[Dict[str, Any]]:
        """Извлекает список блоков из ответа модели."""
        data = self._extract_json(generated_text or "")
        if data is None:
            return []
        blocks = data.get("blocks")
        if not isinstance(blocks, list):
            blocks = data.get("data") if isinstance(data.get("data"), list) else []
        out: List[Dict[str, Any]] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt_raw = b.get("blockType", b.get("type", 0))
            if isinstance(bt_raw, str):
                bt = _UNIFIED_BLOCK_TYPE_MAP.get(bt_raw, 0)
            else:
                try:
                    bt = int(bt_raw)
                except (TypeError, ValueError):
                    bt = 0
            d = b.get("data")
            if not isinstance(d, dict):
                d = {k: v for k, v in b.items() if k not in ("blockType", "type", "tag", "container")}
            out.append({"blockType": bt, "data": d})
        return out

    # ── Post-processing ──────────────────────────────────────────────────────
    @staticmethod
    def _resolve_tags(
        value: Any, pattern: re.Pattern, mapping: Dict[int, str]
    ) -> Any:
        """Рекурсивно заменяет {Bn}/{SEQn}-плейсхолдеры на UUID в data."""
        if isinstance(value, str):
            return pattern.sub(lambda m: mapping.get(int(m.group(1)), m.group(0)), value)
        if isinstance(value, list):
            return [LLMTripletExtractionService._resolve_tags(v, pattern, mapping) for v in value]
        if isinstance(value, dict):
            return {
                k: LLMTripletExtractionService._resolve_tags(v, pattern, mapping)
                for k, v in value.items()
            }
        return value

    _PRIOR_WORK_RE = re.compile(
        r"предыдущ|ранее описан|описанных метод|предыдущей литератур|"
        r"в литературе|сообщало|показано ранее|известно что|"
        r"previous|earlier|prior|previously|reported|described|literature|"
        r"has been shown|was shown|we have shown|as posited",
        re.IGNORECASE,
    )

    _FUNDING_HEADING_RE = re.compile(
        r"^#{1,3}\s*(финансирование|funding|funding sources|источники финансирования)",
        re.IGNORECASE | re.MULTILINE,
    )
    _NEXT_HEADING_RE = re.compile(
        r"^#{1,3}\s+\S", re.MULTILINE
    )
    _BULLET_RE = re.compile(r"^\s*[-*•]\s+(.+)$")

    @classmethod
    def _add_deterministic_sections(
        cls,
        blocks: List[Dict[str, Any]],
        article_text: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Добавляет T47/T51, если модель их не выдала (надёжные секции)."""
        has_type = {int(b.get("blockType", 0)) for b in blocks}

        # T51 «Финансирование» — секция в тексте, bullet-список грантов.
        if 51 not in has_type and article_text:
            funding = cls._extract_funding_text(article_text)
            if funding:
                blocks = list(blocks) + [
                    {"uuid": uuid8_str(), "blockType": 51, "data": {"funding": funding}}
                ]
                has_type.add(51)

        # T47 «Связи с предыдущими исследованиями» — обёртка над prior-work T4.
        if 47 not in has_type:
            prior = [
                b
                for b in blocks
                if int(b.get("blockType", 0)) == 4
                and cls._PRIOR_WORK_RE.search(
                    " ".join(
                        str((b.get("data") or {}).get(k, ""))
                        for k in ("subject", "predicate", "object")
                    )
                )
            ]
            if prior:
                seq = json.dumps([b["uuid"] for b in prior])
                blocks = list(blocks) + [
                    {"uuid": uuid8_str(), "blockType": 47, "data": {"references": "", "sequence": seq}}
                ]
        return blocks

    @classmethod
    def _extract_funding_text(cls, article_text: str) -> str:
        """Извлекает текст секции финансирования (bullet-список) из статьи."""
        m = cls._FUNDING_HEADING_RE.search(article_text)
        if not m:
            return ""
        start = m.end()
        end = len(article_text)
        for nm in cls._NEXT_HEADING_RE.finditer(article_text, start + 1):
            end = nm.start()
            break
        bullets: List[str] = []
        for line in article_text[start:end].splitlines():
            bm = cls._BULLET_RE.match(line)
            if bm:
                bullets.append(bm.group(1).strip())
        return "; ".join(bullets)

    @staticmethod
    def _dedupe_t27(blocks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Сворачивает дубли T27 с одинаковым числовым pValue в один блок.

        Модель повторяет один и тот же p (0.05/0.01/0.001) на каждый чанк,
        раздувая число T27 (43 против 3 в эталоне). Оставляем первый блок на
        каждое значение, а ``pValue``-ссылки в T57 перенаправляем на него.
        """
        value_to_keep: Dict[Any, str] = {}
        by_uuid: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        t57_uuid_to_value: Dict[str, Any] = {}
        out: List[Dict[str, Any]] = []
        for b in blocks:
            bt = int(b.get("blockType", 0))
            data = b.get("data") or {}
            uid = str(b.get("uuid", ""))
            by_uuid[uid] = b
            order.append(uid)
            if bt == 27:
                v = data.get("pValue")
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if v not in value_to_keep:
                        value_to_keep[v] = uid
                out.append(b)
                continue
            if bt == 57:
                pv = data.get("pValue")
                if isinstance(pv, str) and _UUID_RE_SIMPLE.match(pv):
                    t57_uuid_to_value[uid] = pv
            out.append(b)

        if not value_to_keep:
            return list(blocks)

        # Кандидаты на удаление: T27-блоки, значение которых уже занято.
        drop: set = set()
        replacement: Dict[str, str] = {}
        for uid in order:
            b = by_uuid[uid]
            if int(b.get("blockType", 0)) != 27:
                continue
            v = b.get("data", {}).get("pValue")
            keep = value_to_keep.get(v)
            if isinstance(v, (int, float)) and keep and uid != keep:
                drop.add(uid)
                replacement[uid] = keep

        result: List[Dict[str, Any]] = []
        for b in out:
            uid = str(b.get("uuid", ""))
            if uid in drop:
                continue
            if int(b.get("blockType", 0)) == 57:
                pv = b.get("data", {}).get("pValue")
                if isinstance(pv, str) and pv in replacement:
                    b["data"] = dict(b["data"])
                    b["data"]["pValue"] = replacement[pv]
            result.append(b)
        return result

    # Роли CRediT (авторские вклады) — не являются действиями (T54).
    _CREDIT_ROLES = {
        "Conceptualization", "Data curation", "Formal analysis", "Funding acquisition",
        "Investigation", "Methodology", "Project administration", "Resources",
        "Software", "Supervision", "Validation", "Visualization", "Writing",
        "Writing - original draft", "Writing - review & editing",
        "Writing — original draft", "Writing — review & editing",
    }

    @staticmethod
    def _dedupe_t1(blocks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Оставляет один T1 «Метаданные» с авторами (обычно 1-й чанк).

        Модель дублирует T1 на каждый чанк (заголовок без авторов). В эталоне
        один T1. Держим блок с максимальным числом авторов, остальные T1
        удаляем (их sequence-содержимое при этом сохраняется в T4-блоках).
        """
        t1 = [b for b in blocks if int(b.get("blockType", 0)) == 1]
        if len(t1) <= 1:
            return list(blocks)
        keep = max(t1, key=lambda b: len((b.get("data") or {}).get("authors") or []))
        keep_uid = str(keep.get("uuid", ""))
        return [
            b for b in blocks
            if int(b.get("blockType", 0)) != 1 or str(b.get("uuid", "")) == keep_uid
        ]

    @staticmethod
    def _drop_t54_credits(blocks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Удаляет T54-блоки с авторскими ролями CRediT.

        Модель раскладывает раздел Author Contributions на T54-триплеты вида
        «Автор → Концептуализация» (в эталоне таких нет). Роль-предикат из
        CREDIT_ROLES → блок не является действием → удаляем.
        """
        return [
            b for b in blocks
            if not (
                int(b.get("blockType", 0)) == 54
                and str((b.get("data") or {}).get("predicate", "")).strip()
                in LLMTripletExtractionService._CREDIT_ROLES
            )
        ]

    @staticmethod
    def _add_uuidrefs(
        blocks: List[Dict[str, Any]],
        max_words: int = settings.LLM_UUIDREF_MAX_WORDS,
        min_freq: int = settings.LLM_UUIDREF_MIN_FREQ,
    ) -> List[Dict[str, Any]]:
        """Заменяет повторяющиеся термины на UUID определяющего T4-триплета.

        Эталон (reference_blocks.json) ссылается на атомарный T4-триплет по
        UUID, когда термин — каноническое короткое имя (``a. russatus``,
        ``кластерин``, ``мышь``), ранее определённое как SUBJECT этого T4.
        Модель 4B почти не порождает такие перекрёстные ссылки (EN v5: 0.067
        против 0.212 в эталоне), поэтому восстанавливаем их детерминированно:
        для каждого короткого (<= ``max_words`` слов) термина, встречающегося
        >= ``min_freq`` раз в позициях SUBJECT/OBJECT T4-триплетов и являющегося
        полным SUBJECT хотя бы одного T4, все вхождения в ДРУГИХ T4 заменяются
        на UUID этого «определяющего» триплета. Сам определяющий триплет
        сохраняет текст. Многословные объекты вида «у стареющих a. russatus»
        (len > max_words) не трогаются — в эталоне они тоже не ссылаются.
        """
        defining: Dict[str, str] = {}
        for b in blocks:
            if int(b.get("blockType", 0)) == 4:
                s = str((b.get("data") or {}).get("subject", "") or "").strip()
                if s and not _UUID_RE_SIMPLE.match(s):
                    defining.setdefault(
                        s.strip().lower(), str(b.get("uuid", "") or "")
                    )
        freq: Dict[str, int] = {}
        for b in blocks:
            if int(b.get("blockType", 0)) == 4:
                d = b.get("data") or {}
                for k in ("subject", "object"):
                    v = str(d.get(k, "") or "").strip()
                    if v and not _UUID_RE_SIMPLE.match(v):
                        key = v.strip().lower()
                        freq[key] = freq.get(key, 0) + 1
        out: List[Dict[str, Any]] = []
        for b in blocks:
            if int(b.get("blockType", 0)) == 4:
                d = dict(b.get("data") or {})
                uid = str(b.get("uuid", "") or "")
                for k in ("subject", "object"):
                    v = str(d.get(k, "") or "").strip()
                    if not v or _UUID_RE_SIMPLE.match(v):
                        continue
                    key = v.strip().lower()
                    if (
                        key in defining
                        and defining[key] != uid
                        and len(key.split()) <= max_words
                        and freq.get(key, 0) >= min_freq
                    ):
                        d[k] = defining[key]
                out.append({**b, "data": d})
            else:
                out.append(b)
        return out

    @staticmethod
    def _hoist_inline_blocks(
        raw_blocks: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Поднимает вложенные T4-объекты из sequence/steps/findings наверх.

        Модель иногда вкладывает ``{"blockType": 4, "data": {...}}`` прямо в
        списки ``sequence``/``steps``/``findings``. Такие объекты извлекаются
        в отдельные блоки (перед контейнером), а на их место ставится
        плейсхолдер ``{SEQn}`` в порядке встречи.
        """
        out: List[Dict[str, Any]] = []
        seq_counter = 0

        def hoist_value(value: Any, counter: List[int]) -> Any:
            if isinstance(value, list):
                new_list: List[Any] = []
                for item in value:
                    if (
                        isinstance(item, dict)
                        and "blockType" in item
                        and isinstance(item.get("data"), dict)
                    ):
                        counter[0] += 1
                        out.append(
                            {"blockType": int(item["blockType"]), "data": item["data"]}
                        )
                        new_list.append(f"{{SEQ{counter[0]}}}")
                    else:
                        new_list.append(hoist_value(item, counter))
                return new_list
            if isinstance(value, dict):
                return {k: hoist_value(v, counter) for k, v in value.items()}
            return value

        for block in raw_blocks:
            data = block.get("data") or {}
            counter = [seq_counter]
            new_data = hoist_value(data, counter)
            seq_counter = counter[0]
            # out накапливает поднятые вложенные блоки глобально (в порядке
            # встречи), поэтому они оказываются перед текущим контейнером.
            out.append({
                "blockType": int(block.get("blockType", 0)),
                "data": new_data,
                "tag": block.get("tag", ""),
            })
        return out

    def _map_placeholders(self, blocks: Sequence[Dict[str, Any]]) -> Tuple[Dict[int, str], List[Dict[str, Any]]]:
        """Присваивает UUIDv8 блокам и возвращает карту {seq_num: uuid}.

        T4-блоки нумеруются ``{SEQi}`` сквозно в порядке появления в массиве;
        остальные блоки получают UUID без номера. Соответствует поведению
        модели (она считает атомарные T4-триплеты последовательно).
        """
        seq_to_uuid: Dict[int, str] = {}
        out: List[Dict[str, Any]] = []
        seq_counter = 0
        for b in blocks:
            bt = int(b.get("blockType", 0))
            uid = uuid8_str()
            if bt == 4:
                seq_counter += 1
                seq_to_uuid[seq_counter] = uid
            out.append({"blockType": bt, "data": b.get("data", {}), "uuid": uid})
        return seq_to_uuid, out

    def _resolve_placeholders(self, blocks: List[Dict[str, Any]], seq_to_uuid: Dict[int, str]) -> List[Dict[str, Any]]:
        """Заменяет {SEQn} на UUID во всех полях data (строках и массивах)."""
        def resolve_str(value: str) -> str:
            return _PLACEHOLDER_RE.sub(
                lambda m: seq_to_uuid.get(int(m.group(1)), m.group(0)), value
            )

        resolved: List[Dict[str, Any]] = []
        for b in blocks:
            data = {}
            for k, v in (b.get("data") or {}).items():
                if isinstance(v, str):
                    data[k] = resolve_str(v)
                elif isinstance(v, list):
                    data[k] = [
                        resolve_str(item) if isinstance(item, str) else item for item in v
                    ]
                else:
                    data[k] = v
            resolved.append({"blockType": b["blockType"], "uuid": b["uuid"], "data": data})
        return resolved

    def postprocess(
        self, raw_blocks: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Собирает финальные блоки: UUID + резолв плейсхолдеров + order."""
        hoisted = self._hoist_inline_blocks(raw_blocks)
        seq_to_uuid, mapped = self._map_placeholders(hoisted)
        resolved = self._resolve_placeholders(mapped, seq_to_uuid)
        return [
            {
                "instanceId": b["uuid"],
                "blockType": b["blockType"],
                "data": b["data"],
                "order": i,
            }
            for i, b in enumerate(resolved)
        ]

    @staticmethod
    def _summary(blocks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        hist: Dict[int, int] = {}
        containers = 0
        with_seq = 0
        for b in blocks:
            bt = int(b.get("blockType", 0))
            hist[bt] = hist.get(bt, 0) + 1
            if bt in CONTAINER_TYPES:
                containers += 1
                raw = (b.get("data") or {}).get("sequence")
                items = raw if isinstance(raw, list) else []
                if isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                        items = parsed if isinstance(parsed, list) else []
                    except (ValueError, TypeError):
                        items = []
                if any(isinstance(x, str) and x.strip() for x in items):
                    with_seq += 1
        return {
            "total": len(blocks),
            "histogram": {str(k): v for k, v in sorted(hist.items())},
            "containers": containers,
            "containers_with_sequence": with_seq,
        }

    # ── Unified (one-stage) extraction ───────────────────────────────────────
    def call_llm_unified(
        self,
        article_text: str,
        article_title: str,
        *,
        model_id: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Unified one-stage call: full article → all blocks (any language)."""
        prompt = build_unified_prompt_en(
            article_title=article_title, article_text=article_text
        )
        result = self.client.generate_text(
            model_id=model_id,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            enable_chunking=True,
            timeout=timeout,
        )
        return result

    @staticmethod
    def _parse_unified_json(generated_text: str) -> List[Dict[str, Any]]:
        """Парсит unified-ответ (все блоки в одном JSON)."""
        data = LLMTripletExtractionService._extract_json(generated_text or "")
        if data is None:
            return []
        try:
            from src.schemas.llm_extract import UnifiedResponse
            resp = UnifiedResponse.model_validate(data)
        except Exception:
            blocks_raw = data.get("blocks") if isinstance(data, dict) else None
            if not isinstance(blocks_raw, list):
                return []
            resp = None
        if resp is not None:
            raw_blocks = []
            for ub in resp.blocks:
                d = dict(ub.data)
                raw_blocks.append({
                    "blockType": ub.blockType,
                    "data": d,
                    "tag": ub.tag.strip() if ub.tag else "",
                })
        else:
            raw_blocks = []
            for b in blocks_raw:
                if not isinstance(b, dict):
                    continue
                bt_raw = b.get("blockType", b.get("type", 0))
                if isinstance(bt_raw, str):
                    bt = _UNIFIED_BLOCK_TYPE_MAP.get(bt_raw, 0)
                else:
                    try:
                        bt = int(bt_raw)
                    except (TypeError, ValueError):
                        bt = 0
                d = b.get("data")
                if not isinstance(d, dict):
                    d = {k: v for k, v in b.items() if k not in ("blockType", "type", "tag")}
                raw_blocks.append({
                    "blockType": bt,
                    "data": d,
                    "tag": str(b.get("tag", "") or "").strip(),
                })
        return raw_blocks

    def _assign_uuids_unified(
        self, raw_blocks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Присваивает UUIDv8 каждому блоку, резолвит {Bn} и {SEQn}."""
        tag_to_uuid: Dict[str, str] = {}
        tag_num_to_uuid: Dict[int, str] = {}
        seq_to_uuid: Dict[int, str] = {}

        for b in raw_blocks:
            uid = uuid8_str()
            tag = str(b.get("tag", "") or "").strip()
            if tag:
                tag_to_uuid[tag] = uid
                mt = _BTAG_RE.match(tag)
                if mt:
                    tag_num_to_uuid[int(mt.group(1))] = uid
            b["uuid"] = uid

        seq_counter = 0
        for b in raw_blocks:
            if int(b.get("blockType", 0)) == 4:
                seq_counter += 1
                seq_to_uuid[seq_counter] = b["uuid"]

        for b in raw_blocks:
            b["data"] = self._resolve_tags(b["data"], _BTAG_RE, tag_num_to_uuid)
            b["data"] = self._resolve_tags(b["data"], _PLACEHOLDER_RE, seq_to_uuid)

        raw_blocks = self._cleanup_unresolved_btags(raw_blocks)
        raw_blocks = self._normalize_pairs(raw_blocks)
        return raw_blocks

    @staticmethod
    def _normalize_pairs(
        raw_blocks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Конвертирует flat UUID-массивы и сериализует array-поля T14 в JSON-строки.

        Клиент ожидает experimentalPairs/controlPairs в формате JSON-строки:
            '[{"groupRef": "uuid", "interventionRef": "uuid"}]'
       .steps/findings тоже ожидает как JSON-строки: '["uuid1", "uuid2"]'
        ЛLM генерирует нативные Python-списки, которые json.dumps сериализует
        в строки при сохранении в Neo4j, но клиент получает обратно массив.
        str() клиента возвращает '' для массивов — триплеты не создаются.
        """
        _ARRAY_KEYS = ("steps", "findings", "experimentalPairs", "controlPairs")
        for b in raw_blocks:
            if int(b.get("blockType", 0)) != 14:
                continue
            d = b.get("data") or {}
            for key in ("experimentalPairs", "controlPairs"):
                val = d.get(key)
                if isinstance(val, list) and val:
                    if isinstance(val[0], str):
                        d[key] = [{"groupRef": uid, "interventionRef": ""} for uid in val]
            # Сериализуем array-поля в JSON-строки (клиент ожидает строки)
            for key in _ARRAY_KEYS:
                val = d.get(key)
                if isinstance(val, list):
                    d[key] = json.dumps(val, ensure_ascii=False)
            b["data"] = d
        return raw_blocks

    @staticmethod
    def _normalize_t1_authors(
        raw_blocks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Конвертирует authors из массива в строку через запятую.

        LLM генерирует authors как массив строк: ["Author One", "Author Two"]
        Блок-конвертер (block_converter.py t1) ожидает строку и сплитит по запятым.
        """
        for b in raw_blocks:
            if int(b.get("blockType", 0)) != 1:
                continue
            d = b.get("data") or {}
            authors = d.get("authors")
            if isinstance(authors, list):
                d["authors"] = ", ".join(str(a) for a in authors if a)
            b["data"] = d
        return raw_blocks

    @staticmethod
    def _normalize_t58_source_target(
        raw_blocks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Конвертирует sourceRef/targetRef → source/target для T58/T59.

        Модель иногда генерирует sourceRef/targetRef (UUID) вместо
        source/target (имена). Метрика ожидает source/target.
        Резолв UUID → текст выполняется универсальным резолвером из metrics
        (block_to_text + BLOCK_TEXT_FIELDS) — единый алгоритм для всех типов.
        """
        # Нормализуем ссылочные поля в единый source/target.
        for b in raw_blocks:
            bt = int(b.get("blockType", 0) or 0)
            if bt not in (58, 59):
                continue
            d = b.get("data") or {}

            if "sourceRef" in d and "source" not in d:
                d["source"] = d.pop("sourceRef", "")
            if "targetRef" in d and "target" not in d:
                d["target"] = d.pop("targetRef", "")
            if "earlierRef" in d and "source" not in d:
                d["source"] = d.pop("earlierRef", "")
            if "laterRef" in d and "target" not in d:
                d["target"] = d.pop("laterRef", "")
            b["data"] = d

        # Универсальный резолвер UUID → текст (тот же, что в metrics.compute_metrics).
        from tools.llm_extract.metrics import build_uuid_map, resolve_uuid_text

        uuid_map = build_uuid_map(raw_blocks)
        for b in raw_blocks:
            bt = int(b.get("blockType", 0) or 0)
            if bt not in (58, 59):
                continue
            d = b.get("data") or {}
            for key in ("source", "target"):
                d[key] = resolve_uuid_text(d.get(key, ""), uuid_map)
            b["data"] = d
        return raw_blocks

    @staticmethod
    def _cleanup_unresolved_btags(
        raw_blocks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Удаляет нерезолвленные {Bn} и {SEQn} теги из data полей.

        Модель иногда генерирует {Bn} ссылки на блоки, которые не были
        выведены (T4 используют {SEQn}, не {Bn}; T56/T57 могут отсутствовать
        в review-статьях). Нерезолвленные теги заменяются на пустую строку.
        """
        def _strip_tags(value: Any) -> Any:
            if isinstance(value, str):
                cleaned = _BTAG_RE.sub("", value)
                cleaned = _PLACEHOLDER_RE.sub("", cleaned)
                cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
                return cleaned
            if isinstance(value, list):
                return [_strip_tags(v) for v in value]
            if isinstance(value, dict):
                return {k: _strip_tags(v) for k, v in value.items()}
            return value

        out: List[Dict[str, Any]] = []
        for b in raw_blocks:
            d = b.get("data") or {}
            b["data"] = _strip_tags(d)
            out.append(b)
        return out

    def _strip_uuids_from_t4(
        self, raw_blocks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Заменяет UUIDv8 в субъектах/объектах T4 на текст из uuid_to_text карты."""
        import re as _re
        uuid_re = _re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            _re.IGNORECASE,
        )
        # Строим карту uuid → text (берём данные T1/T2/T7/T16/T22/T38/T54/T58)
        uuid_to_text: Dict[str, str] = {}
        for b in raw_blocks:
            uid = b.get("uuid", "")
            bt = int(b.get("blockType", 0))
            d = b.get("data") or {}
            if bt == 1:
                uuid_to_text[uid] = d.get("title", "") or ", ".join(d.get("authors", []))
            elif bt == 2:
                uuid_to_text[uid] = f"{d.get('subject', '')} {d.get('object', '')}".strip()
            elif bt == 7:
                uuid_to_text[uid] = d.get("hypothesis", "")[:60]
            elif bt == 16:
                uuid_to_text[uid] = d.get("mechanism", "")[:60]
            elif bt == 22:
                uuid_to_text[uid] = f"{d.get('subject', '')} {d.get('predicate', '')} {d.get('object', '')}".strip()
            elif bt == 38:
                uuid_to_text[uid] = f"{d.get('claimSubject', '')} {d.get('claimObject', '')}".strip()
            elif bt == 54:
                uuid_to_text[uid] = f"{d.get('subject', '')} {d.get('predicate', '')} {d.get('object', '')}".strip()
            elif bt == 58:
                uuid_to_text[uid] = f"{d.get('source', '')} {d.get('target', '')}".strip()

        # Заменяем UUID в T4 блоках
        for b in raw_blocks:
            if int(b.get("blockType", 0)) != 4:
                continue
            d = b.get("data") or {}
            for key in ("subject", "object", "predicate"):
                val = str(d.get(key, ""))
                if uuid_re.match(val):
                    text = uuid_to_text.get(val, "")
                    if text:
                        d[key] = text[:80]
                    else:
                        d[key] = ""
        return raw_blocks

    def postprocess_unified(
        self,
        raw_blocks: List[Dict[str, Any]],
        article_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Постпроцессинг для unified (one-stage) извлечения."""
        raw_blocks = self._hoist_inline_blocks(raw_blocks)
        raw_blocks = self._assign_uuids_unified(raw_blocks)
        raw_blocks = self._strip_uuids_from_t4(raw_blocks)
        raw_blocks = self._dedupe_t27(raw_blocks)
        raw_blocks = self._dedupe_t1(raw_blocks)
        raw_blocks = self._normalize_t1_authors(raw_blocks)
        raw_blocks = self._drop_t54_credits(raw_blocks)
        raw_blocks = self._normalize_t58_source_target(raw_blocks)
        raw_blocks = self._add_deterministic_sections(raw_blocks, article_text)
        raw_blocks = self._add_uuidrefs(raw_blocks)
        return [
            {
                "instanceId": b["uuid"],
                "blockType": b["blockType"],
                "data": b["data"],
                "order": i,
            }
            for i, b in enumerate(raw_blocks)
        ]

    def extract_whole_article(
        self,
        doc_id: str,
        text: str,
        article_title: str = "",
        *,
        model_id: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = 80000,
        timeout: int = 600,
        progress_cb=None,
    ) -> Dict[str, Any]:
        """Обрабатывает статью целиком (без чанкинга) — один LLM-вызов.

        Оптимизировано для DeepSeek V4 Flash (1M контекст).
        Статья ~40K символов = ~15K токенов, легко умещается.

        Args:
            progress_cb: reserved for future use (currently unused).
        """
        if not text:
            return {"success": False, "message": "Текст статьи пуст", "blocks": []}

        logger.info(
            "Whole-article extraction for %s: %d chars, model=%s",
            doc_id, len(text), model_id,
        )

        for attempt in range(1 + MAX_RETRIES):
            res = self.call_llm_unified(
                text,
                article_title,
                model_id=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if not res.get("success"):
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Whole-article attempt %d failed: %s",
                        attempt, res.get("message"),
                    )
                    continue
                return {
                    "success": False,
                    "doc_id": doc_id,
                    "message": res.get("message", "LLM call failed"),
                    "blocks": [],
                }

            raw_blocks = self._parse_unified_json(res.get("generated_text", ""))
            if raw_blocks:
                break
            logger.warning(
                "Whole-article attempt %d returned 0 blocks", attempt
            )

        if not raw_blocks:
            return {
                "success": False,
                "doc_id": doc_id,
                "message": "LLM returned empty/invalid JSON",
                "blocks": [],
            }

        blocks = self.postprocess_unified(raw_blocks, article_text=text)
        summary = self._summary(blocks)
        summary["tokens"] = {
            "input": res.get("input_tokens", 0),
            "output": res.get("output_tokens", 0),
        }
        summary["attempts"] = attempt + 1

        logger.info(
            "Whole-article extraction done: %d blocks, %s tokens",
            len(blocks), summary["tokens"],
        )
        return {
            "success": True,
            "doc_id": doc_id,
            "blocks": blocks,
            "summary": summary,
            "chunks": [{"index": 0, "chars": len(text), "containers": len(blocks)}],
            "raw_count": len(raw_blocks),
        }

    # ── Chunked (sequential) extraction ───────────────────────────────────────
    def extract_chunked(
        self,
        doc_id: str,
        text: str,
        article_title: str = "",
        *,
        model_id: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: int = DEFAULT_TIMEOUT,
        max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
        progress_cb=None,
        cancel_event: Optional["threading.Event"] = None,
    ) -> Dict[str, Any]:
        """Извлекает структуру статьи по фрагментам (sequential chunking).

        Длинная статья разбивается на логические фрагменты (``split_into_chunks``),
        каждый обрабатывается отдельным LLM-вызовом. Это позволяет модели выдавать
        компактный, сфокусированный вывод на фрагменте и избегает обрыва/дублирования
        вывода на очень длинные статьи (когда модель физически не генерирует все
        150+ блоков за один ответ).

        Нумерация ``{Bn}`` — глобальная: каждый последующий фрагмент получает список
        уже извлечённых блоков (контекст) и продолжает нумерацию с конца, а также
        может ссылаться на блоки из предыдущих фрагментов без битых ссылок.

        Все сырые блоки всех фрагментов собираются вместе и проходят единый
        постпроцессинг (присвоение UUID, дедупликацию, детерминированные секции).
        """
        if not text:
            return {"success": False, "message": "Текст статьи пуст", "blocks": []}

        chunks = self.split_into_chunks(text, max_chars=max_chunk_chars)
        if not chunks:
            return {"success": False, "message": "Не удалось разбить статью на фрагменты", "blocks": []}

        logger.info(
            "Chunked extraction for %s: %d chars -> %d chunks, model=%s, chunk_chars=%d",
            doc_id, len(text), len(chunks), model_id, max_chunk_chars,
        )

        raw_all: List[Dict[str, Any]] = []
        chunk_report: List[Dict[str, Any]] = []
        total_input = 0
        total_output = 0
        total_attempts = 0
        failed_chunks: List[int] = []

        for ci, chunk in enumerate(chunks):
            if cancel_event is not None and cancel_event.is_set():
                return {
                    "success": False,
                    "cancelled": True,
                    "message": "Извлечение отменено",
                    "blocks": [],
                    "chunks": chunk_report,
                }

            next_b = 1
            for b in raw_all:
                mt = _BTAG_RE.match(str(b.get("tag", "") or "").strip())
                if mt:
                    next_b = max(next_b, int(mt.group(1)) + 1)

            prompt = build_unified_chunk_prompt_en(
                article_title=article_title,
                chunk_text=chunk,
                prior_blocks=raw_all,
                next_b_tag=next_b,
            )

            chunk_ok = False
            for attempt in range(1 + MAX_RETRIES):
                if cancel_event is not None and cancel_event.is_set():
                    return {
                        "success": False,
                        "cancelled": True,
                        "message": "Извлечение отменено",
                        "blocks": [],
                        "chunks": chunk_report,
                    }
                if progress_cb:
                    progress_cb(ci, len(chunks), attempt)

                res = self.client.generate_text_stream(
                    model_id=model_id,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=timeout,
                )
                total_attempts += 1
                total_input += int(res.get("input_tokens", 0) or 0)
                total_output += int(res.get("output_tokens", 0) or 0)
                if not res.get("success"):
                    logger.warning(
                        "Chunk %d/%d attempt %d failed: %s",
                        ci + 1, len(chunks), attempt, res.get("message"),
                    )
                    if attempt < MAX_RETRIES:
                        continue
                    failed_chunks.append(ci)
                    chunk_report.append({
                        "index": ci,
                        "chars": len(chunk),
                        "blocks": 0,
                        "success": False,
                        "error": res.get("message", "LLM call failed"),
                    })
                    break

                raw_blocks = self._parse_unified_json(res.get("generated_text", ""))
                chunk_ok = True
                raw_all.extend(raw_blocks)
                chunk_report.append({
                    "index": ci,
                    "chars": len(chunk),
                    "blocks": len(raw_blocks),
                    "success": True,
                })
                logger.info(
                    "Chunk %d/%d done: %d blocks (total %d)",
                    ci + 1, len(chunks), len(raw_blocks), len(raw_all),
                )
                break

            if not chunk_ok and ci not in failed_chunks:
                failed_chunks.append(ci)

        if not raw_all:
            return {
                "success": False,
                "doc_id": doc_id,
                "message": "Все фрагменты вернули пустой/невалидный JSON",
                "blocks": [],
                "chunks": chunk_report,
            }

        blocks = self.postprocess_unified(raw_all, article_text=text)
        summary = self._summary(blocks)
        summary["tokens"] = {
            "input": total_input,
            "output": total_output,
        }
        summary["attempts"] = total_attempts
        summary["chunk_failures"] = failed_chunks

        return {
            "success": len(blocks) > 0,
            "doc_id": doc_id,
            "blocks": blocks,
            "summary": summary,
            "chunks": chunk_report,
            "raw_count": len(raw_all),
            "failed_chunks": failed_chunks,
        }

    # ── Оркестрация ──────────────────────────────────────────────────────────
    def extract(
        self,
        doc_id: str,
        text: Optional[str] = None,
        *,
        article_title: str = "",
        model_id: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: int = DEFAULT_TIMEOUT,
        max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
        chunk_offset: int = 0,
        max_chunks: Optional[int] = None,
        progress_cb=None,
        cancel_event: Optional["threading.Event"] = None,
        use_chunking: bool = True,
    ) -> Dict[str, Any]:
        """Извлекает структуру блоков из текста статьи.

        По умолчанию (``use_chunking=True``) длинная статья обрабатывается
        пофрагментно (sequential chunking) во избежание обрыва вывода на
        длинных статьях. Для очень коротких текстов будет один фрагмент.

        Возвращает:
            {"success", "blocks", "summary", "chunks": [{index, chars, blocks}]}
        """
        if not text:
            return {"success": False, "message": "Текст статьи пуст", "blocks": []}

        if not use_chunking:
            return self.extract_whole_article(
                doc_id,
                text,
                article_title,
                model_id=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                progress_cb=progress_cb,
            )

        return self.extract_chunked(
            doc_id,
            text,
            article_title,
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_chunk_chars=max_chunk_chars,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
        )


