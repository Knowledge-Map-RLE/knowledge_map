/// Layout optimization algorithms
///
/// This module provides algorithms for optimizing the layout after initial placement:
/// - Layout compaction
/// - General optimization passes

use anyhow::Result;
use std::collections::HashMap;
use crate::data_structures::Graph;
use super::placement::VertexPosition;

/// Options for layout optimization
#[derive(Debug, Clone)]
pub struct OptimizationOptions {
    /// Whether to compact the layout
    pub compact_layout: bool,

    /// Maximum number of optimization iterations
    pub max_iterations: usize,
}

impl Default for OptimizationOptions {
    fn default() -> Self {
        Self {
            compact_layout: true,
            max_iterations: 10,
        }
    }
}

/// Run optimization passes on the layout
pub async fn optimize_placement(
    positions: &mut Vec<VertexPosition>,
    _graph: &Graph,
    options: &OptimizationOptions,
) -> Result<()> {
    tracing::info!("Starting layout optimization...");

    for iteration in 0..options.max_iterations {
        let mut improved = false;

        if options.compact_layout {
            improved |= compact_layout(positions).await?;
        }

        if !improved {
            tracing::info!("Optimization converged after {} iterations", iteration + 1);
            break;
        }
    }

    tracing::info!("Layout optimization complete");
    Ok(())
}

/// Compact the layout by removing unnecessary gaps
async fn compact_layout(positions: &mut Vec<VertexPosition>) -> Result<bool> {
    tracing::debug!("Compacting layout...");

    // Group by layer and sort by level
    let mut layers: HashMap<i32, Vec<usize>> = HashMap::new();
    for (idx, pos) in positions.iter().enumerate() {
        layers.entry(pos.layer).or_insert_with(Vec::new).push(idx);
    }

    let mut improved = false;

    // Compact each layer vertically
    for indices in layers.values_mut() {
        // Sort by Y position
        indices.sort_by(|&a, &b| {
            positions[a]
                .y
                .partial_cmp(&positions[b].y)
                .unwrap()
        });

        // Check if there are gaps
        let mut has_gaps = false;
        for i in 1..indices.len() {
            let gap = positions[indices[i]].y - positions[indices[i - 1]].y;
            if gap > 130.0 {
                // Standard vertical gap is 80 + 50 = 130
                has_gaps = true;
                break;
            }
        }

        if has_gaps {
            // Reposition vertices to remove gaps
            let mut current_y = 0.0;
            for &idx in indices.iter() {
                positions[idx].y = current_y;
                current_y += 130.0; // block_height (80) + vertical_gap (50)
            }
            improved = true;
            tracing::trace!("Compacted layer by removing gaps");
        }
    }

    Ok(improved)
}

/// Calculate the number of edge crossings in the layout
pub fn count_edge_crossings(positions: &[VertexPosition], graph: &Graph) -> usize {
    let mut crossings = 0;

    // Build position map
    let pos_map: HashMap<&str, &VertexPosition> = positions
        .iter()
        .map(|p| (p.vertex_id.as_str(), p))
        .collect();

    // Check all pairs of edges
    let edges: Vec<_> = positions
        .iter()
        .flat_map(|pos| {
            graph
                .get_outgoing_edges(&pos.vertex_id)
                .into_iter()
                .flatten()
                .filter_map(|target| {
                    pos_map
                        .get(target.as_str())
                        .map(|target_pos| (pos, *target_pos))
                })
                .collect::<Vec<_>>()
        })
        .collect();

    for i in 0..edges.len() {
        for j in (i + 1)..edges.len() {
            if edges_cross(&edges[i], &edges[j]) {
                crossings += 1;
            }
        }
    }

    crossings
}

/// Check if two edges cross each other
fn edges_cross(
    edge1: &(&VertexPosition, &VertexPosition),
    edge2: &(&VertexPosition, &VertexPosition),
) -> bool {
    let (a1, a2) = edge1;
    let (b1, b2) = edge2;

    // Edges can only cross if they span overlapping layer ranges
    let a_min_layer = a1.layer.min(a2.layer);
    let a_max_layer = a1.layer.max(a2.layer);
    let b_min_layer = b1.layer.min(b2.layer);
    let b_max_layer = b1.layer.max(b2.layer);

    if a_max_layer < b_min_layer || b_max_layer < a_min_layer {
        return false; // No overlap in layers
    }

    // Simple crossing check: if edges are on same layers and Y positions cross
    if a1.layer == b1.layer && a2.layer == b2.layer {
        let a_y_increasing = a2.y > a1.y;
        let b_y_increasing = b2.y > b1.y;

        if a_y_increasing != b_y_increasing {
            // One edge goes up, the other goes down - potential crossing
            return (a1.y < b1.y && a2.y > b2.y) || (a1.y > b1.y && a2.y < b2.y);
        }
    }

    false
}
