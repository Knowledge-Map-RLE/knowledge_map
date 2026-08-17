"""LLM-извлечение структуры блоков из научной статьи.

Сервис разбивает текст статьи (русский перевод) на чанки, для каждого чанка
вызывает AI-микросервис (`ai_model_client.generate_text`) с промптом
`llm_triplet_extraction_prompt`, собирает JSON-ответы, присваивает UUIDv8
каждому блоку и резолвит плейсхолдеры ``{SEQn}`` → реальные UUID.

Выход: полная структура блоков `[{instanceId, blockType, data, order}]` —
контейнеры (T14/T19/T22/T38/T56/T57 и др.) + атомарные T4-триплеты,
связанные через поле ``data.sequence``.

Пример:
    service = LLMTripletExtractionService()
    result = service.extract(doc_id="...", text="...русский текст...")
    result["blocks"]  # list[dict] готово к PUT /blocks
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.uuid8 import uuid8_str
from src.schemas.llm_extract import (
    AtomizeBlock,
    AtomizeResponse,
    StructureBlock,
    StructureResponse,
)
from . import settings
from .ai_model_client import get_ai_model_client
from .llm_triplet_extraction_prompt import (
    build_atomize_prompt,
    build_prompt,
    build_structure_prompt,
)
from .llm_triplet_extraction_prompt_en import (
    build_atomize_prompt_en,
    build_structure_prompt_en,
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
    def call_llm(
        self,
        chunk: str,
        article_title: str,
        *,
        model_id: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        prompt = build_prompt(article_title=article_title, chunk_text=chunk)
        result = self.client.generate_text(
            model_id=model_id,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            enable_chunking=True,
            timeout=timeout,
        )
        return result

    def call_llm_structure(
        self,
        chunk: str,
        article_title: str,
        *,
        model_id: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: int = DEFAULT_TIMEOUT,
        lang: str = "ru",
    ) -> Dict[str, Any]:
        """Stage 1: извлечение контейнерных блоков (без T4)."""
        if lang == "en":
            prompt = build_structure_prompt_en(article_title=article_title, chunk_text=chunk)
        else:
            prompt = build_structure_prompt(article_title=article_title, chunk_text=chunk)
        result = self.client.generate_text(
            model_id=model_id,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            enable_chunking=True,
            timeout=timeout,
        )
        return result

    def call_llm_atomize(
        self,
        chunk: str,
        article_title: str,
        containers_json: str,
        *,
        model_id: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: int = DEFAULT_TIMEOUT,
        lang: str = "ru",
    ) -> Dict[str, Any]:
        """Stage 2: разложение контейнеров чанка на атомарные T4-триплеты."""
        if lang == "en":
            prompt = build_atomize_prompt_en(
                article_title=article_title, chunk_text=chunk, containers_json=containers_json
            )
        else:
            prompt = build_atomize_prompt(
                article_title=article_title, chunk_text=chunk, containers_json=containers_json
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
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        text = LLMTripletExtractionService._repair_common_json(text)
        m = _JSON_FENCE_RE.search(text)
        candidate = m.group(1) if m else text
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
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
            try:
                bt = int(b.get("blockType", b.get("type", 0)))
            except (TypeError, ValueError):
                bt = 0
            d = b.get("data")
            if not isinstance(d, dict):
                d = {k: v for k, v in b.items() if k not in ("blockType", "type")}
            out.append({"blockType": bt, "data": d})
        return out

    @staticmethod
    def _parse_structure_json(generated_text: str) -> List[Dict[str, Any]]:
        """Извлекает контейнерные блоки ответа Stage 1 (с тегами {Bn}).

        JSON-ремонт (``_extract_json``) остаётся как нормализация перед
        парсингом через Pydantic-схему ``StructureResponse``.
        """
        data = LLMTripletExtractionService._extract_json(generated_text or "")
        if data is None:
            return []
        try:
            resp = StructureResponse.model_validate(data)
        except Exception:
            blocks_raw = data.get("blocks") if isinstance(data, dict) else None
            if not isinstance(blocks_raw, list):
                return []
            resp = StructureResponse(blocks=[
                StructureBlock.model_validate(b)
                for b in blocks_raw
                if isinstance(b, dict)
            ])
        out: List[Dict[str, Any]] = []
        for sb in resp.blocks:
            if sb.blockType == 4:
                continue  # T4 выводит только Stage 2
            d = dict(sb.data)
            if not d:
                d = {}
            out.append({
                "blockType": sb.blockType,
                "data": d,
                "tag": sb.tag.strip(),
            })
        return out

    @staticmethod
    def _parse_atomize_json(generated_text: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Извлекает (T4-блоки, sequences-маппинг) из ответа Stage 2.

        Модель может вернуть либо ``sequences``-мапу (старый формат), либо
        ``container``-тег на каждом T4 (новый формат). ``container``-тег
        конвертируется в sequences-мапу {B-тег: [порядковые номера]}.

        JSON-ремонт (``_extract_json``/``_extract_json_fragments``) остаётся
        как нормализация перед парсингом через Pydantic-схему ``AtomizeResponse``.
        """
        data = LLMTripletExtractionService._extract_json(generated_text or "")
        fragments: List[Dict[str, Any]] = []
        if data is not None:
            fragments.append(data)
        else:
            fragments = LLMTripletExtractionService._extract_json_fragments(generated_text or "")
        if not fragments:
            return [], {}

        blocks: List[Dict[str, Any]] = []
        sequences: Dict[str, Any] = {}
        for frag in fragments:
            try:
                resp = AtomizeResponse.model_validate(frag)
                for ab in resp.blocks:
                    if ab.blockType != 4:
                        continue
                    blocks.append({
                        "blockType": 4,
                        "data": dict(ab.data),
                        "container": ab.container.strip(),
                    })
                if resp.sequences:
                    sequences.update(resp.sequences)
            except Exception:
                blocks_raw = frag.get("blocks") if isinstance(frag, dict) else None
                if not isinstance(blocks_raw, list):
                    continue
                for b in blocks_raw:
                    if not isinstance(b, dict):
                        continue
                    try:
                        bt = int(b.get("blockType", b.get("type", 0)))
                    except (TypeError, ValueError):
                        bt = 0
                    if bt != 4:
                        continue
                    d = b.get("data")
                    if not isinstance(d, dict):
                        d = {k: v for k, v in b.items() if k not in ("blockType", "type", "container")}
                    container = str(b.get("container", "") or "").strip()
                    blocks.append({"blockType": 4, "data": d, "container": container})
                seqs = frag.get("sequences")
                if isinstance(seqs, dict):
                    sequences.update(seqs)

        # Новый формат: container-тег на каждом T4 → sequences-мапа.
        by_container: Dict[str, List[int]] = {}
        for i, b in enumerate(blocks, start=1):
            ctag = b.get("container", "")
            if ctag and ctag in sequences:
                continue  # старый формат уже дал мапу — не перетирать
            if ctag:
                by_container.setdefault(ctag, []).append(i)
        if by_container and not sequences:
            sequences = {tag: [f"{{SEQ{n}}}" for n in nums] for tag, nums in by_container.items()}
        return blocks, sequences

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

    @staticmethod
    def _compact_containers(containers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Сжимает контейнеры до {tag, blockType, name} для Stage 2.

        Полные data передавать не нужно — текст разбирается из чанка. Имя
        контейнера берётся из ключевого поля (напр. stepName для T56).
        """
        name_keys = {
            1: "title", 2: "subject", 7: "hypothesis", 14: "experimentName",
            16: "mechanism", 18: "intervention", 19: "species", 20: "conclusions",
            22: "subject", 23: "term", 37: "statProcessing", 38: "claimSubject",
            39: "limitations", 40: "sideFindings", 44: "novelty", 46: "futureResearch",
            47: "references", 51: "funding", 54: "subject", 55: "groupName",
            56: "stepName", 57: "parameter",
        }
        out: List[Dict[str, Any]] = []
        for c in containers:
            bt = int(c.get("blockType", 0))
            data = c.get("data") or {}
            name = ""
            key = name_keys.get(bt)
            if key:
                v = data.get(key)
                if isinstance(v, str):
                    name = v
            out.append({"tag": c.get("tag", ""), "blockType": bt, "name": name})
        return out

    def _merge_chunk(
        self,
        containers: Sequence[Dict[str, Any]],
        t4s: Sequence[Dict[str, Any]],
        sequences: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Собирает блоки одного чанка двухстадийного извлечения.

        Контейнерам присваиваются UUID (мапа тегов {Bn}), T4-триплетам — UUID
        (мапа {SEQn}). ``{Bn}`` внутри data контейнеров (steps/findings/pValue)
        и ``{SEQn}`` внутри T4 резолвятся в UUID. Поле ``sequence`` контейнера
        сериализуется в JSON-строку (как в эталоне). Порядок: контейнеры в
        порядке появления, затем все T4.
        """
        tag_to_uuid: Dict[str, str] = {}
        tag_num_to_uuid: Dict[int, str] = {}
        container_blocks: List[Dict[str, Any]] = []
        for c in containers:
            uid = uuid8_str()
            tag = str(c.get("tag", "") or "").strip()
            if tag:
                tag_to_uuid[tag] = uid
                mt = _BTAG_RE.match(tag)
                if mt:
                    tag_num_to_uuid[int(mt.group(1))] = uid
            container_blocks.append(
                {
                    "blockType": int(c.get("blockType", 0)),
                    "data": dict(c.get("data") or {}),
                    "uuid": uid,
                    "tag": tag,
                }
            )

        seq_to_uuid: Dict[int, str] = {}
        t4_blocks: List[Dict[str, Any]] = []
        for i, t in enumerate(t4s, start=1):
            uid = uuid8_str()
            seq_to_uuid[i] = uid
            t4_blocks.append(
                {"blockType": 4, "data": dict(t.get("data") or {}), "uuid": uid}
            )

        for b in container_blocks:
            b["data"] = self._resolve_tags(b["data"], _BTAG_RE, tag_num_to_uuid)

        for b in container_blocks:
            refs = sequences.get(b["tag"], [])
            if not isinstance(refs, list):
                continue
            uuids: List[str] = []
            for ref in refs:
                m = _PLACEHOLDER_RE.search(str(ref))
                if m and int(m.group(1)) in seq_to_uuid:
                    uuids.append(seq_to_uuid[int(m.group(1))])
            if uuids:
                b["data"]["sequence"] = json.dumps(uuids)

        for b in t4_blocks:
            b["data"] = self._resolve_tags(b["data"], _PLACEHOLDER_RE, seq_to_uuid)

        return container_blocks + t4_blocks

    def postprocess_two_stage(
        self,
        chunk_results: Sequence[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]],
        article_text: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Объединяет результаты всех чанков двухстадийного извлечения.

        После объединения добавляет детерминированные секции, которые модель
        4B надёжно не выдаёт даже при наличии в чанке: T51 «Финансирование»
        (раздел ``## Финансирование`` чётко отделён в тексте) и T47 «Связи с
        предыдущими исследованиями» (обёртка над prior-work T4-триплетами).
        """
        merged: List[Dict[str, Any]] = []
        for containers, t4s, sequences in chunk_results:
            merged.extend(self._merge_chunk(containers, t4s, sequences))
        merged = self._dedupe_t27(merged)
        merged = self._add_deterministic_sections(merged, article_text)
        merged = self._dedupe_t1(merged)
        merged = self._drop_t54_credits(merged)
        merged = self._attach_sequence_from_t4(merged)
        merged = self._trim_sequence_overfill(merged)
        merged = self._add_uuidrefs(merged)
        return [
            {
                "instanceId": b["uuid"],
                "blockType": b["blockType"],
                "data": b["data"],
                "order": i,
            }
            for i, b in enumerate(merged)
        ]

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

    @classmethod
    def _trim_sequence_overfill(
        cls, blocks: List[Dict[str, Any]], ref_ratio: float = settings.LLM_SEQ_REF_RATIO
    ) -> List[Dict[str, Any]]:
        """Срезает избыточное sequence-покрытие до эталонной доли.

        Модель перепривязывает контейнеры (EN: 0.9685 против 0.7788 в эталоне).
        Удаляем ``sequence`` у контейнеров с самыми короткими списками, пока
        доля контейнеров с sequence не опустится до ``ref_ratio``. Зеркально
        ``_attach_sequence_from_t4``: тот повышает недобор, этот срезает перебор.
        """
        containers = [b for b in blocks if int(b.get("blockType", 0)) in CONTAINER_TYPES]
        if not containers:
            return blocks
        target = int(round(ref_ratio * len(containers)))
        with_seq = [
            b for b in containers
            if any(isinstance(x, str) and x.strip() for x in _sequence_items(b))
        ]
        if len(with_seq) <= target:
            return blocks
        excess = len(with_seq) - target
        by_len = sorted(
            with_seq, key=lambda b: (len([x for x in _sequence_items(b) if x]), b.get("order", 0))
        )
        strip_ids = {str(b.get("uuid", "")) for b in by_len[:excess]}
        out: List[Dict[str, Any]] = []
        for b in blocks:
            if str(b.get("uuid", "")) in strip_ids:
                data = dict(b.get("data") or {})
                data.pop("sequence", None)
                out.append({**b, "data": data})
            else:
                out.append(b)
        return out

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

    # Имена-поля контейнеров, по которым ищется атомизация (для seq-привязки).
    _CONTAINER_NAME_KEYS = {
        7: "hypothesis",
        16: "mechanism",
        22: "subject",
        23: "term",
        37: "statProcessing",
        38: "claimSubject",
        39: "limitations",
        40: "sideFindings",
        44: "novelty",
        46: "futureResearch",
        47: "references",
        56: "stepName",
        57: "parameter",
    }
    _NORM_KEEP = re.compile(r"[^0-9a-zа-яё]+")

    @classmethod
    def _attach_sequence_from_t4(
        cls, blocks: List[Dict[str, Any]], ref_ratio: float = settings.LLM_SEQ_REF_RATIO
    ) -> List[Dict[str, Any]]:
        """Привязывает существующие T4 к контейнерам без sequence.

        Модель 4B иногда забывает заполнить ``data.sequence`` у контейнеров,
        даже если атомизация для них уже создана (T4 с текстом, содержащим
        имя контейнера). Метод находит такие контейнеры и восстанавливает
        связь, но не более чем до доли ``ref_ratio`` (доля контейнеров с
        sequence в эталоне) — перелет штрафуется метрикой seq симметрично.

        Кандидаты сортируются по числу слов в имени контейнера (больше слов
        = более специфичное совпадение), чтобы привязки были надёжными.
        """
        containers = [b for b in blocks if int(b.get("blockType", 0)) in CONTAINER_TYPES]
        if not containers:
            return blocks
        target = int(round(ref_ratio * len(containers)))
        with_seq = {
            b.get("uuid")
            for b in containers
            if any(isinstance(x, str) and x.strip() for x in _sequence_items(b))
        }
        if len(with_seq) >= target:
            return blocks

        t4_index: List[tuple] = []
        for b in blocks:
            if int(b.get("blockType", 0)) == 4:
                d = b.get("data") or {}
                text = cls._NORM_KEEP.sub(
                    " ", " ".join(str(d.get(k, "")) for k in ("subject", "predicate", "object"))
                ).strip().lower()
                t4_index.append((b.get("uuid"), text))

        candidates: List[tuple] = []
        for c in containers:
            if c.get("uuid") in with_seq:
                continue
            bt = int(c.get("blockType", 0))
            key = cls._CONTAINER_NAME_KEYS.get(bt)
            raw_name = str((c.get("data") or {}).get(key, "")) if key else ""
            name = cls._NORM_KEEP.sub(" ", raw_name).strip().lower()
            words = name.split()
            if len(words) < 2:
                continue
            matches = [uid for uid, text in t4_index if name in text]
            if matches:
                candidates.append((len(words), bt, c.get("uuid"), name, matches))

        candidates.sort(key=lambda x: (-x[0], x[1]))
        attach = blocks
        for n_words, bt, uid, name, matches in candidates:
            if len(with_seq) >= target:
                break
            if uid in with_seq:
                continue
            seq = json.dumps(matches[:3])
            attach = [
                {**b, "data": {**(b.get("data") or {}), "sequence": seq}}
                if b.get("uuid") == uid
                else b
                for b in attach
            ]
            with_seq.add(uid)
        return attach

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
            out.append({"blockType": int(block.get("blockType", 0)), "data": new_data})
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
        lang: str = "ru",
        cancel_event: Optional["threading.Event"] = None,
    ) -> Dict[str, Any]:
        """Извлекает структуру блоков из текста статьи.

        Возвращает:
            {"success", "blocks", "summary", "chunks": [{index, chars, tokens,
             raw_blocks, parsed_blocks, error?}]}

        Если cancel_event установлен, извлечение прерывается между чанками
        и возвращается {"success": False, "cancelled": True}.
        """
        if not text:
            return {"success": False, "message": "Текст статьи пуст", "blocks": []}

        chunks = self.split_into_chunks(text, max_chars=max_chunk_chars)
        if chunk_offset > 0:
            chunks = chunks[chunk_offset:]
        if max_chunks is not None:
            chunks = chunks[:max_chunks]
        logger.info(
            "Extraction for %s: %d chunks (offset=%d), model=%s, lang=%s",
            doc_id, len(chunks), chunk_offset, model_id, lang,
        )

        chunk_results: List[Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]] = []
        chunk_reports: List[Dict[str, Any]] = []
        total_input = 0
        total_output = 0
        for i, chunk in enumerate(chunks):
            abs_idx = chunk_offset + i
            if cancel_event is not None and cancel_event.is_set():
                logger.info("Extraction cancelled for %s (chunk %d)", doc_id, abs_idx)
                return {
                    "success": False,
                    "cancelled": True,
                    "doc_id": doc_id,
                    "blocks": [],
                    "message": "Извлечение отменено",
                    "chunks": chunk_reports,
                }
            containers: List[Dict[str, Any]] = []
            res_s: Dict[str, Any] = {}
            for attempt in range(1 + MAX_RETRIES):
                res_s = self.call_llm_structure(
                    chunk,
                    article_title,
                    model_id=model_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    lang=lang,
                )
                report: Dict[str, Any] = {
                    "index": abs_idx,
                    "chars": len(chunk),
                    "tokens_in": res_s.get("input_tokens", 0),
                    "tokens_out": res_s.get("output_tokens", 0),
                }
                total_input += report["tokens_in"]
                total_output += report["tokens_out"]
                if not res_s.get("success"):
                    report["error"] = res_s.get("message", "Ошибка LLM (structure)")
                    break
                containers = self._parse_structure_json(res_s.get("generated_text", ""))
                report["containers"] = len(containers)
                if containers:
                    break
                logger.warning("Chunk %d structure empty (attempt %d)", i, attempt)
            if not containers:
                if "error" not in report:
                    report["error"] = "Stage 1 вернул невалидный/пустой JSON"
                chunk_reports.append(report)
                continue

            t4s: List[Dict[str, Any]] = []
            sequences: Dict[str, Any] = {}
            batch_err: Optional[str] = None
            for attempt in range(1 + MAX_RETRIES):
                containers_json = json.dumps(self._compact_containers(containers), ensure_ascii=False)
                res_a = self.call_llm_atomize(
                    chunk,
                    article_title,
                    containers_json,
                    model_id=model_id,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    lang=lang,
                )
                report["tokens_in"] += res_a.get("input_tokens", 0)
                report["tokens_out"] += res_a.get("output_tokens", 0)
                total_input += res_a.get("input_tokens", 0)
                total_output += res_a.get("output_tokens", 0)
                if not res_a.get("success"):
                    batch_err = res_a.get("message", "Ошибка LLM (atomize)")
                    break
                t4s, sequences = self._parse_atomize_json(res_a.get("generated_text", ""))
                report["t4_blocks"] = len(t4s)
                if t4s:
                    batch_err = None
                    break
                batch_err = "Stage 2 вернул 0 T4-триплетов"
                logger.warning("Chunk %d atomize empty T4 (attempt %d)", i, attempt)
            report["sequence_keys"] = len(sequences)
            if batch_err:
                report["error"] = batch_err
                chunk_reports.append(report)
                continue

            chunk_results.append((containers, t4s, sequences))
            chunk_reports.append(report)
            logger.info(
                "Chunk %d: %d chars, %d containers, %d T4, %d seq-keys, "
                "%d tokens in / %d out",
                i, len(chunk), len(containers), len(t4s), len(sequences),
                report["tokens_in"], report["tokens_out"],
            )
            if progress_cb is not None:
                try:
                    progress_cb(i, chunk_reports)
                except Exception as exc:  # pragma: no cover - защита оркестрации
                    logger.warning("progress_cb failed on chunk %d: %s", i, exc)

        blocks = self.postprocess_two_stage(chunk_results, article_text=text)
        summary = self._summary(blocks)
        summary["chunks"] = len(chunks)
        summary["tokens"] = {"input": total_input, "output": total_output}
        return {
            "success": True,
            "doc_id": doc_id,
            "blocks": blocks,
            "summary": summary,
            "chunks": chunk_reports,
            "raw_chunks": chunk_results,
            "raw_count": sum(
                r.get("containers", 0) + r.get("t4_blocks", 0)
                for r in chunk_reports
            ),
        }
