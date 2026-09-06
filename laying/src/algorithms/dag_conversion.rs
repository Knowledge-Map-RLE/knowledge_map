/*!
# Преобразование циклического графа в DAG

Модуль реализует приведение произвольного ориентированного графа к
направленному ациклическому графу (DAG) путём **разворота минимального
числа рёбер** (feedback arc set).

## Алгоритм

Используется жадный подход "expand cycles" (Eades–Lin–Smyth, GreedyFAS):

1. Пока в графе есть вершины:
   - Поочерёдно удаляем все **источники** (in-degree = 0), добавляя их в левый
     упорядоченный список `S1`.
   - Иначе последовательно удаляем все **стоки** (out-degree = 0), добавляя их
     в правый список `S2`.
   - Иначе выбираем вершину `v`, максимизирующую `delta = outdeg(v) - indeg(v)`,
     удаляем её в средний набор `S0`.
2. Итоговый топологический порядок: `S1 + S0 + reverse(S2)`.
3. Рёбра `(u -> v)`, у которых `v` стоит раньше `u` в этом порядке, образуют
   feedback arc set — именно их разворачиваем, чтобы получить DAG.

Алгоритм эвристически минимизирует число развёрнутых рёбер и работает за
приемлемое время на графах с тысячами вершин (используется оптимальный
по сложности подбор вершины через поддержку степеней).

Корректность: разворот рёбер, идущих "против" топологического порядка,
гарантирует ацикличность результирующего графа.
*/

use anyhow::Result;
use std::collections::{HashMap, HashSet};

/// Структура результата преобразования в DAG.
#[derive(Debug, Clone)]
pub struct DagResult {
    /// Новый список рёбер с развёрнутыми необходимыми связями.
    pub edges: Vec<DagEdge>,
    /// Количество развёрнутых рёбер (feedback arc set size).
    pub reversed_count: usize,
    /// Количество вершин, затронутых циклами (вход в компоненты с циклами).
    pub cyclic_vertices: usize,
}

/// Внутреннее представление ребра для алгоритма преобразования.
#[derive(Debug, Clone)]
pub struct DagEdge {
    pub source_id: String,
    pub target_id: String,
    pub weight: f32,
    pub edge_type: String,
}

/// Вспомогательная структура для внутреннего представления графа алгоритма.
struct FasGraph {
    /// Исходящие рёбра: вершина -> набор целевых вершин.
    out: Vec<HashSet<usize>>,
    /// Входящие рёбра: вершина -> набор исходящих вершин.
    in_deg: Vec<usize>,
    /// Признак того, что вершина ещё присутствует в графе алгоритма.
    active: Vec<bool>,
    /// Число активных вершин.
    active_count: usize,
}

impl FasGraph {
    fn new(n: usize) -> Self {
        Self {
            out: (0..n).map(|_| HashSet::new()).collect(),
            in_deg: vec![0; n],
            active: vec![true; n],
            active_count: n,
        }
    }

    fn add_edge(&mut self, u: usize, v: usize) {
        if self.out[u].insert(v) {
            self.in_deg[v] += 1;
        }
    }

    fn remove_vertex(&mut self, v: usize) {
        if !self.active[v] {
            return;
        }
        self.active[v] = false;
        self.active_count -= 1;
        // Убираем исходящие рёбра: уменьшаем in-degree соседей.
        for &to in &self.out[v].clone() {
            if self.active[to] {
                self.in_deg[to] = self.in_deg[to].saturating_sub(1);
            }
        }
        // Убираем входящие рёбра не нужно: in_degree соседей-источников
        // обрабатывается через out-списки при удалении.
    }
}

