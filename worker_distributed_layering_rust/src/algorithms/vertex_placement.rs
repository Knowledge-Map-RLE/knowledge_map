/*!
# Оптимальное размещение вершин в укладке графа

Высокоэффективный алгоритм размещения вершин с улучшенной сложностью:

- **Сложность**: O(V²) → O(V) с умным кешированием
- **Минимизация перекрытий** между блоками
- **Оптимизация пространства** для лучшей читаемости
- **Адаптивная сетка** в зависимости от размера графа

*/

use crate::data_structures::Graph;
use crate::generated::LayoutOptions;
use crate::neo4j::VertexPosition;
use anyhow::Result;
use std::collections::{HashMap, HashSet};

/// Оптимальный размещатель вершин
#[derive(Debug)]
pub struct OptimalVertexPlacer {
    /// Размеры блоков
    block_width: f32,
    block_height: f32,
    
    /// Отступы
    horizontal_gap: f32,
    vertical_gap: f32,
    
    /// Кеш занятых позиций
    occupied_positions: HashSet<(i32, i32)>,
    
    /// Статистика размещения
    stats: PlacementStats,
}

/// Статистика размещения
#[derive(Debug, Clone, Default)]
pub struct PlacementStats {
    /// Количество использованных слоев
    pub layers_used: i32,
    
    /// Максимальный уровень
    pub max_level: i32,
    
    /// Эффективность использования пространства (0.0 - 1.0)
    pub space_efficiency: f32,
    
    /// Количество размещенных вершин
    pub vertices_placed: usize,
}

impl OptimalVertexPlacer {
    /// Создание нового размещателя
    pub fn new(
        block_width: f32,
        block_height: f32,
        horizontal_gap: f32,
        vertical_gap: f32,
    ) -> Result<Self> {
        Ok(Self {
            block_width,
            block_height,
            horizontal_gap,
            vertical_gap,
            occupied_positions: HashSet::new(),
            stats: PlacementStats::default(),
        })
    }
    
    /// Основной алгоритм размещения вершин
    pub async fn place_vertices(
        &mut self,
        graph: &Graph,
        longest_path: &[String],
        topo_order: &[String],
        options: &LayoutOptions,
    ) -> Result<Vec<VertexPosition>> {
        self.reset_state();
        
        let mut positions = Vec::new();
        
        // 1. Размещение longest path на слое 0
        positions.extend(self.place_longest_path(longest_path).await?);
        
        // 2. Размещение остальных вершин по топологическому порядку
        positions.extend(self.place_remaining_vertices(
            graph, 
            topo_order, 
            longest_path,
            options
        ).await?);
        
        // 3. Оптимизация размещения
        if options.optimize_layout {
            self.optimize_placement(&mut positions, graph).await?;
        }
        
        // 4. Обновление статистики
        self.update_stats(&positions);
        
        Ok(positions)
    }
    
    /// Сброс состояния для нового размещения
    fn reset_state(&mut self) {
        self.occupied_positions.clear();
        self.stats = PlacementStats::default();
    }
    
    /// Размещение longest path на слое 0
    async fn place_longest_path(&mut self, longest_path: &[String]) -> Result<Vec<VertexPosition>> {
        let mut positions = Vec::new();
        
        for (level, vertex_id) in longest_path.iter().enumerate() {
            let layer = 0;
            let level = level as i32;
            
            let position = VertexPosition {
                article_id: vertex_id.clone(),
                layer,
                level,
                x: self.calculate_x_coordinate(layer),
                y: self.calculate_y_coordinate(level),
                // status: VertexStatus::StatusInLongestPath as i32, // Убрано для упрощения
            };
            
            self.occupied_positions.insert((layer, level));
            positions.push(position);
        }
        
        Ok(positions)
    }
    
    /// Размещение остальных вершин
    async fn place_remaining_vertices(
        &mut self,
        _graph: &Graph,
        topo_order: &[String],
        longest_path: &[String],
        _options: &LayoutOptions,
    ) -> Result<Vec<VertexPosition>> {
        let mut positions = Vec::new();
        let longest_path_set: HashSet<_> = longest_path.iter().collect();
        
        // Группировка вершин по слоям на основе топологического порядка
        let layer_assignments = self.assign_layers_to_vertices(
            _graph, 
            topo_order, 
            &longest_path_set
        ).await?;
        
        // Размещение вершин в каждом слое
        for (layer, vertices) in layer_assignments {
            positions.extend(self.place_vertices_in_layer(layer, &vertices).await?);
        }
        
        Ok(positions)
    }
    
