/*!
# Типы данных для укладки графов

Структуры для передачи данных между алгоритмами и gRPC-слоем.
*/

/// Связь графа
#[derive(Debug, Clone)]
pub struct GraphEdge {
    pub source_id: String,
    pub target_id: String,
    pub weight: f32,
    pub edge_type: String,
}

/// Позиция вершины после укладки
#[derive(Debug, Clone)]
pub struct VertexPosition {
    pub article_id: String,
    pub layer: i32,
    pub level: i32,
    pub x: f32,
    pub y: f32,
}