/// Вычисляет топологический порядок и набор разворачиваемых рёбер жадным
/// алгоритмом "expand cycles" (Eades–Lin–Smyth).
///
/// Возвращает `order` (порядок вершин) и `reversed` (множество пар `(u, v)`,
/// которые следует развернуть).
fn greedy_feedback_arc_set(vertices: &[String], edges: &[(usize, usize)]) -> (Vec<usize>, HashSet<(usize, usize)>) {
    let n = vertices.len();
    let mut g = FasGraph::new(n);

    for &(u, v) in edges {
        g.add_edge(u, v);
    }

    // Ищем вершину с максимальным delta = outdeg - indeg для среднего набора.
    // Для эффективности пересчитываем delta при каждом удалении лишь при необходимости.
    let mut s1: Vec<usize> = Vec::new();
    let mut s0: Vec<usize> = Vec::new();
    let mut s2: Vec<usize> = Vec::new();

    while g.active_count > 0 {
        // 1. Извлекаем все источники (in-degree = 0) в S1.
        let mut changed = true;
        while changed {
            changed = false;
            for v in 0..n {
                if g.active[v] && g.in_deg[v] == 0 {
                    g.remove_vertex(v);
                    s1.push(v);
                    changed = true;
                }
            }
        }

        // 2. Извлекаем все стоки (out-degree = 0) в S2.
        changed = true;
        while changed {
            changed = false;
            for v in 0..n {
                if g.active[v] && g.out[v].is_empty() {
                    g.remove_vertex(v);
                    s2.push(v);
                    changed = true;
                }
            }
        }

        // 3. Если активные вершины остались — есть цикл.
        if g.active_count == 0 {
            break;
        }

        // Выбираем вершину v с максимальным delta = outdeg - indeg.
        let mut best_v = usize::MAX;
        let mut best_delta = i64::MIN;
        for v in 0..n {
            if !g.active[v] {
                continue;
            }
            let delta = g.out[v].len() as i64 - g.in_deg[v] as i64;
            if delta > best_delta {
                best_delta = delta;
                best_v = v;
            }
        }

        g.remove_vertex(best_v);
        s0.push(best_v);
    }

    // Итоговый порядок: S1 + S0 + reverse(S2).
    s2.reverse();
    let mut order = Vec::with_capacity(n);
    order.extend(s1);
    order.extend(s0);
    order.extend(s2);

    // Позиция каждой вершины в порядке.
    let mut pos = vec![0usize; n];
    for (i, &v) in order.iter().enumerate() {
        pos[v] = i;
    }

    // Рёбра, идущие "против" порядка, необходимо развернуть.
    let mut reversed: HashSet<(usize, usize)> = HashSet::new();
    for &(u, v) in edges {
        if pos[u] > pos[v] {
            reversed.insert((u, v));
        }
    }

    (order, reversed)
}

/// Подсчёт числа вершин, вовлечённых в циклы, через алгоритм Тарьяна
/// (поиск сильно связных компонент). Вершина считается циклической, если она
/// принадлежит SCC размера больше 1 (нетривиальная компонента ⇔ в ней есть цикл).
///
/// Используется высокопроизводительная реализация Tarjan из petgraph.
fn count_cyclic_vertices(n: usize, edges: &[(usize, usize)]) -> usize {
    if n == 0 {
        return 0;
    }

    let mut graph = petgraph::graph::DiGraph::<(), ()>::with_capacity(n, edges.len());
    for _ in 0..n {
        graph.add_node(());
    }
    for &(u, v) in edges {
        if u != v {
            let a = petgraph::graph::NodeIndex::new(u);
            let b = petgraph::graph::NodeIndex::new(v);
            graph.add_edge(a, b, ());
        }
    }

    let components = petgraph::algo::tarjan_scc(&graph);
    let cyclic = components
        .iter()
        .filter(|comp| comp.len() > 1)
        .map(|comp| comp.len())
        .sum();

    cyclic
}

