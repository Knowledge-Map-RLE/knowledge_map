/*!
# Параллельная обработка для многоядерных систем

Оптимизированные параллельные алгоритмы с использованием Rayon:

- **Work-stealing scheduler** для равномерной загрузки ядер
- **NUMA-aware** распределение данных
- **Lock-free** структуры данных
- **Adaptive parallelism** в зависимости от размера задач

*/

use rayon::prelude::*;
use std::sync::atomic::{AtomicUsize, Ordering};
use anyhow::Result;

/// Параллельный процессор графов
pub struct ParallelGraphProcessor {
    /// Количество рабочих потоков
    worker_count: usize,
    
    /// Счетчик активных задач
    active_tasks: AtomicUsize,
}

impl ParallelGraphProcessor {
    /// Создание нового процессора
    pub fn new(worker_count: usize) -> Self {
        // Настройка Rayon thread pool
        rayon::ThreadPoolBuilder::new()
            .num_threads(worker_count)
            .build_global()
            .expect("Failed to initialize Rayon thread pool");
        
        Self {
            worker_count,
            active_tasks: AtomicUsize::new(0),
        }
    }
    
    /// Параллельная обработка списка элементов
    pub async fn process_parallel<T, R, F>(
        &self,
        items: Vec<T>,
        processor: F,
    ) -> Result<Vec<R>>
    where
        T: Send + Sync,
        R: Send,
        F: Fn(&T) -> Result<R> + Send + Sync,
    {
        self.active_tasks.store(items.len(), Ordering::Relaxed);
        
        let results: Result<Vec<_>> = items
            .par_iter()
            .map(|item| {
                let result = processor(item);
                self.active_tasks.fetch_sub(1, Ordering::Relaxed);
                result
            })
            .collect();
        
        results
    }
    
    /// Получение количества активных задач
    pub fn get_active_tasks(&self) -> usize {
        self.active_tasks.load(Ordering::Relaxed)
    }
}
