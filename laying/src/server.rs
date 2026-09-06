/*!
# gRPC сервер для высокопроизводительной укладки графов

Принимает рёбра графа → возвращает координаты вершин.
Никакой работы с БД: все данные передаются в запросе.
*/

use crate::config::Config;
use crate::algorithms::{HighPerformanceLayoutEngine, LayoutAlgorithm};
use crate::neo4j::{GraphEdge as Neo4jGraphEdge};
use crate::generated::{
    graph_layout_service_server::GraphLayoutService,
    LayoutRequest, LayoutResponse, LayoutChunk,
    HealthRequest, HealthResponse, MetricsRequest, MetricsResponse,
    ResponseMetadata, OptimizationFlags,
    SystemMetrics,
};
use crate::metrics::MetricsCollector;

use anyhow::Result;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::sync::RwLock;
use tokio_stream::wrappers::ReceiverStream;
use tonic::{Request, Response, Status};
use tracing::{info, error, instrument};
use uuid::Uuid;

/// gRPC сервер для укладки графов
pub struct GraphLayoutServer {
    /// Конфигурация сервиса
    config: Config,

    /// Алгоритм укладки
    layout_engine: Arc<RwLock<HighPerformanceLayoutEngine>>,

    /// Сборщик метрик
    metrics: Arc<MetricsCollector>,

    /// ID сервера
    server_id: String,

    /// Время запуска
    startup_time: SystemTime,
}

impl GraphLayoutServer {
    pub async fn new(config: Config) -> Result<Self> {
        info!("🔧 Инициализация GraphLayoutServer...");

        let default_options = crate::generated::LayoutOptions {
            block_width: config.algorithms.block_width,
            block_height: config.algorithms.block_height,
            horizontal_gap: config.algorithms.horizontal_gap,
            vertical_gap: config.algorithms.vertical_gap,
            exclude_isolated_vertices: config.algorithms.exclude_isolated_vertices,
            optimize_layout: true,
            max_iterations: config.algorithms.max_iterations as i32,
            convergence_threshold: config.algorithms.convergence_threshold,
            chunk_size: config.performance.chunk_size as i32,
            max_workers: config.performance.worker_threads as i32,
            enable_simd: config.performance.enable_simd,
            enable_gpu: config.performance.enable_gpu,
            memory_strategy: crate::generated::MemoryStrategy::MemoryAuto as i32,
            convert_to_dag: true,
        };

        let layout_engine = HighPerformanceLayoutEngine::new(&default_options)?;
        let metrics = MetricsCollector::new(&config.metrics)?;
        let server_id = Uuid::new_v4().to_string();

        info!("✅ GraphLayoutServer инициализирован (ID: {})", server_id);

        Ok(Self {
            config,
            layout_engine: Arc::new(RwLock::new(layout_engine)),
            metrics: Arc::new(metrics),
            server_id,
            startup_time: SystemTime::now(),
        })
    }

    fn create_response_metadata(&self, used_optimizations: &[String]) -> ResponseMetadata {
        ResponseMetadata {
            server_id: self.server_id.clone(),
            algorithm_version: env!("CARGO_PKG_VERSION").to_string(),
            completion_timestamp: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs() as i64,
            used_memory_strategy: crate::generated::MemoryStrategy::MemoryAuto as i32,
            optimization_flags: Some(OptimizationFlags {
                simd_used: used_optimizations.contains(&"SIMD".to_string()),
                gpu_used: used_optimizations.contains(&"GPU".to_string()),
                multi_threading_used: used_optimizations.contains(&"Parallel Processing".to_string()),
                memory_mapping_used: used_optimizations.contains(&"Memory Mapping".to_string()),
                vectorization_used: used_optimizations.contains(&"Vectorization".to_string()),
            }),
        }
    }

    async fn get_system_metrics(&self) -> SystemMetrics {
        let uptime = self.startup_time
            .elapsed()
            .unwrap_or_default()
            .as_secs() as i64;

        SystemMetrics {
            cpu_usage: self.metrics.get_cpu_usage().await,
            memory_usage_bytes: self.metrics.get_memory_usage().await as i64,
            memory_available_bytes: self.metrics.get_available_memory().await as i64,
            active_tasks: self.metrics.get_active_tasks().await as i32,
            uptime_seconds: uptime,
        }
    }
}

