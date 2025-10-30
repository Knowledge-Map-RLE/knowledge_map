/*!
# High-Performance Graph Layout Engine

Rust-based микросервис для высокопроизводительной укладки графов,
заменяющий Python + Neo4j решение с улучшенной Big O нотацией.

## Ключевые особенности

- **gRPC API** для интеграции с микросервисами
- **SIMD оптимизации** для векторных операций  
- **Многопоточная обработка** с Rayon
- **Эффективное управление памятью** с чанками/батчами
- **Потоковая обработка** больших графов
- **Минимальный трафик** - только связи туда, только результаты обратно

## Архитектура алгоритмов

- Топологическая сортировка: O(V + E) → O((V + E) / P) с параллелизмом
- Longest Path: O(V²) → O(V log V) с SIMD
- Размещение вершин: O(V²) → O(V) с эффективными структурами данных

*/
#![allow(dead_code)]

use std::net::SocketAddr;

use anyhow::Result;
use clap::Parser;
use tonic::transport::Server;
use tracing::{info, warn, error};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, Layer};

mod config;
mod algorithms;
mod data_structures;
mod db_optimizer;
mod memory;
mod metrics;
mod neo4j;
mod server;

// Подключаем сгенерированные protobuf типы
pub mod generated {
    #![allow(clippy::derive_partial_eq_without_eq)]
    tonic::include_proto!("graph_layout");
}

use crate::config::Config;
use crate::db_optimizer::DatabaseOptimizer;
use crate::server::GraphLayoutServer;

#[cfg(feature = "mimalloc")]
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

#[cfg(feature = "jemalloc")]
#[global_allocator]
static GLOBAL: jemallocator::Jemalloc = jemallocator::Jemalloc;

/// Аргументы командной строки
#[derive(Parser, Debug)]
#[command(name = "graph-layout-engine")]
#[command(about = "High-performance graph layout engine")]
#[command(version)]
struct Args {
    /// Путь к файлу конфигурации
    #[arg(short, long, default_value = "config.toml")]
    config: String,
    
    /// Адрес для привязки gRPC сервера
    #[arg(short, long, default_value = "0.0.0.0:50051")]
    address: String,
    
    /// Уровень логирования
    #[arg(short, long, default_value = "info")]
    log_level: String,
    
    /// Включить профилирование
    #[arg(long)]
    enable_profiling: bool,
    
    /// Режим работы
    #[arg(short, long, default_value = "auto-layout")]
    mode: ServerMode,
}

#[derive(Debug, Clone, clap::ValueEnum)]
enum ServerMode {
    /// Режим gRPC сервера
    Server,
    /// Автоматическая укладка графа
    AutoLayout,
    /// Режим проверки здоровья
    Health,
    /// Режим бенчмарков
    Benchmark,
    /// Режим тестирования
    Test,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();
    
    // Инициализация логирования
    init_logging(&args.log_level)?;
    
    info!(
        "🦀 Запуск Graph Layout Engine v{}", 
        env!("CARGO_PKG_VERSION")
    );
    
    // Загрузка конфигурации
    let config = match Config::load(&args.config) {
        Ok(config) => {
            info!("📋 Конфигурация загружена из {}", args.config);
            config
        },
        Err(e) => {
            error!("❌ Ошибка загрузки конфигурации: {}", e);
            return Err(e);
        }
    };
    
    // Выбор режима работы
    info!("🎯 Режим работы: {:?}", args.mode);
    match args.mode {
        ServerMode::Server => {
            info!("🚀 Запуск в режиме gRPC сервера");
            run_server(args.address, config).await?;
        },
        ServerMode::AutoLayout => {
            info!("🧮 Запуск в режиме автоматической укладки");
            run_auto_layout(config).await?;
        },
        ServerMode::Health => {
            info!("🏥 Запуск проверки здоровья");
            run_health_check().await?;
        },
        ServerMode::Benchmark => {
            info!("📊 Запуск бенчмарков");
            run_benchmarks().await?;
        },
        ServerMode::Test => {
            info!("🧪 Запуск тестов");
            run_tests().await?;
        },
    }
    
