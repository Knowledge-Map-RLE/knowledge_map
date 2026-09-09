"""
Layer: Services
Package: services.knowledge_triples_service
Responsibility: Чтение триплетов знаний (KnowledgeStatement) из Neo4j,
построение DAG-карты знаний на основе dependency edges (вычисляемых
DependencyEngine), вычисление укладки через Rust GraphLayoutService
(Sugiyama) и поиск изолированных триплетов для левой панели.

Каждый триплет — узел графа, идентифицируемый своим uid. Рёбра DAG
(bependency edges) вычисляются ДВИЖКОМ dependency_engine из semantic
структуры триплетов (а НЕ напрямую из UUID-ссылок subject/object),
после чего сохраняются в Neo4j как [:DEPENDS_ON].

См.:
  - services.dependency_engine.CandidateGenerator — правила Level 1-4
  - services.dependency_engine.SemanticVerifier — верификация правилами + LLM

Триплеты, не участвующие ни в одном ребре, не попадают на граф и отдаются
отдельным списком для левой панели.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from neomodel import db

from domain.models.dependency import DependencyEdge
from infrastructure.graph_layout_client import get_graph_layout_client
from services.dependency_engine import DependencyEngine, DependencyPersistence

logger = logging.getLogger(__name__)

# Предикаты, не несущие доменной структуры (служебные META-утверждения) —
# по аналогии с application/patterns/statement_graph.py.
_NOISE_PREDICATES = {"is_a", "contains", "related_to", "has"}

# Параметры укладки DAG карты триплетов. horizontal_gap/vertical_gap — это
# зазоры между краями блоков (расстояние учитывает ширину/высоту блока).
_TRIPLE_BLOCK_WIDTH = 250.0
_TRIPLE_BLOCK_HEIGHT = 140.0
_TRIPLE_HORIZONTAL_GAP = 120.0
_TRIPLE_VERTICAL_GAP = 160.0


class KnowledgeTriplesService:
    """Сервис для построения DAG-карты триплетов знаний."""

    async def _load_all_triples(self) -> Dict[str, Dict[str, Any]]:
        """Загружает все валидные триплеты KnowledgeStatement из Neo4j.

        Возвращает словарь {uid: triple}, где triple содержит текст субъекта,
        предикат, текст объекта, их типы и sourceBlockId. Невалидные (пустой
        предикат/субъект/объект) и служебные META-предикаты отбрасываются.
        """
        query = """
        MATCH (s:KnowledgeStatement)
        WITH s, coalesce(s.subject_text, '') AS subj,
             coalesce(s.predicate, '') AS pred,
             coalesce(s.object_text, '') AS obj
        WHERE trim(pred) <> '' AND trim(subj) <> '' AND trim(obj) <> ''
        RETURN s.uid AS uid,
               coalesce(s.subject_type, 'concept') AS subject_type,
               subj AS subject_text,
               pred AS predicate,
               coalesce(s.object_type, 'concept') AS object_type,
               obj AS object_text,
               coalesce(s.type, 'FACT') AS type,
               coalesce(s.sourceBlockId, '') AS source_block_id,
               coalesce(s.is_goal, false) AS is_goal
        """
        result, _ = db.cypher_query(query)
        triples: Dict[str, Dict[str, Any]] = {}
        for row in result:
            uid = str(row[0])
            pred = str(row[3] or "").strip().lower()
            if pred in _NOISE_PREDICATES:
                continue
            triples[uid] = {
                "uid": uid,
                "subject_type": str(row[1] or "concept").strip().lower(),
                "subject_text": str(row[2] or "").strip(),
                "predicate": str(row[3] or "").strip(),
                "object_type": str(row[4] or "concept").strip().lower(),
                "object_text": str(row[5] or "").strip(),
                "type": str(row[6] or "FACT"),
                "source_block_id": str(row[7] or "").strip(),
                "is_goal": bool(row[8]),
            }
        return triples

    @staticmethod
    def _collect_references(triples: Dict[str, Dict[str, Any]]) -> List[DependencyEdge]:
        """Загружает dependency edges из Neo4j (вычисленные DependencyEngine).

        Рёбра [:DEPENDS_ON] строятся движком dependency_engine (rules + LLM)
        из семантической структуры триплетов, а НЕ напрямую из UUID-ссылок.

        Если рёбра в Neo4j ещё не вычислены (незасеяны) — возвращает пустой
        список: карта покажет только plan_uids (декомпозиция целей).

        Возвращает список DependencyEdge.
        """
        return DependencyPersistence.load_edges()

    @staticmethod
    def _collect_goal_references(
        triples: Dict[str, Dict[str, Any]],
    ) -> List[DependencyEdge]:
        """Рёбра декомпозиции целей (META decomposed_into) всегда актуальны.

        Даже до пересчёта dependency graph необходимости декомпозиция целей
        (decomposed_into) показывается на карте: это гарантирует, что план
        цели виден сразу после создания.
        """
        edges: List[DependencyEdge] = []
        for stmt in triples.values():
            if stmt["type"] != "META":
                continue
            if (stmt.get("predicate") or "").lower() != "decomposed_into":
                continue
            if stmt.get("subject_type") != "statement":
                continue
            if stmt.get("object_type") != "statement":
                continue
            child_uid = stmt.get("subject_text", "")
            parent_uid = stmt.get("object_text", "")
            if child_uid and parent_uid:
                from domain.models.dependency import DependencyType, DiscoveryMethod
                edges.append(DependencyEdge(
                    source_uid=child_uid,
                    target_uid=parent_uid,
                    dependency_type=DependencyType.GOAL_DIRECTED,
                    confidence=1.0,
                    discovery_method=DiscoveryMethod.GOAL_DECOMPOSITION,
                    is_verified=True,
                ))
        return edges

    @staticmethod
    def _build_block_names(triples: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """Маппинг блок_uid → имя блока (subject_text первого триплета блока)."""
        block_to_statements: Dict[str, List[str]] = {}
        for stmt in triples.values():
            sbid = stmt.get("source_block_id", "")
            if sbid:
                block_to_statements.setdefault(sbid, []).append(stmt["uid"])

        block_names: Dict[str, str] = {}
        for sbid, stmt_uids in block_to_statements.items():
            for uid_ in stmt_uids:
                st = triples.get(uid_)
                if st and st["subject_text"]:
                    block_names[sbid] = st["subject_text"]
                    break
        return block_names

    @staticmethod
    def _reposition_by_ranks(
        positions: Dict[str, Any],
        block_width: float,
        block_height: float,
        horizontal_gap: float,
        vertical_gap: float,
    ) -> Dict[str, Any]:
        """Пересчитывает (x, y) вершин из их рангов (layer, level).

        Текущая сборка Rust-воркера всегда возвращает фиксированную сетку
        (x = layer * 240, y = level * 130) независимо от переданных размеров
        блоков и зазоров. Чтобы расстояние между блоками учитывало их ширину
        (block_width + horizontal_gap между колонками, block_height +
        vertical_gap между уровнями), координаты пересчитываются из рангов.
        """
        result: Dict[str, Any] = {}
        for uid, pos in positions.items():
            result[uid] = (
                pos.layer * (block_width + horizontal_gap),
                pos.level * (block_height + vertical_gap),
            )
        return result

    async def get_knowledge_triples(
        self,
        isolated_limit: int = 200,
    ) -> Dict[str, Any]:
        """Возвращает DAG-карту триплетов и список изолированных триплетов.

        Рёбра графа — dependency edges (DependencyEngine), вычисленные из
        семантической структуры утверждений и сохранённые в Neo4j как
        [:DEPENDS_ON]. UUID-ссылки внутри утверждений рёбрами НЕ становятся.

        Returns:
            {
              success: bool,
              blocks: [...],   # триплеты, участвующие в DAG (с x/y от Rust)
              links: [...],    # dependency edges с metadata (type/confidence)
              isolated: [...], # триплеты без связей (для левой панели)
              isolated_total: int,
              connected_total: int,
              isolated_limit: int,
            }
        """
        try:
            triples = await self._load_all_triples()
            if not triples:
                return {
                    "success": True,
                    "blocks": [],
                    "links": [],
                    "isolated": [],
                    "isolated_total": 0,
                    "connected_total": 0,
                    "isolated_limit": isolated_limit,
                }

            # Dependency edges: вычисленные движком dependency_engine rёbra
            # (rules + LLM) + всегда актуальные рёбра декомпозиции целей.
            dependency_edges = self._collect_references(triples)
            goal_edges = self._collect_goal_references(triples)
            all_edges = list(dependency_edges) + list(goal_edges)
            block_names = self._build_block_names(triples)

            # uid утверждений, входящих в план декомпозиции (цель и подпункты):
            # они связаны META-триплетами decomposed_into.
            plan_uids: set[str] = set()
            for stmt in triples.values():
                if (
                    stmt["type"] == "META"
                    and stmt["subject_type"] == "statement"
                    and stmt["object_type"] == "statement"
                ):
                    plan_uids.add(stmt["subject_text"])
                    plan_uids.add(stmt["object_text"])
                if bool(stmt.get("is_goal", False)):
                    plan_uids.add(stmt["uid"])

            # Множество uid, задействованных в DAG: source + target каждого ребра.
            connected_uids: set[str] = set()
            edges: List[Dict[str, Any]] = []
            seen = set()
            for e in all_edges:
                key = (e.source_uid, e.target_uid)
                if key in seen:
                    continue
                seen.add(key)
                if e.source_uid in triples and e.target_uid in triples:
                    connected_uids.add(e.source_uid)
                    connected_uids.add(e.target_uid)
                    edges.append({
                        "source_id": e.source_uid,
                        "target_id": e.target_uid,
                        "dependency_type": e.dependency_type.value,
                        "confidence": e.confidence,
                        "discovery_method": e.discovery_method.value,
                        "is_verified": e.is_verified,
                    })

            # Разделяем граф на две части:
            #   - план декомпозиции (рёбра, где оба конца — блоки плана);
            #   - всё остальное (обычные dependency edges).
            # Каждая часть укладывается самостоятельно, после чего план
            # сдвигается вправо от самой правой точки обычной части.
            plan_edge_keys = {
                (e["source_id"], e["target_id"])
                for e in edges
                if e["source_id"] in plan_uids and e["target_id"] in plan_uids
            }
            regular_edges = [e for e in edges if (e["source_id"], e["target_id"]) not in plan_edge_keys]
            regular_uids = connected_uids - plan_uids
            plan_uids_in_graph = connected_uids & plan_uids

            # Укладка обычной части DAG через Rust GraphLayoutService (Sugiyama).
            regular_positions: Dict[str, Any] = {}
            if regular_edges:
                layout_client = get_graph_layout_client()
                regular_positions = await layout_client.compute_layout(
                    regular_edges,
                    block_width=_TRIPLE_BLOCK_WIDTH,
                    block_height=_TRIPLE_BLOCK_HEIGHT,
                    horizontal_gap=_TRIPLE_HORIZONTAL_GAP,
                    vertical_gap=_TRIPLE_VERTICAL_GAP,
                    reduce_crossings=True,
                    convert_to_dag=True,
                )
                # Rust-воркер (порт 50051) в текущей сборке игнорирует
                # block_width/horizontal_gap и возвращает фиксированную сетку
                # (x = layer*240, y = level*130), из-за чего блоки шириной
                # 250px накладываются друг на друга. Пересчитываем координаты
                # из рангов (layer, level), чтобы шаг колонок учитывал ширину
                # блока и зазор между его краями.
                regular_positions = self._reposition_by_ranks(
                    regular_positions,
                    _TRIPLE_BLOCK_WIDTH,
                    _TRIPLE_BLOCK_HEIGHT,
                    _TRIPLE_HORIZONTAL_GAP,
                    _TRIPLE_VERTICAL_GAP,
                )

            # Укладка плана отдельной компонентой.
            plan_positions: Dict[str, Any] = {}
            if plan_edges := [e for e in edges if (e["source_id"], e["target_id"]) in plan_edge_keys]:
                layout_client = get_graph_layout_client()
                plan_positions = await layout_client.compute_layout(
                    plan_edges,
                    block_width=_TRIPLE_BLOCK_WIDTH,
                    block_height=_TRIPLE_BLOCK_HEIGHT,
                    horizontal_gap=_TRIPLE_HORIZONTAL_GAP,
                    vertical_gap=_TRIPLE_VERTICAL_GAP,
                    reduce_crossings=True,
                    convert_to_dag=True,
                )
                plan_positions = self._reposition_by_ranks(
                    plan_positions,
                    _TRIPLE_BLOCK_WIDTH,
                    _TRIPLE_BLOCK_HEIGHT,
                    _TRIPLE_HORIZONTAL_GAP,
                    _TRIPLE_VERTICAL_GAP,
                )
            # Одиночные блоки плана без рёбер (цель без подпунктов) — столбец.
            for i, uid_ in enumerate(sorted(plan_uids_in_graph)):
                if uid_ not in plan_positions:
                    plan_positions[uid_] = (
                        0.0,
                        float(i) * (_TRIPLE_BLOCK_HEIGHT + _TRIPLE_VERTICAL_GAP),
                    )

            # Сдвиг плана вправо от правого края обычной части + зазор.
            max_regular_x: float = 0.0
            if regular_positions:
                max_regular_x = max(
                    float(x) + _TRIPLE_BLOCK_WIDTH
                    for x, _ in regular_positions.values()
                )
            offset_x = max_regular_x + _TRIPLE_HORIZONTAL_GAP
            for uid_ in list(plan_positions.keys()):
                x, y = plan_positions[uid_]
                plan_positions[uid_] = (float(x) + offset_x, float(y))

            # Построение блоков на графе: сначала обычные, затем план.
            def build_block(uid_: str, pos_map: Dict[str, Any]) -> Dict[str, Any]:
                stmt = triples.get(uid_)
                x, y = pos_map.get(uid_, (0.0, 0.0))
                x = float(x)
                y = float(y)
                return {
                    "id": uid_,
                    "content": self._render_content(uid_, stmt, triples, block_names),
                    "uid": uid_,
                    "subject_type": stmt["subject_type"] if stmt else "statement",
                    "subject_text": stmt["subject_text"] if stmt else uid_,
                    "predicate": stmt["predicate"] if stmt else "",
                    "object_type": stmt["object_type"] if stmt else "",
                    "object_text": stmt["object_text"] if stmt else "",
                    "x": x,
                    "y": y,
                    "layer": 0,
                    "level": 0,
                    "metadata": {
                        "is_placeholder": stmt is None,
                        "is_goal": bool(stmt.get("is_goal", False)) if stmt else False,
                        "is_plan": uid_ in plan_uids,
                    },
                }

            blocks: List[Dict[str, Any]] = []
            for uid_ in sorted(regular_uids):
                blocks.append(build_block(uid_, regular_positions))
            for uid_ in sorted(plan_uids_in_graph):
                blocks.append(build_block(uid_, plan_positions))

            links: List[Dict[str, Any]] = []
            for e in edges:
                if e["source_id"] in connected_uids and e["target_id"] in connected_uids:
                    links.append({
                        "id": f"{e['source_id']}->{e['target_id']}",
                        "source_id": e["source_id"],
                        "target_id": e["target_id"],
                        "metadata": {
                            "dependency_type": e.get("dependency_type", "causal"),
                            "confidence": e.get("confidence", 1.0),
                            "discovery_method": e.get("discovery_method", "exact_match"),
                            "is_verified": e.get("is_verified", False),
                        },
                    })

            # Изолированные триплеты (не участвуют ни в одном ребре DAG).
            # META-триплеты (связующие, например decomposed_into) не показываются
            # в левой панели — это служебные рёбра декомпозиции целей.
            isolated_uids = sorted(
                uid_
                for uid_ in triples
                if uid_ not in connected_uids and triples[uid_]["type"] != "META"
            )
            isolated = [
                {
                    "id": uid_,
                    "uid": uid_,
                    "content": self._render_content(uid_, triples[uid_], triples, block_names),
                    "subject_type": triples[uid_]["subject_type"],
                    "subject_text": triples[uid_]["subject_text"],
                    "predicate": triples[uid_]["predicate"],
                    "object_type": triples[uid_]["object_type"],
                    "object_text": triples[uid_]["object_text"],
                }
                for uid_ in isolated_uids[:isolated_limit]
            ]

            logger.info(
                "knowledge_triples: triples=%d connected=%d links=%d isolated_total=%d",
                len(triples),
                len(connected_uids),
                len(links),
                len(isolated_uids),
            )

            return {
                "success": True,
                "blocks": blocks,
                "links": links,
                "isolated": isolated,
                "isolated_total": len(isolated_uids),
                "connected_total": len(connected_uids),
                "isolated_limit": isolated_limit,
            }
        except Exception as e:
            logger.error(f"Error in knowledge triples: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def rebuild_dependencies(self, use_llm: bool = True) -> Dict[str, Any]:
        """Пересчитывает dependency graph карты знаний.

        Запускает DependencyEngine (Candidate Generator + Semantic Verifier),
        сохраняет полученные dependency edges в Neo4j как [:DEPENDS_ON]
        и возвращает статистику.

        Args:
            use_llm: использовать LLM для верификации неоднозначных кандидатов.

        Returns:
            {
              success: bool,
              triples_total: int,
              candidates: int,
              verified: int,
              saved: int,
              use_llm: bool,
            }
        """
        try:
            triples = await self._load_all_triples()
            engine = DependencyEngine()

            verified_edges = await engine.build_dependency_graph(
                triples=triples,
                use_llm=use_llm,
            )
            saved = engine.save(verified_edges)

            logger.info(
                "rebuild_dependencies: triples=%d verified=%d saved=%d use_llm=%s",
                len(triples),
                len(verified_edges),
                saved,
                use_llm,
            )

            return {
                "success": True,
                "triples_total": len(triples),
                "verified": len(verified_edges),
                "saved": saved,
                "use_llm": use_llm,
            }
        except Exception as e:
            logger.error(f"Error in rebuild_dependencies: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def search_isolated_triples(
        self,
        q: str = "",
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Поиск по изолированным (не участвующим в DAG) триплетам.

        Поиск активируется при введённых 3+ символах (CONTAINS по содержимому
        триплета: subject/predicate/object/uid). При пустом/коротком запросе
        возвращается упорядоченный список (по uid) с пагинацией.
        """
        try:
            triples = await self._load_all_triples()
            dependency_edges = self._collect_references(triples)
            goal_edges = self._collect_goal_references(triples)
            block_names = self._build_block_names(triples)

            connected_uids: set[str] = set()
            for e in list(dependency_edges) + list(goal_edges):
                if e.source_uid in triples:
                    connected_uids.add(e.source_uid)
                if e.target_uid in triples:
                    connected_uids.add(e.target_uid)

            isolated_uids = sorted(
                uid_
                for uid_ in triples
                if uid_ not in connected_uids and triples[uid_]["type"] != "META"
            )

            # Строка для полнотекстового поиска.
            def searchable(stmt: Dict[str, Any]) -> str:
                return (
                    f"{stmt['uid']} {stmt['subject_text']} {stmt['predicate']} "
                    f"{stmt['object_text']}"
                ).lower()

            query = q.strip().lower()
            matched_ids = []
            if len(query) >= 3:
                matched_ids = [
                    uid_
                    for uid_ in isolated_uids
                    if query in searchable(triples[uid_])
                ]
            else:
                matched_ids = isolated_uids

            total = len(matched_ids)
            page_ids = matched_ids[skip: skip + limit]
            items = [
                {
                    "id": uid_,
                    "uid": uid_,
                    "content": self._render_content(uid_, triples[uid_], triples, block_names),
                    "subject_type": triples[uid_]["subject_type"],
                    "subject_text": triples[uid_]["subject_text"],
                    "predicate": triples[uid_]["predicate"],
                    "object_type": triples[uid_]["object_type"],
                    "object_text": triples[uid_]["object_text"],
                }
                for uid_ in page_ids
            ]

            logger.info(
                "search_isolated_triples: q=%r skip=%d limit=%d -> %d/%d",
                query,
                skip,
                limit,
                len(items),
                total,
            )

            return {
                "success": True,
                "total_count": total,
                "skip": skip,
                "limit": limit,
                "query": query,
                "items": items,
            }
        except Exception as e:
            logger.error(f"Error in search_isolated_triples: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    def _render_content(
        uid: str,
        stmt: Optional[Dict[str, Any]],
        triples: Dict[str, Dict[str, Any]],
        block_names: Optional[Dict[str, str]] = None,
    ) -> str:
        """Формирует читаемое содержимое триплета.

        Первая строка — uid. Вторая — «субъект → предикат → объект».
        Если объект/субъект — UUID-ссылка на блок (step/result/sequence),
        подставляется имя блока и uid в скобках: «name (uid)».
        Если объект/субъект — UUID-ссылка на утверждение, выводится
        зарезолвленный текст утверждения.
        """
        if stmt is None:
            return f"{uid}\n{uid}"

        if block_names is None:
            block_names = {}

        _STRUCTURAL_PREDICATES = {"step", "result", "sequence"}

        subj = stmt["subject_text"]
        obj = stmt["object_text"]
        pred = stmt["predicate"]

        # Субъект: если это statement-ссылка → резолвим.
        if stmt["subject_type"] == "statement":
            subj = _resolve_statement_ref(subj, triples)

        # Объект: приоритет — резолв блочного UUID (step/result/sequence),
        # иначе — statement-ссылка.
        if pred.lower() in _STRUCTURAL_PREDICATES and obj in block_names:
            obj = f"{block_names[obj]} ({obj})"
        elif stmt["object_type"] == "statement":
            obj = _resolve_statement_ref(obj, triples)

        return f"{uid}\n{subj} → {pred} → {obj}"


def _resolve_statement_ref(ref_uid: str, triples: Dict[str, Dict[str, Any]]) -> str:
    """Резолвит UUID-ссылку на утверждение в читаемый текст.

    Возвращает '<UUID> («содержимое утверждения»)'. Если утверждение с таким
    uid не найдено в БД — просто '<UUID>'.
    """
    target = triples.get(ref_uid)
    if target is None:
        return ref_uid
    resolved = (
        f"{target['subject_text']} → {target['predicate']} → {target['object_text']}"
    )
    return f"{ref_uid} («{resolved}»)"
