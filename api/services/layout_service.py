"""Сервис для работы с укладкой графов"""
import logging
from typing import List, Dict, Any, Optional

from fastapi import HTTPException
from neomodel import db, DoesNotExist

from src.models import Block
from . import get_layout_client, LayoutOptions

logger = logging.getLogger(__name__)


class LayoutService:
    """Сервис для работы с укладкой графов"""
    
    def __init__(self):
        self.layout_client = get_layout_client()
    
    async def get_articles_layout(self) -> Dict[str, Any]:
        """Получает укладку только для статей (блоков с типом "Article")"""
        try:
            logger.info("Starting articles layout calculation from Neo4j")
            
            # Читаем граф из Neo4j: узлы помечены как Article, связи - BIBLIOGRAPHIC_LINK
            logger.info("Querying articles from Neo4j")
            blocks_query = """
            MATCH (n:Article)
            WHERE n.layer IS NOT NULL AND n.level IS NOT NULL
              AND n.x IS NOT NULL AND n.y IS NOT NULL
              AND (
                EXISTS((n)-[:BIBLIOGRAPHIC_LINK]->(:Article)) OR
                EXISTS((:Article)-[:BIBLIOGRAPHIC_LINK]->(n))
              )
            RETURN n.uid as id,
                   n.content as content,
                   n.layer as layer,
                   n.level as level,
                   n.sublevel_id as sublevel_id,
                   n.is_pinned as is_pinned,
                   n.physical_scale as physical_scale,
                   n.x as x,
                   n.y as y
            """
            blocks_result, _ = db.cypher_query(blocks_query)
            logger.info(f"Found {len(blocks_result)} articles total")
            
            if not blocks_result:
                logger.warning("No articles found in Neo4j")
                raise HTTPException(status_code=404, detail="В базе данных нет статей Article. Загрузите данные.")
            
            links_query = """
            MATCH (s:Article)-[r:BIBLIOGRAPHIC_LINK]->(t:Article)
            RETURN s.uid as source_id, t.uid as target_id
            """
            links_result, _ = db.cypher_query(links_query)
            
            # Используем настоящие ID из базы данных
            blocks = []
            for row in blocks_result:
                layer_val = int(row[2] or 0)
                level_val = int(row[3] or 0)
                
                # Используем реальные координаты из базы данных или вычисляем их
                if row[7] is not None and row[8] is not None:
                    # Координаты уже заданы в базе данных
                    x_coord = float(row[7])
                    y_coord = float(row[8])
                else:
                    # Вычисляем координаты на основе layer и level
                    # Используем те же коэффициенты, что и в алгоритме укладки
                    LAYER_SPACING = 240  # BLOCK_WIDTH (200) + HORIZONTAL_GAP (40)
                    LEVEL_SPACING = 130  # BLOCK_HEIGHT (80) + VERTICAL_GAP (50)
                    
                    x_coord = float(layer_val * LAYER_SPACING)
                    y_coord = float(level_val * LEVEL_SPACING)
                
                block_data = {
                    "id": str(row[0]),
                    "content": str(row[1] or ""),
                    "layer": layer_val,
                    "level": level_val,
                    "sublevel_id": int(row[4] or 0),
                    "is_pinned": bool(row[5]) if row[5] is not None else False,
                    "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                    "x": x_coord,
                    "y": y_coord,
                    "metadata": {}
                }
                if block_data.get("is_pinned"):
                    logger.info(f"Found pinned node in DB: {block_data['id']} - is_pinned: {block_data['is_pinned']}")
                blocks.append(block_data)
            
            # Преобразуем связи
            links_for_layout = []
            for row in links_result:
                link_id = f"{row[0]}-{row[1]}"  # Генерируем ID из source и target
                source_id = str(row[0])
                target_id = str(row[1])
                links_for_layout.append(
                    {"id": link_id, "source_id": source_id, "target_id": target_id}
                )

            if not blocks:
                raise HTTPException(status_code=404, detail="В базе данных нет статей.")
            
            # Удаляем потенциальные циклы: оставляем рёбра только вперёд по слоям/уровням
            # TODO это должно делаться на стороне бэкенда
            level_index = {b["id"]: (b.get("layer", 0), b.get("level", 0)) for b in blocks}
            filtered_links = []
            for l in links_for_layout:
                s = l["source_id"]; t = l["target_id"]
                if s in level_index and t in level_index:
                    sl, sv = level_index[s]
                    tl, tv = level_index[t]
                    if (tl > sl) or (tl == sl and tv > sv):
                        filtered_links.append(l)
            if len(filtered_links) < len(links_for_layout):
                logger.info(f"Filtered potential cycles: kept {len(filtered_links)} of {len(links_for_layout)} links")
            
            # Получаем укладку
            try:
                result = await self.layout_client.calculate_layout(
                    blocks=blocks,
                    links=filtered_links,
                    options=LayoutOptions(
                        sublevel_spacing=200,
                        layer_spacing=250,
                        optimize_layout=False
                    )
                )
                return result
            except Exception as e:
                logger.error(f"Error in articles layout calculation: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Ошибка при расчете укладки статей: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error calculating articles layout from Neo4j: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка при получении данных статей из Neo4j: {str(e)}")

    async def get_edges_by_viewport(self, bounds: Dict[str, float], limit_per_node: int = 200, only_with_layout: bool = True) -> Dict[str, Any]:
        """
        Возвращает узлы в окне и рёбра, у которых хотя бы один конец попадает в окно.

        Args:
            bounds: Границы viewport (left, right, top, bottom)
            limit_per_node: Максимальное количество связей на узел (fan-out limiting)
            only_with_layout: Если True, возвращает только узлы с координатами (x, y)

        Performance improvements (vs old version):
            - Removed slow EXISTS clauses (2-3x speedup)
            - Direct x, y filtering (uses new composite indexes)
            - Optional fallback to layer/level coordinates
        """
        try:
            LAYER_SPACING = 240
            LEVEL_SPACING = 130

            # OPTIMIZED: Узлы в окне - БЕЗ EXISTS проверок (в 2-3x быстрее!)
            # EXISTS clauses замедляют запрос, убираем их и полагаемся на фильтрацию связей
            if only_with_layout:
                # Только узлы с реальными координатами (x, y) - самый быстрый вариант
                nodes_query = (
                    "MATCH (n:Article) "
                    "WHERE n.x IS NOT NULL AND n.y IS NOT NULL "
                    "  AND n.x >= $left AND n.x <= $right "
                    "  AND n.y >= $top AND n.y <= $bottom "
                    "RETURN n.uid as id, n.layer as layer, n.level as level, n.x as x, n.y as y"
                )
                params = {
                    "left": bounds["left"],
                    "right": bounds["right"],
                    "top": bounds["top"],
                    "bottom": bounds["bottom"],
                }
            else:
                # Fallback на layer/level если x, y не заданы (медленнее из-за coalesce)
                nodes_query = (
                    "MATCH (n:Article) "
                    "WHERE coalesce(n.x, toFloat(coalesce(n.layer,0))*$LAYER_SPACING) >= $left "
                    "  AND coalesce(n.x, toFloat(coalesce(n.layer,0))*$LAYER_SPACING) <= $right "
                    "  AND coalesce(n.y, toFloat(coalesce(n.level,0))*$LEVEL_SPACING) >= $top "
                    "  AND coalesce(n.y, toFloat(coalesce(n.level,0))*$LEVEL_SPACING) <= $bottom "
                    "RETURN n.uid as id, n.layer as layer, n.level as level, n.x as x, n.y as y"
                )
                params = {
                    "left": bounds["left"],
                    "right": bounds["right"],
                    "top": bounds["top"],
                    "bottom": bounds["bottom"],
                    "LAYER_SPACING": LAYER_SPACING,
                    "LEVEL_SPACING": LEVEL_SPACING,
                }

            nodes_result, _ = db.cypher_query(nodes_query, params)
            ids_in_view = [str(r[0]) for r in nodes_result]

            # Рёбра, где хотя бы один конец в окне, с ограничением fan-out
            edges_query = (
                "UNWIND $ids AS vid "
                "MATCH (s:Article {uid: vid})-[:BIBLIOGRAPHIC_LINK]->(t:Article) "
                "WITH s, t ORDER BY t.uid LIMIT $limit_per_node "
                "RETURN s.uid as sid, s.layer as sl, s.level as sv, s.x as sx, s.y as sy, "
                "       t.uid as tid, t.layer as tl, t.level as tv, t.x as tx, t.y as ty "
                "UNION "
                "UNWIND $ids AS vid "
                "MATCH (s:Article)-[:BIBLIOGRAPHIC_LINK]->(t:Article {uid: vid}) "
                "WITH s, t ORDER BY s.uid LIMIT $limit_per_node "
                "RETURN s.uid as sid, s.layer as sl, s.level as sv, s.x as sx, s.y as sy, "
                "       t.uid as tid, t.layer as tl, t.level as tv, t.x as tx, t.y as ty"
            )
            edges_result, _ = db.cypher_query(edges_query, {"ids": ids_in_view, "limit_per_node": limit_per_node})

            # Собираем выдачу
            blocks_map: dict[str, dict] = {}
            def pack_block(uid, layer, level, x, y):
                if uid in blocks_map:
                    return
                if x is None:
                    x = float((layer or 0) * LAYER_SPACING)
                if y is None:
                    y = float((level or 0) * LEVEL_SPACING)
                blocks_map[uid] = {
                    "id": str(uid),
                    "layer": int(layer or 0),
                    "level": int(level or 0),
                    "x": float(x),
                    "y": float(y),
                }

            # Добавляем видимые узлы
            for r in nodes_result:
                pack_block(r[0], r[1], r[2], r[3], r[4])

            links: list[dict] = []
            seen = set()
            for r in edges_result:
                sid, sl, sv, sx, sy, tid, tl, tv, tx, ty = r
                pack_block(sid, sl, sv, sx, sy)
                pack_block(tid, tl, tv, tx, ty)
                key = f"{sid}->{tid}"
                if key in seen:
                    continue
                seen.add(key)
                links.append({"id": key, "source_id": str(sid), "target_id": str(tid)})

            return {"blocks": list(blocks_map.values()), "links": links}
        except Exception as e:
            logger.error(f"edges_by_viewport failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def get_all_articles_layout(self) -> Dict[str, Any]:
        """Возвращает все блоки и связи из графа статей."""
        try:
            logger.info("Loading all articles and links")

            # Запрос всех статей - только со связями
            nodes_query = """
            MATCH (n:Article)
            WHERE n.layer IS NOT NULL AND n.level IS NOT NULL
              AND n.x IS NOT NULL AND n.y IS NOT NULL
              AND (
                EXISTS((n)-[:BIBLIOGRAPHIC_LINK]->(:Article)) OR
                EXISTS((:Article)-[:BIBLIOGRAPHIC_LINK]->(n))
              )
            RETURN n.uid as id,
                   coalesce(n.title, n.name, n.content, toString(n.uid)) as title,
                   n.layer as layer,
                   n.level as level,
                   n.sublevel_id as sublevel_id,
                   n.is_pinned as is_pinned,
                   n.physical_scale as physical_scale,
                   n.x as x,
                   n.y as y,
                   n.layout_status as layout_status
            """
            blocks_result, _ = db.cypher_query(nodes_query)

            if not blocks_result:
                return {
                    "success": True,
                    "blocks": [],
                    "links": [],
                    "levels": [],
                    "sublevels": [],
                    "total": 0
                }

            blocks: list[dict] = []
            for row in blocks_result:
                block = {
                    "id": str(row[0]),
                    "content": str(row[1] or ""),
                    "layer": int(row[2]) if row[2] is not None else None,
                    "level": int(row[3]) if row[3] is not None else None,
                    "sublevel_id": int(row[4] or 0),
                    "is_pinned": bool(row[5]) if row[5] is not None else False,
                    "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                    "x": float(row[7]) if row[7] is not None else 0.0,
                    "y": float(row[8]) if row[8] is not None else 0.0,
                    "layout_status": str(row[9] or ""),
                    "metadata": {},
                }
                blocks.append(block)

            # Запрос всех связей
            links_query = """
            MATCH (s:Article)-[r:BIBLIOGRAPHIC_LINK]->(t:Article)
            RETURN s.uid as source_id, t.uid as target_id
            """
            links_result, _ = db.cypher_query(links_query)
            
            links: list[dict] = []
            for row in links_result:
                link_id = f"{row[0]}-{row[1]}"  # Генерируем ID из source и target
                links.append({
                    "id": link_id,
                    "source_id": str(row[0]),
                    "target_id": str(row[1]),
                })

            logger.info(f"Loaded {len(blocks)} blocks and {len(links)} links")

            return {
                "success": True,
                "blocks": blocks,
                "links": links,
                "levels": [],
                "sublevels": [],
                "total": len(blocks)
            }
        except Exception as e:
            logger.error(f"Error loading all articles: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def get_articles_layout_page(
        self,
        offset: int = 0,
        limit: int = 2000,
        center_x: float = 0.0,
        center_y: float = 0.0
    ) -> Dict[str, Any]:
        """Возвращает часть графа статей, упорядоченную по близости к (center_x, center_y)."""
        try:
            logger.info(
                f"Articles page requested: offset={offset}, limit={limit}, center=({center_x},{center_y})"
            )

            # ОПТИМИЗАЦИЯ: Убрана медленная проверка EXISTS для total_query
            # Просто считаем статьи с назначенными координатами (layer, level)
            # Если нужен точный подсчёт со связями, лучше кешировать это значение
            total_query = (
                "MATCH (n:Article) "
                "WHERE n.layer IS NOT NULL AND n.level IS NOT NULL "
                "  AND n.x IS NOT NULL AND n.y IS NOT NULL "
                "RETURN count(n) as total"
            )
            total_res, _ = db.cypher_query(total_query)
            logger.info(f"Total query result: {total_res}")
            total_articles = int(total_res[0][0]) if total_res and total_res[0] and total_res[0][0] is not None else 0
            logger.info(f"Total articles: {total_articles}")

            # ОПТИМИЗАЦИЯ: Убрана медленная проверка EXISTS из запроса узлов
            # Предполагаем что статьи с координатами уже прошли укладку и имеют связи
            # Фильтрация по связям (если нужна) должна выполняться на этапе укладки
            nodes_query = (
                "MATCH (n:Article) "
                "WHERE n.layer IS NOT NULL AND n.level IS NOT NULL "
                "  AND n.x IS NOT NULL AND n.y IS NOT NULL "
                "RETURN n.uid as id, "
                "       coalesce(n.title, n.name, n.content, toString(n.uid)) as title, "
                "       n.layer as layer, "
                "       n.level as level, "
                "       coalesce(n.sublevel_id, 0) as sublevel_id, "
                "       coalesce(n.is_pinned, false) as is_pinned, "
                "       coalesce(n.physical_scale, 0) as physical_scale, "
                "       n.x as x, "
                "       n.y as y, "
                "       n.layout_status as layout_status, "
                "       coalesce(n.topo_order, 0) as topo_order, "
                "       sqrt((coalesce(n.x, toFloat(coalesce(n.layer,0)) * $LAYER_SPACING) - $center_x) * (coalesce(n.x, toFloat(coalesce(n.layer,0)) * $LAYER_SPACING) - $center_x) + "
                "            (coalesce(n.y, toFloat(coalesce(n.level,0)) * $LEVEL_SPACING) - $center_y) * (coalesce(n.y, toFloat(coalesce(n.level,0)) * $LEVEL_SPACING) - $center_y)) as distance "
                "ORDER BY distance ASC, n.layer ASC, n.topo_order ASC "
                "SKIP $offset LIMIT $limit"
            )
            blocks_result, _ = db.cypher_query(
                nodes_query,
                {
                    "offset": offset,
                    "limit": limit,
                    "center_x": center_x,
                    "center_y": center_y,
                    "LAYER_SPACING": 240,
                    "LEVEL_SPACING": 130,
                },
            )
            logger.info(f"Blocks query result: {len(blocks_result) if blocks_result else 0} rows")

            if not blocks_result:
                return {
                    "success": True,
                    "blocks": [],
                    "links": [],
                    "levels": [],
                    "sublevels": [],
                    "page": {"offset": offset, "limit": limit, "returned": 0, "total": total_articles},
                }

            blocks: list[dict] = []
            selected_ids: set[str] = set()
            for row in blocks_result:
                block = {
                    "id": str(row[0]),
                    "content": str(row[1] or ""),
                    "layer": int(row[2]) if row[2] is not None else None,
                    "level": int(row[3]) if row[3] is not None else None,
                    "sublevel_id": int(row[4] or 0),
                    "is_pinned": bool(row[5]) if row[5] is not None else False,
                    "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                    "x": float(row[7]) if row[7] is not None else 0.0,
                    "y": float(row[8]) if row[8] is not None else 0.0,
                    "metadata": {},
                }
                blocks.append(block)
                selected_ids.add(block["id"])

            # Загружаем ВСЕ связи для выбранных статей, включая целевые статьи
            links_query = """
            MATCH (s:Article)-[r:BIBLIOGRAPHIC_LINK]->(t:Article)
            WHERE s.uid IN $ids OR t.uid IN $ids
            RETURN s.uid as source_id, t.uid as target_id
            """
            links_result, _ = db.cypher_query(links_query, {"ids": list(selected_ids)})
            links_for_layout: list[dict] = []
            for row in links_result:
                link_id = f"{row[0]}-{row[1]}"  # Генерируем ID из source и target
                links_for_layout.append(
                    {
                        "id": link_id,
                        "source_id": str(row[0]),
                        "target_id": str(row[1]),
                    }
                )

            # Загружаем целевые статьи, которые не попали в текущую страницу, но имеют связи
            target_ids = set()
            for link in links_for_layout:
                target_ids.add(link["target_id"])
                target_ids.add(link["source_id"])
            
            # Находим целевые статьи, которых нет в текущей странице
            missing_target_ids = target_ids - selected_ids
            
            if missing_target_ids:
                # Загружаем недостающие целевые статьи
                missing_targets_query = """
                MATCH (n:Article)
                WHERE n.uid IN $missing_ids
                  AND n.layer IS NOT NULL AND n.level IS NOT NULL
                RETURN n.uid as id,
                       coalesce(n.title, n.name, n.content, toString(n.uid)) as title,
                       n.layer as layer,
                       n.level as level,
                       coalesce(n.sublevel_id, 0) as sublevel_id,
                       coalesce(n.is_pinned, false) as is_pinned,
                       coalesce(n.physical_scale, 0) as physical_scale,
                       n.x as x,
                       n.y as y,
                       n.layout_status as layout_status
                """
                missing_targets_result, _ = db.cypher_query(missing_targets_query, {"missing_ids": list(missing_target_ids)})
                
                # Добавляем недостающие статьи к блокам
                for row in missing_targets_result:
                    block = {
                        "id": str(row[0]),
                        "content": str(row[1] or ""),
                        "layer": int(row[2]) if row[2] is not None else None,
                        "level": int(row[3]) if row[3] is not None else None,
                        "sublevel_id": int(row[4] or 0),
                        "is_pinned": bool(row[5]) if row[5] is not None else False,
                        "physical_scale": int(row[6] or 0) if row[6] is not None else 0,
                        "x": float(row[7]) if row[7] is not None else 0.0,
                        "y": float(row[8]) if row[8] is not None else 0.0,
                        "metadata": {},
                    }
                    blocks.append(block)
                    selected_ids.add(block["id"])
                
                logger.info(f"Added {len(missing_targets_result)} missing target articles to ensure all connections are visible")

            # API просто возвращает все связи как есть - разворот циклов делается в алгоритме укладки
            filtered_links = links_for_layout

            # Возвращаем напрямую без вызова gRPC укладки (уровни/подуровни уже в БД)
            return {
                "success": True,
                "blocks": blocks,
                "links": filtered_links,
                "levels": [],
                "sublevels": [],
                "page": {
                    "offset": offset,
                    "limit": limit,
                    "returned": len(blocks),
                    "total": total_articles,
                },
            }
        except Exception as e:
            logger.error(f"Error in paged articles layout: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def get_knowledge_map_page(
        self,
        offset: int = 0,
        limit: int = 200,
        center_x: float = 0.0,
        center_y: float = 0.0,
    ) -> Dict[str, Any]:
        """Возвращает агрегированный граф знаний из Action-нод с иерархической укладкой.

        Координаты (x, y) вычисляются Rust-воркером GraphLayoutService (порт 50051)
        по алгоритму Сугиямы на основе рёбер LEADS_TO.
        Контракт универсальный: передаём любые рёбра, получаем координаты.
        """
        from infrastructure.graph_layout_client import get_graph_layout_client

        try:
            # Шаг 1: Считаем общее число нод с рёбрами
            total_query = """
            MATCH (a1:Action)-[:LEADS_TO {status: 'confirmed'}]->(a2:Action)
            WHERE a1.norm_key IS NOT NULL AND a2.norm_key IS NOT NULL
              AND a1.norm_key <> a2.norm_key
            WITH collect(DISTINCT a1.norm_key) + collect(DISTINCT a2.norm_key) AS all_keys
            UNWIND all_keys AS k
            RETURN count(DISTINCT k) AS total
            """
            total_res, _ = db.cypher_query(total_query)
            total = int(total_res[0][0]) if total_res and total_res[0][0] else 0

            if total == 0:
                return {
                    "success": True,
                    "blocks": [],
                    "links": [],
                    "page": {"offset": offset, "limit": limit, "returned": 0, "total": 0},
                }

            # Шаг 2: Рёбра агрегированного графа (по norm_key)
            edges_query = """
            MATCH (a1:Action)-[r:LEADS_TO {status: 'confirmed'}]->(a2:Action)
            WHERE a1.norm_key IS NOT NULL AND a2.norm_key IS NOT NULL
              AND a1.norm_key <> a2.norm_key
            WITH a1.norm_key AS src_key, a2.norm_key AS tgt_key,
                 count(r) AS edge_count, avg(r.confidence) AS avg_conf,
                 collect(DISTINCT r.relation_subtype)[0] AS relation_subtype
            RETURN src_key, tgt_key, edge_count, avg_conf, relation_subtype
            """
            edges_result, _ = db.cypher_query(edges_query)

            connected_keys: set[str] = set()
            raw_edges = []
            for row in edges_result:
                connected_keys.add(row[0])
                connected_keys.add(row[1])
                raw_edges.append({
                    "src_key": row[0],
                    "tgt_key": row[1],
                    "count": row[2] or 1,
                    "confidence": row[3] or 0.0,
                    "relation_subtype": row[4] or "",
                })

            # Шаг 3a: Маппинг norm_key → uid для всех connected_keys
            mapping_result, _ = db.cypher_query(
                """
                MATCH (a:Action) WHERE a.norm_key IN $keys
                WITH a.norm_key AS nk, collect(a) AS grp
                RETURN nk, grp[0].uid AS uid
                """,
                {"keys": list(connected_keys)},
            )
            key_to_uid: dict[str, str] = {row[0]: row[1] for row in mapping_result}

            # Шаг 3b: Ноды текущей страницы (пагинация на уровне Neo4j)
            nodes_query = """
            MATCH (a:Action)
            WHERE a.norm_key IN $keys
            WITH a.norm_key AS nk, collect(a) AS grp
            WITH grp[0] AS rep, size(grp) AS doc_count,
                 [g IN grp | g.doc_id] AS doc_ids
            RETURN rep.uid AS uid,
                   rep.verb AS verb,
                   rep.verb_text AS verb_text,
                   rep.subject AS subject,
                   rep.object AS object,
                   rep.action_class AS action_class,
                   rep.norm_key AS norm_key,
                   doc_count,
                   doc_ids
            ORDER BY doc_count DESC
            """
            nodes_result, _ = db.cypher_query(
                nodes_query,
                {"keys": list(connected_keys)},
            )

            if not nodes_result:
                return {
                    "success": True,
                    "blocks": [],
                    "links": [],
                    "page": {"offset": 0, "limit": len(connected_keys), "returned": 0, "total": total},
                }

            # Шаг 4: Рёбра для страницы (хотя бы один конец — нода страницы)
            page_ids_by_uid: dict[str, tuple] = {}
            for row in nodes_result:
                uid = row[0]
                page_ids_by_uid[uid] = row

            page_ids = set(page_ids_by_uid.keys())

            links = []
            for e in raw_edges:
                src_uid = key_to_uid.get(e["src_key"])
                tgt_uid = key_to_uid.get(e["tgt_key"])
                if src_uid and tgt_uid and (src_uid in page_ids or tgt_uid in page_ids):
                    links.append({
                        "id": f"{src_uid}->{tgt_uid}",
                        "source_id": src_uid,
                        "target_id": tgt_uid,
                        "count": e["count"],
                        "confidence": e["confidence"],
                        "relation_subtype": e["relation_subtype"],
                    })

            # Шаг 5: Укладка через Rust-воркер GraphLayoutService
            # Передаём только рёбра — воркер возвращает (x, y) для каждой вершины
            rust_edges = [
                {"source_id": lnk["source_id"], "target_id": lnk["target_id"]}
                for lnk in links
            ]
            layout_client = get_graph_layout_client()
            positions: dict[str, tuple[float, float]] = await layout_client.compute_layout(
                rust_edges,
                reduce_crossings=True,
            )

            # Шаг 6: Собираем итоговые блоки с координатами из Rust
            page_nodes = []
            for row in nodes_result:
                uid, verb, verb_text, subject, obj, action_class, norm_key, doc_count, doc_ids = row
                x, y = positions.get(uid, (0.0, 0.0))
                page_nodes.append({
                    "id": uid,
                    "content": f"{verb} {obj}".strip() if obj else (verb or ""),
                    "verb": verb or "",
                    "verb_text": verb_text or "",
                    "subject": subject or "",
                    "object": obj or "",
                    "action_class": action_class or "action",
                    "norm_key": norm_key,
                    "doc_count": doc_count or 1,
                    "doc_ids": list(doc_ids) if doc_ids else [],
                    "x": x,
                    "y": y,
                    "layer": 0,
                    "level": 0,
                    "metadata": {},
                })

            logger.info(
                f"knowledge_map_page: nodes={len(page_nodes)} links={len(links)} "
                f"total={total} rust_positions={len(positions)}"
            )

            return {
                "success": True,
                "blocks": page_nodes,
                "links": links,
                "page": {"offset": 0, "limit": len(page_nodes), "returned": len(page_nodes), "total": total},
            }
        except Exception as e:
            logger.error(f"Error in knowledge map page: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def get_layout_from_neo4j(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Получает укладку из Neo4j для блоков Block"""
        try:
            logger.info("Starting layout calculation from Neo4j")
            
            # Запрос блоков из Neo4j
            logger.info("Querying blocks from Neo4j")
            blocks_query = """
            MATCH (b:Block)
            RETURN b.uid as id, b.content as content, b.layer as layer, b.level as level, b.is_pinned as is_pinned, b.physical_scale as physical_scale
            """
            blocks_result, _ = db.cypher_query(blocks_query)
            logger.info(f"Found {len(blocks_result)} blocks total")
            
            if not blocks_result:
                logger.warning("No blocks found in Neo4j")
                raise HTTPException(status_code=404, detail="В базе данных нет блоков. Пожалуйста, запустите скрипт заполнения тестовыми данными.")
            
            # Запрос связей из Neo4j (упрощённый без проверки циклов)
            links_query = """
            MATCH (b1:Block)-[r:LINK_TO]->(b2:Block)
            RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id
            """
            links_result, _ = db.cypher_query(links_query)
            
            # Используем настоящие ID из базы данных
            blocks = []
            for row in blocks_result:
                block_data = {
                    "id": str(row[0]),
                    "content": str(row[1] or ""),
                    "layer": int(row[2] or 0),
                    "level": int(row[3] or 0),
                    "is_pinned": bool(row[4]) if row[4] is not None else False,
                    "physical_scale": int(row[5] or 0) if row[5] is not None else 0,
                    "metadata": {}
                }
                if block_data["is_pinned"]:
                    logger.info(f"Found pinned block in DB: {block_data['id']} - is_pinned: {block_data['is_pinned']}")
                blocks.append(block_data)
            
            # Преобразуем связи
            links_for_layout = []
            for row in links_result:
                link_id = f"{row[0]}-{row[1]}"  # Генерируем ID из source и target
                source_id = str(row[0])
                target_id = str(row[1])
                links_for_layout.append(
                    {"id": link_id, "source_id": source_id, "target_id": target_id}
                )

            if not blocks:
                raise HTTPException(status_code=404, detail="В базе данных нет блоков.")
            
            # Получаем укладку
            try:
                result = await self.layout_client.calculate_layout(
                    blocks=blocks,
                    links=links_for_layout,
                    options=LayoutOptions(
                        sublevel_spacing=200,
                        layer_spacing=250,
                        optimize_layout=True
                    )
                )

                
                # Сохраняем обновлённые уровни и подуровни обратно в базу данных
                if result.get('success') and result.get('blocks'):
                    logger.info("🔥 СОХРАНЯЕМ ОБНОВЛЁННЫЕ УРОВНИ БЛОКОВ В БАЗУ ДАННЫХ...")
                    
                    # Сначала покажем что пришло из алгоритма
                    pinned_in_result = [b for b in result['blocks'] if b.get('is_pinned', False)]
                    logger.info(f"🔥 ЗАКРЕПЛЁННЫХ БЛОКОВ В РЕЗУЛЬТАТЕ: {len(pinned_in_result)}")
                    for block_info in pinned_in_result:
                        logger.info(f"   🔥 PINNED RESULT: {block_info['id'][:8]}... level={block_info['level']}, sublevel={block_info['sublevel_id']}")
                    
                    with db.transaction:
                        updates_count = 0
                        for block_info in result['blocks']:
                            try:
                                block = Block.nodes.get(uid=block_info['id'])
                                # Обновляем уровень и подуровень только если они изменились
                                old_level = block.level
                                old_sublevel = block.sublevel_id
                                new_level = block_info['level']
                                new_sublevel = block_info['sublevel_id']
                                
                                if old_level != new_level or old_sublevel != new_sublevel:
                                    block.level = new_level
                                    block.sublevel_id = new_sublevel
                                    block.save()
                                    updates_count += 1
                                    
                                    if block.is_pinned:
                                        logger.info(f"🔥 PINNED UPDATED: {block_info['id'][:8]}... level {old_level}->{new_level}, sublevel {old_sublevel}->{new_sublevel}")
                                    else:
                                        logger.info(f"Updated block {block_info['id'][:8]}...: level {old_level}->{new_level}, sublevel {old_sublevel}->{new_sublevel}")
                                    
                            except DoesNotExist:
                                logger.warning(f"Block {block_info['id']} not found in database")
                            except Exception as e:
                                logger.error(f"Error updating block {block_info['id']}: {e}")
                                
                    logger.info(f"🔥 ✓ ОБНОВЛЕНО {updates_count} БЛОКОВ В БАЗЕ ДАННЫХ")
                
                return result
            except Exception as e:
                logger.error(f"Error in layout calculation: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Ошибка при расчете укладки: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error calculating layout from Neo4j: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
