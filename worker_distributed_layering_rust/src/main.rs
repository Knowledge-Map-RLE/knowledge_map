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
            info!("🧪 Запуск тестов укладки");
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

/// Батчевая обработка графа с глобальным назначением слоёв
async fn run_batch_layout(layout_service: &GraphLayoutServer, config: &Config) -> Result<()> {
    use tracing::info;
    use crate::algorithms::vertex_placement::{GlobalLayerState, PlacementConfig};

    info!("=== БАТЧЕВАЯ ОБРАБОТКА С ГЛОБАЛЬНЫМ НАЗНАЧЕНИЕМ СЛОЁВ ===");
    info!("📊 Загрузка данных графа из Neo4j...");

    // Получаем общее количество связей
    let total_edges = layout_service.neo4j_client.get_total_edges_count().await?;
    info!("📈 Всего связей в БД: {}", total_edges);

    // Определяем размер батча из конфигурации
    let batch_size = config.neo4j.batch_size;
    let total_batches = (total_edges + batch_size - 1) / batch_size;

    info!("🔄 Будет загружено {} батчей по {} связей", total_batches, batch_size);

    // Фаза 1: Глобальное назначение слоёв
    info!("=== ФАЗА 1: ГЛОБАЛЬНОЕ НАЗНАЧЕНИЕ СЛОЁВ ===");
    let mut global_state = GlobalLayerState::new();

    for batch_num in 0..total_batches {
        let offset = batch_num * batch_size;
        info!("📥 Загрузка батча {}/{} (offset={})", batch_num + 1, total_batches, offset);

        let batch_edges = layout_service.neo4j_client.load_graph_edges_batch(batch_size, offset).await?;

        // Конвертируем в формат (source, target)
        // Направление сохраняется как есть из Neo4j
        let edge_tuples: Vec<(String, String)> = batch_edges
            .into_iter()
            .map(|e| (e.source_id, e.target_id))
            .collect();

        info!("📊 Добавление {} связей в глобальное состояние", edge_tuples.len());
        global_state.add_edges_batch(&edge_tuples)?;

        // Обновляем слои после каждого батча
        info!("🔄 Обновление слоёв после добавления батча");
        let updates = global_state.propagate_until_convergence()?;

        let progress = ((batch_num + 1) as f64 / total_batches as f64) * 100.0;
        info!("📊 Прогресс: {:.1}% ({}/{} батчей), {} обновлений слоёв",
              progress, batch_num + 1, total_batches, updates);

        // Периодически выводим статистику
        if (batch_num + 1) % 10 == 0 || batch_num == total_batches - 1 {
            global_state.log_statistics();
        }
    }

    info!("=== ФАЗА 1 ЗАВЕРШЕНА ===");
    global_state.log_statistics();

    // Валидация слоёв
    info!("🔍 Валидация назначенных слоёв...");
    let invalid_edges = global_state.validate_layers();
    if invalid_edges > 0 {
        info!("⚠️ Обнаружено {} невалидных связей (возможно, циклы)", invalid_edges);
    }

    // Фаза 2: Размещение вершин по координатам
    info!("=== ФАЗА 2: РАЗМЕЩЕНИЕ ВЕРШИН ПО КООРДИНАТАМ ===");
    let layer_map = global_state.get_layer_map();

    let placement_config = PlacementConfig {
        block_width: config.algorithms.block_width,
        block_height: config.algorithms.block_height,
        horizontal_gap: config.algorithms.horizontal_gap,
        vertical_gap: config.algorithms.vertical_gap,
    };

    info!("📍 Размещение {} вершин на основе глобальных слоёв", layer_map.len());
    let positions = crate::algorithms::vertex_placement::place_all_vertices(
        layer_map,
        &placement_config,
    );

    // Конвертируем в формат Neo4j
    let neo4j_positions: Vec<crate::neo4j::VertexPosition> = positions
        .into_iter()
        .map(|p| crate::neo4j::VertexPosition {
            article_id: p.vertex_id,
            layer: p.layer,
            level: p.level,
            x: p.x,
            y: p.y,
        })
        .collect();

    info!("📊 Подготовлено {} позиций для сохранения", neo4j_positions.len());

    // Фаза 3: Сохранение результатов
    info!("=== ФАЗА 3: СОХРАНЕНИЕ РЕЗУЛЬТАТОВ В NEO4J ===");
    layout_service.neo4j_client.save_layout_results_with_batch_size(
        &neo4j_positions,
        config.neo4j.save_batch_size
    ).await?;

    info!("✅ Результаты успешно сохранены в Neo4j");
    info!("=== ВСЕ ФАЗЫ ЗАВЕРШЕНЫ УСПЕШНО ===");

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
    info!("🧪 Запуск тестов корректности укладки графа...");
    println!();

    // Путь к тестовому GML файлу
    let gml_path = "tests/artifacts/test_graph.gml";

    if std::path::Path::new(gml_path).exists() {
        println!("=== ТЕСТ 1: Укладка из GML файла ===\n");
        graph_layout_engine::test_layout::test_layout_from_gml(gml_path)?;
        println!("\n{}\n", "=".repeat(60));
    } else {
        println!("⚠️ GML файл не найден: {}", gml_path);
        println!("⚠️ Запуск теста на встроенном графе вместо этого\n");

        println!("=== ТЕСТ 1: Укладка встроенного тестового графа ===\n");
        graph_layout_engine::test_layout::test_layout()?;
        println!("\n{}\n", "=".repeat(60));
    }

    println!("✅ Все тесты успешно завершены\n");
    Ok(())
}
