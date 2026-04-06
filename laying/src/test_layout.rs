/// Test module for graph layout visualization
///
/// This module provides functionality to test the global layer assignment algorithm
/// on a small test graph and visualize the results.

use crate::algorithms::vertex_placement::GlobalLayerState;
use anyhow::Result;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

/// Create a test DAG graph with known structure
///
/// Creates a graph that demonstrates different layering scenarios:
/// - Simple chains
/// - Branching paths
/// - Converging paths
/// - Multiple components
pub fn create_test_graph() -> Vec<(String, String)> {
    vec![
        // Chain 1: A -> B -> C -> D -> E (5 layers)
        ("A".to_string(), "B".to_string()),
        ("B".to_string(), "C".to_string()),
        ("C".to_string(), "D".to_string()),
        ("D".to_string(), "E".to_string()),

        // Chain 2: A -> F -> G -> H (4 layers from A)
        ("A".to_string(), "F".to_string()),
        ("F".to_string(), "G".to_string()),
        ("G".to_string(), "H".to_string()),

        // Converging: B -> I, F -> I, I -> J (I at layer 2, J at layer 3)
        ("B".to_string(), "I".to_string()),
        ("F".to_string(), "I".to_string()),
        ("I".to_string(), "J".to_string()),

        // Diamond: K -> L, K -> M, L -> N, M -> N
        ("K".to_string(), "L".to_string()),
        ("K".to_string(), "M".to_string()),
        ("L".to_string(), "N".to_string()),
        ("M".to_string(), "N".to_string()),

        // Long chain from K: K -> O -> P -> Q -> R -> S -> T
        ("K".to_string(), "O".to_string()),
        ("O".to_string(), "P".to_string()),
        ("P".to_string(), "Q".to_string()),
        ("Q".to_string(), "R".to_string()),
        ("R".to_string(), "S".to_string()),
        ("S".to_string(), "T".to_string()),
    ]
}

/// Parse GML file and extract edges
///
/// Simple parser that extracts node labels and edge connections from GML format
pub fn parse_gml_file<P: AsRef<Path>>(path: P) -> Result<Vec<(String, String)>> {
    let content = fs::read_to_string(path)?;

    // Extract node id -> label mapping
    let mut node_labels: HashMap<i32, String> = HashMap::new();

    let mut current_node_id: Option<i32> = None;

    for line in content.lines() {
        let trimmed = line.trim();

        // Parse node id
        if trimmed.starts_with("id\t") || trimmed.starts_with("id ") {
            if let Some(id_str) = trimmed.split_whitespace().nth(1) {
                current_node_id = id_str.parse().ok();
            }
        }

        // Parse node label
        if trimmed.starts_with("label\t") || trimmed.starts_with("label ") {
            let label = trimmed
                .split_whitespace()
                .nth(1)
                .unwrap_or("?")
                .trim_matches('"')
                .to_string();

            if let Some(id) = current_node_id {
                node_labels.insert(id, label);
                current_node_id = None;
            }
        }
    }

    // Extract edges
    let mut edges = Vec::new();
    let mut current_source: Option<i32> = None;
    let mut current_target: Option<i32> = None;
    let mut in_edge_block = false;

    for line in content.lines() {
        let trimmed = line.trim();

        if trimmed == "edge" {
            in_edge_block = true;
            current_source = None;
            current_target = None;
        }

        if in_edge_block {
            if trimmed.starts_with("source\t") || trimmed.starts_with("source ") {
                if let Some(id_str) = trimmed.split_whitespace().nth(1) {
                    current_source = id_str.parse().ok();
                }
            }

            if trimmed.starts_with("target\t") || trimmed.starts_with("target ") {
                if let Some(id_str) = trimmed.split_whitespace().nth(1) {
                    current_target = id_str.parse().ok();
                }
            }

            if trimmed == "]" && current_source.is_some() && current_target.is_some() {
                let source_id = current_source.unwrap();
                let target_id = current_target.unwrap();

                let source_label = node_labels.get(&source_id).cloned().unwrap_or_else(|| source_id.to_string());
                let target_label = node_labels.get(&target_id).cloned().unwrap_or_else(|| target_id.to_string());

                edges.push((source_label, target_label));

                in_edge_block = false;
                current_source = None;
                current_target = None;
            }
        }
    }

    Ok(edges)
}

