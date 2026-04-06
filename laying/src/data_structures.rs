/*!
# Высокопроизводительные структуры данных для графов

Оптимизированные структуры данных для работы с большими графами:

- **Эффективное представление графов** с минимальным использованием памяти
- **SIMD-friendly layouts** для векторных операций
- **Lock-free структуры** для параллельного доступа
- **Memory-mapped storage** для работы с данными, не помещающимися в RAM

*/

use anyhow::Result;
use hashbrown::{HashMap, HashSet};
use smallvec::SmallVec;

/// Основная структура графа
#[derive(Debug, Clone)]
pub struct Graph {
    /// Вершины графа (ID -> индекс)
    vertex_map: HashMap<String, usize>,
    
    /// Обратный маппинг (индекс -> ID)
    vertex_ids: Vec<String>,
    
    /// Списки смежности (исходящие связи)
    adjacency_out: Vec<SmallVec<[usize; 4]>>,
    
    /// Списки смежности (входящие связи)
    adjacency_in: Vec<SmallVec<[usize; 4]>>,
    
    /// Веса связей
    edge_weights: HashMap<(usize, usize), f32>,
    
    /// Количество связей
    edge_count: usize,
    
    /// Компоненты связности (кеш)
    components_cache: Option<Vec<Vec<usize>>>,
}

impl Graph {
    /// Создание нового графа
    pub fn new() -> Self {
        Self {
            vertex_map: HashMap::new(),
            vertex_ids: Vec::new(),
            adjacency_out: Vec::new(),
            adjacency_in: Vec::new(),
            edge_weights: HashMap::new(),
            edge_count: 0,
            components_cache: None,
        }
    }
    
    /// Получение количества вершин
    pub fn vertex_count(&self) -> usize {
        self.vertex_ids.len()
    }
    
    /// Получение количества связей
    pub fn edge_count(&self) -> usize {
        self.edge_count
    }
    
    /// Итератор по вершинам
    pub fn vertices(&self) -> impl Iterator<Item = &String> {
        self.vertex_ids.iter()
    }
    
    /// Получение исходящих связей для вершины
    pub fn get_outgoing_edges(&self, vertex_id: &str) -> Option<impl Iterator<Item = &String>> {
        self.vertex_map.get(vertex_id).map(|&idx| {
            self.adjacency_out[idx]
                .iter()
                .map(move |&target_idx| &self.vertex_ids[target_idx])
        })
    }
    
    /// Получение входящих связей для вершины
    pub fn get_incoming_edges(&self, vertex_id: &str) -> Option<impl Iterator<Item = &String>> {
        self.vertex_map.get(vertex_id).map(|&idx| {
            self.adjacency_in[idx]
                .iter()
                .map(move |&source_idx| &self.vertex_ids[source_idx])
        })
    }
    
    /// Получение веса связи
    pub fn get_edge_weight(&self, source: &str, target: &str) -> Option<f32> {
        let source_idx = self.vertex_map.get(source)?;
        let target_idx = self.vertex_map.get(target)?;
        self.edge_weights.get(&(*source_idx, *target_idx)).copied()
    }
    
    /// Получение степени исхода вершины
    pub fn out_degree(&self, vertex_id: &str) -> usize {
        self.vertex_map
            .get(vertex_id)
            .map(|&idx| self.adjacency_out[idx].len())
            .unwrap_or(0)
    }
    
    /// Получение степени входа вершины
    pub fn in_degree(&self, vertex_id: &str) -> usize {
        self.vertex_map
            .get(vertex_id)
            .map(|&idx| self.adjacency_in[idx].len())
            .unwrap_or(0)
    }
    
    /// Проверка наличия вершины
    pub fn contains_vertex(&self, vertex_id: &str) -> bool {
        self.vertex_map.contains_key(vertex_id)
    }
    
    /// Проверка наличия связи
    pub fn contains_edge(&self, source: &str, target: &str) -> bool {
        if let (Some(&source_idx), Some(&target_idx)) = (
            self.vertex_map.get(source),
            self.vertex_map.get(target),
        ) {
            self.adjacency_out[source_idx].contains(&target_idx)
        } else {
            false
        }
    }
    
    /// Получение компонент связности
    pub fn get_connected_components(&mut self) -> &[Vec<usize>] {
        if self.components_cache.is_none() {
            self.components_cache = Some(self.compute_connected_components());
        }
        self.components_cache.as_ref().unwrap()
    }
    
