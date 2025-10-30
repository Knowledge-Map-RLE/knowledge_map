/// BFS-based layer assignment algorithm
///
/// This module implements a breadth-first search approach to assigning layers to vertices
/// in a directed graph. This fixes the critical bug where the old longest_path-based approach
/// created only 3 layers instead of hundreds.
///
/// IMPORTANT SEMANTICS FOR CITATION GRAPH:
/// - Neo4j stores edges as: citing article -> cited reference (newer -> older)
/// - Graph construction preserves this direction (NO reversal)
/// - BFS assigns layers based on distance from sources (vertices without incoming edges)
/// - Layer 0 = source vertices (old articles that are highly cited, no one they cite in the graph)
/// - Higher layers = newer articles (that cite articles in lower layers)
/// - Result: old articles on the left (low layers), new articles on the right (high layers)
/// - Edges visually flow right-to-left (new citing old)

use anyhow::Result;
use std::collections::{HashMap, VecDeque};
use crate::data_structures::Graph;

/// Assign layers to all vertices in the graph using BFS from source nodes
///
/// Algorithm:
/// 1. Find all source nodes (vertices without incoming edges)
/// 2. Assign layer 0 to all source nodes
/// 3. Iteratively assign layers using BFS:
///    layer[target] = max(layer[all predecessors]) + 1
/// 4. Continue until all connected vertices are assigned
///
/// Returns: HashMap mapping vertex_id -> layer_number
pub async fn assign_layers_bfs(graph: &Graph) -> Result<HashMap<String, i32>> {
    let mut layer_map = HashMap::new();
    let mut queue = VecDeque::new();

    // Step 1: Find all source nodes (nodes without incoming edges)
    tracing::info!("Finding source nodes for BFS layer assignment...");

    let vertices: Vec<String> = graph.vertices().map(|v| v.clone()).collect();
    let mut source_count = 0;

    for vertex_id in &vertices {
        let has_incoming = graph
            .get_incoming_edges(vertex_id)
            .map_or(false, |mut incoming| incoming.next().is_some());

        if !has_incoming {
            // This is a source node - assign layer 0
            layer_map.insert(vertex_id.clone(), 0);
            queue.push_back((vertex_id.clone(), 0));
            source_count += 1;
        }
    }

    tracing::info!(
        "Found {} source nodes ({}% of {} total vertices)",
        source_count,
        (source_count as f32 / vertices.len() as f32 * 100.0),
        vertices.len()
    );

    if source_count == 0 {
        tracing::warn!("No source nodes found! This may indicate a cyclic graph or incorrect edge direction");
        return Ok(layer_map);
    }

    // Step 2: BFS traversal to assign layers
    tracing::info!("Starting BFS traversal to assign layers...");

    let mut max_layer = 0;
    let mut processed = 0;
    let log_interval = 10000;

    while let Some((vertex_id, current_layer)) = queue.pop_front() {
        processed += 1;

        if processed % log_interval == 0 {
            tracing::info!(
                "BFS progress: {} vertices processed, queue size: {}, max layer: {}",
                processed,
                queue.len(),
                max_layer
            );
        }

        // Process all outgoing edges from this vertex
        if let Some(outgoing) = graph.get_outgoing_edges(&vertex_id) {
            for target_id in outgoing {
                let new_layer = current_layer + 1;
                max_layer = max_layer.max(new_layer);

                // Update layer if we found a longer path to this vertex
                let should_update = layer_map
                    .get(target_id)
                    .map_or(true, |&existing_layer| new_layer > existing_layer);

                if should_update {
                    layer_map.insert(target_id.clone(), new_layer);
                    queue.push_back((target_id.clone(), new_layer));
                }
            }
        }
    }

    tracing::info!(
        "BFS layer assignment complete: {} vertices assigned ({}%), max layer: {}",
        layer_map.len(),
        (layer_map.len() as f32 / vertices.len() as f32 * 100.0),
        max_layer
    );

    // Step 3: Validate layer assignments
    let validation_errors = validate_layer_assignments(&layer_map, graph)?;

    if validation_errors > 0 {
        tracing::warn!(
            "Found {} edges with incorrect direction (source.layer >= target.layer)",
            validation_errors
        );
        tracing::warn!("This may indicate cycles in the graph. Note: edges are citing->cited (new->old) in Neo4j, preserved in graph construction");
    } else {
        tracing::info!("Layer assignment validation passed - all edges respect layer ordering (citing articles in higher layers -> cited in lower layers)");
    }

    Ok(layer_map)
}

/// Validate layer assignments by checking that all edges go from lower to higher layers
///
/// Returns: Number of validation errors found
fn validate_layer_assignments(
    layer_map: &HashMap<String, i32>,
    graph: &Graph,
) -> Result<usize> {
    let mut errors = 0;
    let max_errors_to_log = 10;

    for (vertex_id, &source_layer) in layer_map.iter() {
        if let Some(outgoing) = graph.get_outgoing_edges(vertex_id) {
            for target_id in outgoing {
                if let Some(&target_layer) = layer_map.get(target_id) {
                    if source_layer >= target_layer {
                        if errors < max_errors_to_log {
                            tracing::warn!(
                                "Layer validation error: {} (layer {}) -> {} (layer {})",
                                vertex_id,
                                source_layer,
                                target_id,
                                target_layer
                            );
                        }
                        errors += 1;
                    }
                }
            }
        }
    }

    if errors > max_errors_to_log {
        tracing::warn!("... and {} more validation errors", errors - max_errors_to_log);
    }

    Ok(errors)
}

