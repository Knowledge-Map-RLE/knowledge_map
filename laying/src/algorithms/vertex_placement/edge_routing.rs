/// Edge routing and polyline computation
///
/// This module handles the computation of edge paths (polylines) for edges
/// that span multiple layers. For edges within the same layer or adjacent layers,
/// simple straight lines can be used. For edges spanning multiple layers,
/// we compute intermediate waypoints.

use anyhow::Result;
use std::collections::HashMap;
use crate::data_structures::Graph;
use super::placement::{VertexPosition, PlacementConfig};

/// Layout options for edge routing
#[derive(Debug, Clone)]
pub struct EdgeRoutingOptions {
    /// Whether to use polylines for long edges
    pub use_polylines: bool,

    /// Minimum number of layers to span before using polylines
    pub polyline_threshold: i32,

    /// Whether to route edges around vertices
    pub avoid_vertices: bool,
}

impl Default for EdgeRoutingOptions {
    fn default() -> Self {
        Self {
            use_polylines: true,
            polyline_threshold: 2,
            avoid_vertices: false,
        }
    }
}

/// Compute edge paths (polylines) for all edges in the graph
///
/// Returns a HashMap mapping (source_id, target_id) -> Vec of (x, y) waypoints
pub fn compute_edge_paths(
    positions: &[VertexPosition],
    graph: &Graph,
    config: &PlacementConfig,
    options: &EdgeRoutingOptions,
) -> Result<HashMap<(String, String), Vec<(f32, f32)>>> {
    tracing::info!("Computing edge paths...");

    let mut edge_paths = HashMap::new();

    // Build position lookup map
    let pos_map: HashMap<&str, &VertexPosition> = positions
        .iter()
        .map(|p| (p.vertex_id.as_str(), p))
        .collect();

    let mut edges_processed = 0;
    let mut polylines_created = 0;

    // Process each edge
    for pos in positions {
        if let Some(outgoing) = graph.get_outgoing_edges(&pos.vertex_id) {
            for target_id in outgoing {
                if let Some(target_pos) = pos_map.get(target_id.as_str()) {
                    let path = compute_single_edge_path(
                        pos,
                        target_pos,
                        config,
                        options,
                    )?;

                    if path.len() > 2 {
                        polylines_created += 1;
                    }

                    edge_paths.insert(
                        (pos.vertex_id.clone(), target_id.clone()),
                        path,
                    );

                    edges_processed += 1;
                }
            }
        }
    }

    tracing::info!(
        "Edge path computation complete: {} edges processed, {} polylines created",
        edges_processed,
        polylines_created
    );

    Ok(edge_paths)
}

/// Compute the path for a single edge
///
/// For short edges (spanning 1-2 layers), returns a simple straight line.
/// For long edges, computes intermediate waypoints for better visualization.
fn compute_single_edge_path(
    source: &VertexPosition,
    target: &VertexPosition,
    config: &PlacementConfig,
    options: &EdgeRoutingOptions,
) -> Result<Vec<(f32, f32)>> {
    let layer_span = (target.layer - source.layer).abs();

    // For short edges or if polylines are disabled, use straight line
    if !options.use_polylines || layer_span < options.polyline_threshold {
        return Ok(vec![
            (source.x + config.block_width, source.y + config.block_height / 2.0),
            (target.x, target.y + config.block_height / 2.0),
        ]);
    }

    // For long edges, compute polyline with intermediate waypoints
    compute_polyline(source, target, config)
}

/// Compute a polyline with intermediate waypoints
fn compute_polyline(
    source: &VertexPosition,
    target: &VertexPosition,
    config: &PlacementConfig,
) -> Result<Vec<(f32, f32)>> {
    let mut waypoints = Vec::new();

    // Start point (right edge of source block, middle)
    let start_x = source.x + config.block_width;
    let start_y = source.y + config.block_height / 2.0;
    waypoints.push((start_x, start_y));

    // Calculate number of intermediate layers
    let layer_span = (target.layer - source.layer).abs();
    let num_intermediates = layer_span - 1;

    // Add intermediate waypoints
    if num_intermediates > 0 {
        let x_step = (target.x - start_x) / (num_intermediates + 1) as f32;
        let y_step = (target.y + config.block_height / 2.0 - start_y) / (num_intermediates + 1) as f32;

        for i in 1..=num_intermediates {
            let waypoint_x = start_x + x_step * i as f32;
            let waypoint_y = start_y + y_step * i as f32;
            waypoints.push((waypoint_x, waypoint_y));
        }
    }

    // End point (left edge of target block, middle)
    let end_x = target.x;
    let end_y = target.y + config.block_height / 2.0;
    waypoints.push((end_x, end_y));

    Ok(waypoints)
}

