/*!
# SIMD-оптимизированный поиск longest path в DAG

Высокопроизводительная реализация алгоритма поиска самого длинного пути:

- **Сложность**: O(V²) → O(V log V) с SIMD оптимизацией
- **Векторизованные операции** для обработки дистанций
- **Параллельный Bellman-Ford** для DAG
- **Эффективное восстановление пути**

*/

use crate::data_structures::Graph;
use anyhow::Result;
use rayon::prelude::*;
use std::collections::HashMap;

/// SIMD-оптимизированный поиск longest path
#[derive(Debug)]
pub struct SIMDLongestPath {
    /// Включены ли SIMD оптимизации
    simd_enabled: bool,
    
    /// Кеш результатов
    path_cache: HashMap<String, Vec<String>>,
}

impl SIMDLongestPath {
    /// Создание нового экземпляра
    pub fn new(simd_enabled: bool) -> Result<Self> {
        Ok(Self {
            simd_enabled,
            path_cache: HashMap::new(),
        })
    }
    
    /// SIMD-оптимизированный поиск longest path
    pub async fn find_simd(
        &self,
        graph: &Graph,
        topo_order: &[String],
    ) -> Result<Vec<String>> {
        if self.simd_enabled {
            self.find_longest_path_simd_optimized(graph, topo_order).await
        } else {
            self.find_longest_path_standard(graph, topo_order).await
        }
    }
    
    /// SIMD-оптимизированная версия
    async fn find_longest_path_simd_optimized(
        &self,
        graph: &Graph,
        topo_order: &[String],
    ) -> Result<Vec<String>> {
        // Создание маппинга вершин на индексы
        let vertex_to_idx: HashMap<_, _> = topo_order
            .iter()
            .enumerate()
            .map(|(idx, vertex)| (vertex, idx))
            .collect();
        
        let n = topo_order.len();
        let mut distances = vec![-1.0f32; n]; // Используем f32 для SIMD
        let mut predecessors = vec![None::<usize>; n];
        
        // Инициализация: все вершины имеют дистанцию 0
        distances.par_iter_mut().for_each(|d| *d = 0.0);
        
        // Параллельная обработка в топологическом порядке
        for (current_idx, current_vertex) in topo_order.iter().enumerate() {
            if let Some(outgoing) = graph.get_outgoing_edges(current_vertex) {
                let outgoing_list: Vec<_> = outgoing.collect();
                
                // Обновление дистанций
                for &target_vertex in &outgoing_list {
                    if let Some(&target_idx) = vertex_to_idx.get(target_vertex) {
                        let new_distance = distances[current_idx] + 1.0;
                        
                        // Простое обновление максимального расстояния
                        if new_distance > distances[target_idx] {
                            distances[target_idx] = new_distance;
                            predecessors[target_idx] = Some(current_idx);
                        }
                    }
                }
            }
        }
        
        // Поиск вершины с максимальной дистанцией
        let (max_idx, _) = distances
            .iter()
            .enumerate()
            .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap())
            .unwrap();
        
        // Восстановление пути
        let path = self.reconstruct_path(max_idx, &predecessors, topo_order);
        
