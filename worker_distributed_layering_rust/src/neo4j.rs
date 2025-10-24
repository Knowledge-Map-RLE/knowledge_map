/*!
# Neo4j клиент для Rust Graph Layout Engine

Упрощенная версия клиента для работы с Neo4j.
Пока что реализует только базовую функциональность без сложных зависимостей.
*/

use crate::config::Config;
use anyhow::Result;
use neo4rs::BoltType;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::info;
use neo4rs::*;

/// Конфигурация Neo4j
#[derive(Debug, Clone)]
pub struct Neo4jConfig {
    pub uri: String,
    pub user: String,
    pub password: String,
    pub database: String,
    pub pool_size: u32,
    pub connection_timeout: u64,
    pub transaction_timeout: u64,
    pub batch_size: usize,
}

/// Клиент для работы с Neo4j (упрощенная версия)
pub struct Neo4jClient {
    /// Конфигурация
    config: Neo4jConfig,
    
    /// Neo4j Graph connection
    graph: Arc<Graph>,
    
    /// Статус подключения
    connected: Arc<RwLock<bool>>,
}

impl Neo4jClient {
    /// Создание нового клиента
    pub async fn new(config: &Config) -> Result<Self> {
        info!("🔧 Создание Neo4j клиента...");
        
        let neo4j_config = Neo4jConfig {
            uri: config.neo4j.uri.clone(),
            user: config.neo4j.user.clone(),
            password: config.neo4j.password.clone(),
            database: config.neo4j.database.clone(),
            pool_size: config.neo4j.pool_size as u32,
            connection_timeout: config.neo4j.connection_timeout,
            transaction_timeout: config.neo4j.transaction_timeout,
            batch_size: config.neo4j.batch_size,
        };
        
        info!("📡 Параметры подключения: uri={}, database={}, pool_size={}", 
              neo4j_config.uri, neo4j_config.database, neo4j_config.pool_size);
        
        // Создаем подключение к Neo4j
        info!("🔧 Создание конфигурации Neo4j...");
        let graph_config = ConfigBuilder::default()
            .uri(&neo4j_config.uri)
            .user(&neo4j_config.user)
            .password(&neo4j_config.password)
            .db(&*neo4j_config.database)
            .build()
            .expect("Failed to build Neo4j config");
        
        info!("🔌 Установка соединения с Neo4j...");
        let start_connect = std::time::Instant::now();
        
        let graph = Graph::connect(graph_config).await.expect("Failed to connect to Neo4j");
        
        let connect_time = start_connect.elapsed();
        info!("✅ Соединение с Neo4j установлено за {:.2?}", connect_time);
        
        Ok(Self {
            config: neo4j_config,
            graph: Arc::new(graph),
            connected: Arc::new(RwLock::new(true)),
        })
    }
    
    /// Подключение к Neo4j (заглушка)
    pub async fn connect(&self) -> Result<()> {
        info!("🔌 Подключение к Neo4j: {}", self.config.uri);
        
        // Имитация подключения
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
        
        let mut connected = self.connected.write().await;
        *connected = true;
        
        info!("✅ Neo4j клиент подключен");
        Ok(())
    }
    
    /// Отключение от Neo4j
    pub async fn close(&self) -> Result<()> {
        info!("🔌 Отключение от Neo4j");
        
        let mut connected = self.connected.write().await;
        *connected = false;
        
        info!("✅ Neo4j клиент отключен");
        Ok(())
    }
    
    /// Выполнение запроса (заглушка)
    pub async fn execute_query(&self, query: &str, _params: Option<HashMap<String, BoltType>>) -> Result<Vec<HashMap<String, BoltType>>> {
        info!("📝 Выполнение запроса: {}", query);
        
        // Проверка подключения
        {
            let connected = self.connected.read().await;
            if !*connected {
                return Err(anyhow::anyhow!("Не подключен к Neo4j"));
            }
        }
        
        // Имитация выполнения запроса
        tokio::time::sleep(tokio::time::Duration::from_millis(50)).await;
        
        // Возвращаем пустой результат для заглушки
        Ok(vec![])
    }
    
