/// Layer assignment algorithm using topological relaxation (Bellman-Ford style)
///
/// Works correctly on graphs with cycles: cycles are broken by limiting relaxation
/// to V-1 iterations (standard Bellman-Ford bound). Vertices in cycles get
/// the layer assigned during the last valid relaxation pass.

use anyhow::Result;
use std::collections::HashMap;
use crate::data_structures::Graph;

/// Assign layers to all vertices using longest-path relaxation.
///
/// Algorithm:
/// 1. Find source nodes (no incoming edges) → layer 0
/// 2. Relax all edges up to (V-1) times: layer[target] = max(layer[target], layer[source]+1)
/// 3. Vertices unreachable from sources keep layer 0
///
/// Handles cycles: after V-1 passes, no further changes can propagate in a DAG.
/// In cyclic graphs, the cycle vertices get clamped at whatever layer the last pass set.
pub async fn assign_layers_bfs(graph: &Graph) -> Result<HashMap<String, i32>> {
    let vertices: Vec<String> = graph.vertices().map(|v| v.clone()).collect();
    let n = vertices.len();

    if n == 0 {
        return Ok(HashMap::new());
    }

    // Build vertex index for O(1) lookups
    let vertex_idx: HashMap<&str, usize> = vertices
        .iter()
        .enumerate()
        .map(|(i, v)| (v.as_str(), i))
        .collect();

    // Collect edges as index pairs
    let mut adj: Vec<Vec<usize>> = vec![Vec::new(); n];
    for (i, v) in vertices.iter().enumerate() {
        if let Some(outgoing) = graph.get_outgoing_edges(v) {
            for target in outgoing {
                if let Some(&j) = vertex_idx.get(target.as_str()) {
                    adj[i].push(j);
                }
            }
        }
    }

    // Compute in-degree to find sources
    let mut in_degree = vec![0usize; n];
    for neighbors in &adj {
        for &j in neighbors {
            in_degree[j] += 1;
        }
    }

    let source_count = in_degree.iter().filter(|&&d| d == 0).count();
    tracing::info!(
        "Layer assignment: {} vertices, {} sources",
        n, source_count
    );

    // Initialize layers: sources get 0, others get 0 as well (will be relaxed)
    let mut layers = vec![0i32; n];

    // Relaxation passes — Bellman-Ford bound is V-1 passes
    // For typical DAGs convergence happens in diameter passes (much less than V)
    // We stop early if no changes occurred
    let max_passes = (n - 1).min(500); // cap at 500 for huge graphs

    for pass in 0..max_passes {
        let mut changed = false;

        for i in 0..n {
            let src_layer = layers[i];
            for &j in &adj[i] {
                let new_layer = src_layer + 1;
                if new_layer > layers[j] {
                    layers[j] = new_layer;
                    changed = true;
                }
            }
        }

        if !changed {
            let max_layer = layers.iter().copied().max().unwrap_or(0);
            tracing::info!(
                "Layer assignment converged after {} passes: max layer = {}",
                pass + 1, max_layer
            );
            break;
        }

        // Progress every 50 passes
        if (pass + 1) % 50 == 0 {
            let max_layer = layers.iter().copied().max().unwrap_or(0);
            tracing::info!(
                "Layer assignment: pass {}/{} ({:.0}%), max layer so far = {}",
                pass + 1, max_passes,
                (pass + 1) as f32 / max_passes as f32 * 100.0,
                max_layer
            );
        }
    }

    let max_layer = layers.iter().copied().max().unwrap_or(0);
    let assigned = layers.iter().filter(|&&l| l > 0).count() + source_count;
    tracing::info!(
        "Layer assignment done: {} vertices assigned, max layer = {}",
        assigned, max_layer
    );

    let layer_map: HashMap<String, i32> = vertices
        .into_iter()
        .enumerate()
        .map(|(i, v)| (v, layers[i]))
        .collect();

    Ok(layer_map)
}

/// Get distribution of vertices across layers
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

    tracing::info!(
        "Layers: range [{}, {}], unique={}, total vertices={}",
        min_layer, max_layer, distribution.len(), layer_map.len()
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data_structures::GraphBuilder;

    #[tokio::test]
    async fn test_simple_chain() {
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
        assert_eq!(layers.get("D"), Some(&2));
    }
}
