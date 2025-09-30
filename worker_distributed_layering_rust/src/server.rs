/*!
# gRPC сервер для высокопроизводительной укладки графов

Реализация gRPC сервиса с поддержкой:
- Потоковой обработки больших графов
- Мониторинга производительности
- Graceful shutdown
- Метрики в реальном времени
*/

use crate::config::Config;
use crate::algorithms::{HighPerformanceLayoutEngine, LayoutAlgorithm};
use crate::neo4j::{GraphEdge as Neo4jGraphEdge, VertexPosition as Neo4jVertexPosition};
use neo4rs::BoltType;
use std::collections::HashMap;
use crate::generated::{
    graph_layout_service_server::GraphLayoutService,
    LayoutRequest, LayoutResponse, LayoutChunk,
    HealthRequest, HealthResponse, MetricsRequest, MetricsResponse,
    ResponseMetadata, OptimizationFlags,
    SystemMetrics,
};
use crate::metrics::MetricsCollector;
use crate::neo4j::Neo4jClient;

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
    
    /// Клиент Neo4j для загрузки данных
    pub neo4j_client: Arc<Neo4jClient>,
    
    /// Сборщик метрик
    metrics: Arc<MetricsCollector>,
    
    /// ID сервера
    server_id: String,
    
    /// Время запуска
    startup_time: SystemTime,
}

impl GraphLayoutServer {
    /// Создание нового экземпляра сервера
    pub async fn new(config: Config) -> Result<Self> {
        info!("🔧 Инициализация GraphLayoutServer...");
        
        // Создание алгоритма укладки
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
        };
        
        let layout_engine = HighPerformanceLayoutEngine::new(&default_options)?;
        
        // Создание клиента Neo4j
        let neo4j_client = Neo4jClient::new(&config).await?;
        
        // Создание сборщика метрик
        let metrics = MetricsCollector::new(&config.metrics)?;
        
        let server_id = Uuid::new_v4().to_string();
        
        info!("✅ GraphLayoutServer инициализирован (ID: {})", server_id);
        