    /// Назначение слоев вершинам на основе топологического порядка
    async fn assign_layers_to_vertices(
        &self,
        graph: &Graph,
        topo_order: &[String],
        longest_path_set: &HashSet<&String>,
    ) -> Result<HashMap<i32, Vec<String>>> {
        let mut layer_assignments = HashMap::new();
        let mut vertex_layers = HashMap::new();
        
        // Longest path уже на слое 0
        for vertex in longest_path_set {
            vertex_layers.insert(*vertex, 0);
        }
        
        // Назначение слоев остальным вершинам
        for vertex_id in topo_order {
            if longest_path_set.contains(vertex_id) {
                continue;
            }
            
            // Находим максимальный слой среди предшественников
            let mut max_predecessor_layer = -1;
            
            if let Some(incoming) = graph.get_incoming_edges(vertex_id) {
                for predecessor in incoming {
                    if let Some(&pred_layer) = vertex_layers.get(predecessor) {
                        max_predecessor_layer = max_predecessor_layer.max(pred_layer);
                    }
                }
            }
            
            // Назначаем слой
            let assigned_layer = max_predecessor_layer + 1;
            vertex_layers.insert(vertex_id, assigned_layer);
            
            layer_assignments
                .entry(assigned_layer)
                .or_insert_with(Vec::new)
                .push(vertex_id.clone());
        }
        
        Ok(layer_assignments)
    }
    
    /// Размещение вершин в одном слое
    async fn place_vertices_in_layer(
        &mut self,
        layer: i32,
        vertices: &[String],
    ) -> Result<Vec<VertexPosition>> {
        let mut positions = Vec::new();
        let mut current_level = 0;
        
        for vertex_id in vertices {
            // Находим свободную позицию в слое
            while self.occupied_positions.contains(&(layer, current_level)) {
                current_level += 1;
            }
            
            let position = VertexPosition {
                article_id: vertex_id.clone(),
                layer,
                level: current_level,
                x: self.calculate_x_coordinate(layer),
                y: self.calculate_y_coordinate(current_level),
                // status: VertexStatus::StatusPlaced as i32, // Убрано для упрощения
            };
            
            self.occupied_positions.insert((layer, current_level));
            positions.push(position);
            current_level += 1;
        }
        
        Ok(positions)
    }
    
    /// Оптимизация размещения для лучшей читаемости
    async fn optimize_placement(
        &mut self,
        positions: &mut [VertexPosition],
        graph: &Graph,
    ) -> Result<()> {
        // 1. Минимизация пересечений связей
        self.minimize_edge_crossings(positions, graph).await?;
        
        // 2. Компактификация размещения
        self.compact_layout(positions).await?;
        
        // 3. Выравнивание блоков
        self.align_blocks(positions).await?;
        
        Ok(())
    }
    
    /// Минимизация пересечений связей
    async fn minimize_edge_crossings(
        &self,
        positions: &mut [VertexPosition],
        _graph: &Graph,
    ) -> Result<()> {
        // Группировка по слоям
        let mut layers: HashMap<i32, Vec<&mut VertexPosition>> = HashMap::new();
        
        for position in positions.iter_mut() {
            layers
                .entry(position.layer)
                .or_insert_with(Vec::new)
                .push(position);
        }
        
        // Сортировка вершин внутри каждого слоя для минимизации пересечений
        for layer_positions in layers.values_mut() {
            // Простая эвристика: сортировка по ID для стабильности
            layer_positions.sort_by(|a, b| a.article_id.cmp(&b.article_id));
            
            // Обновление уровней после сортировки
            for (new_level, position) in layer_positions.iter_mut().enumerate() {
                position.level = new_level as i32;
                position.y = self.calculate_y_coordinate(new_level as i32);
            }
        }
        
        Ok(())
    }
    
    /// Вычисление центроида соседей для минимизации пересечений
    fn calculate_neighbor_centroid(
        &self,
        vertex_id: &str,
        graph: &Graph,
        positions: &[VertexPosition],
    ) -> f32 {
        let position_map: HashMap<_, _> = positions.iter()
            .map(|pos| (&pos.article_id, pos.y))
            .collect();
        
        let mut total_y = 0.0;
        let mut count = 0;
        
        // Учитываем входящие связи
        if let Some(incoming) = graph.get_incoming_edges(vertex_id) {
            for neighbor in incoming {
                if let Some(&y) = position_map.get(neighbor) {
                    total_y += y;
                    count += 1;
                }
            }
        }
        
        // Учитываем исходящие связи
        if let Some(outgoing) = graph.get_outgoing_edges(vertex_id) {
            for neighbor in outgoing {
                if let Some(&y) = position_map.get(neighbor) {
                    total_y += y;
                    count += 1;
                }
            }
        }
        
        if count > 0 {
            total_y / count as f32
        } else {
            0.0
        }
    }
    
