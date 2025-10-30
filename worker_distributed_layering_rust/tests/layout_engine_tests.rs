use std::collections::{HashMap, HashSet};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::Result;
use graph_layout_engine::{
    generated::{LayoutOptions, MemoryStrategy},
    neo4j::{GraphEdge, VertexPosition},
    HighPerformanceLayoutEngine, LayoutAlgorithm,
};
use proptest::prelude::*;
use proptest::test_runner::TestRunner;
use serde_json;
use tokio::runtime::Runtime;

fn default_options() -> LayoutOptions {
    LayoutOptions {
        block_width: 160.0,
        block_height: 80.0,
        horizontal_gap: 40.0,
        vertical_gap: 60.0,
        exclude_isolated_vertices: false,
        optimize_layout: true,
        max_iterations: 8,
        convergence_threshold: 0.001,
        chunk_size: 4,
        max_workers: 4,
        enable_simd: true,
        enable_gpu: false,
        memory_strategy: MemoryStrategy::MemoryAuto as i32,
    }
}

fn sample_edges() -> Vec<GraphEdge> {
    vec![
        GraphEdge {
            source_id: "A".into(),
            target_id: "B".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "A".into(),
            target_id: "C".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "B".into(),
            target_id: "D".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "C".into(),
            target_id: "D".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "C".into(),
            target_id: "E".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "D".into(),
            target_id: "F".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "E".into(),
            target_id: "F".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "A".into(),
            target_id: "E".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "G".into(),
            target_id: "F".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "G".into(),
            target_id: "H".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
        GraphEdge {
            source_id: "B".into(),
            target_id: "F".into(),
            weight: 1.0,
            edge_type: "ref".into(),
        },
    ]
}

fn position_map(positions: &[VertexPosition]) -> HashMap<String, VertexPosition> {
    positions
        .iter()
        .map(|pos| (pos.article_id.clone(), pos.clone()))
        .collect()
}

fn edge_paths_from_metadata(parameters: &HashMap<String, String>) -> HashMap<(String, String), Vec<(f32, f32)>> {
    let Some(raw_json) = parameters.get("edge_paths") else {
        return HashMap::new();
    };

    let raw: HashMap<String, Vec<[f32; 2]>> = serde_json::from_str(raw_json)
        .expect("edge_paths metadata should be valid JSON");

    raw.into_iter()
        .map(|(key, coords)| {
            let mut parts = key.split("->");
            let src = parts.next().unwrap_or_default().to_string();
            let dst = parts.next().unwrap_or_default().to_string();
            let points = coords.into_iter().map(|pair| (pair[0], pair[1])).collect();
            ((src, dst), points)
        })
        .collect()
}

fn parse_dummy_id(id: &str) -> Option<(String, String, usize)> {
    const PREFIX: &str = "__dummy__";
    if !id.starts_with(PREFIX) {
        return None;
    }

    let remainder = &id[PREFIX.len()..];
    let mut parts = remainder.split("::");
    let source = parts.next()?;
    let target = parts.next()?;
    let step = parts.next()?.parse().ok()?;
    if parts.next().is_some() {
        return None;
    }

    Some((source.to_string(), target.to_string(), step))
}

fn is_dummy_vertex(id: &str) -> bool {
    parse_dummy_id(id).is_some()
}

fn artifacts_path(file_name: &str) -> PathBuf {
    let base = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests").join("artifacts");
    if !base.exists() {
        fs::create_dir_all(&base).expect("unable to create tests/artifacts directory");
    }
    base.join(file_name)
}

#[tokio::test]
async fn layout_engine_places_vertices_for_small_dag() -> Result<()> {
    let options = default_options();
    let mut engine = HighPerformanceLayoutEngine::new(&options)?;
    let edges = sample_edges();

    let result = engine.compute_layout(edges.clone(), &options).await?;

    let positions = position_map(&result.positions);
    let edge_paths = edge_paths_from_metadata(&result.metadata.parameters);

    let mut unique_real = HashSet::new();
    for pos in &result.positions {
        if !is_dummy_vertex(&pos.article_id) {
            unique_real.insert(pos.article_id.clone());
        }
    }
    assert_eq!(unique_real.len(), 8, "expected eight unique real vertices in the sample DAG");

    let real_entry_count = result
        .positions
        .iter()
        .filter(|pos| !is_dummy_vertex(&pos.article_id))
        .count();
    assert_eq!(real_entry_count, unique_real.len(), "duplicate real vertex entries detected");

    let step_x = options.block_width + options.horizontal_gap;
    let step_y = options.block_height + options.vertical_gap;

    let mut expected_dummy = 0usize;
    let mut actual_dummy = 0usize;

    for edge in &edges {
        let src = positions
            .get(&edge.source_id)
            .unwrap_or_else(|| panic!("missing source {}", edge.source_id));
        let dst = positions
            .get(&edge.target_id)
            .unwrap_or_else(|| panic!("missing target {}", edge.target_id));

        let path = edge_paths
            .get(&(edge.source_id.clone(), edge.target_id.clone()))
            .unwrap_or_else(|| panic!("missing edge path {} -> {}", edge.source_id, edge.target_id));

        let start = path.first().expect("path should contain start point");
        let end = path.last().expect("path should contain end point");

        let expected_start = (src.x + options.block_width, src.y + options.block_height / 2.0);
        let expected_end = (dst.x, dst.y + options.block_height / 2.0);
        assert!(
            (start.0 - expected_start.0).abs() < 1e-3 && (start.1 - expected_start.1).abs() < 1e-3,
            "edge {} -> {} start mismatch {:?} != {:?}",
            edge.source_id,
            edge.target_id,
            start,
            expected_start
        );
        assert!(
            (end.0 - expected_end.0).abs() < 1e-3 && (end.1 - expected_end.1).abs() < 1e-3,
            "edge {} -> {} end mismatch {:?} != {:?}",
            edge.source_id,
            edge.target_id,
            end,
            expected_end
        );

        let gap = dst.layer - src.layer;
        assert_eq!(path.len(), (gap + 1) as usize, "edge {} -> {} path length mismatch", edge.source_id, edge.target_id);

        if gap > 1 {
            expected_dummy += (gap - 1) as usize;
        }
        actual_dummy += path.len().saturating_sub(2);

        for window in path.windows(2) {
            assert!(
                window[1].0 >= window[0].0 - 1e-3,
                "edge {} -> {} should be monotonically increasing in X",
                edge.source_id,
                edge.target_id
            );
        }
    }

    assert_eq!(actual_dummy, expected_dummy, "dummy vertex count mismatch");

    for pos in positions.values() {
        let expected_x = pos.layer as f32 * step_x;
        let expected_y = pos.level as f32 * step_y;
        assert!(
            (pos.x - expected_x).abs() < 1e-3,
            "x coordinate for {} mismatch: {} != {}",
            pos.article_id,
            pos.x,
            expected_x
        );
        assert!(
            (pos.y - expected_y).abs() < 1e-3,
            "y coordinate for {} mismatch: {} != {}",
            pos.article_id,
            pos.y,
            expected_y
        );
    }

    let max_layer = result.positions.iter().map(|pos| pos.layer).max().unwrap_or(0);
    let stats = result.statistics;
    assert!(
        stats.longest_path_length as i32 <= max_layer + 1,
        "longest path length should not exceed used layers"
    );
    assert!(
        stats.vertices_processed >= real_entry_count as i64,
        "statistics should mention processed vertices"
    );
    assert!(
        stats.edges_processed >= edges.len() as i64,
        "statistics should mention processed edges"
    );
    assert!(
        stats.algorithm_metrics.is_some(),
        "algorithm metrics must be populated"
    );

    Ok(())
}

#[tokio::test]
async fn layout_engine_rejects_empty_input() {
    let options = default_options();
    let mut engine = HighPerformanceLayoutEngine::new(&options).expect("valid engine init");
    let result = engine.compute_layout(Vec::new(), &options).await;
    assert!(
        result.is_err(),
        "layout engine must refuse empty edge list to avoid meaningless layouts"
    );
}

fn write_gml(
    positions: &[VertexPosition],
    edges: &[GraphEdge],
    edge_paths: &HashMap<(String, String), Vec<(f32, f32)>>,
    block_width: f32,
    block_height: f32,
    path: &Path,
) -> Result<()> {
    use std::fmt::Write as _;

    let mut buffer = String::new();
    writeln!(buffer, "Creator	\"Codex\"")?;
    writeln!(buffer, "Version	\"1.0\"")?;
    writeln!(buffer, "graph")?;
    writeln!(buffer, "[")?;
    writeln!(buffer, "	hierarchic	1")?;
    writeln!(buffer, "	label	\"\"")?;
    writeln!(buffer, "	directed	1")?;
    writeln!(buffer)?;

    let mut id_map = HashMap::new();
    let mut position_lookup = HashMap::new();

    for (idx, pos) in positions.iter().enumerate() {
        id_map.insert(pos.article_id.clone(), idx);
        position_lookup.insert(pos.article_id.clone(), pos.clone());

        writeln!(buffer, "	node")?;
        writeln!(buffer, "	[")?;
        writeln!(buffer, "		id	{}", idx)?;
        writeln!(buffer, "		label	\"{}\"", pos.article_id)?;
        writeln!(buffer, "		graphics")?;
        writeln!(buffer, "		[")?;
        writeln!(buffer, "			x	{:.3}", pos.x)?;
        writeln!(buffer, "			y	{:.3}", pos.y)?;
        writeln!(buffer, "			w	{:.3}", block_width)?;
        writeln!(buffer, "			h	{:.3}", block_height)?;
        writeln!(buffer, "			type	\"roundrectangle\"")?;
        writeln!(buffer, "		]")?;
        writeln!(buffer, "	]")?;
    }

    let mut push_edge = |src_idx: usize, dst_idx: usize, path_points: &[(f32, f32)]| -> Result<()> {
        writeln!(buffer, "	edge")?;
        writeln!(buffer, "	[")?;
        writeln!(buffer, "		source	{}", src_idx)?;
        writeln!(buffer, "		target	{}", dst_idx)?;
        writeln!(buffer, "		graphics")?;
        writeln!(buffer, "		[")?;
        writeln!(buffer, "			smoothBends	1")?;
        writeln!(buffer, "			width	2")?;
        writeln!(buffer, "			fill	\"#B266FF\"")?;
        writeln!(buffer, "			targetArrow	\"standard\"")?;
        writeln!(buffer, "			Line")?;
        writeln!(buffer, "			[")?;
        for (x, y) in path_points {
            writeln!(buffer, "				point")?;
            writeln!(buffer, "				[")?;
            writeln!(buffer, "					x	{:.3}", x)?;
            writeln!(buffer, "					y	{:.3}", y)?;
            writeln!(buffer, "				]")?;
        }
        writeln!(buffer, "			]")?;
        writeln!(buffer, "		]")?;
        writeln!(buffer, "		edgeAnchor")?;
        writeln!(buffer, "		[")?;
        writeln!(buffer, "			xSource	1.0")?;
        writeln!(buffer, "			xTarget	-1.0")?;
        writeln!(buffer, "		]")?;
        writeln!(buffer, "	]")?;
        Ok(())
    };

    for edge in edges {
        let src_idx = *id_map.get(&edge.source_id).expect("source id missing");
        let dst_idx = *id_map.get(&edge.target_id).expect("target id missing");

        let path_points = if let Some(points) = edge_paths.get(&(edge.source_id.clone(), edge.target_id.clone())) {
            points.clone()
        } else {
            let src = position_lookup.get(&edge.source_id).expect("source missing");
            let dst = position_lookup.get(&edge.target_id).expect("target missing");
            vec![
                (src.x + block_width, src.y + block_height / 2.0),
                (dst.x, dst.y + block_height / 2.0),
            ]
        };

        push_edge(src_idx, dst_idx, &path_points)?;
    }

    writeln!(buffer, "]")?;

    let mut file = fs::File::create(path)?;
    file.write_all(buffer.as_bytes())?;
    file.flush()?;
    Ok(())
}



fn dag_edges_strategy() -> impl Strategy<Value = Vec<GraphEdge>> {
    (4usize..=8).prop_flat_map(|node_count| {
        let max_edges = node_count * (node_count - 1) / 2;
        proptest::collection::vec(any::<bool>(), max_edges).prop_map(move |mask| {
            let mut edges = Vec::new();
            let mut bit = 0;
            for src in 0..node_count {
                for dst in (src + 1)..node_count {
                    if mask[bit] {
                        edges.push(GraphEdge {
                            source_id: format!("v{}", src),
                            target_id: format!("v{}", dst),
                            weight: 1.0,
                            edge_type: "test".into(),
                        });
                    }
                    bit += 1;
                }
            }

            if edges.is_empty() {
                for src in 0..(node_count - 1) {
                    edges.push(GraphEdge {
                        source_id: format!("v{}", src),
                        target_id: format!("v{}", src + 1),
                        weight: 1.0,
                        edge_type: "fallback".into(),
                    });
                }
            }

            edges
        })
    })
}

#[test]
fn random_dag_layout_preserves_partial_order() {
    let mut config = ProptestConfig::with_cases(20);
    config.failure_persistence = None;
    let mut runner = TestRunner::new(config);
    runner
        .run(&dag_edges_strategy(), |edges| {
            let options = default_options();
            let mut engine = HighPerformanceLayoutEngine::new(&options).expect("engine initialization");

            let runtime = Runtime::new().expect("tokio runtime");
            let result = runtime
                .block_on(engine.compute_layout(edges.clone(), &options))
                .expect("layout computation");

            let positions_vec = result.positions;
            let stats = result.statistics;
            let positions = position_map(&positions_vec);
            let edge_paths = edge_paths_from_metadata(&result.metadata.parameters);
            prop_assert_eq!(
                positions.len(),
                positions_vec.len(),
                "positions must stay unique"
            );

            let step_x = options.block_width + options.horizontal_gap;
            let step_y = options.block_height + options.vertical_gap;

            for pos in &positions_vec {
                let expected_x = pos.layer as f32 * step_x;
                let expected_y = pos.level as f32 * step_y;
                prop_assert!(
                    (pos.x - expected_x).abs() < 1e-3,
                    "x coordinate mismatch for {}: {} != {}",
                    pos.article_id,
                    pos.x,
                    expected_x
                );
                prop_assert!(
                    (pos.y - expected_y).abs() < 1e-3,
                    "y coordinate mismatch for {}: {} != {}",
                    pos.article_id,
                    pos.y,
                    expected_y
                );
            }

            let max_layer = positions_vec.iter().map(|pos| pos.layer).max().unwrap_or(0);
            prop_assert!(
                stats.longest_path_length as i32 <= max_layer + 1,
                "longest path length should not exceed used layers ({} <= {})",
                stats.longest_path_length,
                max_layer + 1
            );

            for edge in &edges {
                prop_assert!(
                    positions.contains_key(&edge.source_id),
                    "missing source vertex {}",
                    edge.source_id
                );
                prop_assert!(
                    positions.contains_key(&edge.target_id),
                    "missing target vertex {}",
                    edge.target_id
                );

                let src = positions.get(&edge.source_id).unwrap();
                let dst = positions.get(&edge.target_id).unwrap();

                prop_assert!(
                    dst.layer >= src.layer + 1,
                    "edge {} -> {} must advance at least one layer forward ({} -> {})",
                    edge.source_id,
                    edge.target_id,
                    src.layer,
                    dst.layer
                );

                let path = edge_paths
                    .get(&(edge.source_id.clone(), edge.target_id.clone()))
                    .expect("edge path missing");

                let start = path.first().unwrap();
                let end = path.last().unwrap();
                let expected_start = (src.x + options.block_width, src.y + options.block_height / 2.0);
                let expected_end = (dst.x, dst.y + options.block_height / 2.0);
                prop_assert!(
                    (start.0 - expected_start.0).abs() < 1e-3 && (start.1 - expected_start.1).abs() < 1e-3,
                    "edge {} -> {} start mismatch",
                    edge.source_id,
                    edge.target_id
                );
                prop_assert!(
                    (end.0 - expected_end.0).abs() < 1e-3 && (end.1 - expected_end.1).abs() < 1e-3,
                    "edge {} -> {} end mismatch",
                    edge.source_id,
                    edge.target_id
                );

                let gap = dst.layer - src.layer;
                prop_assert_eq!(
                    path.len(),
                    (gap + 1) as usize,
                    "edge {} -> {} path length mismatch",
                    edge.source_id,
                    edge.target_id
                );

                for window in path.windows(2) {
                    prop_assert!(
                        window[1].0 >= window[0].0 - 1e-3,
                        "edge {} -> {} should be monotonically increasing in X",
                        edge.source_id,
                        edge.target_id
                    );
                }
            }

            Ok(())
        })
        .expect("proptest execution");
}


#[tokio::test]
async fn layout_engine_exports_gml_snapshot() -> Result<()> {
    let options = default_options();
    let mut engine = HighPerformanceLayoutEngine::new(&options)?;
    let edges = sample_edges();

    let result = engine.compute_layout(edges.clone(), &options).await?;
    assert!(
        !result.positions.is_empty(),
        "layout computation should return positions"
    );

    let edge_paths = edge_paths_from_metadata(&result.metadata.parameters);
    let output_path = artifacts_path("test_graph.gml");
    write_gml(&result.positions, &edges, &edge_paths, options.block_width, options.block_height, &output_path)?;

    assert!(
        output_path.exists(),
        "expected GML file to be written at {}",
        output_path.display()
    );

    Ok(())
}

