/*!
# Конфигурация системы

Управление настройками производительности, подключений и алгоритмов.
*/

use serde::{Deserialize, Serialize};
use std::path::Path;
use anyhow::Result;

/// Основная конфигурация сервиса
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    /// Конфигурация сервера
    pub server: ServerConfig,
    
    /// Конфигурация Neo4j
    pub neo4j: Neo4jConfig,
    
    /// Конфигурация алгоритмов
    pub algorithms: AlgorithmConfig,
    
    /// Конфигурация производительности
    pub performance: PerformanceConfig,
    
    /// Конфигурация памяти
    pub memory: MemoryConfig,
    
    /// Конфигурация метрик
    pub metrics: MetricsConfig,
}

/// Конфигурация сервера
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerConfig {
    /// Адрес для привязки
    pub bind_address: String,
    
    /// Порт gRPC сервера
    pub grpc_port: u16,
    
    /// Порт метрик Prometheus
    pub metrics_port: u16,
    
    /// Максимальное количество одновременных подключений
    pub max_connections: usize,
    
    /// Таймаут запроса (секунды)
    pub request_timeout: u64,
    
    /// Размер буфера для streaming
    pub stream_buffer_size: usize,
}

/// Конфигурация Neo4j
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Neo4jConfig {
    /// URI подключения
    pub uri: String,
    
    /// Имя пользователя
    pub user: String,
    
    /// Пароль
    pub password: String,
    
    /// База данных
    pub database: String,
    
    /// Размер пула соединений
    pub pool_size: usize,
    
    /// Таймаут подключения (секунды)
    pub connection_timeout: u64,
    
    /// Таймаут транзакции (секунды)
    pub transaction_timeout: u64,
    
    /// Размер батча для запросов
    pub batch_size: usize,
    
    /// Размер батча для сохранения результатов
    pub save_batch_size: usize,

    /// Количество параллельных транзакций сохранения
    pub save_parallelism: usize,
}

/// Конфигурация алгоритмов укладки
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlgorithmConfig {
    /// Размеры блоков
    pub block_width: f32,
    pub block_height: f32,
    
    /// Отступы
    pub horizontal_gap: f32,
    pub vertical_gap: f32,
    
    /// Исключать изолированные вершины
    pub exclude_isolated_vertices: bool,
    
    /// Максимальное количество итераций
    pub max_iterations: u32,
    
    /// Порог сходимости
    pub convergence_threshold: f32,
    
    /// Стратегия оптимизации
    pub optimization_strategy: OptimizationStrategy,
}

/// Стратегия оптимизации
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OptimizationStrategy {
    /// Максимальная скорость
    Speed,
    /// Баланс скорости и качества
    Balanced,
    /// Максимальное качество укладки
    Quality,
    /// Минимальное использование памяти
    Memory,
}

/// Конфигурация производительности
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PerformanceConfig {
    /// Количество рабочих потоков
    pub worker_threads: usize,
    
    /// Размер чанка для обработки
    pub chunk_size: usize,
    
    /// Максимальное количество параллельных задач
    pub max_parallel_tasks: usize,
    
    /// Включить SIMD оптимизации
    pub enable_simd: bool,
    
    /// Включить GPU вычисления
    pub enable_gpu: bool,
    
    /// Включить векторизацию
    pub enable_vectorization: bool,
    
    /// Приоритет процесса
    pub process_priority: ProcessPriority,
}

/// Приоритет процесса
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ProcessPriority {
    Low,
    Normal,
    High,
    RealTime,
}

/// Конфигурация управления памятью
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryConfig {
    /// Лимит памяти в байтах
    pub memory_limit_bytes: usize,
    
    /// Стратегия управления памятью
    pub strategy: MemoryStrategy,
    
    /// Размер кеша для горячих данных
    pub hot_cache_size: usize,
    
    /// Размер кеша для теплых данных
    pub warm_cache_size: usize,
    
    /// Путь для временных файлов
    pub temp_dir: String,
    
    /// Использовать memory mapping
    pub use_memory_mapping: bool,
    
    /// Размер страницы для memory mapping
    pub page_size: usize,
}

/// Стратегия управления памятью
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MemoryStrategy {
    /// Автоматический выбор
    Auto,
    /// Приоритет RAM
    RamFirst,
    /// Использование SSD кеша
    SsdCache,
    /// Потоковая обработка
    Streaming,
}

/// Конфигурация метрик
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetricsConfig {
    /// Включить сбор метрик
    pub enabled: bool,
    
    /// Интервал сбора метрик (секунды)
    pub collection_interval: u64,
    
    /// Экспортировать в Prometheus
    pub prometheus_enabled: bool,
    
    /// Экспортировать в OpenTelemetry
    pub opentelemetry_enabled: bool,
    
    /// Endpoint для экспорта трейсов
    pub tracing_endpoint: Option<String>,
    
    /// Уровень детализации метрик
    pub detail_level: MetricDetailLevel,
}