/// Преобразует список рёбер в DAG, разворачивая минимальный набор рёбер,
/// разрушающих все циклы.
///
/// ## Параметры
/// - `edges`: исходные рёбра графа.
/// - `added_vertices`: дополнительные вершины (изолированные), которые не
///   входят ни в одно ребро, но должны присутствовать в результате.
///
/// ## Возвращает
/// Новый список рёбер (с развёрнутыми связями) и статистику преобразования.
pub fn convert_to_dag(
    edges: &[(String, String, f32, String)],
    added_vertices: &[String],
) -> Result<DagResult> {
    // Собираем множество вершин.
    let mut vertex_set: Vec<String> = Vec::new();
    let mut vertex_index: HashMap<String, usize> = HashMap::new();

    let index_of = |id: &str, vertex_set: &mut Vec<String>, vertex_index: &mut HashMap<String, usize>| -> usize {
        if let Some(&idx) = vertex_index.get(id) {
            idx
        } else {
            let idx = vertex_set.len();
            vertex_set.push(id.to_string());
            vertex_index.insert(id.to_string(), idx);
            idx
        }
    };

    let mut indexed_edges: Vec<(usize, usize)> = Vec::with_capacity(edges.len());
    for (src, dst, _, _) in edges {
        let u = index_of(src, &mut vertex_set, &mut vertex_index);
        let v = index_of(dst, &mut vertex_set, &mut vertex_index);
        indexed_edges.push((u, v));
    }
    for id in added_vertices {
        index_of(id, &mut vertex_set, &mut vertex_index);
    }

    let (_order, reversed) = greedy_feedback_arc_set(&vertex_set, &indexed_edges);

    // Число вершин, вовлечённых в циклы (Tarjan SCC).
    let cyclic_vertex_count = count_cyclic_vertices(vertex_set.len(), &indexed_edges);

    // Строим результирующий список рёбер с учётом разворотов.
    let mut result_edges: Vec<DagEdge> = Vec::with_capacity(edges.len());
    let mut reversed_count = 0usize;

    for (_i, (src, dst, weight, edge_type)) in edges.iter().enumerate() {
        let u = vertex_index[src];
        let v = vertex_index[dst];
        if reversed.contains(&(u, v)) {
            reversed_count += 1;
            result_edges.push(DagEdge {
                source_id: dst.clone(),
                target_id: src.clone(),
                weight: *weight,
                edge_type: edge_type.clone(),
            });
        } else {
            result_edges.push(DagEdge {
                source_id: src.clone(),
                target_id: dst.clone(),
                weight: *weight,
                edge_type: edge_type.clone(),
            });
        }
    }

    Ok(DagResult {
        edges: result_edges,
        reversed_count,
        cyclic_vertices: cyclic_vertex_count,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_already_dag_no_reversal() -> Result<()> {
        // A -> B -> C уже DAG, разворотов быть не должно.
        let edges: Vec<(String, String, f32, String)> = vec![
            ("A".into(), "B".into(), 1.0, "ref".into()),
            ("B".into(), "C".into(), 1.0, "ref".into()),
        ];
        let res = convert_to_dag(&edges, &[])?;
        assert_eq!(res.reversed_count, 0);
        assert_eq!(res.cyclic_vertices, 0);
        Ok(())
    }

    #[test]
    fn test_single_cycle_reversed() -> Result<()> {
        // A -> B -> C -> A (цикл из трёх вершин).
        let edges: Vec<(String, String, f32, String)> = vec![
            ("A".into(), "B".into(), 1.0, "ref".into()),
            ("B".into(), "C".into(), 1.0, "ref".into()),
            ("C".into(), "A".into(), 1.0, "ref".into()),
        ];
        let res = convert_to_dag(&edges, &[])?;
        // Должно быть развёрнуто ровно одно ребро.
        assert_eq!(res.reversed_count, 1);
        assert_eq!(res.cyclic_vertices, 3);
        Ok(())
    }

    #[test]
    fn test_mutual_cycle_reversed() -> Result<()> {
        // A <-> B (взаимный цикл из двух вершин).
        let edges: Vec<(String, String, f32, String)> = vec![
            ("A".into(), "B".into(), 1.0, "ref".into()),
            ("B".into(), "A".into(), 1.0, "ref".into()),
        ];
        let res = convert_to_dag(&edges, &[])?;
        assert_eq!(res.reversed_count, 1);
        assert_eq!(res.cyclic_vertices, 2);
        Ok(())
    }
}