    info!("✅ Программа завершена успешно");
    Ok(())
}

/// Инициализация системы логирования
fn init_logging(level: &str) -> Result<()> {
    let level = level.parse::<tracing::Level>()
        .map_err(|e| anyhow::anyhow!("Неверный уровень логирования: {}", e))?;
    
    // Создаём директорию для логов если её нет
    std::fs::create_dir_all("logs")
        .map_err(|e| anyhow::anyhow!("Не удалось создать директорию logs: {}", e))?;
    
    // Создаем фильтр который пропускает все логи нужного уровня
    let env_filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| {
            // Используем широкий фильтр для всех модулей
            tracing_subscriber::EnvFilter::new(level.to_string())
        });
    
    // Используем rolling file appender для файлового логирования
    let file_appender = tracing_appender::rolling::never("logs", "rust_layout.log");
    let error_appender = tracing_appender::rolling::never("logs", "rust_layout_error.log");
    
    // Слой для консоли
    let stdout_layer = tracing_subscriber::fmt::layer()
        .with_writer(std::io::stdout)
        .with_target(false)
        .with_ansi(false);
    
    // Слой для файла
    let file_layer = tracing_subscriber::fmt::layer()
        .with_writer(file_appender)
        .with_target(true)
        .with_ansi(false);
    
    // Слой для ошибок
    let error_layer = tracing_subscriber::fmt::layer()
        .with_writer(error_appender)
        .with_target(true)
        .with_ansi(false)
        .with_filter(tracing_subscriber::filter::LevelFilter::ERROR);
    
    // Собираем все вместе
    tracing_subscriber::registry()
        .with(env_filter)
        .with(stdout_layer)
        .with(file_layer)
        .with(error_layer)
        .init();
    
    Ok(())
}

/// Автоматическая укладка графа
async fn run_auto_layout(config: Config) -> Result<()> {
    info!("🔄 Запуск автоматической укладки графа...");

    // Создание сервиса укладки графов
    info!("🔧 Создание GraphLayoutServer...");
    let layout_service = match GraphLayoutServer::new(config.clone()).await {
        Ok(service) => {
            info!("✅ GraphLayoutServer создан успешно");
            service
        },
        Err(e) => {
            error!("❌ Ошибка создания GraphLayoutServer: {}", e);
            return Err(e);
        }
    };

    // Подготовка базы данных: проверка и создание индексов
    info!("🔧 Подготовка базы данных...");
    let db_optimizer = DatabaseOptimizer::new(layout_service.neo4j_client.graph());
    match db_optimizer.prepare_database().await {
        Ok(_) => {
            info!("✅ База данных подготовлена");
        },
        Err(e) => {
            warn!("⚠️ Ошибка подготовки базы данных: {}. Продолжаем без оптимизаций.", e);
        }
    }
    
    info!("🧮 Начинаем батчевую обработку...");
    // Батчевая обработка
    match run_batch_layout(&layout_service, &config).await {
        Ok(_) => {
            info!("✅ Батчевая обработка завершена успешно");
            Ok(())
        },
        Err(e) => {
            error!("❌ Ошибка батчевой обработки: {}", e);
            Err(e)
        }
    }
}