#[tonic::async_trait]
impl GraphLayoutService for GraphLayoutServer {
    #[instrument(skip(self, request))]
    async fn compute_layout(
        &self,
        request: Request<LayoutRequest>,
    ) -> Result<Response<LayoutResponse>, Status> {
        let req = request.into_inner();
        info!("🎯 Обработка запроса укладки (ID: {}, рёбер: {})", req.task_id, req.edges.len());

        let start_time = std::time::Instant::now();
        self.metrics.increment_active_tasks().await;

        let result = async {
            if req.edges.is_empty() {
                return Err(anyhow::anyhow!("Запрос не содержит рёбер"));
            }

            // Подсчёт уникальных вершин на входе
            let mut vertex_set: std::collections::HashSet<String> = std::collections::HashSet::new();
            for e in &req.edges {
                vertex_set.insert(e.source_id.clone());
                vertex_set.insert(e.target_id.clone());
            }
            info!(
                "LAYOUT_IN | Вершин: {}, рёбер: {}",
                vertex_set.len(),
                req.edges.len()
            );

            let options = req.options.unwrap_or_else(|| crate::generated::LayoutOptions {
                block_width: self.config.algorithms.block_width,
                block_height: self.config.algorithms.block_height,
                horizontal_gap: self.config.algorithms.horizontal_gap,
                vertical_gap: self.config.algorithms.vertical_gap,
                exclude_isolated_vertices: self.config.algorithms.exclude_isolated_vertices,
                optimize_layout: true,
                max_iterations: self.config.algorithms.max_iterations as i32,
                convergence_threshold: self.config.algorithms.convergence_threshold,
                chunk_size: self.config.performance.chunk_size as i32,
                max_workers: self.config.performance.worker_threads as i32,
                enable_simd: self.config.performance.enable_simd,
                enable_gpu: self.config.performance.enable_gpu,
                memory_strategy: crate::generated::MemoryStrategy::MemoryAuto as i32,
                convert_to_dag: true,
            });

            let neo4j_edges: Vec<Neo4jGraphEdge> = req.edges.into_iter().map(|e| Neo4jGraphEdge {
                source_id: e.source_id,
                target_id: e.target_id,
                weight: e.weight,
                edge_type: e.edge_type,
            }).collect();

            let mut layout_engine = self.layout_engine.write().await;
            let layout_result = layout_engine.compute_layout(neo4j_edges, &options).await?;

            let metadata = self.create_response_metadata(&layout_result.metadata.optimizations_used);

            let response_positions: Vec<crate::generated::VertexPosition> = layout_result.positions
                .into_iter()
                .map(|p| crate::generated::VertexPosition {
                    article_id: p.article_id,
                    layer: p.layer,
                    level: p.level,
                    x: p.x,
                    y: p.y,
                    status: crate::generated::VertexStatus::StatusPlaced as i32,
                })
                .collect();

            Ok::<_, anyhow::Error>(LayoutResponse {
                success: true,
                error_message: String::new(),
                positions: response_positions,
                statistics: Some(layout_result.statistics),
                metadata: Some(metadata),
            })
        }.await;

        self.metrics.decrement_active_tasks().await;

        let total_time = start_time.elapsed();

        match result {
            Ok(response) => {
                let layers = response.positions.iter().map(|p| p.layer).max().unwrap_or(0) + 1;
                let levels = response.positions.iter().map(|p| p.level).max().unwrap_or(0) + 1;
                info!(
                    "LAYOUT_OUT | Слоёв: {}, уровней: {}, позиций: {} (за {:.2}с)",
                    layers, levels, response.positions.len(), total_time.as_secs_f64()
                );
                info!(
                    "✅ Укладка завершена за {:.2}с ({} позиций, ID: {})",
                    total_time.as_secs_f64(),
                    response.positions.len(),
                    req.task_id
                );
                self.metrics.record_successful_layout(total_time).await;
                Ok(Response::new(response))
            }
            Err(e) => {
                error!(
                    "❌ Ошибка укладки: {} (ID: {}, время: {:.2}с)",
                    e, req.task_id, total_time.as_secs_f64()
                );
                self.metrics.record_failed_layout(total_time).await;
                Ok(Response::new(LayoutResponse {
                    success: false,
                    error_message: e.to_string(),
                    positions: vec![],
                    statistics: None,
                    metadata: Some(self.create_response_metadata(&[])),
                }))
            }
        }
    }

    type ComputeLayoutStreamingStream = ReceiverStream<Result<LayoutChunk, Status>>;

    #[instrument(skip(self, request))]
    async fn compute_layout_streaming(
        &self,
        request: Request<LayoutRequest>,
    ) -> Result<Response<Self::ComputeLayoutStreamingStream>, Status> {
        let req = request.into_inner();
        info!("🌊 Потоковый запрос укладки (ID: {})", req.task_id);

        let (tx, rx) = tokio::sync::mpsc::channel(32);

        tokio::spawn(async move {
            if let Err(e) = tx.send(Err(Status::unimplemented(
                "Потоковая обработка будет реализована в следующей версии"
            ))).await {
                error!("Ошибка отправки потокового ответа: {}", e);
            }
        });

        Ok(Response::new(ReceiverStream::new(rx)))
    }

    #[instrument(skip(self, _request))]
    async fn get_health(
        &self,
        _request: Request<HealthRequest>,
    ) -> Result<Response<HealthResponse>, Status> {
        let system_metrics = self.get_system_metrics().await;
        let memory_ok = system_metrics.memory_available_bytes > 0
            && system_metrics.memory_usage_bytes < (system_metrics.memory_available_bytes * 9 / 10);

        let status = if memory_ok {
            crate::generated::health_response::ServingStatus::Serving
        } else {
            crate::generated::health_response::ServingStatus::NotServing
        };

        Ok(Response::new(HealthResponse {
            status: status as i32,
            message: if memory_ok {
                "Сервис работает нормально".to_string()
            } else {
                "Недостаточно памяти".to_string()
            },
            system_metrics: Some(system_metrics),
        }))
    }

    #[instrument(skip(self, _request))]
    async fn get_metrics(
        &self,
        _request: Request<MetricsRequest>,
    ) -> Result<Response<MetricsResponse>, Status> {
        let metrics = self.metrics.get_prometheus_metrics().await;
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;

        Ok(Response::new(MetricsResponse {
            metrics,
            collection_timestamp: timestamp,
        }))
    }
}

impl Clone for GraphLayoutServer {
    fn clone(&self) -> Self {
        Self {
            config: self.config.clone(),
            layout_engine: Arc::clone(&self.layout_engine),
            metrics: Arc::clone(&self.metrics),
            server_id: self.server_id.clone(),
            startup_time: self.startup_time,
        }
    }
}
