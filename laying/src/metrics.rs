/*!
# Система метрик для мониторинга производительности

Сбор и экспорт метрик в формате Prometheus с поддержкой:
- Производительности алгоритмов
- Использования ресурсов
- Качества укладки графов
- Статистики gRPC запросов

*/

use crate::generated::{PrometheusMetric, MetricSample};
use anyhow::Result;
use prometheus::{
    Counter, Gauge, Histogram, Registry, Encoder, TextEncoder,
    HistogramOpts, Opts,
};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;

/// Сборщик метрик
#[derive(Debug)]
pub struct MetricsCollector {
    /// Prometheus registry
    registry: Registry,
    
    /// Счетчики запросов
    layout_requests_total: Counter,
    layout_requests_success: Counter,
    layout_requests_failed: Counter,
    
    /// Гистограммы времени выполнения
    layout_duration: Histogram,
    topo_sort_duration: Histogram,
    longest_path_duration: Histogram,
    placement_duration: Histogram,
    
    /// Метрики ресурсов
    memory_usage_bytes: Gauge,
    memory_peak_bytes: Gauge,
    cpu_usage_percent: Gauge,
    
    /// Метрики качества укладки
    vertices_processed: Counter,
    edges_processed: Counter,
    vertices_per_second: Gauge,
    
    /// Активные задачи
    active_tasks: Arc<RwLock<usize>>,
    
    /// Время запуска для uptime
    start_time: Instant,
}

impl MetricsCollector {
    /// Создание нового сборщика метрик
    pub fn new(_config: &crate::config::MetricsConfig) -> Result<Self> {
        let registry = Registry::new();
        
        // Создание счетчиков запросов
        let layout_requests_total = Counter::with_opts(Opts::new(
            "graph_layout_requests_total",
            "Total number of layout requests"
        ))?;
        
        let layout_requests_success = Counter::with_opts(Opts::new(
            "graph_layout_requests_success_total", 
            "Total number of successful layout requests"
        ))?;
        
        let layout_requests_failed = Counter::with_opts(Opts::new(
            "graph_layout_requests_failed_total",
            "Total number of failed layout requests"
        ))?;
        
        // Создание гистограмм времени
        let layout_duration = Histogram::with_opts(HistogramOpts::new(
            "graph_layout_duration_seconds",
            "Duration of layout computation in seconds"
        ).buckets(vec![0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0]))?;
        
        let topo_sort_duration = Histogram::with_opts(HistogramOpts::new(
            "graph_layout_topo_sort_duration_seconds", 
            "Duration of topological sort in seconds"
        ).buckets(vec![0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]))?;
        
        let longest_path_duration = Histogram::with_opts(HistogramOpts::new(
            "graph_layout_longest_path_duration_seconds",
            "Duration of longest path computation in seconds"
        ).buckets(vec![0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]))?;
        
        let placement_duration = Histogram::with_opts(HistogramOpts::new(
            "graph_layout_placement_duration_seconds",
            "Duration of vertex placement in seconds"
        ).buckets(vec![0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]))?;
        
        // Создание метрик ресурсов
        let memory_usage_bytes = Gauge::with_opts(Opts::new(
            "graph_layout_memory_usage_bytes",
            "Current memory usage in bytes"
        ))?;
        
        let memory_peak_bytes = Gauge::with_opts(Opts::new(
            "graph_layout_memory_peak_bytes", 
            "Peak memory usage in bytes"
        ))?;
        
        let cpu_usage_percent = Gauge::with_opts(Opts::new(
            "graph_layout_cpu_usage_percent",
            "Current CPU usage percentage"
        ))?;
        
        // Создание метрик качества
        let vertices_processed = Counter::with_opts(Opts::new(
            "graph_layout_vertices_processed_total",
            "Total number of vertices processed"
        ))?;
        
        let edges_processed = Counter::with_opts(Opts::new(
            "graph_layout_edges_processed_total",
            "Total number of edges processed"
        ))?;
        
        let vertices_per_second = Gauge::with_opts(Opts::new(
            "graph_layout_vertices_per_second",
            "Processing rate in vertices per second"
        ))?;
        
        // Регистрация метрик
        registry.register(Box::new(layout_requests_total.clone()))?;
        registry.register(Box::new(layout_requests_success.clone()))?;
        registry.register(Box::new(layout_requests_failed.clone()))?;
        registry.register(Box::new(layout_duration.clone()))?;
        registry.register(Box::new(topo_sort_duration.clone()))?;
        registry.register(Box::new(longest_path_duration.clone()))?;
        registry.register(Box::new(placement_duration.clone()))?;
        registry.register(Box::new(memory_usage_bytes.clone()))?;
        registry.register(Box::new(memory_peak_bytes.clone()))?;
        registry.register(Box::new(cpu_usage_percent.clone()))?;
        registry.register(Box::new(vertices_processed.clone()))?;
        registry.register(Box::new(edges_processed.clone()))?;
        registry.register(Box::new(vertices_per_second.clone()))?;
        
        Ok(Self {
            registry,
            layout_requests_total,
            layout_requests_success,
            layout_requests_failed,
            layout_duration,
            topo_sort_duration,
            longest_path_duration,
            placement_duration,
            memory_usage_bytes,
            memory_peak_bytes,
            cpu_usage_percent,
            vertices_processed,
            edges_processed,
            vertices_per_second,
            active_tasks: Arc::new(RwLock::new(0)),
            start_time: Instant::now(),
        })
    }
    
