/// Global layer state for iterative batch processing
///
/// This module implements global layer assignment that works across multiple batches.
/// The key insight is that layer assignment must be done globally, not per-batch,
/// to correctly capture the full depth of citation chains in the graph.
///
/// Algorithm:
/// 1. Process edges in batches to save memory
/// 2. Maintain global state of vertex layers across all batches
/// 3. Iteratively update layers as new edges are discovered
/// 4. Use topological ordering principles: layer[target] = max(layer[source] + 1)

use std::collections::{HashMap, HashSet, VecDeque};
use anyhow::Result;
use tracing::{info, debug};

/// Global state for layer assignment across multiple batches
#[derive(Debug)]
pub struct GlobalLayerState {
    /// Maps vertex_id -> current assigned layer
    vertex_layers: HashMap<String, i32>,

    /// Maps vertex_id -> set of outgoing edges (target vertices)
    outgoing_edges: HashMap<String, HashSet<String>>,

    /// Maps vertex_id -> set of incoming edges (source vertices)
    incoming_edges: HashMap<String, HashSet<String>>,

    /// Vertices that need layer recalculation (dirty set)
    dirty_vertices: HashSet<String>,

    /// Statistics
    max_layer: i32,
    total_vertices: usize,
    total_edges: usize,
    update_iterations: usize,
}

impl GlobalLayerState {
    /// Create a new empty global layer state
    pub fn new() -> Self {
        info!("🌍 Initializing Global Layer State for iterative batch processing");
        Self {
            vertex_layers: HashMap::new(),
            outgoing_edges: HashMap::new(),
            incoming_edges: HashMap::new(),
            dirty_vertices: HashSet::new(),
            max_layer: 0,
            total_vertices: 0,
            total_edges: 0,
            update_iterations: 0,
        }
    }

    /// Add a batch of edges to the global state
    ///
    /// This method:
    /// 1. Adds new edges to the graph structure
    /// 2. Marks affected vertices as "dirty" for recalculation
    /// 3. Does NOT immediately update layers (use propagate_layers for that)
    pub fn add_edges_batch(&mut self, edges: &[(String, String)]) -> Result<()> {
        debug!("📥 Adding batch of {} edges to global state", edges.len());

        let mut new_vertices = 0;
        let mut new_edges = 0;

        for (source, target) in edges {
            // Skip invalid edges
            if source.trim().is_empty() || target.trim().is_empty() || source == target {
                continue;
            }

            // Track if vertices are new
            let source_is_new = !self.vertex_layers.contains_key(source);
            let target_is_new = !self.vertex_layers.contains_key(target);

            if source_is_new {
                self.vertex_layers.insert(source.clone(), 0);
                new_vertices += 1;
            }

            if target_is_new {
                self.vertex_layers.insert(target.clone(), 0);
                new_vertices += 1;
            }

            // Add outgoing edge from source
            let outgoing = self.outgoing_edges.entry(source.clone()).or_insert_with(HashSet::new);
            if outgoing.insert(target.clone()) {
                new_edges += 1;
            }

            // Add incoming edge to target
            let incoming = self.incoming_edges.entry(target.clone()).or_insert_with(HashSet::new);
            incoming.insert(source.clone());

            // Mark target as dirty (its layer may need updating)
            self.dirty_vertices.insert(target.clone());
        }

        self.total_vertices = self.vertex_layers.len();
        self.total_edges += new_edges;

        debug!("✅ Batch added: {} new vertices, {} new edges, {} dirty vertices",
               new_vertices, new_edges, self.dirty_vertices.len());

        Ok(())
    }