    /// Загрузка связей графа из Neo4j
    pub async fn load_graph_edges(&self) -> Result<Vec<GraphEdge>> {
        info!("📊 Загрузка связей графа из Neo4j...");
        
        // Сначала проверим схему данных
        let schema_query = r#"
        MATCH (n:Article) 
        RETURN keys(n) as article_properties 
        LIMIT 1
        "#;
        
        let mut schema_result = self.graph.execute(schema_query.into()).await?;
        if let Ok(Some(row)) = schema_result.next().await {
            if let Ok(properties) = row.get::<Vec<String>>("article_properties") {
                info!("🔍 Свойства Article узлов: {:?}", properties);
            }
        }
        
        // Проверим количество данных
        let count_query = r#"
        MATCH (n:Article) 
        RETURN count(n) as node_count
        "#;
        
        let mut count_result = self.graph.execute(count_query.into()).await?;
        if let Ok(Some(row)) = count_result.next().await {
            if let Ok(count) = row.get::<i64>("node_count") {
                info!("📊 Всего Article узлов в БД: {}", count);
            }
        }
        
        // Проверим количество связей
        let edges_count_query = r#"
        MATCH (a:Article)-[r]->(b:Article)
        RETURN count(r) as edge_count
        "#;
        
        let mut edges_count_result = self.graph.execute(edges_count_query.into()).await?;
        if let Ok(Some(row)) = edges_count_result.next().await {
            if let Ok(count) = row.get::<i64>("edge_count") {
                info!("🔗 Всего связей в БД: {}", count);
            }
        }
        
        // Проверим узлы с пустыми uid
        let empty_uid_query = r#"
        MATCH (n:Article)
        WHERE n.uid IS NULL OR n.uid = ''
        RETURN count(n) as empty_uid_count
        "#;
        
        let mut empty_uid_result = self.graph.execute(empty_uid_query.into()).await?;
        if let Ok(Some(row)) = empty_uid_result.next().await {
            if let Ok(count) = row.get::<i64>("empty_uid_count") {
                info!("⚠️ Узлов с пустым uid: {}", count);
            }
        }
        
        // Проверим примеры связей
        let sample_edges_query = r#"
        MATCH (a:Article)-[r]->(b:Article)
        WHERE a.uid IS NOT NULL AND b.uid IS NOT NULL
        RETURN a.uid as source, b.uid as target, type(r) as edge_type
        LIMIT 5
        "#;
        
        let mut sample_result = self.graph.execute(sample_edges_query.into()).await?;
        info!("📝 Примеры связей:");
        let mut sample_count = 0;
        while let Ok(Some(row)) = sample_result.next().await {
            if sample_count < 5 {
                let source: String = row.get("source").unwrap_or_default();
                let target: String = row.get("target").unwrap_or_default();
                let edge_type: String = row.get("edge_type").unwrap_or_else(|_| "UNKNOWN".to_string());
                info!("   {}. '{}' -> '{}' ({})", sample_count + 1, source, target, edge_type);
                sample_count += 1;
            }
        }
        
            // Используем правильное поле uid вместо id
            let query = r#"
            MATCH (a:Article)-[r]->(b:Article)
            WHERE a.uid IS NOT NULL AND b.uid IS NOT NULL 
            RETURN a.uid as source, b.uid as target, type(r) as edge_type
            "#;
        
        let mut result = self.graph.execute(query.into()).await?;
        let mut edges = Vec::new();
        let mut batch_count = 0;
        let mut total_loaded = 0;
        
        info!("📥 Начинаем загрузку всех связей из Neo4j...");
        let start_time = std::time::Instant::now();
        
        while let Ok(Some(row)) = result.next().await {
            let source: String = row.get("source").unwrap_or_default();
            let target: String = row.get("target").unwrap_or_default();
            let edge_type: String = row.get("edge_type").unwrap_or_else(|_| "RELATES_TO".to_string());
            
            edges.push(GraphEdge {
                source_id: source,
                target_id: target,
                edge_type,
                weight: 1.0,
            });
            
            total_loaded += 1;
            batch_count += 1;
            
            // Показываем прогресс каждые 100,000 связей
            if batch_count >= 100_000 {
                let elapsed = start_time.elapsed();
                let rate = total_loaded as f64 / elapsed.as_secs_f64();
                info!("📊 Загружено {} связей (скорость: {:.0} связей/сек)", total_loaded, rate);
                batch_count = 0;
            }
        }
        
        let total_time = start_time.elapsed();
        let rate = total_loaded as f64 / total_time.as_secs_f64();
        info!("✅ Загружено {} связей из Neo4j за {:.2?} (скорость: {:.0} связей/сек)", 
               total_loaded, total_time, rate);
        Ok(edges)
    }
    