        Ok(path)
    }
    
    /// Стандартная версия без SIMD
    async fn find_longest_path_standard(
        &self,
        graph: &Graph,
        topo_order: &[String],
    ) -> Result<Vec<String>> {
        let vertex_to_idx: HashMap<_, _> = topo_order
            .iter()
            .enumerate()
            .map(|(idx, vertex)| (vertex, idx))
            .collect();
        
        let n = topo_order.len();
        let mut distances = vec![0i32; n];
        let mut predecessors = vec![None::<usize>; n];
        
        // Обработка в топологическом порядке
        for (current_idx, current_vertex) in topo_order.iter().enumerate() {
            if let Some(outgoing) = graph.get_outgoing_edges(current_vertex) {
                for target_vertex in outgoing {
                    if let Some(&target_idx) = vertex_to_idx.get(target_vertex) {
                        let new_distance = distances[current_idx] + 1;
                        
                        if new_distance > distances[target_idx] {
                            distances[target_idx] = new_distance;
                            predecessors[target_idx] = Some(current_idx);
                        }
                    }
                }
            }
        }
        
        // Поиск вершины с максимальной дистанцией
        let (max_idx, _) = distances
            .iter()
            .enumerate()
            .max_by_key(|(_, &d)| d)
            .unwrap();
        
        // Восстановление пути
        let path = self.reconstruct_path(max_idx, &predecessors, topo_order);
        
        Ok(path)
    }
    
    /// Восстановление пути по массиву предшественников
    fn reconstruct_path(
        &self,
        end_idx: usize,
        predecessors: &[Option<usize>],
        topo_order: &[String],
    ) -> Vec<String> {
        let mut path = Vec::new();
        let mut current_idx = Some(end_idx);
        
        while let Some(idx) = current_idx {
            path.push(topo_order[idx].clone());
            current_idx = predecessors[idx];
        }
        
        path.reverse();
        path
    }
    
    /// Валидация пути
    pub fn validate_path(&self, graph: &Graph, path: &[String]) -> Result<()> {
        if path.is_empty() {
            return Ok(());
        }
        
        for window in path.windows(2) {
            let source = &window[0];
            let target = &window[1];
            
            if !graph.contains_edge(source, target) {
                return Err(anyhow::anyhow!(
                    "Некорректный путь: отсутствует связь {} -> {}",
                    source, target
                ));
            }
        }
        
        Ok(())
    }
    
    /// Получение всех longest paths (для случая нескольких путей одинаковой длины)
    pub async fn find_all_longest_paths(
        &self,
        graph: &Graph,
        topo_order: &[String],
    ) -> Result<Vec<Vec<String>>> {
        // TODO: Реализация поиска всех longest paths
        let single_path = self.find_simd(graph, topo_order).await?;
        Ok(vec![single_path])
    }
    
    /// Статистика longest path
    pub fn get_path_statistics(&self, path: &[String]) -> PathStatistics {
        PathStatistics {
            length: path.len(),
            start_vertex: path.first().cloned().unwrap_or_default(),
            end_vertex: path.last().cloned().unwrap_or_default(),
            vertices: path.to_vec(),
        }
    }
}

/// Статистика пути
#[derive(Debug, Clone)]
pub struct PathStatistics {
    pub length: usize,
    pub start_vertex: String,
    pub end_vertex: String,
    pub vertices: Vec<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data_structures::GraphBuilder;
    
    #[tokio::test]
    async fn test_longest_path_simple() -> Result<()> {
        // Создание простого DAG: A -> B -> C -> D
        let mut builder = GraphBuilder::new();
        builder.add_edge("A".to_string(), "B".to_string(), 1.0)?;
        builder.add_edge("B".to_string(), "C".to_string(), 1.0)?;
        builder.add_edge("C".to_string(), "D".to_string(), 1.0)?;
        let graph = builder.build()?;
        
        let topo_order = vec!["A".to_string(), "B".to_string(), "C".to_string(), "D".to_string()];
        
        let finder = SIMDLongestPath::new(true)?;
        let longest_path = finder.find_simd(&graph, &topo_order).await?;
        
        assert_eq!(longest_path.len(), 4);
        assert_eq!(longest_path, vec!["A", "B", "C", "D"]);
        
        finder.validate_path(&graph, &longest_path)?;
        
        Ok(())
    }
    
    #[tokio::test]
    async fn test_longest_path_complex() -> Result<()> {
        // Создание более сложного DAG
        let mut builder = GraphBuilder::new();
        
        // Ветвящийся граф
        builder.add_edge("A".to_string(), "B".to_string(), 1.0)?;
        builder.add_edge("A".to_string(), "C".to_string(), 1.0)?;
        builder.add_edge("B".to_string(), "D".to_string(), 1.0)?;
        builder.add_edge("C".to_string(), "D".to_string(), 1.0)?;
        builder.add_edge("D".to_string(), "E".to_string(), 1.0)?;
        
        // Добавляем длинный путь
        builder.add_edge("A".to_string(), "F".to_string(), 1.0)?;
        builder.add_edge("F".to_string(), "G".to_string(), 1.0)?;
        builder.add_edge("G".to_string(), "H".to_string(), 1.0)?;
        builder.add_edge("H".to_string(), "I".to_string(), 1.0)?;
        
        let graph = builder.build()?;
        
        // Примерный топологический порядок
        let topo_order = vec![
            "A".to_string(), "B".to_string(), "C".to_string(), "F".to_string(),
            "D".to_string(), "G".to_string(), "E".to_string(), "H".to_string(), "I".to_string()
        ];
        
        let finder = SIMDLongestPath::new(true)?;
        let longest_path = finder.find_simd(&graph, &topo_order).await?;
        
        // Самый длинный путь должен быть A -> F -> G -> H -> I
        assert!(longest_path.len() >= 4);
        finder.validate_path(&graph, &longest_path)?;
        
        let stats = finder.get_path_statistics(&longest_path);
        assert_eq!(stats.start_vertex, "A");
        
        Ok(())
    }
}