    /// Propagate layer updates through the graph
    ///
    /// This implements an iterative BFS-like algorithm:
    /// - For each vertex, layer = max(all predecessor layers) + 1
    /// - Continue until no more updates are needed (convergence)
    ///
    /// Returns: number of vertices whose layers were updated
    pub fn propagate_layers(&mut self) -> Result<usize> {
        self.update_iterations += 1;

        debug!("🔄 Starting layer propagation iteration {} with {} dirty vertices",
               self.update_iterations, self.dirty_vertices.len());

        if self.dirty_vertices.is_empty() {
            debug!("✅ No dirty vertices, skipping propagation");
            return Ok(0);
        }

        let mut updated_count = 0;
        let mut queue = VecDeque::new();

        // Initialize queue with dirty vertices
        for vertex in self.dirty_vertices.drain() {
            queue.push_back(vertex);
        }

        // Process queue until empty
        while let Some(vertex) = queue.pop_front() {
            // Calculate new layer based on predecessors
            let new_layer = if let Some(incoming) = self.incoming_edges.get(&vertex) {
                if incoming.is_empty() {
                    // No incoming edges = source vertex = layer 0
                    0
                } else {
                    // Layer = max(predecessor layers) + 1
                    incoming.iter()
                        .filter_map(|pred| self.vertex_layers.get(pred))
                        .max()
                        .map(|&max_pred_layer| max_pred_layer + 1)
                        .unwrap_or(0)
                }
            } else {
                // No incoming edges = source vertex = layer 0
                0
            };

            // Get current layer
            let current_layer = *self.vertex_layers.get(&vertex).unwrap_or(&0);

            // Update if layer changed
            if new_layer != current_layer {
                self.vertex_layers.insert(vertex.clone(), new_layer);
                self.max_layer = self.max_layer.max(new_layer);
                updated_count += 1;

                // Mark all successors as dirty
                if let Some(outgoing) = self.outgoing_edges.get(&vertex) {
                    for successor in outgoing {
                        queue.push_back(successor.clone());
                    }
                }
            }
        }

        debug!("✅ Layer propagation complete: {} vertices updated, max layer = {}",
               updated_count, self.max_layer);

        Ok(updated_count)
    }

    /// Run layer propagation until convergence
    ///
    /// Continues propagating until no more updates occur
    ///
    /// Returns: total number of updates across all iterations
    pub fn propagate_until_convergence(&mut self) -> Result<usize> {
        info!("🔄 Starting layer propagation until convergence...");

        let mut total_updates = 0;
        let mut iteration = 0;
        let max_iterations = 100; // Safety limit

        loop {
            iteration += 1;
            let updates = self.propagate_layers()?;
            total_updates += updates;

            if updates == 0 {
                info!("✅ Convergence reached after {} iterations, {} total updates", iteration, total_updates);
                break;
            }

            if iteration >= max_iterations {
                info!("⚠️ Reached max iterations ({}), stopping propagation", max_iterations);
                break;
            }

            if iteration % 10 == 0 {
                info!("📊 Iteration {}: {} updates, max layer = {}", iteration, updates, self.max_layer);
            }
        }

        Ok(total_updates)
    }

    /// Get the final layer assignments
    pub fn get_layer_map(&self) -> &HashMap<String, i32> {
        &self.vertex_layers
    }

    /// Get statistics about the current state
    pub fn get_statistics(&self) -> LayerStatistics {
        let mut layer_distribution: HashMap<i32, usize> = HashMap::new();

        for &layer in self.vertex_layers.values() {
            *layer_distribution.entry(layer).or_insert(0) += 1;
        }

        LayerStatistics {
            total_vertices: self.total_vertices,
            total_edges: self.total_edges,
            max_layer: self.max_layer,
            unique_layers: layer_distribution.len(),
            layer_distribution,
            update_iterations: self.update_iterations,
        }
    }

    /// Log detailed statistics
    pub fn log_statistics(&self) {
        let stats = self.get_statistics();

        info!("=== Global Layer State Statistics ===");
        info!("📊 Total vertices: {}", stats.total_vertices);
        info!("🔗 Total edges: {}", stats.total_edges);
        info!("📏 Max layer: {}", stats.max_layer);
        info!("🔢 Unique layers: {}", stats.unique_layers);
        info!("🔄 Update iterations: {}", stats.update_iterations);

        if !stats.layer_distribution.is_empty() {
            info!("📈 Layer distribution (first 20 layers):");
            let mut sorted_layers: Vec<_> = stats.layer_distribution.iter().collect();
            sorted_layers.sort_by_key(|(layer, _)| *layer);

            for (layer, count) in sorted_layers.iter().take(20) {
                info!("   Layer {:3}: {:6} vertices ({:.1}%)",
                      layer, count,
                      (**count as f32 / stats.total_vertices as f32) * 100.0);
            }

            if sorted_layers.len() > 20 {
                info!("   ... and {} more layers", sorted_layers.len() - 20);
            }
        }
    }