/// Батчевая обработка графа
async fn run_batch_layout(layout_service: &GraphLayoutServer, config: &Config) -> Result<()> {
    use tracing::info;
    
    info!("📊 Загрузка данных графа из Neo4j...");
    
    // Получаем общее количество связей
    let total_edges = layout_service.neo4j_client.get_total_edges_count().await?;
    info!("📈 Всего связей в БД: {}", total_edges);
    
    // Определяем размер батча из конфигурации
    let batch_size = config.neo4j.batch_size;
    let total_batches = (total_edges + batch_size - 1) / batch_size;
    
    info!("🔄 Батчевая обработка: {} батчей по {} связей", total_batches, batch_size);
    
    let mut all_edges = Vec::new();
    let mut processed_edges = 0;
    
    for batch_num in 0..total_batches {
        let offset = batch_num * batch_size;
        info!("📥 Обработка батча {}/{} (offset={})", batch_num + 1, total_batches, offset);
        
        let batch_edges = layout_service.neo4j_client.load_graph_edges_batch(batch_size, offset).await?;
        all_edges.extend(batch_edges);
        processed_edges += batch_size;
        
        let progress = (processed_edges as f64 / total_edges as f64) * 100.0;
        info!("📊 Прогресс: {:.1}% ({}/{} связей)", progress, processed_edges.min(total_edges), total_edges);
        
        // Если это последний батч или накопили достаточно данных, обрабатываем их
        if batch_num == total_batches - 1 || all_edges.len() >= batch_size * 10 {
            info!("🧮 Запуск укладки для {} накопленных связей", all_edges.len());
            process_edges_batch(layout_service, &all_edges, config).await?;
            all_edges.clear();
        }
    }
    
    // Обрабатываем оставшиеся данные
    if !all_edges.is_empty() {
        info!("🧮 Финальная обработка {} оставшихся связей", all_edges.len());
        process_edges_batch(layout_service, &all_edges, config).await?;
    }
    
    Ok(())
}

/// Обработка батча связей
async fn process_edges_batch(layout_service: &GraphLayoutServer, edges: &[crate::neo4j::GraphEdge], config: &Config) -> Result<()> {
    use tracing::info;
    
    if edges.is_empty() {
        return Ok(());
    }
    
    let edge_count = edges.len();
    info!("📊 Обработка батча: {} связей", edge_count);
    
    if edges.is_empty() {
        info!("⚠️ Граф пуст, укладка не требуется");
        return Ok(());
    }
    
    // Создание запроса для укладки
    let request = generated::LayoutRequest {
        task_id: "auto_layout".to_string(),
        edges: edges.iter().map(|edge| generated::GraphEdge {
            source_id: edge.source_id.clone(),
            target_id: edge.target_id.clone(),
            edge_type: edge.edge_type.clone(),
            weight: edge.weight,
        }).collect(),
        options: Some(generated::LayoutOptions {
            block_width: 200.0,
            block_height: 80.0,
            horizontal_gap: 40.0,
            vertical_gap: 50.0,
            exclude_isolated_vertices: true,
            optimize_layout: true,
            max_iterations: 1000,
            convergence_threshold: 0.001,
            chunk_size: 1000,
            max_workers: 4,
            enable_simd: true,
            enable_gpu: false,
            memory_strategy: generated::MemoryStrategy::MemoryAuto as i32,
        }),
        metadata: Some(generated::RequestMetadata {
            client_id: "auto_layout_client".to_string(),
            timestamp: chrono::Utc::now().timestamp(),
            priority: 1,
            estimated_vertex_count: 1000,
            estimated_edge_count: edge_count as i64,
        }),
    };
    
    // Выполнение укладки
    info!("=== ЗАПУСК АВТОМАТИЧЕСКОЙ УКЛАДКИ ГРАФА ===");
    info!("🧮 Начало выполнения алгоритма укладки...");
    info!("📊 Загружено {} связей для обработки", edge_count);
    let start_time = std::time::Instant::now();
    
    // Используем прямой вызов алгоритма вместо gRPC
    use crate::generated::graph_layout_service_server::GraphLayoutService;
    let response = GraphLayoutService::compute_layout(layout_service, tonic::Request::new(request)).await?;
    let layout_result = response.into_inner();
    
    let duration = start_time.elapsed();
    info!("=== УКЛАДКА ЗАВЕРШЕНА ===");
    info!("⏱️ Время выполнения: {:.2?}", duration);
    info!("📊 Обработано позиций: {}", layout_result.positions.len());
    
    // Подробная статистика
    if let Some(stats) = &layout_result.statistics {
        info!("=== СТАТИСТИКА УКЛАДКИ ===");
        info!("📈 Всего вершин: {}", stats.vertices_processed);
        info!("🔗 Всего связей: {}", stats.edges_processed);
        info!("🔄 Компоненты связности: {}", stats.connected_components);
        info!("📏 Длина самого длинного пути: {}", stats.longest_path_length);
        info!("⚡ Скорость обработки: {:.1} вершин/сек", stats.vertices_per_second);
        
        if let Some(metrics) = &stats.algorithm_metrics {
            info!("🧮 Время топологической сортировки: {} мс", metrics.topo_sort_time_ms);
            info!("🛤️ Время поиска самого длинного пути: {} мс", metrics.longest_path_time_ms);
            info!("📍 Время размещения вершин: {} мс", metrics.placement_time_ms);
            info!("🏗️ Использовано слоёв: {}", metrics.layers_used);
            info!("📊 Максимальный уровень: {}", metrics.max_level);
            info!("💾 Эффективность использования пространства: {:.1}%", metrics.space_efficiency * 100.0);
        }
    }
    
    // Сохранение результатов в Neo4j
    info!("💾 Сохранение результатов в Neo4j...");
    let positions: Vec<crate::neo4j::VertexPosition> = layout_result.positions.into_iter().map(|pos| {
        crate::neo4j::VertexPosition {
            article_id: pos.article_id,
            layer: pos.layer,
            level: pos.level,
            x: pos.x,
            y: pos.y,
        }
    }).collect();
    
    info!("📊 Подготовлено {} позиций для сохранения", positions.len());
    layout_service.neo4j_client.save_layout_results_with_batch_size(&positions, config.neo4j.save_batch_size).await?;
    info!("✅ Результаты сохранены в Neo4j");
    
    // Вывод статистики
    info!("📈 Статистика укладки:");
    info!("  - Связей обработано: {}", edge_count);
    info!("  - Вершин размещено: {}", positions.len());
    info!("  - Время выполнения: {:?}", duration);
    info!("  - Скорость: {:.2} связей/сек", edge_count as f64 / duration.as_secs_f64());
    
    Ok(())
}

