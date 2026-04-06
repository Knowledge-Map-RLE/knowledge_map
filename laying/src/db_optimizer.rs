/*!
# Database Optimizer Module

Модуль для автоматической проверки и создания индексов в Neo4j,
а также применения оптимизаций базы данных перед запуском укладки графа.
*/

use anyhow::{Context, Result};
use neo4rs::{Graph, query};
use std::sync::Arc;
use tracing::{info, warn};

/// Структура для управления оптимизацией базы данных
pub struct DatabaseOptimizer {
    graph: Arc<Graph>,
}

/// Описание индекса для создания
struct IndexDefinition {
    name: String,
    label: String,
    properties: Vec<String>,
    description: String,
}

impl DatabaseOptimizer {
    /// Создать новый оптимизатор БД
    pub fn new(graph: Arc<Graph>) -> Self {
        Self { graph }
    }

    /// Проверить и создать все необходимые индексы
    pub async fn ensure_indexes(&self) -> Result<()> {
        info!("🔍 Проверка индексов Neo4j...");

        // Получить список существующих индексов
        let existing_indexes = self.get_existing_indexes().await?;
        info!("📊 Найдено существующих индексов: {}", existing_indexes.len());

        // Определить необходимые индексы
        let required_indexes = self.get_required_indexes();
        info!("📋 Требуется индексов: {}", required_indexes.len());

        // Создать недостающие индексы
        let mut created_count = 0;
        let mut skipped_count = 0;

        for index_def in required_indexes {
            if existing_indexes.contains(&index_def.name) {
                info!("✅ Индекс '{}' уже существует", index_def.name);
                skipped_count += 1;
            } else {
                info!("🔧 Создание индекса '{}': {}", index_def.name, index_def.description);
                self.create_index(&index_def).await?;
                created_count += 1;
            }
        }

        info!(
            "✨ Индексы готовы: создано {}, пропущено {} (уже существуют)",
            created_count, skipped_count
        );

        Ok(())
    }

    /// Применить оптимизации к базе данных
    pub async fn apply_optimizations(&self) -> Result<()> {
        info!("⚡ Применение оптимизаций Neo4j...");

        // Проверка существующих ограничений
        self.ensure_constraints().await?;

        // Статистика базы
        self.log_database_stats().await?;

        info!("✅ Оптимизации применены");
        Ok(())
    }

    /// Получить список существующих индексов
    async fn get_existing_indexes(&self) -> Result<Vec<String>> {
        let query = query("SHOW INDEXES");
        let mut result = self.graph.execute(query).await?;

        let mut indexes = Vec::new();
        while let Some(row) = result.next().await? {
            if let Ok(name) = row.get::<String>("name") {
                indexes.push(name);
            }
        }

        Ok(indexes)
    }

    /// Определить необходимые индексы
    fn get_required_indexes(&self) -> Vec<IndexDefinition> {
        vec![
            IndexDefinition {
                name: "article_uid_unique".to_string(),
                label: "Article".to_string(),
                properties: vec!["uid".to_string()],
                description: "Уникальный индекс на UID статьи (constraint)".to_string(),
            },
            IndexDefinition {
                name: "article_layer_level".to_string(),
                label: "Article".to_string(),
                properties: vec!["layer".to_string(), "level".to_string()],
                description: "Составной индекс на layer и level для фильтрации".to_string(),
            },
            IndexDefinition {
                name: "article_coordinates".to_string(),
                label: "Article".to_string(),
                properties: vec!["x".to_string(), "y".to_string()],
                description: "Составной индекс на координаты x, y для сортировки по расстоянию".to_string(),
            },
            IndexDefinition {
                name: "article_topo_order".to_string(),
                label: "Article".to_string(),
                properties: vec!["topo_order".to_string()],
                description: "Индекс на топологический порядок для сортировки".to_string(),
            },
            IndexDefinition {
                name: "article_layout_status".to_string(),
                label: "Article".to_string(),
                properties: vec!["layout_status".to_string()],
                description: "Индекс на статус укладки для фильтрации".to_string(),
            },
        ]
    }

