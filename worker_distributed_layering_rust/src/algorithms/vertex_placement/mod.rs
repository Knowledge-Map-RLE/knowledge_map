/// Vertex placement module - Main coordinator
///
/// This module coordinates the entire vertex placement process:
/// 1. Layer assignment using BFS algorithm
/// 2. Vertex placement within layers
/// 3. Optional layout optimization
/// 4. Edge routing and polyline computation
///
/// This refactored version fixes the critical bug where only 3 layers were created
/// instead of hundreds, by replacing the longest_path approach with BFS-based layer assignment.

mod stats;
mod layer_assignment;
mod placement;
mod optimization;
mod edge_routing;
mod global_layer_state;

// Re-export public types
pub use stats::PlacementStats;
pub use placement::{VertexPosition, PlacementConfig, OccupiedPositions, place_all_vertices};
pub use optimization::{OptimizationOptions, count_edge_crossings};
pub use edge_routing::{EdgeRoutingOptions, calculate_edge_length, get_edge_statistics};
pub use global_layer_state::{GlobalLayerState, LayerStatistics};

use anyhow::Result;
use std::collections::HashMap;
use crate::data_structures::Graph;

/// Main vertex placer orchestrator
#[derive(Debug)]
pub struct OptimalVertexPlacer {
    /// Configuration for vertex placement
    config: PlacementConfig,

    /// Options for layout optimization
    opt_options: OptimizationOptions,

    /// Options for edge routing
    edge_options: EdgeRoutingOptions,

    /// Statistics about the placement
    stats: PlacementStats,
}

impl OptimalVertexPlacer {
    /// Create a new vertex placer with default settings
    pub fn new() -> Self {
        Self {
            config: PlacementConfig::default(),
            opt_options: OptimizationOptions::default(),
            edge_options: EdgeRoutingOptions::default(),
            stats: PlacementStats::new(),
        }
    }

    /// Create a new vertex placer with custom configuration
    pub fn with_config(
        config: PlacementConfig,
        opt_options: OptimizationOptions,
        edge_options: EdgeRoutingOptions,
    ) -> Self {
        Self {
            config,
            opt_options,
            edge_options,
            stats: PlacementStats::new(),
        }
    }

    /// Main entry point: place all vertices in the graph
    ///
    /// This is the new BFS-based algorithm that fixes the 3-layer bug.
    ///
    /// Process:
    /// 1. Assign layers using BFS from source nodes
    /// 2. Place vertices within their assigned layers
    /// 3. Optionally optimize the layout
    /// 4. Compute edge paths (polylines)
    /// 5. Update statistics
    ///
    /// Note: The unused parameters (_longest_path, _topo_order) are kept for
    /// backward compatibility with existing code that calls this method.
    pub async fn place_vertices(
        &mut self,
        graph: &Graph,
        _longest_path: &[String], // No longer used, kept for compatibility
        _topo_order: &[String],   // No longer used, kept for compatibility
    ) -> Result<(Vec<crate::neo4j::VertexPosition>, HashMap<(String, String), Vec<(f32, f32)>>)> {
        self.reset_state();

        tracing::info!("=== Starting BFS-based vertex placement (FIXED algorithm) ===");

        // Step 1: Assign layers using BFS (FIXED: replaces longest_path approach)
        tracing::info!("Step 1/5: Assigning layers using BFS from source nodes...");
        let layer_map = layer_assignment::assign_layers_bfs(graph).await?;

        if layer_map.is_empty() {
            tracing::warn!("No vertices were assigned layers!");
            return Ok((vec![], HashMap::new()));
        }

        // Log layer statistics
        layer_assignment::log_layer_statistics(&layer_map);

        // Step 2: Place vertices at (x, y) coordinates based on their layers
        tracing::info!("Step 2/5: Placing vertices at coordinates...");
        let mut positions = placement::place_all_vertices(&layer_map, &self.config);

        // Step 3: Optional optimization
        if self.opt_options.compact_layout {
            tracing::info!("Step 3/5: Optimizing layout...");
            optimization::optimize_placement(&mut positions, graph, &self.opt_options).await?;
        } else {
            tracing::info!("Step 3/5: Skipping optimization (disabled)");
        }

        // Step 4: Compute edge paths (polylines)
        tracing::info!("Step 4/5: Computing edge paths...");
        let edge_paths = edge_routing::compute_edge_paths(
            &positions,
            graph,
            &self.config,
            &self.edge_options,
        )?;

        edge_routing::get_edge_statistics(&edge_paths);

        // Step 5: Update statistics
        tracing::info!("Step 5/5: Updating statistics...");
        self.update_stats(&positions);

        let (width, height) = placement::calculate_layout_dimensions(&positions, &self.config);

        tracing::info!("=== Vertex placement complete ===");
        tracing::info!("Final statistics:");
        tracing::info!("  Vertices placed: {}", self.stats.vertices_placed);
        tracing::info!("  Layers used: {}", self.stats.layers_used);
        tracing::info!("  Avg vertices/layer: {:.2}", self.stats.avg_vertices_per_layer);
        tracing::info!("  Layout dimensions: {:.0} x {:.0} px", width, height);

        // Convert internal VertexPosition to neo4j::VertexPosition
        let neo4j_positions: Vec<crate::neo4j::VertexPosition> = positions
            .into_iter()
            .map(|p| crate::neo4j::VertexPosition {
                article_id: p.vertex_id,
                layer: p.layer,
                level: p.level,
                x: p.x,
                y: p.y,
            })
            .collect();

        Ok((neo4j_positions, edge_paths))
    }

