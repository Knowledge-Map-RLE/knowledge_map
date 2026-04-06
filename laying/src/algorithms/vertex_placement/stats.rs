/// Statistics tracking for vertex placement algorithm
use serde::{Deserialize, Serialize};

/// Statistics collected during the vertex placement process
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlacementStats {
    /// Number of vertices successfully placed
    pub vertices_placed: usize,

    /// Number of unique layers used in the layout
    pub layers_used: usize,

    /// Average number of vertices per layer
    pub avg_vertices_per_layer: f32,

    /// Maximum number of vertices in any single layer
    pub max_vertices_in_layer: usize,

    /// Total width of the layout in pixels
    pub total_width: f32,

    /// Total height of the layout in pixels
    pub total_height: f32,
}

impl PlacementStats {
    /// Create a new empty statistics object
    pub fn new() -> Self {
        Self {
            vertices_placed: 0,
            layers_used: 0,
            avg_vertices_per_layer: 0.0,
            max_vertices_in_layer: 0,
            total_width: 0.0,
            total_height: 0.0,
        }
    }

    /// Reset all statistics to zero
    pub fn reset(&mut self) {
        self.vertices_placed = 0;
        self.layers_used = 0;
        self.avg_vertices_per_layer = 0.0;
        self.max_vertices_in_layer = 0;
        self.total_width = 0.0;
        self.total_height = 0.0;
    }
}

impl Default for PlacementStats {
    fn default() -> Self {
        Self::new()
    }
}