    /// Запись метрики успешной укладки
    pub async fn record_successful_layout(&self, duration: Duration) {
        self.layout_requests_total.inc();
        self.layout_requests_success.inc();
        self.layout_duration.observe(duration.as_secs_f64());
    }
    
    /// Запись метрики неудачной укладки
    pub async fn record_failed_layout(&self, duration: Duration) {
        self.layout_requests_total.inc();
        self.layout_requests_failed.inc();
        self.layout_duration.observe(duration.as_secs_f64());
    }
    
    /// Запись времени топологической сортировки
    pub async fn record_topo_sort(&self, duration: Duration) {
        self.topo_sort_duration.observe(duration.as_secs_f64());
    }
    
    /// Запись времени поиска longest path
    pub async fn record_longest_path(&self, duration: Duration) {
        self.longest_path_duration.observe(duration.as_secs_f64());
    }
    
    /// Запись времени размещения вершин
    pub async fn record_placement(&self, duration: Duration) {
        self.placement_duration.observe(duration.as_secs_f64());
    }
    
    /// Обновление использования памяти
    pub async fn update_memory_usage(&self, current_bytes: u64, peak_bytes: u64) {
        self.memory_usage_bytes.set(current_bytes as f64);
        self.memory_peak_bytes.set(peak_bytes as f64);
    }
    
    /// Обновление использования CPU
    pub async fn update_cpu_usage(&self, percent: f64) {
        self.cpu_usage_percent.set(percent);
    }
    
    /// Запись обработанных вершин и связей
    pub async fn record_processing(&self, vertices: usize, edges: usize, duration: Duration) {
        self.vertices_processed.inc_by(vertices as f64);
        self.edges_processed.inc_by(edges as f64);
        
        if duration.as_secs_f64() > 0.0 {
            let rate = vertices as f64 / duration.as_secs_f64();
            self.vertices_per_second.set(rate);
        }
    }
    
    /// Запись загрузки данных
    pub async fn record_data_load(&self, edge_count: usize, _duration: Duration) {
        // Можно добавить специальные метрики для загрузки данных
        self.edges_processed.inc_by(edge_count as f64);
    }
    
    /// Запись сохранения данных
    pub async fn record_data_save(&self, position_count: usize, _duration: Duration) {
        // Можно добавить специальные метрики для сохранения данных
        self.vertices_processed.inc_by(position_count as f64);
    }
    
    /// Увеличение счетчика активных задач
    pub async fn increment_active_tasks(&self) {
        let mut tasks = self.active_tasks.write().await;
        *tasks += 1;
    }
    
    /// Уменьшение счетчика активных задач
    pub async fn decrement_active_tasks(&self) {
        let mut tasks = self.active_tasks.write().await;
        if *tasks > 0 {
            *tasks -= 1;
        }
    }
    
    /// Получение количества активных задач
    pub async fn get_active_tasks(&self) -> usize {
        *self.active_tasks.read().await
    }
    
