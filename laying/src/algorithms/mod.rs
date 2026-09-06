/*!
# Высокопроизводительные алгоритмы укладки графов

Модуль содержит оптимизированные реализации алгоритмов для укладки больших графов:

- **Топологическая сортировка**: O(V + E) → O((V + E) / P) с параллелизмом
- **Поиск longest path**: O(V²) → O(V log V) с SIMD 
- **Размещение вершин**: O(V²) → O(V) с эффективными структурами данных
- **Пространственная оптимизация**: Минимизация перекрытий и улучшение читаемости

## Архитектура

```text
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Graph Input     │───▶│ Preprocessing   │───▶│ Topological     │
│ (Edges only)    │    │ & Validation    │    │ Sort (SIMD)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Layout Result   │◀───│ Position        │◀───│ Longest Path    │
│ (ID+Layer+Level)│    │ Assignment      │    │ Detection       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```
*/

pub mod topological_sort;
pub mod longest_path;
pub mod vertex_placement;
pub mod memory_optimized;
pub mod parallel_processing;
pub mod dag_conversion;

use crate::generated::{LayoutOptions, LayoutStatistics};
use crate::neo4j::{GraphEdge, VertexPosition};
use anyhow::Result;
use std::collections::HashMap;
use serde_json;

/// Трейт для алгоритмов укладки графов
pub trait LayoutAlgorithm: Send + Sync {
    /// Вычисление укладки графа
    fn compute_layout<'a>(
        &'a mut self,
        edges: Vec<GraphEdge>,
        options: &'a LayoutOptions,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<LayoutResult>> + Send + 'a>>;
    
    /// Получение статистики алгоритма
    fn get_algorithm_stats(&self) -> AlgorithmStats;
    
    /// Валидация входных данных
    fn validate_input(&self, edges: &[GraphEdge]) -> Result<()>;
}

/// Результат работы алгоритма укладки
#[derive(Debug, Clone)]
pub struct LayoutResult {
    /// Позиции вершин
    pub positions: Vec<VertexPosition>,
    
    /// Статистика выполнения
    pub statistics: LayoutStatistics,
    
    /// Метаданные алгоритма
    pub metadata: AlgorithmMetadata,
}

/// Метаданные алгоритма
#[derive(Debug, Clone)]
pub struct AlgorithmMetadata {
    /// Использованные оптимизации
    pub optimizations_used: Vec<String>,
    
    /// Сложность алгоритма
    pub complexity: String,
    
    /// Версия алгоритма
    pub version: String,
    
    /// Параметры алгоритма
    pub parameters: HashMap<String, String>,
}

/// Статистика алгоритма
#[derive(Debug, Clone)]
pub struct AlgorithmStats {
    /// Время выполнения компонентов (мс)
    pub component_times: HashMap<String, u64>,
    
    /// Использование памяти (байты)
    pub memory_usage: HashMap<String, u64>,
    
    /// Количество итераций
    pub iterations: u32,
    
    /// Эффективность (0.0 - 1.0)
    pub efficiency: f32,
}

/// Основной алгоритм укладки графов
#[derive(Debug)]
pub struct HighPerformanceLayoutEngine {
    /// Алгоритм топологической сортировки
    topo_sorter: topological_sort::ParallelTopoSort,
    
    /// Алгоритм поиска longest path
    longest_path_finder: longest_path::SIMDLongestPath,
    
    /// Алгоритм размещения вершин
    vertex_placer: vertex_placement::OptimalVertexPlacer,
    
    /// Менеджер памяти
    memory_manager: memory_optimized::MemoryManager,
    
    /// Статистика
    stats: AlgorithmStats,
}

impl HighPerformanceLayoutEngine {
    /// Создание нового экземпляра алгоритма
    pub fn new(options: &LayoutOptions) -> Result<Self> {
        let topo_sorter = topological_sort::ParallelTopoSort::new(
            options.max_workers as usize,
            options.chunk_size as usize,
        )?;
        
        let longest_path_finder = longest_path::SIMDLongestPath::new(
            options.enable_simd,
        )?;
        
        // Create vertex placer with custom configuration
        let placement_config = vertex_placement::PlacementConfig {
            block_width: options.block_width,
            block_height: options.block_height,
            horizontal_gap: options.horizontal_gap,
            vertical_gap: options.vertical_gap,
        };

        let opt_options = vertex_placement::OptimizationOptions {
            compact_layout: options.optimize_layout,
            max_iterations: 10,
        };

        let edge_options = vertex_placement::EdgeRoutingOptions::default();

        let vertex_placer = vertex_placement::OptimalVertexPlacer::with_config(
            placement_config,
            opt_options,
            edge_options,
        );
        
        let memory_manager = memory_optimized::MemoryManager::new(
            crate::generated::MemoryStrategy::try_from(options.memory_strategy).unwrap_or(crate::generated::MemoryStrategy::MemoryAuto),
        )?;
        
        Ok(Self {
            topo_sorter,
            longest_path_finder,
            vertex_placer,
            memory_manager,
            stats: AlgorithmStats {
                component_times: HashMap::new(),
                memory_usage: HashMap::new(),
                iterations: 0,
                efficiency: 0.0,
            },
        })
    }
    
