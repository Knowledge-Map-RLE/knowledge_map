"""Сервис декомпозиции цели (goal decomposition, reverse planning).

Слой: Services.

Назначение
==========
Пользователь вводит цель на естественном языке. Сервис:

1. Вызывает LLM с отдельным промптом декомпозиции
   (``goal_decomposition_prompt_en.build_goal_decomposition_prompt``),
   который возвращает иерархическое дерево плана (goal/sub_goal/task/action).
2. Формализует ТЕКСТ каждого пункта в одно атомарное утверждение
   ``sub → pred → obj`` через существующий DSL-промпт формализации
   (``llm_triplet_extraction_prompt_dsl.build_goal_plan_dsl_prompt`` + парсер
   ``tools/llm_extract/dsl_parser.parse_dsl_text``) — промпт формализации НЕ
   дублируется. Каждый пункт связывается со своим фактом по метке ``item:<ID>``.
3. Иерархия плана — детерминированные связующие META-триплеты
   ``decomposed_into`` (statement-типы, UUID-ссылки), которые в
   ``KnowledgeTriplesService`` образуют прямые рёбра DAG-компоненты.
4. Сохраняет план как отдельный ``Document`` (doc_type='goal_plan') в Neo4j.
5. Возвращает дерево + блоки/рёбра в формате KnowledgeGraphBlock/Link для
   отображения на карте знаний страницы /km.

ВАЖНО (требование пользователя): цель, задача, действие, шаг — это ОДНА
сущность (``KnowledgeStatement``). Для цели ставится флаг в свойствах
(``is_goal=True``, ``level=0``). Задачи/действия — обычные ``KnowledgeStatement``
с ``level>0``. Отдельные label-сущности (Goal/Task/Step) НЕ создаются.

ВАЖНО (требование пользователя): формализация НЕ выдают бесполезные триплеты
``текст → is → goal/sub_goal/task/action``. Каждый пункт — содержательное
атомарное утверждение, извлечённое моделью из текста пункта.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from neomodel import db

from .ai_model_client import get_ai_model_client
from . import settings
from .goal_decomposition_prompt_en import build_goal_decomposition_prompt

logger = logging.getLogger(__name__)

# Model settings (как в llm_triplet_extraction_service).
DEFAULT_MODEL = settings.LLM_EXTRACT_MODEL
DEFAULT_MAX_TOKENS = 12000
DEFAULT_TIMEOUT = settings.LLM_TIMEOUT
DEFAULT_TEMPERATURE = 0.2

# Служебные предикаты, не несущие доменной структуры (как knowledge_triples_service).
_NOISE_PREDICATES = {"is_a", "contains", "related_to", "has"}

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

# Предикаты, которыми связываем элементы плана в графе утверждений.
# Каждый элемент плана — одно атомарное утверждение из формализации,
# связанные meta-рёбрами decomposed_into (дочерний элемент → родитель).
_PREDICATE_DECOMPOSED_INTO = "decomposed_into"


class GoalDecompositionService:
    """Оркестрация декомпозиции цели и её формализации в Язык Знаний."""

    def __init__(self) -> None:
        self.client = get_ai_model_client()

    # ─────────────────────────────────────────────────────────────────────
    # 1. LLM декомпозиция
    # ─────────────────────────────────────────────────────────────────────
    async def _call_decomposition_llm(self, goal_text: str) -> Dict[str, Any]:
        """Запрашивает дерево декомпозиции у LLM и парсит JSON.

        Модель нестабильна: иногда возвращает битый/обрезанный JSON. Поэтому
        при неудаче парсинга запрос повторяется (до 3 попыток) с чуть большей
        температурой, а сырой ответ логируется для диагностики.
        """
        prompt = build_goal_decomposition_prompt(goal_text)
        last_error: Optional[str] = None
        for attempt in range(1, 4):
            result = self.client.generate_text(
                model_id=DEFAULT_MODEL,
                prompt=prompt,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=0.2 + (attempt - 1) * 0.4,
                enable_chunking=False,
                timeout=DEFAULT_TIMEOUT,
                extra_body={"thinking": False},
            )
            if not result.get("success"):
                last_error = f"LLM декомпозиции недоступен: {result.get('message')}"
                logger.warning(
                    "goal_decomposition попытка %d: %s", attempt, last_error
                )
                continue
            generated = result.get("generated_text", "")
            try:
                return self._parse_goal_json(generated)
            except RuntimeError as exc:
                last_error = str(exc)
                preview = generated.strip().replace("\n", " ")[:300]
                logger.warning(
                    "goal_decomposition попытка %d: парсинг не удался. "
                    "tokens_out=%s preview=%r",
                    attempt,
                    result.get("output_tokens"),
                    preview,
                )
        raise RuntimeError(last_error or "Не удалось декомпозировать цель")

    @staticmethod
    def _parse_goal_json(text: str) -> Dict[str, Any]:
        """Извлекает JSON-дерево декомпозиции из ответа LLM."""
        text = (text or "").strip()
        # 1. Убираем BOM и markdown-fence.
        if text.startswith("\ufeff"):
            text = text[1:].lstrip()
        m = _JSON_FENCE_RE.search(text)
        if m:
            text = m.group(1).strip()
        # 2. Пробуем распарсить как есть (с нормализацией мусора).
        cleaned = _sanitize_json(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # 3. Ищем первый { ... } сбалансированный объект, пробуя каждый.
        start = text.find("{")
        while start >= 0:
            end = _balanced_object_end(text, start)  # реализация ниже
            if end >= 0:
                candidate = text[start:end + 1]
                try:
                    return json.loads(_sanitize_json(candidate))
                except json.JSONDecodeError:
                    start = text.find("{", start + 1)
                    continue
            else:
                break
        raise RuntimeError("Не удалось распарсить JSON-дерево декомпозиции цели")

    # ─────────────────────────────────────────────────────────────────────
    # 2. Валидация дерева
    # ─────────────────────────────────────────────────────────────────────
    def _validate_tree(self, tree: Dict[str, Any]) -> None:
        items = tree.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("Дерево декомпозиции пустое (нет items)")
        # Корень — единственный item без parent_id (level 0).
        roots = [it for it in items if it.get("parent_id") is None]
        if not roots:
            raise ValueError("Нет корневого элемента плана (без parent_id)")
        ids = {it.get("id") for it in items}
        for it in items:
            pid = it.get("parent_id")
            if pid is not None and pid not in ids:
                raise ValueError(f"Пункт {it.get('id')} ссылается на несуществующий родителя {pid}")
        # Заглушка: если goal пуст — использовать text корня.
        if not tree.get("goal"):
            tree["goal"] = roots[0].get("text", "")

    # ─────────────────────────────────────────────────────────────────────
    # 3. Дерево плана -> текст для формализации (вход DSL-промпта)
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def _tree_to_lines(tree: Dict[str, Any]) -> str:
        """Строит маркированный список пунктов плана с метками ``[item:ID]``.

        Каждая строка — один пункт, порядок — дерево (parent перед детьми).
        В таком виде текст подаётся в DSL-промпт формализации целей, а по
        меткам ``item:<ID>`` факты привязываются к пунктам дерева.
        """
        items = tree.get("items", [])
        if not items:
            return ""

        # parent_id -> [children]
        children: Dict[Optional[str], List[Dict[str, Any]]] = {}
        for it in items:
            children.setdefault(it.get("parent_id"), []).append(it)

        lines: List[str] = []
        seen: set = set()

        def walk(pid: Optional[str]) -> None:
            for it in children.get(pid, []):
                iid = it.get("id")
                if not iid or iid in seen:
                    continue
                seen.add(iid)
                text = (it.get("text") or "").strip()
                if text:
                    lines.append(f"[item:{iid}] {text}")
                walk(iid)

        # Корень включаем через children[None].
        walk(None)
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # 4. Формализация пунктов через СУЩЕСТВУЮЩИЙ DSL-промпт
    # ─────────────────────────────────────────────────────────────────────
    async def _call_goal_plan_formalize(
        self,
        plan_text: str,
        plan_title: str,
        chunk_size: int = 8,
    ) -> List[Dict[str, Any]]:
        """Формализует текст плана в атомарные утверждения (T4-блоки).

        Переиспользует DSL-формат вывода и парсер ``parse_dsl_text``; промпт
        формализации не дублируется (используется существующий построитель
        ``build_goal_plan_dsl_prompt``). Большие планы разбиваются на чанки по
        ``chunk_size`` пунктов, чтобы один вызов LLM не упирался в лимит токенов
        (иначе модель возвращает пустой ``content`` с ``finish_reason=length``).

        Возвращает список фактов с полями item_id/subject_text/predicate/
        object_text после постобработки (отброс ``none``, разбиение
        ``sub/obj`` с союзом ``and``).
        """
        from .llm_triplet_extraction_prompt_dsl import build_goal_plan_dsl_prompt
        from tools.llm_extract.dsl_parser import parse_dsl_text

        raw_lines = [ln for ln in (plan_text or "").splitlines() if ln.strip()]
        if not raw_lines:
            return []
        chunks = list(_chunks(raw_lines, chunk_size))

        all_facts: List[Dict[str, Any]] = []
        last_error: Optional[str] = None
        for ci, chunk_lines in enumerate(chunks, start=1):
            chunk_text = "\n".join(chunk_lines)
            prompt = build_goal_plan_dsl_prompt(
                plan_title=plan_title, plan_lines=chunk_text
            )
            for attempt in range(1, 4):
                result = self.client.generate_text(
                    model_id=DEFAULT_MODEL,
                    prompt=prompt,
                    max_tokens=DEFAULT_MAX_TOKENS,
                    temperature=DEFAULT_TEMPERATURE + (attempt - 1) * 0.4,
                    enable_chunking=False,
                    timeout=DEFAULT_TIMEOUT,
                    extra_body={"thinking": False},
                )
                if not result.get("success"):
                    last_error = f"LLM формализации недоступен: {result.get('message')}"
                    logger.warning(
                        "goal_plan формализация чанк %d/%d попытка %d: %s",
                        ci, len(chunks), attempt, last_error,
                    )
                    continue
                generated = result.get("generated_text", "")
                blocks = parse_dsl_text(generated)
                facts = self._facts_from_dsl_blocks(blocks)
                if facts:
                    all_facts.extend(facts)
                    break
                last_error = "Формализация плана не вернула ни одного утверждения"
                preview = generated.strip().replace("\n", " ")[:300]
                logger.warning(
                    "goal_plan формализация чанк %d/%d попытка %d: пусто. "
                    "tokens_out=%s preview=%r",
                    ci, len(chunks), attempt,
                    result.get("output_tokens"),
                    preview,
                )
        if not all_facts:
            raise RuntimeError(last_error or "Не удалось формализовать план")
        return all_facts

    @staticmethod
    def _facts_from_dsl_blocks(
        blocks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Извлекает факты плана из T4-блоков DSL (привязка по ``ctx=item:ID``).

        Постобработка:
          - отбрасывает тривиальные самозаголовки ``X -> is -> goal/task/...``;
          - отбрасывает «пустые» значения subj/pred/obj (``none``/``null``/
            ``-``/``N/A`` и т.п.);
          - разбивает subj/obj с союзом ``and``/``и``/``&``/``/`` на отдельные
            атомарные факты (по одному на каждый элемент списка).
        """
        facts: List[Dict[str, Any]] = []
        for b in blocks:
            if int(b.get("blockType", 0)) != 4:
                continue
            data = b.get("data") or {}
            ctx = str(data.get("context") or "").strip()
            subj = str(data.get("subject") or "").strip()
            pred = str(data.get("predicate") or "").strip()
            obj = str(data.get("object") or "").strip()
            if not (ctx and subj and pred and obj):
                continue
            if _is_blank_value(subj) or _is_blank_value(pred) or _is_blank_value(obj):
                continue
            if pred.strip().lower() == "is" and obj.strip().lower() in {
                "goal", "sub_goal", "task", "action", "step",
            }:
                # Защита от тривиальных самозаголовков из текста пункта.
                continue
            m = re.search(r"item:([\w.]+)", ctx)
            if not m:
                continue
            item_id = m.group(1)
            subj_parts = _split_conjoined(subj)
            obj_parts = _split_conjoined(obj)
            # Декартово произведение: каждый subj с каждым obj.
            for s in subj_parts:
                for o in obj_parts:
                    facts.append({
                        "item_id": item_id,
                        "subject_text": s,
                        "predicate": pred,
                        "object_text": o,
                    })
        return facts

    # ─────────────────────────────────────────────────────────────────────
    # 5. Дерево плана + извлечённые факты -> KnowledgeStatement c UUID-ссылками
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def _blocks_to_plan_statements(
        tree: Dict[str, Any],
        facts: List[Dict[str, Any]],
        user_uid: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Строит KnowledgeStatement из дерева плана и извлечённых фактов.

        КАЖДЫЙ пункт дерева декомпозиции становится ОДНИМ атомарным
        утверждением ``subj → pred → obj``, извлечённым из его текста
        (формализация не выдаёт тривиальные ``текст → is → kind``). Иерархия —
        связующие META-триплеты ``decomposed_into`` (subject/object_type
        == 'statement') между uid ребёнка и родителя.

        Гарантирует, что цель и все подпункты плана появляются на карте знаний
        как связная DAG-компонента: uid назначается факту по метке
        ``item:<ID>``, а рёбра строятся из дерева (child → parent).
        """
        items = tree.get("items", [])
        statements: List[Dict[str, Any]] = []
        item_uids: Dict[str, str] = {}
        order = 0

        # 1. Формализованные факты -> атомарные утверждения (привязка по item).
        facts_by_item: Dict[str, List[Dict[str, Any]]] = {}
        for f in facts:
            facts_by_item.setdefault(f.get("item_id"), []).append(f)
        item_all_uids: Dict[str, List[str]] = {}
        missing: List[str] = []
        for it in items:
            iid = it.get("id")
            item_facts = facts_by_item.get(iid)
            if not item_facts:
                missing.append(str(iid))
                continue
            # Первый факт пункта получает «канонический» uid, по которому
            # строятся рёбра decomposed_into (если фактов несколько — это
            # and-разбиение; все факты остаются в графе отдельными блоками).
            first_uid = _uuid8()
            item_uids[iid] = first_uid
            item_all_uids[iid] = []
            for idx, fact in enumerate(item_facts):
                uid = first_uid if idx == 0 else _uuid8()
                item_all_uids[iid].append(uid)
                statements.append({
                    "uid": uid,
                    "subject_text": fact["subject_text"],
                    "predicate": fact["predicate"],
                    "object_text": fact["object_text"],
                    "subject_type": "concept",
                    "object_type": "concept",
                    "type": "FACT",
                    "is_goal": bool(int(it.get("level", 0)) == 0),
                    "level": int(it.get("level", 1)),
                    "source_block_id": "",
                    "sort_order": order,
                    "created_by_uid": user_uid,
                })
                order += 1

# 2. Связующие META-триплеты decomposed_into (ребёнок -> родитель).
        # Ребёнок ссылается на родителя: стрелка указывает на более абстрактный
        # уровень, визуально показывая декомпозицию как "восхождение к цели".
        for it in items:
            pid = it.get("parent_id")
            parent_uids = item_all_uids.get(pid) if pid is not None else None
            child_uids = item_all_uids.get(it["id"]) or []
            if not parent_uids or not child_uids:
                continue
            for cuid in child_uids:
                for puid in parent_uids:
                    if puid == cuid:
                        continue
                    statements.append({
                        "uid": _uuid8(),
                        "subject_text": cuid,
                        "predicate": _PREDICATE_DECOMPOSED_INTO,
                        "object_text": puid,
                        "subject_type": "statement",
                        "object_type": "statement",
                        "type": "META",
                        "is_goal": False,
                        "level": -1,
                        "source_block_id": "",
                        "sort_order": 100_000 + order,
                        "created_by_uid": user_uid,
                    })
                    order += 1

        if missing:
            logger.warning(
                "goal_plan формализация пропустила пункты (нет факта): %s",
                ", ".join(missing),
            )

        return statements

    # ─────────────────────────────────────────────────────────────────────
    # 6. Сохранение в Neo4j как отдельный Document
    # ─────────────────────────────────────────────────────────────────────
    def _save_plan_to_neo4j(
        self,
        plan_id: str,
        plan_title: str,
        statements: List[Dict[str, Any]],
        user_uid: Optional[str],
    ) -> None:
        """Создаёт (или пересоздаёт) Document-план и его KnowledgeStatement."""
        now = datetime.now(timezone.utc).isoformat()

        # Удаляем старый план с тем же id (идемпотентность повторных декомпозиций).
        db.cypher_query(
            "MATCH (d:Document {uid: $uid, doc_type: 'goal_plan'}) "
            "OPTIONAL MATCH (d)-[r:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "DETACH DELETE r, s, d",
            {"uid": plan_id},
        )

        # Создаём Document.
        db.cypher_query(
            "CREATE (d:Document {uid: $uid, title: $title, doc_type: 'goal_plan', "
            "processing_status: 'annotated', upload_date: datetime($now), "
            "edit_date: datetime($now)})",
            {"uid": plan_id, "title": plan_title, "now": now},
        )

        if not statements:
            return

        batch: List[Dict[str, Any]] = []
        for st in statements:
            batch.append({
                "uid": st["uid"],
                "subj": st["subject_text"],
                "pred": st["predicate"],
                "obj": st["object_text"],
                "subj_type": st["subject_type"],
                "obj_type": st["object_type"],
                "type": st["type"],
                "is_goal": st.get("is_goal", False),
                "level": st.get("level", 1),
                "source_block": st.get("source_block_id", ""),
                "order": st.get("sort_order", 0),
                "creator": st.get("created_by_uid"),
            })
        for chunk in _chunks(batch, 500):
            db.cypher_query(
                "MATCH (d:Document {uid: $doc_id}) "
                "UNWIND $batch AS item "
                "CREATE (s:KnowledgeStatement {uid: item.uid, subject_text: item.subj, "
                "predicate: item.pred, object_text: item.obj, "
                "subject_type: item.subj_type, object_type: item.obj_type, "
                "type: item.type, is_goal: item.is_goal, level: item.level, "
                "sourceBlockId: item.source_block, sort_order: item.order, "
                "created_by_uid: item.creator}) "
                "CREATE (d)-[:HAS_STATEMENT]->(s)",
                {"batch": chunk, "doc_id": plan_id},
            )

    # ─────────────────────────────────────────────────────────────────────
    # 7. Построение блоков/рёбер для отображения на карте
    # ─────────────────────────────────────────────────────────────────────
    @staticmethod
    def _build_graph_component(statements: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Строит подмножество карты для плана (blocks + links).

        Семантика:
          - Каждый atomарный триплет (subject/object_type == 'concept') — БЛОК
            на карте (текст-триплет).
          - Каждое мета-утверждение (statement-типы: decomposed_into) — РЕБРО
            между блоками: subject_text (uid ребёнка) -> object_text (uid родителя).

        Координаты — простая сетка: layer по уровню дерева, строка по индексу
        внутри слоя (без обращения к Rust — план всегда отдельная компонента,
        укладываемая самостоятельно).
        """
        # Блоки: только концепт-триплеты (содержательные).
        node_rows: List[Dict[str, Any]] = [
            st for st in statements
            if st["subject_type"] != "statement" and st["object_type"] != "statement"
        ]

        # Рёбра: из meta-утверждений (subject/object_type == 'statement').
        # Мета-триплет (subject_text=child_uid, object_text=parent_uid) — это
        # РЕБРО child_uid -> parent_uid напрямую, без промежуточного узла
        # (ребёнок ссылается на родителя: стрелка указывает к цели).
        edges: List[tuple[str, str]] = []
        for st in statements:
            if st["subject_type"] == "statement" and st["object_type"] == "statement":
                edges.append((st["subject_text"], st["object_text"]))

        # Слой каждого блока: берём level из statement (0=цель, 1..N=уклон).
        layer_of: Dict[str, int] = {}
        for n in node_rows:
            layer_of[n["uid"]] = int(n.get("level", 1))
        changed = True
        n_iter = 0
        while changed and n_iter < 50:
            changed = False
            n_iter += 1
            # Раскладка по слоям строится по рёбрам (child -> parent), но для
            # дерева цель слева, а потомки правее: ребёнок должен быть в слое
            # ПРАВЕЕ родителя. Здесь src=child, tgt=parent.
            for src, tgt in edges:
                if src not in layer_of or tgt not in layer_of:
                    continue
                src_layer = layer_of[src]
                tgt_layer = layer_of[tgt]
                # Родитель (tgt) должен быть ЛЕВЕЕ ребёнка (src).
                if src_layer <= tgt_layer:
                    layer_of[src] = tgt_layer + 1
                    changed = True

        # Укладка: колонка = layer, строка = индекс внутри слоя.
        cols: Dict[int, List[str]] = {}
        for n in node_rows:
            cols.setdefault(layer_of.get(n["uid"], 0), []).append(n["uid"])
        col_index: Dict[str, int] = {}
        for layer, uids in cols.items():
            for idx, uid in enumerate(uids):
                col_index[uid] = idx

        blocks: List[Dict[str, Any]] = []
        for n in node_rows:
            uid = n["uid"]
            layer = layer_of.get(uid, 0)
            idx = col_index.get(uid, 0)
            blocks.append({
                "id": uid,
                "uid": uid,
                "content": _display_content(n),
                "subject_text": n["subject_text"],
                "predicate": n["predicate"],
                "object_text": n["object_text"],
                "subject_type": "concept",
                "object_type": "concept",
                "x": float(layer) * (250 + 120),
                "y": float(idx) * (140 + 160),
                "layer": layer,
                "level": idx,
                "metadata": {"is_placeholder": False, "is_goal": bool(n.get("is_goal", False)), "level": int(n.get("level", 1))},
            })

        links: List[Dict[str, Any]] = []
        seen: set = set()
        for src, tgt in edges:
            # Ребро остаётся, только если оба конца — блоки на карте.
            if src not in layer_of or tgt not in layer_of:
                continue
            if (src, tgt) in seen:
                continue
            seen.add((src, tgt))
            links.append({"id": f"{src}-{tgt}", "source_id": src, "target_id": tgt})

        return blocks, links

    # ─────────────────────────────────────────────────────────────────────
    # Основной публичный вызов
    # ─────────────────────────────────────────────────────────────────────
    async def decompose(self, goal_text: str, user_uid: Optional[str] = None) -> Dict[str, Any]:
        """Полный пайплайн декомпозиции цели."""
        goal_text = goal_text.strip()
        if not goal_text:
            raise ValueError("Цель не может быть пустой")

        # 1. Декомпозиция.
        tree = await self._call_decomposition_llm(goal_text)
        self._validate_tree(tree)
        tree = self._normalize_tree(tree)

        # 2. Заголовок плана-документа.
        plan_title = _plan_title(tree)

        # 3. Формализация: каждый пункт -> одно атомарное утверждение.
        plan_lines = self._tree_to_lines(tree)
        facts = await self._call_goal_plan_formalize(plan_lines, plan_title)
        if not facts:
            raise RuntimeError(
                "Формализация плана не вернула ни одного утверждения"
            )

        # 4. Statement'ы плана (факты + META decomposed_into).
        plan_id = _uuid8()
        statements = self._blocks_to_plan_statements(tree, facts, user_uid)

        # 5. Сохранение в Neo4j.
        self._save_plan_to_neo4j(plan_id, plan_title, statements, user_uid)

        # 6. Блоки/рёбра для карты.
        blocks_out, links_out = self._build_graph_component(statements)

        return {
            "success": True,
            "tree": tree,
            "plan_id": plan_id,
            "blocks": blocks_out,
            "links": links_out,
            "message": "",
        }

    @staticmethod
    def _normalize_tree(tree: Dict[str, Any]) -> Dict[str, Any]:
        """Приводит items к каноничному виду (заполняет отсутствующие поля)."""
        items = tree.get("items", [])
        for it in items:
            it.setdefault("level", 0)
            it.setdefault("kind", "task")
            it.setdefault("rationale", "")
            it.setdefault("expected_outcome", None)
        ordered = sorted(items, key=lambda it: int(it.get("level", 0)))
        for it in ordered:
            if it.get("parent_id") is None:
                it["level"] = 0
                it["kind"] = "goal"
        tree["items"] = ordered
        return tree


def _chunks(lst: List[Any], n: int) -> Any:
    """Разбивает список на куски по n элементов."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _uuid8() -> str:
    from src.uuid8 import uuid8_str
    return uuid8_str()


def _plan_title(tree: Dict[str, Any]) -> str:
    goal = (tree.get("goal") or "").strip()
    return f"Goal Plan: {goal[:80]}"


def _display_content(st: Dict[str, Any]) -> str:
    """Человекочитаемый текст блока для карты."""
    s = st["subject_text"]
    p = st["predicate"]
    o = st["object_text"]
    if st["subject_type"] == "statement" or st["object_type"] == "statement":
        return f"{s} → {p} → {o}"
    if st.get("is_goal"):
        return f"🎯 {s}"
    return f"{s} → {p} → {o}"


def _delift(text: str) -> str:
    """Экранирует control-символы, мешающие json.loads (табуляции,
    переводы строк и прочие управляющие коды вне escape-последовательностей).

    Настоящий таб/новая строка внутри JSON-строк запрещены спецификацией;
    модель же часто вставляет их буквально. Заменяем их на пробелы как
    внутри строк, так и снаружи, но НЕ трогаем экранированные ``\\n``/``\\t``.
    """
    out: List[str] = []
    esc = False
    for ch in text:
        if esc:
            out.append(ch)
            esc = False
        elif ch == "\\":
            out.append(ch)
            esc = True
        elif ch in "\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\x0d":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _sanitize_json(text: str) -> str:
    """Пытается сделать из мусорного ответа LLM валидный JSON.

    1. Убирает trailing-comma перед `}`/`]`.
    2. Экранирует неконтролируемые control-символы (например, реальные
       переносы строк внутри строк), заменяя их пробелами.
    3. Оставляет текст как есть; если LLM вставил прозу снаружи — дальше
       разбираем сбалансированный объект.
    """
    t = _delift(text)
    # Убираем запятые перед закрывающими скобками (частая ошибка модели).
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    return t


def _balanced_object_end(text: str, start: int) -> int:
    """Возвращает индекс закрывающей `}` для `{` на позиции start, или -1."""
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


_BLANK_VALUES = {
    "", "none", "null", "nil", "na", "n/a", "-", "--", "—", "empty",
    "пусто", "нет", "нечего", "отсутствует",
}


def _is_blank_value(value: str) -> bool:
    """True, если значение — «пустышка» (none/null/na/— ...)."""
    return value.strip().lower() in _BLANK_VALUES


_CONJOIN_RE = re.compile(r"\s+(?:and|&|и)\s+", re.IGNORECASE)


def _split_conjoined(phrase: str) -> List[str]:
    """Разбивает фразу с союзом-списком на атомарные части.

    Работает только для списков, образованных союзом ``and``/``и``/``&``.
    Элементы списка могут разделять общий хвост (heads): последний элемент
    несёт общее существительное, которое дописывается предыдущим частям:

        "molecular and cellular hallmarks" ->
            ["molecular hallmarks", "cellular hallmarks"]

    Примеры: "federal and state laws" -> ["federal laws", "state laws"];
              "a and b"               -> ["a", "b"].
    """
    parts = [p.strip() for p in _CONJOIN_RE.split(phrase)]
    if len(parts) < 2:
        return [phrase]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return [phrase]
    last = parts[-1]
    # Общий хвост — всё, что в последней части следует после её первого слова.
    sp = last.find(" ")
    tail = last[sp:].strip() if sp >= 0 else ""
    out: List[str] = []
    for p in parts[:-1]:
        if tail and not p.endswith(tail):
            out.append(f"{p} {tail}".strip())
        else:
            out.append(p)
    out.append(last)
    return out