/// Уровень детализации метрик
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MetricDetailLevel {
    Basic,
    Detailed,
    Verbose,
}

impl Config {
    /// Загрузка конфигурации из файла
    pub fn load<P: AsRef<Path>>(path: P) -> Result<Self> {
        let content = std::fs::read_to_string(path)?;
        let config: Config = toml::from_str(&content)?;
        Ok(config)
    }
    
    /// Конфигурация по умолчанию
    pub fn default() -> Self {
        Self {
            server: ServerConfig {
                bind_address: "0.0.0.0".to_string(),
                grpc_port: 50051,
                metrics_port: 9090,
                max_connections: 1000,
                request_timeout: 300,
                stream_buffer_size: 1024,
            },
            neo4j: Neo4jConfig {
                uri: "bolt://localhost:7687".to_string(),
                user: "neo4j".to_string(),
                password: "password".to_string(),
                database: "neo4j".to_string(),
                pool_size: 50,
                connection_timeout: 30,
                transaction_timeout: 300,
                batch_size: 5000,
                save_batch_size: 1000,
                save_parallelism: 4,
            },
            algorithms: AlgorithmConfig {
                block_width: 200.0,
                block_height: 80.0,
                horizontal_gap: 40.0,
                vertical_gap: 50.0,
                exclude_isolated_vertices: true,
                max_iterations: 1000,
                convergence_threshold: 0.001,
                optimization_strategy: OptimizationStrategy::Balanced,
            },
            performance: PerformanceConfig {
                worker_threads: num_cpus::get(),
                chunk_size: 10000,
                max_parallel_tasks: num_cpus::get() * 2,
                enable_simd: true,
                enable_gpu: false,
                enable_vectorization: true,
                process_priority: ProcessPriority::High,
            },
            memory: MemoryConfig {
                memory_limit_bytes: 8 * 1024 * 1024 * 1024, // 8GB
                strategy: MemoryStrategy::Auto,
                hot_cache_size: 100_000,
                warm_cache_size: 1_000_000,
                temp_dir: "/tmp/graph_layout".to_string(),
                use_memory_mapping: true,
                page_size: 4096,
            },
            metrics: MetricsConfig {
                enabled: true,
                collection_interval: 10,
                prometheus_enabled: true,
                opentelemetry_enabled: false,
                tracing_endpoint: None,
                detail_level: MetricDetailLevel::Detailed,
            },
        }
    }
    
    /// Валидация конфигурации
    pub fn validate(&self) -> Result<()> {
        // Проверка портов
        if self.server.grpc_port == self.server.metrics_port {
            return Err(anyhow::anyhow!(
                "gRPC порт и порт метрик не могут совпадать"
            ));
        }
        
        // Проверка лимитов памяти
        if self.memory.memory_limit_bytes < 1024 * 1024 * 1024 {
            return Err(anyhow::anyhow!(
                "Лимит памяти должен быть не менее 1GB"
            ));
        }
        
        // Проверка размеров
        if self.performance.chunk_size == 0 {
            return Err(anyhow::anyhow!(
                "Размер чанка должен быть больше 0"
            ));
        }
        
        Ok(())
    }
    
    /// Оптимизация конфигурации под конкретную систему
    pub fn optimize_for_system(&mut self) -> Result<()> {
        // Определение доступной памяти
        let available_memory = get_available_memory()?;
        
        // Адаптация под доступную память
        if available_memory < 4 * 1024 * 1024 * 1024 {
            // Менее 4GB - консервативные настройки
            self.memory.memory_limit_bytes = available_memory / 2;
            self.performance.chunk_size = 5000;
            self.memory.strategy = MemoryStrategy::Streaming;
        } else if available_memory < 16 * 1024 * 1024 * 1024 {
            // 4-16GB - сбалансированные настройки
            self.memory.memory_limit_bytes = available_memory * 3 / 4;
            self.performance.chunk_size = 10000;
            self.memory.strategy = MemoryStrategy::RamFirst;
        } else {
            // Более 16GB - агрессивные настройки
            self.memory.memory_limit_bytes = available_memory * 7 / 8;
            self.performance.chunk_size = 20000;
            self.memory.strategy = MemoryStrategy::RamFirst;
        }
        
        // Адаптация количества потоков
        let cpu_count = num_cpus::get();
        self.performance.worker_threads = cpu_count;
        self.performance.max_parallel_tasks = cpu_count * 2;
        
        Ok(())
    }
}

/// Получение количества доступной памяти
fn get_available_memory() -> Result<usize> {
    use sysinfo::System;
    
    let mut system = System::new_all();
    system.refresh_memory();
    
    Ok(system.available_memory() as usize * 1024) // sysinfo возвращает в KB
}

impl Default for Config {
    fn default() -> Self {
        Self::default()
    }
}
