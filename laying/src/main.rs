/*!
# High-Performance Graph Layout Engine

Rust-based микросервис для высокопроизводительной укладки графов.

## Ключевые особенности

- **gRPC API** для интеграции с микросервисами
- **SIMD оптимизации** для векторных операций
- **Многопоточная обработка** с Rayon
- **Эффективное управление памятью** с чанками/батчами
- **Минимальный трафик** - только рёбра на вход, только координаты на выход

## Архитектура алгоритмов

- Топологическая сортировка: O(V + E) → O((V + E) / P) с параллелизмом
- Longest Path: O(V²) → O(V log V) с SIMD
- Размещение вершин: O(V²) → O(V) с эффективными структурами данных

*/
#![allow(dead_code)]

use std::net::SocketAddr;

use anyhow::Result;
use tonic::transport::Server;
use tracing::{info, error};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, Layer};

mod config;
mod algorithms;
mod data_structures;
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
use crate::server::GraphLayoutServer;

#[cfg(feature = "mimalloc")]
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

#[cfg(feature = "jemalloc")]
#[global_allocator]
static GLOBAL: jemallocator::Jemalloc = jemallocator::Jemalloc;

#[tokio::main]
async fn main() -> Result<()> {
    // Инициализация логирования
    init_logging("info")?;

    info!(
        "🦀 Запуск Graph Layout Engine v{}",
        env!("CARGO_PKG_VERSION")
    );

    // Загрузка конфигурации
    let config = match Config::load("config.toml") {
        Ok(config) => {
            info!("📋 Конфигурация загружена из config.toml");
            config
        },
        Err(e) => {
            error!("❌ Ошибка загрузки конфигурации: {}", e);
            return Err(e);
        }
    };

    let address = format!("{}:{}", config.server.bind_address, config.server.grpc_port);
    run_server(address, config).await?;

    info!("✅ Программа завершена успешно");
    Ok(())
}

/// Инициализация системы логирования
fn init_logging(level: &str) -> Result<()> {
    let level = level.parse::<tracing::Level>()
        .map_err(|e| anyhow::anyhow!("Неверный уровень логирования: {}", e))?;

    std::fs::create_dir_all("logs")
        .map_err(|e| anyhow::anyhow!("Не удалось создать директорию logs: {}", e))?;

    let env_filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new(level.to_string()));

    let file_appender = tracing_appender::rolling::never("logs", "rust_layout.log");
    let error_appender = tracing_appender::rolling::never("logs", "rust_layout_error.log");

    let stdout_layer = tracing_subscriber::fmt::layer()
        .with_writer(std::io::stdout)
        .with_target(false)
        .with_ansi(false);

    let file_layer = tracing_subscriber::fmt::layer()
        .with_writer(file_appender)
        .with_target(true)
        .with_ansi(false);

    let error_layer = tracing_subscriber::fmt::layer()
        .with_writer(error_appender)
        .with_target(true)
        .with_ansi(false)
        .with_filter(tracing_subscriber::filter::LevelFilter::ERROR);

    tracing_subscriber::registry()
        .with(env_filter)
        .with(stdout_layer)
        .with(file_layer)
        .with(error_layer)
        .init();

    Ok(())
}

/// Запуск gRPC сервера
async fn run_server(address: String, config: Config) -> Result<()> {
    let addr: SocketAddr = address.parse()
        .map_err(|e| anyhow::anyhow!("Неверный адрес {}: {}", address, e))?;

    info!("🚀 Запуск gRPC сервера на {}", addr);

    let layout_service = GraphLayoutServer::new(config).await?;

    let service = tower::ServiceBuilder::new()
        .service(generated::graph_layout_service_server::GraphLayoutServiceServer::new(layout_service));

    Server::builder()
        .add_service(service)
        .serve(addr)
        .await
        .map_err(|e| anyhow::anyhow!("Ошибка сервера: {}", e))?;

    Ok(())
}
