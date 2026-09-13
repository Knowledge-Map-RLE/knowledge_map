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
use opentelemetry::trace::TracerProvider;
use opentelemetry_otlp::WithExportConfig;
use tonic::transport::Server;
use tracing::info;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

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
    // Загрузка конфигурации
    let config = match Config::load("config.toml") {
        Ok(config) => {
            info!("Конфигурация загружена из config.toml");
            config
        },
        Err(e) => {
            eprintln!("Ошибка загрузки конфигурации: {}", e);
            return Err(e);
        }
    };

    // Инициализация observability (stdout-логи + опционально OTLP)
    let _otel_provider = init_logging(
        "info",
        config.metrics.opentelemetry_enabled,
        config.metrics.tracing_endpoint.clone(),
    )?;

    info!("Запуск Graph Layout Engine v{}", env!("CARGO_PKG_VERSION"));

    let address = format!("{}:{}", config.server.bind_address, config.server.grpc_port);
    run_server(address, config).await?;

    info!("Программа завершена успешно");
    Ok(())
}

fn otel_sdk_disabled() -> bool {
    matches!(
        std::env::var("OTEL_SDK_DISABLED").as_deref(),
        Ok(v) if matches!(v, "1" | "true" | "YES" | "yes")
    )
}

/// Инициализация observability: stdout-логи + OTLP-трейсы (по env/конфигу).
///
/// Включение OTLP: `OTEL_SDK_DISABLED` не установлен и (задан
/// `OTEL_EXPORTER_OTLP_ENDPOINT` или `config.metrics.opentelemetry_enabled = true`).
/// Endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT` > config > http://127.0.0.1:4317.
fn init_logging(
    level: &str,
    config_opentelemetry_enabled: bool,
    tracing_endpoint: Option<String>,
) -> Result<Option<opentelemetry_sdk::trace::TracerProvider>> {
    let env_filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new(level.to_string()));

    let stdout_layer = tracing_subscriber::fmt::layer()
        .with_writer(std::io::stdout)
        .with_target(true)
        .with_ansi(false);

    let env_enabled = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").is_ok();
    if otel_sdk_disabled() || !(env_enabled || config_opentelemetry_enabled) {
        tracing_subscriber::registry()
            .with(env_filter)
            .with(stdout_layer)
            .init();
        return Ok(None);
    }

    let endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
        .ok()
        .or(tracing_endpoint)
        .unwrap_or_else(|| "http://127.0.0.1:4317".to_string());
    let service_name =
        std::env::var("OTEL_SERVICE_NAME").unwrap_or_else(|_| "graph-layout-engine".to_string());

    let exporter = opentelemetry_otlp::new_exporter()
        .tonic()
        .with_endpoint(endpoint)
        .build_span_exporter()
        .map_err(|e| anyhow::anyhow!("Не удалось создать OTLP-экспортер: {}", e))?;

    let provider = opentelemetry_sdk::trace::TracerProvider::builder()
        .with_config(
            opentelemetry_sdk::trace::Config::default().with_resource(
                opentelemetry_sdk::Resource::new(vec![
                    opentelemetry::KeyValue::new("service.name", service_name),
                    opentelemetry::KeyValue::new("service.namespace", "knowledge-map"),
                ]),
            ),
        )
        .with_simple_exporter(exporter)
        .build();

    let tracer = provider.tracer("graph-layout");

    tracing_subscriber::registry()
        .with(env_filter)
        .with(stdout_layer)
        .with(tracing_opentelemetry::layer().with_tracer(tracer))
        .init();

    Ok(Some(provider))
}

/// Запуск gRPC сервера
async fn run_server(address: String, config: Config) -> Result<()> {
    let addr: SocketAddr = address.parse()
        .map_err(|e| anyhow::anyhow!("Неверный адрес {}: {}", address, e))?;

    info!("Запуск gRPC сервера на {}", addr);

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