/// Run layout test on a GML file
pub fn test_layout_from_gml<P: AsRef<Path>>(path: P) -> Result<()> {
    println!("=== ТЕСТ ГЛОБАЛЬНОЙ УКЛАДКИ ГРАФА ИЗ GML ===\n");

    let path_ref = path.as_ref();
    println!("📁 Загрузка файла: {}", path_ref.display());

    // Parse GML file
    let edges = parse_gml_file(path)?;

    if edges.is_empty() {
        println!("❌ Граф пустой или не удалось распарсить файл");
        return Ok(());
    }

    println!("✅ Граф загружен:");
    println!("   - Рёбер: {}", edges.len());
    println!("   - Вершин (уникальных): {}", count_unique_vertices(&edges));
    println!();

    // Print graph structure
    println!("📝 Структура графа:");
    for (source, target) in &edges {
        println!("   {} → {}", source, target);
    }
    println!();

    // Create global state and process
    let mut global_state = GlobalLayerState::new();

    println!("🔄 Добавление рёбер в глобальное состояние...");
    global_state.add_edges_batch(&edges)?;

    println!("🔄 Вычисление слоёв...");
    let updates = global_state.propagate_until_convergence()?;
    println!("   ✅ Выполнено {} обновлений слоёв\n", updates);

    // Get results
    let layer_map = global_state.get_layer_map();
    let stats = global_state.get_statistics();

    // Print statistics
    println!("=== СТАТИСТИКА ===");
    println!("📊 Всего вершин: {}", stats.total_vertices);
    println!("🔗 Всего рёбер: {}", stats.total_edges);
    println!("📏 Максимальный слой: {}", stats.max_layer);
    println!("🔢 Уникальных слоёв: {}", stats.unique_layers);
    println!();

    // Visualize layer assignment
    visualize_layers(layer_map);

    // Validate
    println!("🔍 Валидация...");
    let invalid_edges = global_state.validate_layers();
    if invalid_edges == 0 {
        println!("   ✅ Все рёбра корректны\n");
    } else {
        println!("   ⚠️ Найдено {} некорректных рёбер\n", invalid_edges);
    }

    // ASCII visualization
    println!("=== ASCII ВИЗУАЛИЗАЦИЯ УКЛАДКИ ===\n");
    visualize_ascii(layer_map, &edges);

    Ok(())
}

/// Run layout test on the test graph
pub fn test_layout() -> Result<()> {
    println!("=== ТЕСТ ГЛОБАЛЬНОЙ УКЛАДКИ ГРАФА ===\n");

    // Create test graph
    let edges = create_test_graph();
    println!("📊 Создан тестовый граф:");
    println!("   - Рёбер: {}", edges.len());
    println!("   - Вершин (уникальных): {}", count_unique_vertices(&edges));
    println!();

    // Print graph structure
    println!("📝 Структура графа:");
    for (source, target) in &edges {
        println!("   {} → {}", source, target);
    }
    println!();

    // Create global state and process
    let mut global_state = GlobalLayerState::new();

    println!("🔄 Добавление рёбер в глобальное состояние...");
    global_state.add_edges_batch(&edges)?;

    println!("🔄 Вычисление слоёв...");
    let updates = global_state.propagate_until_convergence()?;
    println!("   ✅ Выполнено {} обновлений слоёв\n", updates);

    // Get results
    let layer_map = global_state.get_layer_map();
    let stats = global_state.get_statistics();

    // Print statistics
    println!("=== СТАТИСТИКА ===");
    println!("📊 Всего вершин: {}", stats.total_vertices);
    println!("🔗 Всего рёбер: {}", stats.total_edges);
    println!("📏 Максимальный слой: {}", stats.max_layer);
    println!("🔢 Уникальных слоёв: {}", stats.unique_layers);
    println!();

    // Visualize layer assignment
    visualize_layers(layer_map);

    // Validate
    println!("🔍 Валидация...");
    let invalid_edges = global_state.validate_layers();
    if invalid_edges == 0 {
        println!("   ✅ Все рёбра корректны\n");
    } else {
        println!("   ⚠️ Найдено {} некорректных рёбер\n", invalid_edges);
    }

    // ASCII visualization
    println!("=== ASCII ВИЗУАЛИЗАЦИЯ УКЛАДКИ ===\n");
    visualize_ascii(layer_map, &edges);

    Ok(())
}