/// Compute orthogonal edge routing (manhattan-style)
///
/// This creates edges that follow horizontal and vertical lines,
/// which can be more visually appealing than diagonal lines.
#[allow(dead_code)]
fn compute_orthogonal_path(
    source: &VertexPosition,
    target: &VertexPosition,
    config: &PlacementConfig,
) -> Result<Vec<(f32, f32)>> {
    let mut waypoints = Vec::new();

    // Start point
    let start_x = source.x + config.block_width;
    let start_y = source.y + config.block_height / 2.0;
    waypoints.push((start_x, start_y));

    // Calculate intermediate X position (midpoint)
    let mid_x = (start_x + target.x) / 2.0;

    // Add intermediate horizontal-vertical segments
    waypoints.push((mid_x, start_y)); // Horizontal from source
    waypoints.push((mid_x, target.y + config.block_height / 2.0)); // Vertical
    waypoints.push((target.x, target.y + config.block_height / 2.0)); // Horizontal to target

    Ok(waypoints)
}

/// Calculate edge length (useful for optimization)
pub fn calculate_edge_length(path: &[(f32, f32)]) -> f32 {
    let mut total_length = 0.0;

    for i in 1..path.len() {
        let (x1, y1) = path[i - 1];
        let (x2, y2) = path[i];

        let dx = x2 - x1;
        let dy = y2 - y1;

        total_length += (dx * dx + dy * dy).sqrt();
    }

    total_length
}

/// Get statistics about edge paths
pub fn get_edge_statistics(edge_paths: &HashMap<(String, String), Vec<(f32, f32)>>) {
    let total_edges = edge_paths.len();
    let polylines = edge_paths.values().filter(|path| path.len() > 2).count();
    let straight_lines = total_edges - polylines;

    let avg_waypoints = edge_paths.values().map(|p| p.len()).sum::<usize>() as f32 / total_edges as f32;

    tracing::info!("Edge Path Statistics:");
    tracing::info!("  Total edges: {}", total_edges);
    tracing::info!("  Straight lines: {}", straight_lines);
    tracing::info!("  Polylines: {}", polylines);
    tracing::info!("  Average waypoints per edge: {:.2}", avg_waypoints);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_straight_line_path() {
        let config = PlacementConfig::default();
        let options = EdgeRoutingOptions::default();

        let source = VertexPosition {
            vertex_id: "A".to_string(),
            x: 0.0,
            y: 0.0,
            layer: 0,
            level: 0,
        };

        let target = VertexPosition {
            vertex_id: "B".to_string(),
            x: 240.0,
            y: 0.0,
            layer: 1,
            level: 0,
        };

        let path = compute_single_edge_path(&source, &target, &config, &options).unwrap();

        assert_eq!(path.len(), 2); // Start and end points only
        assert_eq!(path[0].0, 160.0); // Source right edge
        assert_eq!(path[1].0, 240.0); // Target left edge
    }

    #[test]
    fn test_polyline_path() {
        let config = PlacementConfig::default();
        let options = EdgeRoutingOptions::default();

        let source = VertexPosition {
            vertex_id: "A".to_string(),
            x: 0.0,
            y: 0.0,
            layer: 0,
            level: 0,
        };

        let target = VertexPosition {
            vertex_id: "B".to_string(),
            x: 720.0, // 3 layers away
            y: 0.0,
            layer: 3,
            level: 0,
        };

        let path = compute_single_edge_path(&source, &target, &config, &options).unwrap();

        assert!(path.len() > 2); // Should have intermediate waypoints
    }

    #[test]
    fn test_edge_length_calculation() {
        let path = vec![(0.0, 0.0), (3.0, 4.0)]; // 3-4-5 triangle
        let length = calculate_edge_length(&path);
        assert_eq!(length, 5.0);
    }
}