    /// Validate layer assignments
    ///
    /// Checks that all edges go from lower to higher layers
    ///
    /// Returns: number of invalid edges found
    pub fn validate_layers(&self) -> usize {
        let mut invalid_count = 0;
        let max_errors_to_log = 10;

        for (source, targets) in &self.outgoing_edges {
            let source_layer = self.vertex_layers.get(source).unwrap_or(&0);

            for target in targets {
                let target_layer = self.vertex_layers.get(target).unwrap_or(&0);

                if source_layer >= target_layer {
                    if invalid_count < max_errors_to_log {
                        debug!("⚠️ Invalid edge: {} (layer {}) -> {} (layer {})",
                              source, source_layer, target, target_layer);
                    }
                    invalid_count += 1;
                }
            }
        }

        if invalid_count > 0 {
            if invalid_count > max_errors_to_log {
                debug!("... and {} more invalid edges", invalid_count - max_errors_to_log);
            }
            info!("⚠️ Found {} invalid edges (may indicate cycles)", invalid_count);
        } else {
            info!("✅ All edges respect layer ordering");
        }

        invalid_count
    }
}

impl Default for GlobalLayerState {
    fn default() -> Self {
        Self::new()
    }
}

/// Statistics about layer assignments
#[derive(Debug, Clone)]
pub struct LayerStatistics {
    pub total_vertices: usize,
    pub total_edges: usize,
    pub max_layer: i32,
    pub unique_layers: usize,
    pub layer_distribution: HashMap<i32, usize>,
    pub update_iterations: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_chain() {
        // Test: A -> B -> C should give layers 0, 1, 2
        let mut state = GlobalLayerState::new();

        let edges = vec![
            ("A".to_string(), "B".to_string()),
            ("B".to_string(), "C".to_string()),
        ];

        state.add_edges_batch(&edges).unwrap();
        state.propagate_until_convergence().unwrap();

        let layers = state.get_layer_map();
        assert_eq!(layers.get("A"), Some(&0));
        assert_eq!(layers.get("B"), Some(&1));
        assert_eq!(layers.get("C"), Some(&2));
        assert_eq!(state.max_layer, 2);
    }

    #[test]
    fn test_diamond_graph() {
        // Test: A -> B, A -> C, B -> D, C -> D
        let mut state = GlobalLayerState::new();

        let edges = vec![
            ("A".to_string(), "B".to_string()),
            ("A".to_string(), "C".to_string()),
            ("B".to_string(), "D".to_string()),
            ("C".to_string(), "D".to_string()),
        ];

        state.add_edges_batch(&edges).unwrap();
        state.propagate_until_convergence().unwrap();

        let layers = state.get_layer_map();
        assert_eq!(layers.get("A"), Some(&0));
        assert_eq!(layers.get("B"), Some(&1));
        assert_eq!(layers.get("C"), Some(&1));
        assert_eq!(layers.get("D"), Some(&2)); // max(1, 1) + 1
        assert_eq!(state.max_layer, 2);
    }

    #[test]
    fn test_batch_processing() {
        // Test that processing in batches gives same result as all-at-once
        let mut state = GlobalLayerState::new();

        // Add first batch
        let batch1 = vec![
            ("A".to_string(), "B".to_string()),
            ("B".to_string(), "C".to_string()),
        ];
        state.add_edges_batch(&batch1).unwrap();
        state.propagate_until_convergence().unwrap();

        // Add second batch that extends the chain
        let batch2 = vec![
            ("C".to_string(), "D".to_string()),
            ("D".to_string(), "E".to_string()),
        ];
        state.add_edges_batch(&batch2).unwrap();
        state.propagate_until_convergence().unwrap();

        let layers = state.get_layer_map();
        assert_eq!(layers.get("A"), Some(&0));
        assert_eq!(layers.get("B"), Some(&1));
        assert_eq!(layers.get("C"), Some(&2));
        assert_eq!(layers.get("D"), Some(&3));
        assert_eq!(layers.get("E"), Some(&4));
        assert_eq!(state.max_layer, 4);
    }

    #[test]
    fn test_validation() {
        let mut state = GlobalLayerState::new();

        let edges = vec![
            ("A".to_string(), "B".to_string()),
            ("B".to_string(), "C".to_string()),
        ];

        state.add_edges_batch(&edges).unwrap();
        state.propagate_until_convergence().unwrap();

        let invalid_count = state.validate_layers();
        assert_eq!(invalid_count, 0); // Should be valid
    }
}