/// Count unique vertices in edge list
fn count_unique_vertices(edges: &[(String, String)]) -> usize {
    let mut vertices = std::collections::HashSet::new();
    for (source, target) in edges {
        vertices.insert(source);
        vertices.insert(target);
    }
    vertices.len()
}

/// Visualize layer assignments (grouped by layer)
fn visualize_layers(layer_map: &HashMap<String, i32>) {
    println!("=== НАЗНАЧЕНИЕ СЛОЁВ ===");

    // Group by layer
    let mut layers: HashMap<i32, Vec<String>> = HashMap::new();
    for (vertex, &layer) in layer_map {
        layers.entry(layer).or_insert_with(Vec::new).push(vertex.clone());
    }

    // Sort layers
    let mut sorted_layers: Vec<_> = layers.into_iter().collect();
    sorted_layers.sort_by_key(|(layer, _)| *layer);

    // Print each layer
    for (layer, mut vertices) in sorted_layers {
        vertices.sort();
        println!("Слой {:2}: {}", layer, vertices.join(", "));
    }
    println!();
}

/// ASCII visualization of the graph layout
fn visualize_ascii(layer_map: &HashMap<String, i32>, edges: &[(String, String)]) {
    // Group vertices by layer
    let mut layers: HashMap<i32, Vec<String>> = HashMap::new();
    for (vertex, &layer) in layer_map {
        layers.entry(layer).or_insert_with(Vec::new).push(vertex.clone());
    }

    // Find max layer
    let max_layer = *layer_map.values().max().unwrap_or(&0);

    // Print layer by layer
    for layer in 0..=max_layer {
        if let Some(vertices) = layers.get(&layer) {
            let mut sorted_vertices = vertices.clone();
            sorted_vertices.sort();

            // Print layer header
            print!("Layer {:2} │ ", layer);

            // Print vertices
            for vertex in &sorted_vertices {
                print!("[{}] ", vertex);
            }
            println!();

            // Print edges going to next layer
            if layer < max_layer {
                print!("         │ ");
                for vertex in &sorted_vertices {
                    let outgoing: Vec<_> = edges
                        .iter()
                        .filter(|(s, _)| s == vertex)
                        .map(|(_, t)| t)
                        .collect();

                    if !outgoing.is_empty() {
                        print!("↓   ");
                    } else {
                        print!("    ");
                    }
                }
                println!();
            }
        }
    }

    println!();
    println!("📊 Описание графа:");
    println!("   - Вершины в квадратных скобках [A]");
    println!("   - Стрелка ↓ указывает на исходящие рёбра");
    println!("   - Слои идут сверху вниз (0 → max)");
    println!();

    // Print edge list with layers
    println!("📋 Список рёбер с указанием слоёв:");
    let mut sorted_edges = edges.to_vec();
    sorted_edges.sort_by_key(|(s, t)| {
        (layer_map.get(s).unwrap_or(&0), layer_map.get(t).unwrap_or(&0), s.clone(), t.clone())
    });

    for (source, target) in sorted_edges {
        let source_layer = layer_map.get(&source).unwrap_or(&-1);
        let target_layer = layer_map.get(&target).unwrap_or(&-1);
        println!("   {} (L{}) → {} (L{})", source, source_layer, target, target_layer);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_graph_structure() {
        let edges = create_test_graph();
        assert!(edges.len() > 0);
        assert!(count_unique_vertices(&edges) > 0);
    }

    #[test]
    fn test_layout_execution() {
        let result = test_layout();
        assert!(result.is_ok());
    }
}