    /// Reset internal state before a new placement
    fn reset_state(&mut self) {
        self.stats.reset();
    }

    /// Update placement statistics after placing vertices
    fn update_stats(&mut self, positions: &[VertexPosition]) {
        if positions.is_empty() {
            return;
        }

        self.stats.vertices_placed = positions.len();

        // Count unique layers
        let mut layers = std::collections::HashSet::new();
        let mut layer_counts: HashMap<i32, usize> = HashMap::new();

        for pos in positions {
            layers.insert(pos.layer);
            *layer_counts.entry(pos.layer).or_insert(0) += 1;
        }

        self.stats.layers_used = layers.len();

        // Calculate average and max vertices per layer
        if !layer_counts.is_empty() {
            self.stats.avg_vertices_per_layer =
                positions.len() as f32 / layer_counts.len() as f32;
            self.stats.max_vertices_in_layer =
                *layer_counts.values().max().unwrap_or(&0);
        }

        // Calculate layout dimensions
        let (width, height) = placement::calculate_layout_dimensions(positions, &self.config);
        self.stats.total_width = width;
        self.stats.total_height = height;
    }

    /// Get current placement statistics
    pub fn get_stats(&self) -> &PlacementStats {
        &self.stats
    }

    /// Get mutable reference to configuration (for testing/adjustment)
    pub fn get_config_mut(&mut self) -> &mut PlacementConfig {
        &mut self.config
    }

    /// Get mutable reference to optimization options (for testing/adjustment)
    pub fn get_opt_options_mut(&mut self) -> &mut OptimizationOptions {
        &mut self.opt_options
    }

    /// Get mutable reference to edge routing options (for testing/adjustment)
    pub fn get_edge_options_mut(&mut self) -> &mut EdgeRoutingOptions {
        &mut self.edge_options
    }
}

impl Default for OptimalVertexPlacer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_simple_graph_placement() {
        // Create a simple graph: A -> B -> C
        let mut graph = Graph::new();
        graph.add_edge("A", "B");
        graph.add_edge("B", "C");

        let mut placer = OptimalVertexPlacer::new();

        // Empty vectors for backward compatibility
        let longest_path = vec![];
        let topo_order = vec![];

        let (positions, _edge_paths) = placer
            .place_vertices(&graph, &longest_path, &topo_order)
            .await
            .unwrap();

        // Should have 3 positions
        assert_eq!(positions.len(), 3);

        // Verify layers are assigned correctly (A=0, B=1, C=2)
        let pos_map: HashMap<&str, &VertexPosition> = positions
            .iter()
            .map(|p| (p.vertex_id.as_str(), p))
            .collect();

        assert_eq!(pos_map.get("A").unwrap().layer, 0);
        assert_eq!(pos_map.get("B").unwrap().layer, 1);
        assert_eq!(pos_map.get("C").unwrap().layer, 2);

        // Verify statistics
        let stats = placer.get_stats();
        assert_eq!(stats.vertices_placed, 3);
        assert_eq!(stats.layers_used, 3);
    }

    #[tokio::test]
    async fn test_diamond_graph_placement() {
        // Create a diamond: A -> B, A -> C, B -> D, C -> D
        let mut graph = Graph::new();
        graph.add_edge("A", "B");
        graph.add_edge("A", "C");
        graph.add_edge("B", "D");
        graph.add_edge("C", "D");

        let mut placer = OptimalVertexPlacer::new();

        let (positions, _edge_paths) = placer
            .place_vertices(&graph, &vec![], &vec![])
            .await
            .unwrap();

        assert_eq!(positions.len(), 4);

        let pos_map: HashMap<&str, &VertexPosition> = positions
            .iter()
            .map(|p| (p.vertex_id.as_str(), p))
            .collect();

        // A should be layer 0 (source)
        assert_eq!(pos_map.get("A").unwrap().layer, 0);

        // B and C should be layer 1
        assert_eq!(pos_map.get("B").unwrap().layer, 1);
        assert_eq!(pos_map.get("C").unwrap().layer, 1);

        // D should be layer 2 (max of predecessors + 1)
        assert_eq!(pos_map.get("D").unwrap().layer, 2);

        let stats = placer.get_stats();
        assert_eq!(stats.layers_used, 3);
    }
}