    /// Получение связей графа (алиас для load_graph_edges)
    pub async fn get_edges(&self) -> Result<Vec<GraphEdge>> {
        self.load_graph_edges().await
    }

    /// Батчевая загрузка связей графа
    pub async fn load_graph_edges_batch(&self, batch_size: usize, offset: usize) -> Result<Vec<GraphEdge>> {
        info!("📥 Загрузка батча связей: offset={}, batch_size={}", offset, batch_size);
        
        let query = format!(
            r#"
            MATCH (a:Article)-[r]->(b:Article)
            WHERE a.uid IS NOT NULL AND b.uid IS NOT NULL 
            RETURN a.uid as source, b.uid as target, type(r) as edge_type
            SKIP {} LIMIT {}
            "#,
            offset, batch_size
        );
        
        info!("📝 Выполнение запроса загрузки батча...");
        let start_query = std::time::Instant::now();
        
        // Попытка с ретраями
        let max_retries = 3;
        for attempt in 1..=max_retries {
            if attempt > 1 {
                info!("🔄 Повторная попытка {} из {}", attempt, max_retries);
            }
            
            match self.graph.execute(query.clone().into()).await {
                Ok(mut result) => {
                    info!("✅ Запрос выполнен, обработка результатов...");
                    let mut edges = Vec::new();
                    let mut row_count = 0;
                    
                    // Добавляем таймаут для получения первой строки
                    let timeout_duration = std::time::Duration::from_secs(60);
                    info!("⏱️ Ожидание первой строки результата (таймаут {} сек)...", timeout_duration.as_secs());
                    
                    loop {
                        match tokio::time::timeout(timeout_duration, result.next()).await {
                            Ok(Ok(Some(row))) => {
                                if row_count == 0 {
                                    info!("📦 Первая строка получена, обработка данных...");
                                }
                                
                                let source: String = row.get("source").unwrap_or_default();
                                let target: String = row.get("target").unwrap_or_default();
                                let edge_type: String = row.get("edge_type").unwrap_or_else(|_| "RELATES_TO".to_string());
                                
                                edges.push(GraphEdge {
                                    source_id: source,
                                    target_id: target,
                                    edge_type,
                                    weight: 1.0,
                                });
                                
                                row_count += 1;
                                if row_count % 10000 == 0 {
                                    info!("📊 Обработано {} строк из батча...", row_count);
                                }
                            }
                            Ok(Ok(None)) => {
                                info!("✅ Конец результатов, обработано {} строк", row_count);
                                break;
                            }
                            Ok(Err(e)) => {
                                info!("❌ Ошибка при чтении строки: {}", e);
                                break;
                            }
                            Err(_) => {
                                info!("⏱️ Таймаут при получении строки {} (> {} сек)", row_count + 1, timeout_duration.as_secs());
                                if attempt < max_retries {
                                    let backoff_ms = (1u64 << attempt.min(6)) * 500;
                                    info!("⏳ Ожидание {} мс перед повтором всего батча...", backoff_ms);
                                    tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                                    continue;
                                }
                                return Err(anyhow::anyhow!("Таймаут при получении данных после {} попыток", max_retries));
                            }
                        }
                    }
                    
                    let query_time = start_query.elapsed();
                    info!("✅ Загружен батч: {} связей (offset={}, время: {:.2?})", edges.len(), offset, query_time);
                    return Ok(edges);
                }
                Err(e) => {
                    info!("❌ Ошибка выполнения запроса батча (попытка {}): {}", attempt, e);
                    if attempt < max_retries {
                        let backoff_ms = (1u64 << attempt.min(6)) * 500;
                        info!("⏳ Ожидание {} мс перед повтором...", backoff_ms);
                        tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                        continue;
                    }
                    return Err(anyhow::anyhow!("Ошибка загрузки батча после {} попыток: {}", max_retries, e));
                }
            }
        }
        
        Err(anyhow::anyhow!("Не удалось загрузить батч после {} попыток", max_retries))
    }