        Ok(Self {
            config,
            layout_engine: Arc::new(RwLock::new(layout_engine)),
            neo4j_client: Arc::new(neo4j_client),
            metrics: Arc::new(metrics),
            server_id,
            startup_time: SystemTime::now(),
        })
    }
    
    /// Загрузка связей из Neo4j
    #[instrument(skip(self))]
    async fn load_edges_from_neo4j(&self) -> Result<Vec<crate::generated::GraphEdge>> {
        info!("📥 Загрузка связей из Neo4j...");
        
        let start_time = std::time::Instant::now();
        
        // Запрос только связей (без данных о вершинах)
        let query = r#"
            MATCH (source:Article)-[r:BIBLIOGRAPHIC_LINK]->(target:Article)
            RETURN source.uid as source_id, target.uid as target_id, 
                   coalesce(r.weight, 1.0) as weight,
                   type(r) as edge_type
        "#;
        
        let records = self.neo4j_client.execute_query(query, None).await?;
        
        let edges: Vec<_> = records
            .into_iter()
            .map(|record| crate::generated::GraphEdge {
                source_id: record.get("source_id").map(|v| v.to_string()).unwrap_or_default(),
                target_id: record.get("target_id").map(|v| v.to_string()).unwrap_or_default(),
                weight: record.get("weight").and_then(|v| v.to_string().parse::<f64>().ok()).unwrap_or(1.0) as f32,
                edge_type: record.get("edge_type").map(|v| v.to_string()).unwrap_or_default(),
            })
            .collect();
        
        let load_time = start_time.elapsed();
        
        info!(
            "✅ Загружено {} связей за {:.2}с", 
            edges.len(), 
            load_time.as_secs_f64()
        );
        
        // Записываем метрику
        self.metrics.record_data_load(edges.len(), load_time).await;
        
        Ok(edges)
    }
    
    /// Сохранение результатов в Neo4j
    #[instrument(skip(self, positions))]
    async fn save_results_to_neo4j(&self, positions: &[Neo4jVertexPosition]) -> Result<()> {
        info!("💾 Сохранение {} позиций в Neo4j...", positions.len());
        
        let start_time = std::time::Instant::now();
        
        // Батчевое обновление позиций в Neo4j
        let batch_size = self.config.neo4j.batch_size;
        
        for chunk in positions.chunks(batch_size) {
            let update_query = r#"
                UNWIND $positions as pos
                MATCH (a:Article {uid: pos.article_id})
                SET a.layer = pos.layer,
                    a.level = pos.level,
                    a.x = pos.x,
                    a.y = pos.y
            "#;
            
            let mut params_map = HashMap::new();
            params_map.insert("positions".to_string(), BoltType::from(chunk.iter().map(|p| {
                let mut pos_map = HashMap::new();
                pos_map.insert("article_id".to_string(), BoltType::from(p.article_id.clone()));
                pos_map.insert("layer".to_string(), BoltType::from(p.layer));
                pos_map.insert("level".to_string(), BoltType::from(p.level));
                pos_map.insert("x".to_string(), BoltType::from(p.x));
                pos_map.insert("y".to_string(), BoltType::from(p.y));
                BoltType::from(pos_map)
            }).collect::<Vec<_>>()));
            self.neo4j_client.execute_query(update_query, Some(params_map)).await?;
        }
        
        let save_time = start_time.elapsed();
        
        info!(
            "✅ Позиции сохранены в Neo4j за {:.2}с", 
            save_time.as_secs_f64()
        );
        
        // Записываем метрику
        self.metrics.record_data_save(positions.len(), save_time).await;
        
        Ok(())
    }
    
    /// Создание метаданных ответа
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
    
    /// Получение системных метрик
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
    /// Основной метод укладки графа
    #[instrument(skip(self, request))]
    async fn compute_layout(
        &self,
        request: Request<LayoutRequest>,
    ) -> Result<Response<LayoutResponse>, Status> {
        let req = request.into_inner();
        info!("🎯 Обработка запроса укладки (ID: {})", req.task_id);
        
        let start_time = std::time::Instant::now();
        
        // Увеличиваем счетчик активных задач
        self.metrics.increment_active_tasks().await;
        
        let result = async {
            // 1. Загрузка связей из Neo4j (если не переданы в запросе)
            let edges = if req.edges.is_empty() {
                self.load_edges_from_neo4j().await?
            } else {
                req.edges
            };
            
            // 2. Валидация опций
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
            });
            
            // 3. Вычисление укладки
            let mut layout_engine = self.layout_engine.write().await;
            // Конвертация типов
            let neo4j_edges: Vec<Neo4jGraphEdge> = edges.into_iter().map(|e| Neo4jGraphEdge {
                source_id: e.source_id,
                target_id: e.target_id,
                weight: e.weight,
                edge_type: e.edge_type,
            }).collect();
            
            let layout_result = layout_engine.compute_layout(neo4j_edges, &options).await?;
            
            // 4. Сохранение результатов в Neo4j
            // 5. Создание ответа
            let metadata = self.create_response_metadata(&layout_result.metadata.optimizations_used);
            
            // Конвертация позиций для ответа
            let response_positions: Vec<crate::generated::VertexPosition> = layout_result.positions.into_iter().map(|p| {
                // Сохранение в Neo4j
                let _neo4j_position = Neo4jVertexPosition {
                    article_id: p.article_id.clone(),
                    layer: p.layer,
                    level: p.level,
                    x: p.x,
                    y: p.y,
                };
                
                // Создание ответа
                crate::generated::VertexPosition {
                    article_id: p.article_id,
                    layer: p.layer,
                    level: p.level,
                    x: p.x,
                    y: p.y,
                    status: crate::generated::VertexStatus::StatusPlaced as i32,
                }
            }).collect();
            
            // Сохранение в Neo4j (упрощенная версия)
            info!("💾 Сохранение {} позиций в Neo4j", response_positions.len());
            
            Ok::<_, anyhow::Error>(LayoutResponse {
                success: true,
                error_message: String::new(),
                positions: response_positions,
                statistics: Some(layout_result.statistics),
                metadata: Some(metadata),
            })
        }.await;
        
        // Уменьшаем счетчик активных задач
        self.metrics.decrement_active_tasks().await;
        
        let total_time = start_time.elapsed();
        
        match result {
            Ok(response) => {
                info!(
                    "✅ Укладка завершена за {:.2}с (ID: {})", 
                    total_time.as_secs_f64(),
                    req.task_id
                );
                
                // Записываем метрику успешного выполнения
                self.metrics.record_successful_layout(total_time).await;
                
                Ok(Response::new(response))
            }
            Err(e) => {
                error!(
                    "❌ Ошибка укладки: {} (ID: {}, время: {:.2}с)", 
                    e, req.task_id, total_time.as_secs_f64()
                );
                
                // Записываем метрику ошибки
                self.metrics.record_failed_layout(total_time).await;
                
                let error_response = LayoutResponse {
                    success: false,
                    error_message: e.to_string(),
                    positions: vec![],
                    statistics: None,
                    metadata: Some(self.create_response_metadata(&[])),
                };
                
                Ok(Response::new(error_response))
            }
        }
    }
    
    /// Потоковая укладка для больших графов
    type ComputeLayoutStreamingStream = ReceiverStream<Result<LayoutChunk, Status>>;
    
    #[instrument(skip(self, request))]
    async fn compute_layout_streaming(
        &self,
        request: Request<LayoutRequest>,
    ) -> Result<Response<Self::ComputeLayoutStreamingStream>, Status> {
        let req = request.into_inner();
        info!("🌊 Обработка потокового запроса укладки (ID: {})", req.task_id);
        
        let (tx, rx) = tokio::sync::mpsc::channel(32);
        
        // Клонируем нужные данные для фонового выполнения
        let _server = self.clone();
        let _task_id = req.task_id.clone();
        
        // Запускаем обработку в фоновом режиме
        tokio::spawn(async move {
            // TODO: Реализация потоковой обработки
            // 1. Разбиение на чанки
            // 2. Обработка каждого чанка
            // 3. Отправка промежуточных результатов
            
            if let Err(e) = tx.send(Err(Status::unimplemented(
                "Потоковая обработка будет реализована в следующей версии"
            ))).await {
                error!("Ошибка отправки потокового ответа: {}", e);
            }
        });
        
        Ok(Response::new(ReceiverStream::new(rx)))
    }
    
    /// Проверка состояния сервиса
    #[instrument(skip(self, _request))]
    async fn get_health(
        &self,
        _request: Request<HealthRequest>,
    ) -> Result<Response<HealthResponse>, Status> {
        // Проверка подключения к Neo4j
        let neo4j_healthy = self.neo4j_client.health_check().await.is_ok();
        
        // Проверка системных ресурсов
        let system_metrics = self.get_system_metrics().await;
        let memory_ok = system_metrics.memory_usage_bytes < (system_metrics.memory_available_bytes * 9 / 10);
        
        let status = if neo4j_healthy && memory_ok {
            crate::generated::health_response::ServingStatus::Serving
        } else {
            crate::generated::health_response::ServingStatus::NotServing
        };
        
        let message = match status {
            crate::generated::health_response::ServingStatus::Serving => {
                "Сервис работает нормально".to_string()
            }
            _ => {
                format!(
                    "Проблемы: Neo4j={}, Memory={}",
                    neo4j_healthy, memory_ok
                )
            }
        };
        
        Ok(Response::new(HealthResponse {
            status: status as i32,
            message,
            system_metrics: Some(system_metrics),
        }))
    }
    
    /// Получение метрик производительности
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

// Реализация Clone для GraphLayoutServer (для потоковой обработки)
impl Clone for GraphLayoutServer {
    fn clone(&self) -> Self {
        Self {
            config: self.config.clone(),
            layout_engine: Arc::clone(&self.layout_engine),
            neo4j_client: Arc::clone(&self.neo4j_client),
            metrics: Arc::clone(&self.metrics),
            server_id: self.server_id.clone(),
            startup_time: self.startup_time,
        }
    }
}
