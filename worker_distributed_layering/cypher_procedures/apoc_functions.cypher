// =============================================================================
// APOC функции для предварительной обработки больших графов
// Заменяют пользовательские процедуры и работают с Neo4j + APOC
// =============================================================================

// 1. Создание индексов для производительности
CREATE INDEX node_layout_composite IF NOT EXISTS 
FOR (n:Article) ON (n.level, n.layer, n.is_pinned);

CREATE INDEX node_uid_index IF NOT EXISTS 
FOR (n:Article) ON (n.uid);

CREATE INDEX relationship_uids IF NOT EXISTS 
FOR ()-[r:BIBLIOGRAPHIC_LINK]-() ON (r.uid);

CREATE INDEX pinned_nodes IF NOT EXISTS 
FOR (n:Article) ON (n.is_pinned);

// 2. Функция для получения статистики графа
// Вызов: CALL apoc.custom.asFunction('getGraphStats', 'MATCH (n) RETURN count(n) as nodeCount', 'MAP')
CALL apoc.custom.declareProcedure(
    'distributed_layout.get_graph_stats()',
    'CALL {
        MATCH (n:Article) 
        RETURN count(n) as nodes
    }
    CALL {
        MATCH ()-[r:BIBLIOGRAPHIC_LINK]->() 
        RETURN count(r) as edges
    }
    CALL {
        MATCH (n:Article) 
        WHERE n.is_pinned = true 
        RETURN count(n) as pinned
    }
    RETURN nodes as nodeCount, 
           edges as edgeCount,
           1 as componentCount,
           nodes as maxComponentSize,
           pinned as pinnedNodes,
           CASE WHEN nodes > 0 THEN toFloat(edges * 2) / nodes ELSE 0.0 END as avgDegree',
    'read',
    [['nodeCount', 'long'], ['edgeCount', 'long'], ['componentCount', 'long'], ['maxComponentSize', 'long'], ['pinnedNodes', 'long'], ['avgDegree', 'double']]
);

// 3. Функция для получения подграфа по ID узлов  
CALL apoc.custom.declareProcedure(
    'distributed_layout.get_subgraph_by_ids(nodeIds :: LIST<STRING>)',
    'WITH $nodeIds as nodeIds
     UNWIND nodeIds as nodeId
     MATCH (n:Article {uid: nodeId})
     WITH collect(distinct n) as nodes, nodeIds
     
     UNWIND nodes as n1
     UNWIND nodes as n2
     MATCH (n1:Article)-[r:BIBLIOGRAPHIC_LINK]->(n2:Article)
     WHERE n1.uid IN nodeIds AND n2.uid IN nodeIds
     
     WITH nodes, collect(distinct r) as edges
     RETURN [{nodes: [n IN nodes | {
         id: n.uid,
         content: coalesce(n.content, ""),
         is_pinned: coalesce(n.is_pinned, false),
         level: coalesce(n.level, 0),
         physical_scale: coalesce(n.physical_scale, 0)
     }], edges: [r IN edges | {
         id: r.uid,
         source_id: startNode(r).uid,
         target_id: endNode(r).uid
     }]}] as result',
    'read',
    [['result', 'list']]
);

// 4. Функция для батчевого обновления результатов укладки
CALL apoc.custom.declareProcedure(
    'distributed_layout.batch_update_positions(positions :: LIST<MAP>)',
    'UNWIND $positions as pos
     MATCH (n:Article {uid: pos.nodeId})
     SET n.level = pos.level,
         n.sublevel_id = pos.sublevelId,  
         n.layer = pos.layer,
         n.layout_updated_at = timestamp()
     RETURN count(*) as updatedCount',
    'write',
    [['updatedCount', 'long']]
);