    /// Валидация и фильтрация входных данных
    fn validate_edges(&self, edges: &[GraphEdge]) -> Result<()> {
        if edges.is_empty() {
            return Err(anyhow::anyhow!("Граф не может быть пустым"));
        }

        let valid = edges.iter()
            .filter(|e| !e.source_id.trim().is_empty() && !e.target_id.trim().is_empty())
            .filter(|e| e.source_id != e.target_id)
            .count();

        if valid == 0 {
            return Err(anyhow::anyhow!("Нет валидных связей после фильтрации"));
        }

        Ok(())
    }
    
    /// Построение графа из связей
    fn build_graph(&self, edges: &[GraphEdge]) -> Result<crate::data_structures::Graph> {
        use crate::data_structures::GraphBuilder;
        use std::collections::HashSet;
        use tracing::info;

        let mut builder = GraphBuilder::new();
        let mut unique_edges = HashSet::new();
        let mut added_count = 0;

        // Добавление связей с фильтрацией и дедупликацией
        for edge in edges {
            // Пропускаем пустые и self-loop связи
            if edge.source_id.trim().is_empty() || edge.target_id.trim().is_empty() {
                continue;
            }
            if edge.source_id == edge.target_id {
                continue;
            }

            // Пропускаем дубликаты
            let edge_key = (&edge.source_id, &edge.target_id);
            if !unique_edges.insert(edge_key) {
                continue;
            }

            // УНИФИЦИРОВАННАЯ СЕМАНТИКА SOURCE/TARGET:
            //
            // SOURCE (left, слева):
            // - Старая cited статья из reference list
            // - Получает НИЗКИЕ слои (0, 1, 2...) - слева на графе
            // - Это наиболее цитируемые статьи
            //
            // TARGET (right, справа):
            // - Новая citing статья
            // - Получает ВЫСОКИЕ слои - справа на графе
            // - Это статьи которые цитируют SOURCE
            //
            // Направление: SOURCE -> TARGET (старая -> новая)
            //
            // В Neo4j хранится ТАК ЖЕ: SOURCE -> TARGET (cited -> citing)
            // НЕ разворачиваем! Используем как есть.
            //
            // BFS корректно работает с этим направлением:
            // - Вершины без входящих рёбер (старые, SOURCE) получают слой 0
            // - Вершины, цитирующие их (новые, TARGET) получают более высокие слои
            //
            builder.add_edge(
                edge.source_id.clone(),  // SOURCE: cited reference (старая статья)
                edge.target_id.clone(),  // TARGET: citing article (новая статья)
                edge.weight,
            )?;
            added_count += 1;
        }


        builder.build()
    }
}