    /// Получение текущего использования CPU
    pub async fn get_cpu_usage(&self) -> f32 {
        self.cpu_usage_percent.get() as f32
    }
    
    /// Получение использования памяти
    pub async fn get_memory_usage(&self) -> usize {
        self.memory_usage_bytes.get() as usize
    }
    
    /// Получение доступной памяти (заглушка)
    pub async fn get_available_memory(&self) -> usize {
        8 * 1024 * 1024 * 1024 // 8GB заглушка
    }
    
    /// Экспорт метрик в формате Prometheus
    pub async fn export_metrics(&self) -> Result<String> {
        let encoder = TextEncoder::new();
        let metric_families = self.registry.gather();
        let mut buffer = Vec::new();
        encoder.encode(&metric_families, &mut buffer)?;
        Ok(String::from_utf8(buffer)?)
    }
    
    /// Получение метрик в формате protobuf
    pub async fn get_prometheus_metrics(&self) -> Vec<PrometheusMetric> {
        let metric_families = self.registry.gather();
        let mut metrics = Vec::new();
        
        for family in metric_families {
            let metric = PrometheusMetric {
                name: family.get_name().to_string(),
                help: family.get_help().to_string(),
                metric_type: format!("{:?}", family.get_field_type()),
                samples: family.get_metric()
                    .iter()
                    .map(|m| {
                        MetricSample {
                            label_names: m.get_label()
                                .iter()
                                .map(|l| l.get_name().to_string())
                                .collect(),
                            label_values: m.get_label()
                                .iter()
                                .map(|l| l.get_value().to_string())
                                .collect(),
                            value: self.extract_metric_value(m),
                            timestamp: chrono::Utc::now().timestamp(),
                        }
                    })
                    .collect(),
            };
            metrics.push(metric);
        }
        
        metrics
    }
    
    /// Извлечение значения метрики
    fn extract_metric_value(&self, metric: &prometheus::proto::Metric) -> f64 {
        if metric.has_counter() {
            metric.get_counter().get_value()
        } else if metric.has_gauge() {
            metric.get_gauge().get_value()
        } else if metric.has_histogram() {
            metric.get_histogram().get_sample_sum()
        } else {
            0.0
        }
    }
    
    /// Сброс всех метрик
    pub async fn reset_metrics(&self) {
        // Prometheus метрики нельзя сбросить, но можно пересоздать registry
        // В продакшене это может быть не нужно
    }
}

/// Middleware для автоматического сбора метрик gRPC
pub struct MetricsMiddleware {
    collector: Arc<MetricsCollector>,
}

impl MetricsMiddleware {
    /// Создание нового middleware
    pub fn new(collector: Arc<MetricsCollector>) -> Self {
        Self { collector }
    }
    
    /// Обработка запроса с автоматическим сбором метрик
    pub async fn process_request<F, R>(&self, request_handler: F) -> R
    where
        F: std::future::Future<Output = R>,
    {
        let start_time = Instant::now();
        self.collector.increment_active_tasks().await;
        
        let result = request_handler.await;
        
        let _duration = start_time.elapsed();
        self.collector.decrement_active_tasks().await;
        
        // Здесь можно добавить логику для определения успешности запроса
        // и вызвать соответствующие методы collector
        
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::MetricsConfig;
    
    #[tokio::test]
    async fn test_metrics_collection() -> Result<()> {
        let config = MetricsConfig {
            enabled: true,
            collection_interval: 10,
            prometheus_enabled: true,
            opentelemetry_enabled: false,
            tracing_endpoint: None,
            detail_level: crate::config::MetricDetailLevel::Detailed,
        };
        
        let collector = MetricsCollector::new(&config)?;
        
        // Тест записи метрик
        collector.record_successful_layout(Duration::from_secs(5)).await;
        collector.update_memory_usage(1024 * 1024, 2 * 1024 * 1024).await;
        collector.record_processing(1000, 2000, Duration::from_secs(2)).await;
        
        // Тест экспорта метрик
        let metrics = collector.export_metrics().await?;
        assert!(metrics.contains("graph_layout_requests_total"));
        assert!(metrics.contains("graph_layout_memory_usage_bytes"));
        
        Ok(())
    }
}
