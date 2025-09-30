/*!
# High-Performance Graph Layout Engine Library

Библиотека высокопроизводительных алгоритмов укладки графов на Rust.

## Модули

- `algorithms` - Основные алгоритмы укладки
- `data_structures` - Оптимизированные структуры данных для графов
- `memory` - Управление памятью и кешированием
- `metrics` - Сбор метрик производительности
- `neo4j` - Интеграция с Neo4j базой данных
- `server` - gRPC сервер

*/

pub mod algorithms;
pub mod config;
pub mod data_structures;
pub mod memory;
pub mod metrics;
pub mod neo4j;
pub mod server;

// Re-export основных типов
pub use algorithms::{HighPerformanceLayoutEngine, LayoutAlgorithm, LayoutResult};
pub use config::Config;
pub use data_structures::{Graph, GraphBuilder};
pub use server::GraphLayoutServer;

// Подключаем сгенерированные protobuf типы
pub mod generated {
    #![allow(clippy::derive_partial_eq_without_eq)]
    tonic::include_proto!("graph_layout");
}

// Версия API
pub const API_VERSION: &str = env!("CARGO_PKG_VERSION");