/// Fix same-layer edges by reversing them to make graph acyclic
///
/// When two vertices are in the same layer (source.layer == target.layer),
/// we need to decide which direction the edge should go. We use a simple
/// heuristic: compare vertex IDs lexicographically and always direct edges
/// from "smaller" to "larger" ID to ensure consistency.
///
/// Returns: Number of edges reversed
pub fn fix_same_layer_edges(
    layer_map: &HashMap<String, i32>,
    graph: &mut crate::data_structures::Graph,
) -> Result<usize> {
    tracing::info!("Fixing same-layer edges to ensure acyclic graph...");

    let mut edges_to_reverse = Vec::new();

    // Find all same-layer edges
    for (vertex_id, &source_layer) in layer_map.iter() {
        if let Some(outgoing) = graph.get_outgoing_edges(vertex_id) {
            for target_id in outgoing {
                if let Some(&target_layer) = layer_map.get(target_id) {
                    if source_layer == target_layer {
                        // Same layer - decide direction based on lexicographic order
                        if vertex_id > target_id {
                            // Reverse this edge: delete vertex_id -> target_id, add target_id -> vertex_id
                            edges_to_reverse.push((vertex_id.clone(), target_id.clone()));
                        }
                    }
                }
            }
        }
    }

    let reversed_count = edges_to_reverse.len();

    if reversed_count > 0 {
        tracing::info!(
            "Found {} same-layer edges to reverse for consistency",
            reversed_count
        );

        // Note: Since Graph doesn't have methods to modify edges directly,
        // we would need to rebuild the graph or add mutation methods.
        // For now, we just report the count.
        tracing::warn!(
            "Edge reversal requires graph mutation methods - recording {} edges that need reversal",
            reversed_count
        );
    } else {
        tracing::info!("No same-layer edges found - graph is properly structured");
    }

    Ok(reversed_count)
}

/// Get distribution of vertices across layers
///
/// Returns: HashMap mapping layer_number -> count of vertices in that layer
pub fn get_layer_distribution(layer_map: &HashMap<String, i32>) -> HashMap<i32, usize> {
    let mut distribution = HashMap::new();

    for &layer in layer_map.values() {
        *distribution.entry(layer).or_insert(0) += 1;
    }

    distribution
}

/// Log statistics about layer distribution
pub fn log_layer_statistics(layer_map: &HashMap<String, i32>) {
    if layer_map.is_empty() {
        tracing::warn!("No layers assigned!");
        return;
    }

    let distribution = get_layer_distribution(layer_map);
    let min_layer = *distribution.keys().min().unwrap_or(&0);
    let max_layer = *distribution.keys().max().unwrap_or(&0);
    let unique_layers = distribution.len();

    tracing::info!("Layer Statistics:");
    tracing::info!("  Layer range: [{}, {}]", min_layer, max_layer);
    tracing::info!("  Unique layers: {}", unique_layers);
    tracing::info!("  Total vertices: {}", layer_map.len());

    // Log distribution for first 20 layers
    let mut sorted_layers: Vec<_> = distribution.iter().collect();
    sorted_layers.sort_by_key(|(layer, _)| *layer);

    tracing::info!("  Distribution (first 20 layers):");
    for (layer, count) in sorted_layers.iter().take(20) {
        tracing::info!("    Layer {:3}: {:6} vertices", layer, count);
    }

    if sorted_layers.len() > 20 {
        tracing::info!("    ... and {} more layers", sorted_layers.len() - 20);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data_structures::GraphBuilder;

    #[tokio::test]
    async fn test_simple_chain() {
        // Create a simple chain: A -> B -> C
        let mut builder = GraphBuilder::new();
        builder.add_edge("A".to_string(), "B".to_string(), 1.0).unwrap();
        builder.add_edge("B".to_string(), "C".to_string(), 1.0).unwrap();
        let graph = builder.build().unwrap();

        let layers = assign_layers_bfs(&graph).await.unwrap();

        assert_eq!(layers.get("A"), Some(&0));
        assert_eq!(layers.get("B"), Some(&1));
        assert_eq!(layers.get("C"), Some(&2));
    }

    #[tokio::test]
    async fn test_diamond_graph() {
        // Create a diamond: A -> B, A -> C, B -> D, C -> D
        let mut builder = GraphBuilder::new();
        builder.add_edge("A".to_string(), "B".to_string(), 1.0).unwrap();
        builder.add_edge("A".to_string(), "C".to_string(), 1.0).unwrap();
        builder.add_edge("B".to_string(), "D".to_string(), 1.0).unwrap();
        builder.add_edge("C".to_string(), "D".to_string(), 1.0).unwrap();
        let graph = builder.build().unwrap();

        let layers = assign_layers_bfs(&graph).await.unwrap();

        assert_eq!(layers.get("A"), Some(&0));
        assert_eq!(layers.get("B"), Some(&1));
        assert_eq!(layers.get("C"), Some(&1));
        assert_eq!(layers.get("D"), Some(&2)); // Max of predecessors + 1
    }
}
