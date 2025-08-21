// =============================================================================
// Neo4j процедуры для предварительной обработки больших графов
// Оптимизированы для работы с 30M+ узлов и 80M+ связей
// =============================================================================

// 1. Процедура для получения статистики графа с компонентами связности
CREATE OR REPLACE PROCEDURE distributed_layout.get_graph_stats()
YIELD nodeCount, edgeCount, componentCount, maxComponentSize, pinnedNodes, avgDegree
AS
$$
BEGIN
    // Получаем основную статистику
    CALL {
        MATCH (n) 
        RETURN count(n) as nodes
    }
    
    CALL {
        MATCH ()-[r:CITES]->() 
        RETURN count(r) as edges
    }
    
    CALL {
        MATCH (n) 
        WHERE n.is_pinned = true 
        RETURN count(n) as pinned
    }
    
    // Находим компоненты связности (упрощённая версия)
    CALL {
        MATCH (n)
        WITH n
        CALL apoc.path.subgraphAll(n, {
            relationshipFilter: "",
            maxLevel: -1
        }) YIELD nodes
        RETURN count(DISTINCT nodes) as components, max(size(nodes)) as maxSize
    }
    
    RETURN nodes as nodeCount, 
           edges as edgeCount,
           components as componentCount,
           maxSize as maxComponentSize,
           pinned as pinnedNodes,
           CASE WHEN nodes > 0 THEN toFloat(edges * 2) / nodes ELSE 0.0 END as avgDegree;
END
$$;

// 2. Процедура для разбиения графа на компоненты
CREATE OR REPLACE PROCEDURE distributed_layout.partition_graph(maxComponentSize INTEGER)
YIELD componentId, nodeIds, edgeCount
AS
$$
BEGIN
    // Используем Weakly Connected Components для разбиения
    CALL gds.graph.project(
        'graph_for_partitioning',
        '*',
        {
            CITES: {orientation: 'UNDIRECTED'}
        }
    );
    
    CALL gds.wcc.stream('graph_for_partitioning')
    YIELD nodeId, componentId
    WITH componentId, collect(gds.util.asNode(nodeId).uid) as nodeIds
    WHERE size(nodeIds) <= maxComponentSize
    
    // Подсчитываем рёбра для каждой компоненты
    UNWIND nodeIds as nodeId
    MATCH (n {uid: nodeId})-[r:CITES]-(m)
    WHERE m.uid IN nodeIds
    WITH componentId, nodeIds, count(DISTINCT r) as edgeCount
    
    RETURN componentId, nodeIds, edgeCount;
    
    // Очищаем временный граф
    CALL gds.graph.drop('graph_for_partitioning');
END
$$;

// 3. Процедура для топологической сортировки подграфа
CREATE OR REPLACE PROCEDURE distributed_layout.topological_sort_subgraph(nodeIds LIST<STRING>)
YIELD nodeId, layer
AS
$$
BEGIN
    // Создаём подграф из указанных узлов
    WITH nodeIds
    UNWIND nodeIds as nodeId
    MATCH (n {uid: nodeId})
    
    // Вычисляем слои через итеративный алгоритм
    WITH collect(n) as nodes
    CALL apoc.custom.asFunction('calculateLayers', 
        'UNWIND $nodes as node
         WITH node, size([(node)<-[:CITES]-(pred) WHERE pred.uid IN $nodeIds | pred]) as inDegree
         WITH node, inDegree
         ORDER BY inDegree
         WITH collect({node: node, layer: 0}) as nodeLayerMap
         
         // Итеративно вычисляем слои
         UNWIND range(0, size($nodes)-1) as iteration
         UNWIND nodeLayerMap as item
         WITH item.node as node, 
              max([layer IN [(item.node)-[:CITES]->(succ) WHERE succ.uid IN $nodeIds | 
                   head([nlm IN nodeLayerMap WHERE nlm.node = succ | nlm.layer])] | layer + 1]) as newLayer
         RETURN node.uid as nodeId, coalesce(newLayer, 0) as layer',
        'LIST<STRING>', 'MAP', true
    ) YIELD value
    
    RETURN value.nodeId as nodeId, value.layer as layer;
END
$$;

// 4. Процедура для получения подграфа компоненты
CREATE OR REPLACE PROCEDURE distributed_layout.get_component_subgraph(componentId INTEGER, batchSize INTEGER)
YIELD nodes, edges
AS
$$
BEGIN
    // Получаем узлы компоненты
    CALL distributed_layout.partition_graph(1000000)
    YIELD nodeIds
    WHERE componentId = $componentId
    
    // Получаем узлы
    UNWIND nodeIds as nodeId
    MATCH (n {uid: nodeId})
    WITH collect(n) as nodes, nodeIds
    
    // Получаем рёбра между узлами компоненты
    UNWIND nodes as n1
    UNWIND nodes as n2
    MATCH (n1)-[r:CITES]->(n2)
    WHERE n1.uid IN nodeIds AND n2.uid IN nodeIds
    WITH nodes, collect(r) as edges
    
    RETURN nodes, edges;