// 5. Функция для получения метрик производительности
CALL apoc.custom.declareProcedure(
    'distributed_layout.get_performance_metrics()',
    'CALL {
        MATCH (n:Article), (m:Article)
        WITH count(n) as nodes
        MATCH ()-[r:BIBLIOGRAPHIC_LINK]->()
        WITH nodes, count(r) as edges
        RETURN CASE WHEN nodes > 1 
               THEN toFloat(edges) / (nodes * (nodes - 1))
               ELSE 0.0 END as density
    }
    CALL {
        MATCH (n:Article)
        WITH n, size([(n)-[:BIBLIOGRAPHIC_LINK]-() | 1]) as degree
        RETURN avg(degree) as avgDegree
    }
    CALL {
        MATCH (n:Article)
        WHERE NOT (n)-[:BIBLIOGRAPHIC_LINK]-()
        RETURN count(n) as isolatedNodes
    }
    RETURN [
        {metric: "density", value: density},
        {metric: "avg_degree", value: avgDegree},
        {metric: "isolated_nodes", value: toFloat(isolatedNodes)}
    ] as metrics',
    'read',
    [['metrics', 'list']]
);

// 6. Функция для очистки старых результатов укладки
CALL apoc.custom.declareProcedure(
    'distributed_layout.cleanup_old_layout(olderThanDays :: LONG)',
    'MATCH (n:Article)
     WHERE n.layout_updated_at < timestamp() - ($olderThanDays * 24 * 60 * 60 * 1000)
     REMOVE n.level, n.sublevel_id, n.layer, n.layout_updated_at
     RETURN count(*) as cleanedCount',
    'write', 
    [['cleanedCount', 'long']]
);

// 7. Функция для топологической сортировки подграфа
CALL apoc.custom.declareProcedure(
    'distributed_layout.topological_sort(nodeIds :: LIST<STRING>)',
    'WITH $nodeIds as nodeIds
     UNWIND nodeIds as nodeId
     MATCH (n:Article {uid: nodeId})
     
     // Вычисляем входящие степени
     WITH nodeIds, collect(n) as nodes
     UNWIND nodes as node
     WITH node, nodeIds, 
          size([(node)<-[:BIBLIOGRAPHIC_LINK]-(pred:Article) 
                WHERE pred.uid IN nodeIds | pred]) as inDegree
     
     // Сортируем топологически (упрощённая версия)
     WITH node, inDegree
     ORDER BY inDegree
     WITH collect({nodeId: node.uid, layer: 0}) as sortedNodes
     
     // Назначаем слои итеративно  
     UNWIND range(0, size(sortedNodes)-1) as i
     WITH sortedNodes[i] as item, sortedNodes
     MATCH (n:Article {uid: item.nodeId})
     WITH n, sortedNodes,
          max([0] + [layer + 1 | pred IN [(n)<-[:BIBLIOGRAPHIC_LINK]-(p:Article) 
                                          WHERE p.uid IN [s.nodeId | s IN sortedNodes] | p]
                     | head([s IN sortedNodes WHERE s.nodeId = pred.uid | s.layer])]) as calculatedLayer
     
     RETURN {nodeId: n.uid, layer: calculatedLayer} as result',
    'read',
    [['result', 'map']]
);

// 8. Функция для разбиения графа на компоненты (упрощённая версия)
CALL apoc.custom.declareProcedure(
    'distributed_layout.partition_graph(maxComponentSize :: LONG)',
    'MATCH (n:Article)
     WITH collect(n.uid) as allNodes, $maxComponentSize as maxSize
     
     // Упрощённое разбиение - берём чанки фиксированного размера
     UNWIND range(0, size(allNodes)-1, maxSize) as start
     WITH allNodes[start..start+maxSize] as componentNodes, start/maxSize as componentId
     WHERE size(componentNodes) > 0
     
     // Подсчитываем рёбра в компоненте
     UNWIND componentNodes as nodeId1
     UNWIND componentNodes as nodeId2  
     MATCH (n1:Article {uid: nodeId1})-[r:BIBLIOGRAPHIC_LINK]->(n2:Article {uid: nodeId2})
     WHERE nodeId1 <> nodeId2
     WITH componentId, componentNodes, count(r) as edgeCount
     
     RETURN {
         componentId: componentId, 
         nodeIds: componentNodes, 
         edgeCount: edgeCount
     } as result',
    'read',
    [['result', 'map']]
);
