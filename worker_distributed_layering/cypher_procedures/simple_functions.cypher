// =============================================================================
// Базовые индексы для производительности
// =============================================================================

// 1. Индекс для узлов Article по uid
CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.uid);

// 2. Индекс для узлов Article по is_pinned
CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.is_pinned);

// 3. Индекс для связей CITES по uid
CREATE INDEX IF NOT EXISTS FOR ()-[r:BIBLIOGRAPHIC_LINK]-() ON (r.uid);

// 4. Составной индекс для укладки
CREATE INDEX IF NOT EXISTS FOR (n:Article) ON (n.level, n.layer, n.is_pinned);