END
$$;

// 5. Процедура для батчевого обновления позиций
CREATE OR REPLACE PROCEDURE distributed_layout.batch_update_layout(updates LIST<MAP>)
YIELD updatedCount
AS
$$
BEGIN
    UNWIND $updates as update
    MATCH (n {uid: update.nodeId})
    SET n.level = update.level,
        n.layer = update.layer,
        n.sublevel_id = update.sublevelId,
        n.layout_updated_at = timestamp()
    
    RETURN count(*) as updatedCount;
END
$$;

// 6. Процедура для получения метрик производительности
CREATE OR REPLACE PROCEDURE distributed_layout.get_performance_metrics()
YIELD metric, value
AS
$$
BEGIN
    // Плотность графа
    CALL {
        MATCH (n), (m)
        WITH count(n) as nodes
        MATCH ()-[r:CITES]->()
        WITH nodes, count(r) as edges
        RETURN CASE WHEN nodes > 1 
               THEN toFloat(edges) / (nodes * (nodes - 1))
               ELSE 0.0 END as density
    }
    
    // Средняя степень
    CALL {
        MATCH (n)
        WITH n, size([(n)-[:CITES]-() | 1]) as degree
        RETURN avg(degree) as avgDegree
    }
    
    // Изолированные узлы
    CALL {
        MATCH (n)
        WHERE NOT (n)-[:CITES]-()
        RETURN count(n) as isolatedNodes
    }
    
    RETURN 'density' as metric, density as value
    UNION
    RETURN 'avg_degree' as metric, avgDegree as value
    UNION
    RETURN 'isolated_nodes' as metric, toFloat(isolatedNodes) as value;
END
$$;

// 7. Процедура для очистки старых результатов
CREATE OR REPLACE PROCEDURE distributed_layout.cleanup_old_layout(olderThanDays INTEGER)
YIELD cleanedCount
AS
$$
BEGIN
    MATCH (n)
    WHERE n.layout_updated_at < timestamp() - ($olderThanDays * 24 * 60 * 60 * 1000)
    REMOVE n.level, n.layer, n.sublevel_id, n.layout_updated_at
    
    RETURN count(*) as cleanedCount;
END
$$;

// 8. Процедура для получения статистики связности
CREATE OR REPLACE PROCEDURE distributed_layout.get_connectivity_stats()
YIELD totalNodes, totalEdges, avgDegree, isolatedNodes, maxDegree
AS
$$
BEGIN
    // Общая статистика
    CALL {
        MATCH (n)
        RETURN count(n) as nodes
    }
    
    CALL {
        MATCH ()-[r:CITES]->()
        RETURN count(r) as edges
    }
    
    // Статистика степеней
    CALL {
        MATCH (n)
        WITH n, size([(n)-[:CITES]-() | 1]) as degree
        RETURN avg(degree) as avgDegree,
               max(degree) as maxDegree,
               count(CASE WHEN degree = 0 THEN n END) as isolatedNodes
    }
    
    RETURN nodes as totalNodes,
           edges as totalEdges,
           avgDegree,
           isolatedNodes,
           maxDegree;
END
$$;

// 9. Процедура для получения топологических уровней
CREATE OR REPLACE PROCEDURE distributed_layout.get_topological_levels()
YIELD nodeId, level
AS
$$
BEGIN
    // Инициализируем все узлы с уровнем 0
    MATCH (n)
    SET n.temp_level = 0
    
    // Итеративно вычисляем уровни
    WITH 0 as iteration
    CALL {
        MATCH (n)
        WITH n, iteration
        MATCH (n)-[:CITES]->(succ)
        WITH n, succ, iteration
        WHERE succ.temp_level <= iteration
        SET n.temp_level = iteration + 1
        RETURN count(*) as updated
    }
    
    // Возвращаем результаты
    MATCH (n)
    WHERE n.temp_level IS NOT NULL
    RETURN n.uid as nodeId, n.temp_level as level
    ORDER BY level;
    
    // Очищаем временные данные
    MATCH (n)
    REMOVE n.temp_level;
END
$$;

// 10. Создание индексов для производительности
CREATE INDEX IF NOT EXISTS FOR ()-[r:CITES]-() ON (r.uid);

CREATE INDEX IF NOT EXISTS FOR (n) ON (n.level, n.layer, n.is_pinned);

CREATE INDEX IF NOT EXISTS FOR (n) ON (n.uid);

CREATE INDEX IF NOT EXISTS FOR (n) ON (n.is_pinned);