    /// Получение общего количества связей
    pub async fn get_total_edges_count(&self) -> Result<usize> {
        info!("🔍 Запрос общего количества связей в БД...");
        
        let query = r#"
        MATCH (a:Article)-[r]->(b:Article)
        WHERE a.uid IS NOT NULL AND b.uid IS NOT NULL 
        RETURN count(r) as total_count
        "#;
        
        info!("📝 Выполнение запроса подсчета связей...");
        let start_query = std::time::Instant::now();
        
        // Попытка с ретраями
        let max_retries = 3;
        for attempt in 1..=max_retries {
            info!("🔄 Попытка {} из {}", attempt, max_retries);
            
            match self.graph.execute(query.into()).await {
                Ok(mut result) => {
                    info!("✅ Запрос выполнен, получение результата...");
                    
                    // Добавляем таймаут для получения результата (60 секунд)
                    let timeout_duration = std::time::Duration::from_secs(60);
                    match tokio::time::timeout(timeout_duration, result.next()).await {
                        Ok(Ok(Some(row))) => {
                            info!("📦 Результат получен, извлечение данных...");
                            if let Ok(count) = row.get::<i64>("total_count") {
                                let query_time = start_query.elapsed();
                                info!("✅ Общее количество связей в БД: {} (время запроса: {:.2?})", count, query_time);
                                return Ok(count as usize);
                            } else {
                                info!("⚠️ Не удалось извлечь count из результата");
                            }
                        }
                        Ok(Ok(None)) => {
                            info!("⚠️ Запрос не вернул результатов");
                        }
                        Ok(Err(e)) => {
                            info!("❌ Ошибка получения результата: {}", e);
                        }
                        Err(_) => {
                            info!("⏱️ Таймаут при получении результата (> {} сек)", timeout_duration.as_secs());
                            if attempt < max_retries {
                                let backoff_ms = (1u64 << attempt.min(6)) * 500;
                                info!("⏳ Ожидание {} мс перед повтором...", backoff_ms);
                                tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                                continue;
                            }
                            return Err(anyhow::anyhow!("Таймаут при получении результата после {} попыток", max_retries));
                        }
                    }
                }
                Err(e) => {
                    info!("❌ Ошибка выполнения запроса (попытка {}): {}", attempt, e);
                    if attempt < max_retries {
                        let backoff_ms = (1u64 << attempt.min(6)) * 500;
                        info!("⏳ Ожидание {} мс перед повтором...", backoff_ms);
                        tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                        continue;
                    }
                    return Err(anyhow::anyhow!("Ошибка выполнения запроса после {} попыток: {}", max_retries, e));
                }
            }
        }
        
        Err(anyhow::anyhow!("Не удалось получить количество связей после {} попыток", max_retries))
    }
    
    /// Сохранение результатов укладки в Neo4j
    pub async fn save_layout_results(&self, positions: &[VertexPosition]) -> Result<()> {
        self.save_layout_results_with_batch_size(positions, 1000).await
    }