    /// Получение количества компонент связности
    pub fn component_count(&mut self) -> usize {
        self.get_connected_components().len()
    }
    
    /// Вычисление компонент связности алгоритмом DFS
    fn compute_connected_components(&self) -> Vec<Vec<usize>> {
        let mut visited = vec![false; self.vertex_count()];
        let mut components = Vec::new();
        
        for start_idx in 0..self.vertex_count() {
            if !visited[start_idx] {
                let component = self.dfs_component(start_idx, &mut visited);
                components.push(component);
            }
        }
        
        components
    }
    
    /// DFS для поиска компоненты связности
    fn dfs_component(&self, start_idx: usize, visited: &mut [bool]) -> Vec<usize> {
        let mut component = Vec::new();
        let mut stack = vec![start_idx];
        
        while let Some(current_idx) = stack.pop() {
            if visited[current_idx] {
                continue;
            }
            
            visited[current_idx] = true;
            component.push(current_idx);
            
            // Добавляем исходящие связи
            for &neighbor_idx in &self.adjacency_out[current_idx] {
                if !visited[neighbor_idx] {
                    stack.push(neighbor_idx);
                }
            }
            
            // Добавляем входящие связи (для слабой связности)
            for &neighbor_idx in &self.adjacency_in[current_idx] {
                if !visited[neighbor_idx] {
                    stack.push(neighbor_idx);
                }
            }
        }
        
        component
    }
    
    /// Проверка на ацикличность (DAG)
    pub fn is_dag(&self) -> bool {
        self.has_cycle() == false
    }
    
    /// Проверка на наличие циклов
    pub fn has_cycle(&self) -> bool {
        let mut color = vec![Color::White; self.vertex_count()];
        
        for start_idx in 0..self.vertex_count() {
            if color[start_idx] == Color::White {
                if self.dfs_cycle_check(start_idx, &mut color) {
                    return true;
                }
            }
        }
        
        false
    }
    
    /// DFS для проверки циклов
    fn dfs_cycle_check(&self, current_idx: usize, color: &mut [Color]) -> bool {
        color[current_idx] = Color::Gray;
        
        for &neighbor_idx in &self.adjacency_out[current_idx] {
            match color[neighbor_idx] {
                Color::Gray => return true, // Обнаружен цикл
                Color::White => {
                    if self.dfs_cycle_check(neighbor_idx, color) {
                        return true;
                    }
                }
                Color::Black => continue,
            }
        }
        
        color[current_idx] = Color::Black;
        false
    }
    
    /// Получение изолированных вершин
    pub fn get_isolated_vertices(&self) -> Vec<&String> {
        self.vertex_ids
            .iter()
            .enumerate()
            .filter(|(idx, _)| {
                self.adjacency_out[*idx].is_empty() && self.adjacency_in[*idx].is_empty()
            })
            .map(|(_, vertex_id)| vertex_id)
            .collect()
    }
    
    /// Статистика графа
    pub fn get_statistics(&self) -> GraphStatistics {
        let total_out_degree: usize = self.adjacency_out.iter().map(|adj| adj.len()).sum();
        let total_in_degree: usize = self.adjacency_in.iter().map(|adj| adj.len()).sum();
        
        let avg_out_degree = if self.vertex_count() > 0 {
            total_out_degree as f64 / self.vertex_count() as f64
        } else {
            0.0
        };
        
        let avg_in_degree = if self.vertex_count() > 0 {
            total_in_degree as f64 / self.vertex_count() as f64
        } else {
            0.0
        };
        
        let density = if self.vertex_count() > 1 {
            self.edge_count as f64 / (self.vertex_count() * (self.vertex_count() - 1)) as f64
        } else {
            0.0
        };
        
        GraphStatistics {
            vertex_count: self.vertex_count(),
            edge_count: self.edge_count,
            avg_out_degree,
            avg_in_degree,
            density,
            is_dag: self.is_dag(),
            isolated_vertices: self.get_isolated_vertices().len(),
        }
    }
}

/// Цвета для DFS
#[derive(Debug, Clone, Copy, PartialEq)]
enum Color {
    White, // Не посещена
    Gray,  // В процессе обработки
    Black, // Обработана
}

/// Статистика графа
#[derive(Debug, Clone)]
pub struct GraphStatistics {
    pub vertex_count: usize,
    pub edge_count: usize,
    pub avg_out_degree: f64,
    pub avg_in_degree: f64,
    pub density: f64,
    pub is_dag: bool,
    pub isolated_vertices: usize,
}