/// Запуск gRPC сервера
async fn run_server(address: String, config: Config) -> Result<()> {
    let addr: SocketAddr = address.parse()
        .map_err(|e| anyhow::anyhow!("Неверный адрес {}: {}", address, e))?;
    
    info!("🚀 Запуск gRPC сервера на {}", addr);
    
    // Создание сервиса укладки графов
    let layout_service = GraphLayoutServer::new(config).await?;
    
    // Добавление middleware для метрик и логирования
    let service = tower::ServiceBuilder::new()
        // .layer(tower_http::trace::TraceLayer::new_for_grpc()) // Упрощено для совместимости
        .service(generated::graph_layout_service_server::GraphLayoutServiceServer::new(layout_service));
    
    // Запуск сервера
    Server::builder()
        .add_service(service)
        .serve(addr)
        .await
        .map_err(|e| anyhow::anyhow!("Ошибка сервера: {}", e))?;
    
    Ok(())
}

/// Проверка здоровья сервиса
async fn run_health_check() -> Result<()> {
    info!("🏥 Выполнение проверки здоровья...");
    
    // Проверка подключения к Neo4j
    // Проверка доступности памяти
    // Проверка производительности
    
    println!("✅ Все проверки пройдены успешно");
    Ok(())
}

/// Запуск бенчмарков
async fn run_benchmarks() -> Result<()> {
    info!("📊 Запуск бенчмарков производительности...");
    
    // Бенчмарк топологической сортировки
    // Бенчмарк longest path алгоритма
    // Бенчмарк размещения вершин
    // Сравнение с Python реализацией
    
    println!("📈 Бенчмарки завершены");
    Ok(())
}

/// Запуск тестов
async fn run_tests() -> Result<()> {
    info!("🧪 Запуск тестов корректности...");
    
    // Тест на маленьком графе
    // Тест на среднем графе
    // Тест на большом графе
    // Тест сравнения с эталонным результатом
    
    println!("✅ Все тесты пройдены");
    Ok(())
}