    /// Сохранение результатов укладки в Neo4j с настраиваемым размером батча
    pub async fn save_layout_results_with_batch_size(&self, positions: &[VertexPosition], batch_size: usize) -> Result<()> {
        use neo4rs::Query;
        use std::collections::HashMap;

        info!("💾 Сохранение результатов укладки в Neo4j: {} позиций", positions.len());
        
        if positions.is_empty() {
            info!("⚠️ Нет позиций для сохранения");
            return Ok(());
        }

        // 0) Убедимся, что есть индекс по uid для быстрого MATCH
        let ensure_index = Query::new(
            "CREATE INDEX article_uid IF NOT EXISTS FOR (a:Article) ON (a.uid)".to_string()
        );
        let _ = self.graph.execute(ensure_index).await; // best-effort

        // Батчевое сохранение с прогресс-индикатором и UNWIND
        let total_positions = positions.len();
        let total_batches = (total_positions + batch_size - 1) / batch_size;
        info!("🔄 Батчевое сохранение: {} батчей по {} позиций", total_batches, batch_size);
        let start_time = std::time::Instant::now();

        // Ограничим параллелизм, чтобы не перегрузить пул соединений
        // Читаем параллелизм из конфигурации, по умолчанию 4
        let max_parallel = 2; // Фиксированное значение для стабильности
        let semaphore = std::sync::Arc::new(tokio::sync::Semaphore::new(max_parallel));

        let mut join_handles = Vec::with_capacity(total_batches);
        for batch_num in 0..total_batches {
            let permit = semaphore.clone().acquire_owned().await?;
            let graph = self.graph.clone();

            let start_idx = batch_num * batch_size;
            let end_idx = (start_idx + batch_size).min(total_positions);

            // Копируем слайс для таска
            let slice = positions[start_idx..end_idx].to_vec();

            let handle = tokio::spawn(async move {
                let _permit = permit;
                // Транзакция на батч
                // Ретраи с экспоненциальной задержкой
                let mut attempt = 0u32;
                let max_attempts = 5u32;
                loop {
                    let mut txn = match graph.start_txn().await {
                        Ok(t) => t,
                        Err(e) => {
                            if attempt >= max_attempts { return Err(anyhow::anyhow!(e)); }
                            attempt += 1;
                            let backoff_ms = (1u64 << attempt.min(6)) * 100;
                            tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                            continue;
                        }
                    };

                    let mut rows: Vec<HashMap<String, BoltType>> = Vec::with_capacity(slice.len());
                    for p in &slice {
                        let mut m: HashMap<String, BoltType> = HashMap::new();
                        m.insert("uid".to_string(), p.article_id.clone().into());
                        m.insert("layer".to_string(), (p.layer as i64).into());
                        m.insert("level".to_string(), (p.level as i64).into());
                        m.insert("x".to_string(), (p.x as f64).into());
                        m.insert("y".to_string(), (p.y as f64).into());
                        rows.push(m);
                    }

                    let q = Query::new(
                        "UNWIND $rows AS row \
                        MATCH (a:Article {uid: row.uid}) \
                        SET a.layer = row.layer, a.level = row.level, a.x = row.x, a.y = row.y".to_string()
                    ).param("rows", rows);

                    match txn.run(q).await {
                        Ok(_) => {
                            if let Err(e) = txn.commit().await {
                                if attempt >= max_attempts { return Err(anyhow::anyhow!(e)); }
                                attempt += 1;
                                let backoff_ms = (1u64 << attempt.min(6)) * 100;
                                tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                                continue;
                            }
                            break anyhow::Ok(());
                        }
                        Err(e) => {
                            if attempt >= max_attempts { return Err(anyhow::anyhow!(e)); }
                            attempt += 1;
                            let backoff_ms = (1u64 << attempt.min(6)) * 100;
                            tokio::time::sleep(std::time::Duration::from_millis(backoff_ms)).await;
                        }
                    }
                }
            });

            join_handles.push((batch_num, start_idx, end_idx, handle));

            // Логируем прогресс на основании завершения задач
            // (ниже after-await loop)
        }

        // Собираем результаты и логируем прогресс по мере завершения
        let mut completed = 0usize;
        for (batch_num, start_idx, end_idx, handle) in join_handles {
            let res = handle.await;
            if let Err(e) = res {
                return Err(anyhow::anyhow!("Ошибка сохранения батча {}: {}", batch_num + 1, e));
            }
            if let Err(e) = res.unwrap() {
                return Err(anyhow::anyhow!("Ошибка выполнения транзакции батча {}: {}", batch_num + 1, e));
            }

            completed = end_idx;
            let progress = (completed as f64 / total_positions as f64) * 100.0;
            let elapsed = start_time.elapsed();
            let rate = (completed as f64 / elapsed.as_secs_f64()).max(0.0);
            info!("📥 Сохранение батча {}/{} (позиции {}-{})", batch_num + 1, total_batches, start_idx, end_idx.saturating_sub(1));
            info!("📊 Прогресс сохранения: {:.1}% ({}/{} позиций, {:.0} позиций/сек)", progress, completed, total_positions, rate);
        }

        let total_time = start_time.elapsed();
        let rate = total_positions as f64 / total_time.as_secs_f64();
        info!("✅ Результаты укладки сохранены в Neo4j за {:.2?} (скорость: {:.0} позиций/сек)", total_time, rate);
        Ok(())
    }
    
    /// Проверка здоровья соединения (заглушка)
    pub async fn health_check(&self) -> Result<()> {
        let connected = self.connected.read().await;
        if *connected {
            Ok(())
        } else {
            Err(anyhow::anyhow!("Neo4j не подключен"))
        }
    }
}

/// Структура для представления связи графа
#[derive(Debug, Clone)]
pub struct GraphEdge {
    pub source_id: String,
    pub target_id: String,
    pub weight: f32,
    pub edge_type: String,
}

/// Структура для представления позиции вершины
#[derive(Debug, Clone)]
pub struct VertexPosition {
    pub article_id: String,
    pub layer: i32,
    pub level: i32,
    pub x: f32,
    pub y: f32,
}