    /// Создать индекс
    async fn create_index(&self, index_def: &IndexDefinition) -> Result<()> {
        // Для constraint (уникальный индекс) используем другой синтаксис
        let cypher = if index_def.name == "article_uid_unique" {
            // Constraint уже может быть создан, проверяем его отдельно
            match self.check_constraint_exists("Article", "uid").await {
                Ok(true) => {
                    info!("✅ Constraint на Article.uid уже существует");
                    return Ok(());
                }
                Ok(false) => {
                    format!(
                        "CREATE CONSTRAINT {} IF NOT EXISTS FOR (n:{}) REQUIRE n.uid IS UNIQUE",
                        index_def.name, index_def.label
                    )
                }
                Err(e) => {
                    warn!("⚠️ Не удалось проверить constraint: {}", e);
                    format!(
                        "CREATE CONSTRAINT {} IF NOT EXISTS FOR (n:{}) REQUIRE n.uid IS UNIQUE",
                        index_def.name, index_def.label
                    )
                }
            }
        } else {
            // Обычный индекс
            let properties_str = index_def
                .properties
                .iter()
                .map(|p| format!("n.{}", p))
                .collect::<Vec<_>>()
                .join(", ");

            format!(
                "CREATE INDEX {} IF NOT EXISTS FOR (n:{}) ON ({})",
                index_def.name, index_def.label, properties_str
            )
        };

        info!("📝 Выполняем: {}", cypher);

        let query = query(&cypher);
        self.graph.run(query).await.context(format!(
            "Не удалось создать индекс '{}'",
            index_def.name
        ))?;

        info!("✅ Индекс '{}' создан", index_def.name);
        Ok(())
    }

    /// Проверить существование constraint
    async fn check_constraint_exists(&self, label: &str, property: &str) -> Result<bool> {
        let query = query("SHOW CONSTRAINTS");
        let mut result = self.graph.execute(query).await?;

        while let Some(row) = result.next().await? {
            if let (Ok(labels), Ok(properties)) = (
                row.get::<Vec<String>>("labelsOrTypes"),
                row.get::<Vec<String>>("properties"),
            ) {
                if labels.contains(&label.to_string()) && properties.contains(&property.to_string()) {
                    return Ok(true);
                }
            }
        }

        Ok(false)
    }

    /// Обеспечить существование constraints
    async fn ensure_constraints(&self) -> Result<()> {
        info!("🔒 Проверка constraints...");

        // UID должен быть уникальным
        if !self.check_constraint_exists("Article", "uid").await? {
            info!("🔧 Создание UNIQUE constraint на Article.uid...");
            let query = query(
                "CREATE CONSTRAINT article_uid_unique IF NOT EXISTS \
                 FOR (n:Article) REQUIRE n.uid IS UNIQUE"
            );
            self.graph.run(query).await?;
            info!("✅ Constraint на Article.uid создан");
        } else {
            info!("✅ Constraint на Article.uid уже существует");
        }

        Ok(())
    }

    /// Вывести статистику базы данных
    async fn log_database_stats(&self) -> Result<()> {
        info!("📊 Сбор статистики базы данных...");

        // Количество статей
        let articles_query = query("MATCH (n:Article) RETURN count(n) as count");
        let mut articles_result = self.graph.execute(articles_query).await?;
        if let Some(row) = articles_result.next().await? {
            let count: i64 = row.get("count")?;
            info!("📄 Статей в базе: {}", count);
        }

        // Количество связей
        let links_query = query("MATCH ()-[r:BIBLIOGRAPHIC_LINK]->() RETURN count(r) as count");
        let mut links_result = self.graph.execute(links_query).await?;
        if let Some(row) = links_result.next().await? {
            let count: i64 = row.get("count")?;
            info!("🔗 Библиографических связей: {}", count);
        }

        // Статьи с координатами
        let positioned_query = query(
            "MATCH (n:Article) WHERE n.layer IS NOT NULL AND n.level IS NOT NULL \
             AND n.x IS NOT NULL AND n.y IS NOT NULL RETURN count(n) as count"
        );
        let mut positioned_result = self.graph.execute(positioned_query).await?;
        if let Some(row) = positioned_result.next().await? {
            let count: i64 = row.get("count")?;
            info!("📍 Статей с позициями: {}", count);
        }

        Ok(())
    }

    /// Полная проверка и оптимизация перед запуском укладки
    pub async fn prepare_database(&self) -> Result<()> {
        info!("🚀 Подготовка базы данных к укладке...");
        info!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

        self.ensure_indexes().await?;
        self.apply_optimizations().await?;

        info!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
        info!("✅ База данных готова к укладке");

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_required_indexes() {
        let graph = Graph::new("bolt://localhost:7687", "neo4j", "password")
            .await
            .unwrap();
        let optimizer = DatabaseOptimizer::new(graph);
        let indexes = optimizer.get_required_indexes();

        assert!(!indexes.is_empty());
        assert!(indexes.iter().any(|i| i.name == "article_uid_unique"));
        assert!(indexes.iter().any(|i| i.name == "article_coordinates"));
    }
}
