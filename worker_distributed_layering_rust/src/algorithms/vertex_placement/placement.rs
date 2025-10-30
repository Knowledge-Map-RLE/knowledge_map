/// Vertex placement within layers
///
/// This module handles the placement of vertices at specific (x, y) coordinates
/// within their assigned layers.

use std::collections::{HashMap, HashSet};

/// Represents a single vertex's position in the layout
#[derive(Debug, Clone)]
pub struct VertexPosition {
    pub vertex_id: String,
    pub x: f32,
    pub y: f32,
    pub layer: i32,
    pub level: i32,
}

/// Configuration for vertex placement
#[derive(Debug, Clone)]
pub struct PlacementConfig {
    /// Horizontal spacing between blocks (pixels)
    pub block_width: f32,

    /// Vertical spacing between blocks (pixels)
    pub block_height: f32,

    /// Horizontal gap between layers (pixels)
    pub horizontal_gap: f32,

    /// Vertical gap between levels (pixels)
    pub vertical_gap: f32,
}

impl Default for PlacementConfig {
    fn default() -> Self {
        Self {
            block_width: 160.0,
            block_height: 80.0,
            horizontal_gap: 80.0,
            vertical_gap: 50.0,
        }
    }
}

/// Place vertices in a specific layer
///
/// Given a list of vertex IDs that belong to the same layer,
/// calculate their (x, y) positions by distributing them vertically.
pub fn place_vertices_in_layer(
    layer: i32,
    vertex_ids: &[String],
    config: &PlacementConfig,
) -> Vec<VertexPosition> {
    let mut positions = Vec::new();

    // Calculate X coordinate for this layer
    let x = layer as f32 * (config.block_width + config.horizontal_gap);

    // Distribute vertices vertically within the layer
    for (level, vertex_id) in vertex_ids.iter().enumerate() {
        let y = level as f32 * (config.block_height + config.vertical_gap);

        positions.push(VertexPosition {
            vertex_id: vertex_id.clone(),
            x,
            y,
            layer,
            level: level as i32,
        });
    }

    positions
}

/// Place all vertices based on their layer assignments
///
/// Takes a HashMap of layer assignments and produces a Vec of VertexPosition
pub fn place_all_vertices(
    layer_map: &HashMap<String, i32>,
    config: &PlacementConfig,
) -> Vec<VertexPosition> {
    // Group vertices by layer
    let mut layer_assignments: HashMap<i32, Vec<String>> = HashMap::new();

    for (vertex_id, &layer) in layer_map {
        layer_assignments
            .entry(layer)
            .or_insert_with(Vec::new)
            .push(vertex_id.clone());
    }

    // Sort layers for consistent ordering
    let mut sorted_layers: Vec<_> = layer_assignments.into_iter().collect();
    sorted_layers.sort_by_key(|(layer, _)| *layer);

    // Place vertices in each layer
    let mut all_positions = Vec::new();

    for (layer, vertex_ids) in sorted_layers {
        let positions = place_vertices_in_layer(layer, &vertex_ids, config);
        all_positions.extend(positions);
    }

    tracing::info!(
        "Placed {} vertices across {} layers",
        all_positions.len(),
        layer_map.values().max().unwrap_or(&0) + 1
    );

    all_positions
}

/// Track occupied positions to avoid overlaps
pub struct OccupiedPositions {
    occupied: HashSet<(i32, i32)>,
}

impl OccupiedPositions {
    pub fn new() -> Self {
        Self {
            occupied: HashSet::new(),
        }
    }

    /// Check if a position is occupied
    pub fn is_occupied(&self, layer: i32, level: i32) -> bool {
        self.occupied.contains(&(layer, level))
    }

    /// Mark a position as occupied
    pub fn mark_occupied(&mut self, layer: i32, level: i32) {
        self.occupied.insert((layer, level));
    }

    /// Find the next available level in a given layer
    pub fn find_next_available_level(&self, layer: i32, start_level: i32) -> i32 {
        let mut level = start_level;
        while self.is_occupied(layer, level) {
            level += 1;
        }
        level
    }
}

impl Default for OccupiedPositions {
    fn default() -> Self {
        Self::new()
    }
}

/// Calculate layout dimensions
pub fn calculate_layout_dimensions(positions: &[VertexPosition], config: &PlacementConfig) -> (f32, f32) {
    if positions.is_empty() {
        return (0.0, 0.0);
    }

    let max_x = positions
        .iter()
        .map(|p| p.x + config.block_width)
        .max_by(|a, b| a.partial_cmp(b).unwrap())
        .unwrap_or(0.0);

    let max_y = positions
        .iter()
        .map(|p| p.y + config.block_height)
        .max_by(|a, b| a.partial_cmp(b).unwrap())
        .unwrap_or(0.0);

    (max_x, max_y)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_place_vertices_in_layer() {
        let config = PlacementConfig::default();
        let vertices = vec!["A".to_string(), "B".to_string(), "C".to_string()];

        let positions = place_vertices_in_layer(0, &vertices, &config);

        assert_eq!(positions.len(), 3);
        assert_eq!(positions[0].vertex_id, "A");
        assert_eq!(positions[0].layer, 0);
        assert_eq!(positions[0].level, 0);

        assert_eq!(positions[1].vertex_id, "B");
        assert_eq!(positions[1].level, 1);

        assert_eq!(positions[2].vertex_id, "C");
        assert_eq!(positions[2].level, 2);
    }

    #[test]
    fn test_occupied_positions() {
        let mut occupied = OccupiedPositions::new();

        assert!(!occupied.is_occupied(0, 0));

        occupied.mark_occupied(0, 0);
        assert!(occupied.is_occupied(0, 0));

        let next_level = occupied.find_next_available_level(0, 0);
        assert_eq!(next_level, 1);
    }
}
