"""
Модуль для топологической сортировки графа статей.
Реализует алгоритм Кана с батчевой обработкой для предотвращения переполнения памяти.
"""

import logging
import time
from typing import List

from ..neo4j_client import neo4j_client
from ..utils.simple_circuit_breaker import SimpleCircuitBreaker

logger = logging.getLogger(__name__)


class TopologicalSorter:
    """
    Класс для выполнения топологической сортировки графа статей.
    Использует алгоритм Кана с батчевой обработкой.
    """
    
    def __init__(self):
        self.circuit_breaker = SimpleCircuitBreaker()
        self._last_progress_time = 0
        self._progress_throttle_sec = 5.0  # Логируем прогресс не чаще чем раз в 5 секунд

    def should_throttle_progress(self) -> bool:
        """Проверяет, нужно ли ограничить частоту логирования прогресса"""
        current_time = time.time()
        if current_time - self._last_progress_time < self._progress_throttle_sec:
            return True
        self._last_progress_time = current_time
        return False

    async def compute_toposort_order_db(self) -> None:
        """
        Вычисляет полный топологический порядок используя алгоритм Кана с батчевой обработкой.
        Сложность O(V + E) - оптимальная для топологической сортировки.
        """
        logger.info("Computing complete topological order using Kahn's algorithm with batching")

        # Получаем общее количество статей для контроля (только связанные вершины)
        total_articles_query = """
        MATCH (n:Article)
        WHERE (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        RETURN count(n) AS total
        """
        async with self.circuit_breaker:
            total_rows = await neo4j_client.execute_query_with_retry(total_articles_query)
        total_articles = int(total_rows[0]["total"]) if total_rows else 0
        logger.info(f"Total articles to process: {total_articles}")

        # Инициализация: вычисляем in_degree для всех узлов батчами
        logger.info("Initializing in_degree calculation...")
        init_query = """
        CALL apoc.periodic.iterate(
          "MATCH (n:Article) WHERE (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() }) RETURN n",
          "SET n.in_deg = size([(m:Article)-[:BIBLIOGRAPHIC_LINK]->(n) | m]),
           n.topo_order = -1,
           n.visited = false",
          {batchSize: 5000, parallel: false}
        ) YIELD batches, total, errorMessages
        RETURN batches, total, errorMessages
        """
        
        async with self.circuit_breaker:
            init_result = await neo4j_client.execute_query_with_retry(init_query)
        logger.info(f"Initialization completed: {init_result[0]['total']} nodes processed")

        # Основной алгоритм Кана с батчевой обработкой
        order_counter = 0
        batch_size = 10000
        processed_total = 0
        
        while True:
            # Находим ВСЕ узлы с in_deg = 0 и visited = false (алгоритм Кана требует обработки всех источников на одном уровне)
            find_zero_degree_query = """
            MATCH (n:Article)
            WHERE n.in_deg = 0 AND n.visited = false
            AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
            RETURN n.uid AS uid
            """
            
            async with self.circuit_breaker:
                zero_degree_nodes = await neo4j_client.execute_query_with_retry(find_zero_degree_query)
            
            if not zero_degree_nodes:
                break
                
            # Обрабатываем найденные узлы
            node_uids = [row["uid"] for row in zero_degree_nodes]
            current_batch_size = len(node_uids)
            logger.info(f"Обрабатываем уровень {order_counter}-{order_counter + current_batch_size - 1}: {current_batch_size} узлов")
            
            # Разбиваем на батчи для избежания проблем с памятью
            batch_size = 5000  # Уменьшаем размер батча
            for i in range(0, len(node_uids), batch_size):
                batch_uids = node_uids[i:i + batch_size]
                batch_data = [
                    {"uid": uid, "order_value": order_counter + i + j}
                    for j, uid in enumerate(batch_uids)
                ]
                
                # Устанавливаем топологический порядок для текущего батча
                set_order_query = """
                UNWIND $node_data AS item
                MATCH (n:Article {uid: item.uid})
                SET n.topo_order = item.order_value,
                    n.visited = true
                """
                
                async with self.circuit_breaker:
                    await neo4j_client.execute_query_with_retry(
                        set_order_query, 
                        {"node_data": batch_data}
                    )
                
                # Логируем прогресс каждые 10 батчей
                if (i // batch_size) % 10 == 0:
                    logger.info(f"Обработано {min(i + batch_size, len(node_uids))}/{len(node_uids)} узлов уровня")
            
            
            # Уменьшаем in_degree у соседей обработанных узлов (тоже батчами)
            for i in range(0, len(node_uids), batch_size):
                batch_uids = node_uids[i:i + batch_size]
                
                update_neighbors_query = """
                UNWIND $node_uids AS uid
                MATCH (n:Article {uid: uid})-[:BIBLIOGRAPHIC_LINK]->(neighbor:Article)
                WHERE neighbor.visited = false
                SET neighbor.in_deg = neighbor.in_deg - 1
                """
                
                async with self.circuit_breaker:
                    await neo4j_client.execute_query_with_retry(
                        update_neighbors_query, {"node_uids": batch_uids}
                    )
            
            processed_total += current_batch_size
            order_counter += current_batch_size  # Увеличиваем на реальное количество обработанных узлов
            
            if not self.should_throttle_progress():
                logger.info(f"Processed {processed_total}/{total_articles} nodes in topological order")
        
        # Обрабатываем оставшиеся узлы (если есть циклы, только связанные вершины)
        remaining_query = """
        MATCH (n:Article)
        WHERE n.visited = false
        AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
        RETURN count(n) AS remaining_count
        """
        
        async with self.circuit_breaker:
            remaining_result = await neo4j_client.execute_query_with_retry(remaining_query)
        remaining_count = int(remaining_result[0]["remaining_count"]) if remaining_result else 0
        
        if remaining_count > 0:
            logger.warning(f"Found {remaining_count} nodes in cycles, assigning fallback order")
            
            # Присваиваем порядок оставшимся узлам (циклы)
            # Получаем список оставшихся узлов
            remaining_nodes_query = """
            MATCH (n:Article)
            WHERE n.visited = false
            AND (EXISTS { ()-[:BIBLIOGRAPHIC_LINK]->(n) } OR EXISTS { (n)-[:BIBLIOGRAPHIC_LINK]->() })
            RETURN n.uid AS uid
            """
            
            async with self.circuit_breaker:
                remaining_nodes = await neo4j_client.execute_query_with_retry(remaining_nodes_query)
            
            # Присваиваем порядок всем узлам в цикле батчем
            if remaining_nodes:
                handle_cycles_query = """
                UNWIND $node_data AS item
                MATCH (n:Article {uid: item.uid})
                SET n.topo_order = item.order_value,
                    n.visited = true
                """
                
                # Подготавливаем данные для батча
                cycle_data = [
                    {"uid": row["uid"], "order_value": order_counter + i}
                    for i, row in enumerate(remaining_nodes)
                ]
                
                async with self.circuit_breaker:
                    await neo4j_client.execute_query_with_retry(
                        handle_cycles_query, {"node_data": cycle_data}
                    )
            
            processed_total += remaining_count
        
        logger.info(f"Complete topological sort finished: {processed_total}/{total_articles} nodes processed")


# Создаем глобальный экземпляр для использования в других модулях
topological_sorter = TopologicalSorter()