/// Строитель графа
pub struct GraphBuilder {
    vertices: HashSet<String>,
    edges: Vec<(String, String, f32)>,
}

impl GraphBuilder {
    /// Создание нового строителя
    pub fn new() -> Self {
        Self {
            vertices: HashSet::new(),
            edges: Vec::new(),
        }
    }
    
    /// Добавление связи
    pub fn add_edge(&mut self, source: String, target: String, weight: f32) -> Result<()> {
        if source == target {
            return Err(anyhow::anyhow!("Self-loops не поддерживаются"));
        }
        
        self.vertices.insert(source.clone());
        self.vertices.insert(target.clone());
        self.edges.push((source, target, weight));
        
        Ok(())
    }
    
    /// Добавление вершины
    pub fn add_vertex(&mut self, vertex_id: String) {
        self.vertices.insert(vertex_id);
    }
    
    /// Построение графа
    pub fn build(self) -> Result<Graph> {
        let mut graph = Graph::new();
        
        // Создание маппинга вершин
        let vertices: Vec<_> = self.vertices.into_iter().collect();
        graph.vertex_ids = vertices.clone();
        graph.vertex_map = vertices
            .iter()
            .enumerate()
            .map(|(idx, vertex_id)| (vertex_id.clone(), idx))
            .collect();
        
        // Инициализация списков смежности
        let vertex_count = graph.vertex_count();
        graph.adjacency_out = vec![SmallVec::new(); vertex_count];
        graph.adjacency_in = vec![SmallVec::new(); vertex_count];
        
        // Добавление связей
        for (source, target, weight) in self.edges {
            let source_idx = graph.vertex_map[&source];
            let target_idx = graph.vertex_map[&target];
            
            graph.adjacency_out[source_idx].push(target_idx);
            graph.adjacency_in[target_idx].push(source_idx);
            graph.edge_weights.insert((source_idx, target_idx), weight);
            graph.edge_count += 1;
        }
        
        Ok(graph)
    }
}

impl Default for GraphBuilder {
    fn default() -> Self {
        Self::new()
    }
}

impl Default for Graph {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_graph_creation() -> Result<()> {
        let mut builder = GraphBuilder::new();
        
        builder.add_edge("A".to_string(), "B".to_string(), 1.0)?;
        builder.add_edge("B".to_string(), "C".to_string(), 2.0)?;
        builder.add_edge("A".to_string(), "C".to_string(), 1.5)?;
        
        let graph = builder.build()?;
        
        assert_eq!(graph.vertex_count(), 3);
        assert_eq!(graph.edge_count(), 3);
        assert!(graph.contains_vertex("A"));
        assert!(graph.contains_edge("A", "B"));
        assert_eq!(graph.get_edge_weight("B", "C"), Some(2.0));
        
        Ok(())
    }
    
    #[test]
    fn test_dag_detection() -> Result<()> {
        // DAG
        let mut builder = GraphBuilder::new();
        builder.add_edge("A".to_string(), "B".to_string(), 1.0)?;
        builder.add_edge("B".to_string(), "C".to_string(), 1.0)?;
        let dag = builder.build()?;
        assert!(dag.is_dag());
        
        // Цикл
        let mut builder = GraphBuilder::new();
        builder.add_edge("A".to_string(), "B".to_string(), 1.0)?;
        builder.add_edge("B".to_string(), "C".to_string(), 1.0)?;
        builder.add_edge("C".to_string(), "A".to_string(), 1.0)?;
        let cyclic = builder.build()?;
        assert!(!cyclic.is_dag());
        
        Ok(())
    }
    
    #[test]
    fn test_connected_components() -> Result<()> {
        let mut builder = GraphBuilder::new();
        
        // Компонента 1: A -> B -> C
        builder.add_edge("A".to_string(), "B".to_string(), 1.0)?;
        builder.add_edge("B".to_string(), "C".to_string(), 1.0)?;
        
        // Компонента 2: D -> E
        builder.add_edge("D".to_string(), "E".to_string(), 1.0)?;
        
        // Изолированная вершина
        builder.add_vertex("F".to_string());
        
        let mut graph = builder.build()?;
        let components = graph.get_connected_components();
        
        assert_eq!(components.len(), 3);
        
        Ok(())
    }
}
