"""
Утилиты и вспомогательные функции для алгоритма укладки
"""

import logging
import time
import networkx as nx
from typing import Dict, List, Any, Optional
from ..neo4j_client import neo4j_client
from ..utils.simple_circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class LayoutUtils:
    """Утилиты для алгоритма укладки"""
    
    def __init__(self, circuit_breaker: CircuitBreaker):
        self.circuit_breaker = circuit_breaker
        self._last_progress_time = 0.0
        self._progress_throttle_sec = 0.2
        self._last_progress_pct: float = -1.0
        self._no_change_count: int = 0
        self._stall_threshold_logs: int = 60
        self._min_pct_delta: float = 0.05
    
    def log_progress(self, stage: str, substage: str, processed: int, total: int, 
                    converges: Optional[bool], extra: str = "", iteration_count: int = 0, 
                    db_operations: int = 0) -> None:
        """Логирует прогресс выполнения алгоритма"""
        try:
            pct = (processed / total * 100.0) if total and total > 0 else 0.0
        except Exception:
            pct = 0.0
        if pct > 100.0:
            pct = 100.0
        
        # Обновляем внутреннее состояние стагнации
        if self._last_progress_pct < 0:
            self._last_progress_pct = pct
            self._no_change_count = 0
        else:
            if abs(pct - self._last_progress_pct) < self._min_pct_delta:
                self._no_change_count += 1
            else:
                self._no_change_count = 0
                self._last_progress_pct = pct
        
        converge_str = "yes" if converges is True else ("no" if converges is False else "-")
        line = (
            f"[layout] {stage}>{substage} | {processed}/{total} ({pct:.1f}%) | "
            f"conv:{converge_str} | it:{iteration_count} | db:{db_operations} {extra}"
        )
        if len(line) > 200:
            line = line[:197] + "..."
        print(line)  # Добавляем перенос строки

    async def get_processed_count_db(self) -> int:
        """Считает число размещённых статей в БД."""
        query = """
        MATCH (n:Article)
        WHERE n.layout_status IN ['placed','in_longest_path','pinned']
        AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        RETURN count(n) AS cnt
        """
        async with self.circuit_breaker:
            rows = await neo4j_client.execute_query_with_retry(query)
        return int(rows[0]["cnt"]) if rows else 0

    async def ensure_total_articles_estimate(self) -> int:
        """Инициализирует или возвращает оценку общего числа статей."""
        # Всегда обновляем из БД для точности (только связанные вершины)
        q = """
        MATCH (n:Article)
        WHERE (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        RETURN count(n) AS total
        """
        async with self.circuit_breaker:
            rows = await neo4j_client.execute_query_with_retry(q)
        total_articles = int(rows[0]["total"]) if rows else 0
        return total_articles

    def update_progress_state(self, processed: int, total: int) -> bool:
        """Обновляет счетчики стагнации. Возвращает True, если наблюдается застой прогресса."""
        try:
            pct = (processed / total * 100.0) if total and total > 0 else 0.0
        except Exception:
            pct = 0.0
        if pct > 100.0:
            pct = 100.0
        
        if self._last_progress_pct < 0:
            self._last_progress_pct = pct
            self._no_change_count = 0
        else:
            if abs(pct - self._last_progress_pct) < self._min_pct_delta:
                self._no_change_count += 1
            else:
                self._no_change_count = 0
                self._last_progress_pct = pct
        
        return self._no_change_count >= self._stall_threshold_logs

    async def initialize_layout_tables(self):
        """
        Инициализация таблиц в Neo4j для хранения состояния укладки
        Разделяем операции на две транзакции: SCHEMA и WRITE
        """
        async with self.circuit_breaker:
            async with neo4j_client.session() as session:
                # Транзакция 1: SCHEMA операции (constraints и индексы)
                tx_schema = await session.begin_transaction()
                try:
                    # 1. Создаём таблицу для отслеживания свободных позиций
                    await tx_schema.run("""
                        CREATE CONSTRAINT IF NOT EXISTS FOR (p:Position) REQUIRE p.id IS UNIQUE
                    """)
                    
                    # 2. Гарантируем уникальность места (layer, level) - ОТКЛЮЧЕНО для LP размещения
                    # await tx_schema.run("""
                    #     CREATE CONSTRAINT IF NOT EXISTS FOR (n:Article) REQUIRE (n.layer, n.level) IS UNIQUE
                    # """)
                    
                    # 3. Создаём индекс для layout_status
                    await tx_schema.run("""
                        CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.layout_status)
                    """)
                    
                    # Коммитим SCHEMA транзакцию
                    await tx_schema.commit()
                except Exception as e:
                    # Откатываем SCHEMA транзакцию в случае ошибки
                    await tx_schema.rollback()
                    raise e
                finally:
                    # Закрываем SCHEMA транзакцию
                    await tx_schema.close()
                
                # Транзакция 2: WRITE операции (изменение данных)
                tx_write = await session.begin_transaction()
                try:
                    # 1. Очищаем координаты у изолированных вершин
                    await tx_write.run("""
                        MATCH (n:Article)
                        WHERE NOT ()-[:BIBLIOGRAPHIC_LINK]->(n) AND NOT (n)-[:BIBLIOGRAPHIC_LINK]->()
                        REMOVE n.layer, n.level, n.x, n.y
                        SET n.layout_status = 'isolated'
                    """)
                    
                    # 2. Инициализируем статус и сбрасываем временные поля топосортировки (только связанные вершины)
                    await tx_write.run("""
                        MATCH (n:Article)
                        WHERE (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
                        SET n.layout_status = 'unprocessed'
                        REMOVE n.topo_order, n.visited, n.in_deg
                    """)
                    
                    # Коммитим WRITE транзакцию
                    await tx_write.commit()
                except Exception as e:
                    # Откатываем WRITE транзакцию в случае ошибки
                    await tx_write.rollback()
                    raise e
                finally:
                    # Закрываем WRITE транзакцию
                    await tx_write.close()

    async def create_performance_indexes(self):
        """Создаёт индексы для ускорения запросов"""
        logger.info("Creating performance indexes...")
        
        # Выполняем все индексы в одной транзакции
        try:
            async with self.circuit_breaker:
                async with neo4j_client.session() as session:
                    tx = await session.begin_transaction()
                    try:
                        # 1. Составной индекс для layout_status, layer, level
                        await tx.run("""
                            CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.layout_status, n.layer, n.level)
                        """)
                        
                        # 2. Индекс для топологического порядка
                        await tx.run("""
                            CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.topo_order)
                        """)
                        
                        # 3. Индекс для связей CITES
                        await tx.run("""
                            CREATE INDEX IF NOT EXISTS FOR ()-[r:BIBLIOGRAPHIC_LINK]->() ON (r)
                        """)
                        
                        # 4. Составной индекс для uid и layout_status
                        await tx.run("""
                            CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.uid, n.layout_status)
                        """)
                        
                        # Коммитим транзакцию
                        await tx.commit()
                    except Exception as e:
                        # Откатываем транзакцию в случае ошибки
                        await tx.rollback()
                        raise e
                    finally:
                        # Закрываем транзакцию
                        await tx.close()
        except Exception as e:
            logger.warning(f"Failed to create some indexes: {e}")

    async def detect_and_fix_cycles(self) -> int:
        """
        Обнаружение и исправление циклов путем разворота связей.
        Не удаляем связи, а разворачиваем их для устранения циклов.
        """
        logger.info("Checking graph acyclicity and fixing cycles by reversing edges...")
        
        # 1. Удаляем только петли и кратные рёбра (это безопасно)
        removed_loops_duplicates = await self._remove_loops_and_duplicates()
        
        # 2. Разворачиваем циклы
        reversed_edges = await self._reverse_cycles()
        
        # 3. Проверяем ацикличность после разворота
        is_acyclic = await self._check_acyclicity()
        
        if not is_acyclic:
            logger.warning("Graph still contains cycles after reversal")
        else:
            logger.info("Graph is now acyclic after cycle reversal")
        
        logger.info(f"Cycle fix completed. Removed {removed_loops_duplicates} loops/duplicates, reversed {reversed_edges} edges")
        return removed_loops_duplicates + reversed_edges
    
    async def _check_acyclicity(self) -> bool:
        """
        Простая проверка ацикличности через поиск источников (узлов без входящих рёбер).
        Если есть хотя бы один источник, граф ациклический.
        """
        logger.info("Checking graph acyclicity...")
        
        # Проверяем, есть ли узлы без входящих рёбер (только связанные вершины)
        sources_query = """
        MATCH (n:Article)
        WHERE NOT ()-[:BIBLIOGRAPHIC_LINK]->(n)
        AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        RETURN count(n) AS source_count
        """
        
        async with self.circuit_breaker:
            result = await neo4j_client.execute_query_with_retry(sources_query)
        
        source_count = int(result[0]["source_count"]) if result else 0
        logger.info(f"Found {source_count} source nodes (nodes without incoming edges)")
        
        # Если есть хотя бы один источник, граф ациклический
        return source_count > 0
    
    async def _reverse_cycles(self) -> int:
        """
        Разворачивает циклы в графе, используя топологическую сортировку.
        Если связь идет от узла с большим topo_order к узлу с меньшим, разворачиваем её.
        """
        logger.info("Reversing cycles using topological order...")
        
        # Получаем все связи с их топологическими порядками
        edges_query = """
        MATCH (s:Article)-[r:BIBLIOGRAPHIC_LINK]->(t:Article)
        WHERE s.topo_order IS NOT NULL AND t.topo_order IS NOT NULL
        RETURN s.uid as source_id, t.uid as target_id, s.topo_order as source_order, t.topo_order as target_order
        """
        
        async with self.circuit_breaker:
            edges_result = await neo4j_client.execute_query_with_retry(edges_query)
        
        reversed_count = 0
        
        # Обрабатываем связи батчами
        batch_size = 1000
        for i in range(0, len(edges_result), batch_size):
            batch = edges_result[i:i + batch_size]
            
            # Находим связи, которые нужно развернуть (идут "назад" по топологическому порядку)
            edges_to_reverse = []
            for edge in batch:
                source_order = edge["source_order"]
                target_order = edge["target_order"]
                
                # Если связь идет от узла с большим порядком к узлу с меньшим - это цикл
                if source_order > target_order:
                    edges_to_reverse.append({
                        "source_id": edge["source_id"],
                        "target_id": edge["target_id"]
                    })
            
            if edges_to_reverse:
                # Разворачиваем связи батчами
                reverse_query = """
                UNWIND $edges AS edge
                MATCH (s:Article {uid: edge.source_id})-[r:BIBLIOGRAPHIC_LINK]->(t:Article {uid: edge.target_id})
                DELETE r
                CREATE (t)-[:BIBLIOGRAPHIC_LINK]->(s)
                """
                
                async with self.circuit_breaker:
                    await neo4j_client.execute_query_with_retry(reverse_query, {"edges": edges_to_reverse})
                
                reversed_count += len(edges_to_reverse)
                logger.info(f"Reversed {len(edges_to_reverse)} edges in batch {i//batch_size + 1}")
        
        logger.info(f"Total reversed edges: {reversed_count}")
        return reversed_count

    async def _remove_loops_and_duplicates(self) -> int:
        """
        Удаляет петли (v→v) и дублирующиеся рёбра.
        Сложность: O(E)
        """
        logger.info("Removing loops and duplicate edges...")
        
        # Удаляем петли
        remove_loops_query = """
        MATCH (n:Article)-[r:BIBLIOGRAPHIC_LINK]->(n)
        DELETE r
        RETURN count(r) AS removed_loops
        """
        
        async with self.circuit_breaker:
            loops_result = await neo4j_client.execute_query_with_retry(remove_loops_query)
        removed_loops = int(loops_result[0]["removed_loops"]) if loops_result else 0
        
        # Удаляем дублирующиеся рёбра (оставляем только одно ребро между парой узлов)
        remove_duplicates_query = """
        MATCH (a:Article)-[r1:BIBLIOGRAPHIC_LINK]->(b:Article)
        WHERE a.uid < b.uid  // Используем uid вместо id() для избежания дублирования
        WITH a, b, collect(r1) AS edges
        WHERE size(edges) > 1
        UNWIND edges[1..] AS edge_to_remove
        DELETE edge_to_remove
        RETURN count(edge_to_remove) AS removed_duplicates
        """
        
        async with self.circuit_breaker:
            duplicates_result = await neo4j_client.execute_query_with_retry(remove_duplicates_query)
        removed_duplicates = int(duplicates_result[0]["removed_duplicates"]) if duplicates_result else 0
        
        total_removed = removed_loops + removed_duplicates
        logger.info(f"Removed {removed_loops} loops and {removed_duplicates} duplicates (total: {total_removed})")
        return total_removed


    def should_throttle_progress(self) -> bool:
        """Проверяет, нужно ли ограничить частоту логирования прогресса"""
        current_time = time.time()
        if current_time - self._last_progress_time < self._progress_throttle_sec:
            return True
        self._last_progress_time = current_time
        return False