impl LayoutAlgorithm for HighPerformanceLayoutEngine {
    fn compute_layout<'a>(
        &'a mut self,
        edges: Vec<GraphEdge>,
        options: &'a LayoutOptions,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<LayoutResult>> + Send + 'a>> {
        Box::pin(async move {
        use std::time::Instant;
        use tracing::info;
        
        let start_time = Instant::now();
        
        info!("Layout: {} edges", edges.len());

        // 1. Валидация входных данных
        self.validate_edges(&edges)?;

        // 1.1. Приведение к DAG (разворот минимального числа рёбер).
        // Включается опцией convert_to_dag. Применяется только при наличии
        // циклов: разворачиваем feedback arc set, чтобы топологическая
        // сортировка корректно покрыла все вершины (все слои заполняются).
        let processed_edges;
        let mut dag_stats: Option<dag_conversion::DagResult> = None;
        if options.convert_to_dag {
            let tuples: Vec<(String, String, f32, String)> = edges
                .iter()
                .map(|e| (e.source_id.clone(), e.target_id.clone(), e.weight, e.edge_type.clone()))
                .collect();
            let dag = dag_conversion::convert_to_dag(&tuples, &[])?;
            if dag.reversed_count > 0 {
                info!(
                    "DAG conversion: reversed {} edges, {} cyclic vertices",
                    dag.reversed_count, dag.cyclic_vertices
                );
                let reversed_count = dag.reversed_count;
                let cyclic_vertices = dag.cyclic_vertices;
                processed_edges = dag
                    .edges
                    .into_iter()
                    .map(|e| GraphEdge {
                        source_id: e.source_id,
                        target_id: e.target_id,
                        weight: e.weight,
                        edge_type: e.edge_type,
                    })
                    .collect();
                dag_stats = Some(dag_conversion::DagResult {
                    edges: Vec::new(),
                    reversed_count,
                    cyclic_vertices,
                });
            } else {
                processed_edges = edges;
            }
        } else {
            processed_edges = edges;
        }

        // 2. Построение графа
        let graph = self.build_graph(&processed_edges)?;
        info!("Graph: {} vertices, {} edges", graph.vertex_count(), graph.edge_count());

        // 3. Топологическая сортировка
        let topo_start = Instant::now();
        let topo_order = self.topo_sorter.compute_parallel(&graph).await?;
        let topo_time = topo_start.elapsed().as_millis() as u64;
        info!("Topo sort: {} vertices in {} ms", topo_order.order.len(), topo_time);

        // 4. Поиск longest path
        let lp_start = Instant::now();
        let longest_path = self.longest_path_finder.find_simd(&graph, &topo_order.order).await?;
        let lp_time = lp_start.elapsed().as_millis() as u64;
        info!("Longest path: {} vertices in {} ms", longest_path.len(), lp_time);

        // 5. Размещение вершин
        let placement_start = Instant::now();
        let (positions, edge_paths) = self.vertex_placer.place_vertices(
            &graph,
            &longest_path,
            &topo_order.order,
        ).await?;
        let placement_time = placement_start.elapsed().as_millis() as u64;
        info!("Placement: {} vertices in {} ms", positions.len(), placement_time);
        
        let total_time = start_time.elapsed().as_millis() as u64;

        let edge_paths_payload = if edge_paths.is_empty() {
            None
        } else {
            let mut map = HashMap::new();
            for ((src, dst), points) in &edge_paths {
                let key = format!("{}->{}", src, dst);
                let value: Vec<[f32; 2]> = points.iter().map(|(x, y)| [*x, *y]).collect();
                map.insert(key, value);
            }
            Some(serde_json::to_string(&map)?)
        };
        
        
        // Создание статистики
        let statistics = LayoutStatistics {
            processing_time_ms: total_time as i64,
            vertices_processed: graph.vertex_count() as i64,
            edges_processed: processed_edges.len() as i64,
            iterations_completed: 1,
            memory_used_bytes: self.memory_manager.get_memory_usage() as i64,
            connected_components: 1, // Упрощенная версия
            longest_path_length: longest_path.len() as i32,
            vertices_per_second: (graph.vertex_count() as f32 / total_time as f32 * 1000.0),
            algorithm_metrics: Some(crate::generated::AlgorithmMetrics {
                topo_sort_complexity: "O((V + E) / P)".to_string(),
                topo_sort_time_ms: topo_time as i64,
                longest_path_time_ms: lp_time as i64,
                placement_time_ms: placement_time as i64,
                layers_used: self.vertex_placer.get_stats().layers_used as i32,
                max_level: positions.iter().map(|p| p.level).max().unwrap_or(0),
                space_efficiency: if self.vertex_placer.get_stats().vertices_placed > 0 {
                    self.vertex_placer.get_stats().vertices_placed as f32 /
                    (self.vertex_placer.get_stats().layers_used * self.vertex_placer.get_stats().vertices_placed / self.vertex_placer.get_stats().layers_used) as f32
                } else {
                    0.0
                },
            }),
        };
        
        // Метаданные
        let mut optimizations_used = vec![
            "SIMD".to_string(),
            "Parallel Processing".to_string(),
            "Memory Optimization".to_string(),
        ];
        let mut parameters = {
            let mut params = HashMap::new();
            params.insert("chunk_size".to_string(), options.chunk_size.to_string());
            params.insert("max_workers".to_string(), options.max_workers.to_string());
            params.insert("simd_enabled".to_string(), options.enable_simd.to_string());
            if let Some(ref payload) = edge_paths_payload {
                params.insert("edge_paths".to_string(), payload.clone());
            }
            params
        };
        if let Some(ref dag) = dag_stats {
            optimizations_used.push("DAG conversion (feedback arc set)".to_string());
            parameters.insert("dag_reversed_edges".to_string(), dag.reversed_count.to_string());
            parameters.insert("dag_cyclic_vertices".to_string(), dag.cyclic_vertices.to_string());
        }

        let metadata = AlgorithmMetadata {
            optimizations_used,
            complexity: "O((V + E) / P + V log V)".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
            parameters,
        };
        
        let result = LayoutResult {
            positions,
            statistics,
            metadata,
        };
        
        info!(
            "Layout done: {} vertices, {} edges in {} ms ({:.0} v/s)",
            graph.vertex_count(), processed_edges.len(), total_time,
            graph.vertex_count() as f32 / total_time as f32 * 1000.0
        );
        
        Ok(result)
        })
    }
    
    fn get_algorithm_stats(&self) -> AlgorithmStats {
        self.stats.clone()
    }
    
    fn validate_input(&self, edges: &[GraphEdge]) -> Result<()> {
        self.validate_edges(edges)
    }
}