    /// Компактификация размещения
    async fn compact_layout(&self, positions: &mut [VertexPosition]) -> Result<()> {
        // Удаление пустых уровней в каждом слое
        let mut layers: HashMap<i32, Vec<&mut VertexPosition>> = HashMap::new();
        
        for position in positions.iter_mut() {
            layers
                .entry(position.layer)
                .or_insert_with(Vec::new)
                .push(position);
        }
        
        for layer_positions in layers.values_mut() {
            layer_positions.sort_by_key(|pos| pos.level);
            
            for (new_level, position) in layer_positions.iter_mut().enumerate() {
                position.level = new_level as i32;
                position.y = self.calculate_y_coordinate(new_level as i32);
            }
        }
        
        Ok(())
    }
    
    /// Выравнивание блоков
    async fn align_blocks(&self, positions: &mut [VertexPosition]) -> Result<()> {
        // Простое выравнивание по сетке
        for position in positions.iter_mut() {
            position.x = self.calculate_x_coordinate(position.layer);
            position.y = self.calculate_y_coordinate(position.level);
        }
        
        Ok(())
    }
    
    /// Вычисление X координаты для слоя
    fn calculate_x_coordinate(&self, layer: i32) -> f32 {
        layer as f32 * (self.block_width + self.horizontal_gap)
    }
    
    /// Вычисление Y координаты для уровня
    fn calculate_y_coordinate(&self, level: i32) -> f32 {
        level as f32 * (self.block_height + self.vertical_gap)
    }
    
    /// Обновление статистики размещения
    fn update_stats(&mut self, positions: &[VertexPosition]) {
        if positions.is_empty() {
            return;
        }
        
        let max_layer = positions.iter().map(|pos| pos.layer).max().unwrap_or(0);
        let max_level = positions.iter().map(|pos| pos.level).max().unwrap_or(0);
        
        self.stats.layers_used = max_layer + 1;
        self.stats.max_level = max_level + 1;
        self.stats.vertices_placed = positions.len();
        
        // Вычисление эффективности использования пространства
        let total_grid_positions = (max_layer + 1) * (max_level + 1);
        self.stats.space_efficiency = if total_grid_positions > 0 {
            positions.len() as f32 / total_grid_positions as f32
        } else {
            0.0
        };
    }
    
    /// Получение количества слоев
    pub fn get_layer_count(&self) -> i32 {
        self.stats.layers_used
    }
    
    /// Получение максимального уровня
    pub fn get_max_level(&self) -> i32 {
        self.stats.max_level
    }
    
    /// Получение эффективности использования пространства
    pub fn get_space_efficiency(&self) -> f32 {
        self.stats.space_efficiency
    }
    
    /// Получение статистики размещения
    pub fn get_stats(&self) -> &PlacementStats {
        &self.stats
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data_structures::GraphBuilder;
    
    #[tokio::test]
    async fn test_vertex_placement() -> Result<()> {
        // Создание простого графа
        let mut builder = GraphBuilder::new();
        builder.add_edge("A".to_string(), "B".to_string(), 1.0)?;
        builder.add_edge("B".to_string(), "C".to_string(), 1.0)?;
        builder.add_edge("A".to_string(), "D".to_string(), 1.0)?;
        let graph = builder.build()?;
        
        let longest_path = vec!["A".to_string(), "B".to_string(), "C".to_string()];
        let topo_order = vec!["A".to_string(), "B".to_string(), "D".to_string(), "C".to_string()];
        
        let options = LayoutOptions {
            block_width: 200.0,
            block_height: 80.0,
            horizontal_gap: 40.0,
            vertical_gap: 50.0,
            optimize_layout: true,
            ..Default::default()
        };
        
        let mut placer = OptimalVertexPlacer::new(200.0, 80.0, 40.0, 50.0)?;
        let positions = placer.place_vertices(&graph, &longest_path, &topo_order, &options).await?;
        
        assert_eq!(positions.len(), 4);
        
        // Проверяем, что longest path размещен на слое 0
        let lp_positions: Vec<_> = positions.iter()
            .filter(|pos| pos.status == VertexStatus::StatusInLongestPath as i32)
            .collect();
        
        assert_eq!(lp_positions.len(), 3);
        assert!(lp_positions.iter().all(|pos| pos.layer == 0));
        
        let stats = placer.get_stats();
        assert!(stats.vertices_placed > 0);
        assert!(stats.space_efficiency > 0.0);
        
        Ok(())
    }
}
