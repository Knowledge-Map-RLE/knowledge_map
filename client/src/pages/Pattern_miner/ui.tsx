import React, { useCallback, useEffect, useState } from 'react';
import Header from '../../widgets/Header';
import {
    listMinerDocuments,
    minePatterns,
    applyPattern,
    generateKnowledge,
} from '../../services/api/pattern_miner';
import type {
    PatternMinerPattern,
    CorpusDocument,
    ApplyPatternResult,
    GapCandidate,
    GenerationGroup,
    KnowledgeCheck,
    GenerateAllMethod,
} from '../../services/api/pattern_miner';
import { DEFAULT_PARAMS, PREDICATE_MODES, labelForNode } from './model';
import type { PatternMinerParams } from './model';
import styles from './PatternMiner.module.css';

const PatternMinerPage: React.FC = () => {
    const [params, setParams] = useState<PatternMinerParams>(DEFAULT_PARAMS);
    const [documents, setDocuments] = useState<CorpusDocument[]>([]);
    const [selectedDocId, setSelectedDocId] = useState<string>('');

    const [patterns, setPatterns] = useState<PatternMinerPattern[]>([]);
    const [selectedPattern, setSelectedPattern] = useState<PatternMinerPattern | null>(null);

    const [corpusSize, setCorpusSize] = useState(0);
    const [mining, setMining] = useState(false);
    const [applying, setApplying] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [applyResult, setApplyResult] = useState<ApplyPatternResult | null>(null);
    const [generation, setGeneration] = useState<GenerateAllMethod[] | null>(null);
    const [generationPool, setGenerationPool] = useState<number>(0);
    const [generationCorpus, setGenerationCorpus] = useState<number>(0);

    const loadDocuments = useCallback(async () => {
        try {
            const res = await listMinerDocuments();
            setDocuments(res.documents ?? []);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Не удалось загрузить документы');
        }
    }, []);

    useEffect(() => {
        loadDocuments();
    }, [loadDocuments]);

    const handleMine = useCallback(async () => {
        setMining(true);
        setError(null);
        setPatterns([]);
        setSelectedPattern(null);
        setApplyResult(null);
        try {
            const res = await minePatterns({
                min_support: params.minSupport,
                min_size: params.minSize,
                max_size: params.maxSize,
                limit: params.limit,
                predicate_mode: params.predicateMode,
                useful_only: params.usefulOnly,
                statements_per_doc_cap: params.statementsPerDocCap,
                max_nodes: params.maxNodes,
            });
            setPatterns(res.patterns ?? []);
            setCorpusSize(res.corpus_size ?? 0);
            setSelectedPattern(res.patterns?.[0] ?? null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Ошибка майнинга паттернов');
        } finally {
            setMining(false);
        }
    }, [params]);

    const handleApply = useCallback(async () => {
        if (!selectedPattern) return;
        if (!selectedDocId) {
            setError('Выберите целевой документ');
            return;
        }
        setApplying(true);
        setError(null);
        setApplyResult(null);
        try {
            const res = await applyPattern({
                doc_id: selectedDocId,
                pattern: selectedPattern
                    ? {
                          id: selectedPattern.id,
                          size: selectedPattern.size,
                          edges_count: selectedPattern.edges_count,
                          support: selectedPattern.support,
                          nodes: selectedPattern.nodes,
                          edges: selectedPattern.edges,
                      }
                    : undefined,
                predicate_mode: params.predicateMode,
                max_nodes: params.maxNodes,
                knowledge_method: 'pattern',
            });
            if (!res.success) {
                setError(res.message ?? 'Не удалось наложить паттерн');
            } else {
                setApplyResult(res.result ?? null);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Ошибка наложения паттерна');
        } finally {
            setApplying(false);
        }
    }, [selectedPattern, selectedDocId, params.predicateMode, params.maxNodes]);

    const handleGenerate = useCallback(async () => {
        setGenerating(true);
        setError(null);
        setGeneration(null);
        try {
            const res = await generateKnowledge({
                predicate_mode: params.predicateMode,
                check_existing: true,
                limit_per_method: Math.min(30, params.limit),
                max_nodes: params.maxNodes,
                min_support: params.minSupport,
                min_size: params.minSize,
                max_size: params.maxSize,
                statements_per_doc_cap: params.statementsPerDocCap,
            });
            if (!res.success) {
                setError(res.message ?? 'Не удалось сгенерировать знание');
            } else {
                setGeneration(res.methods ?? []);
                setGenerationPool(res.corpus_pool_size ?? 0);
                setGenerationCorpus(res.corpus_size ?? 0);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Ошибка генерации знания');
        } finally {
            setGenerating(false);
        }
    }, [params]);

    const patternSupportRatio = (p: PatternMinerPattern) =>
        `${p.support}/${corpusSize || '?'}`;

    const renderGraphPreview = (g: { nodes: string[]; edges: [number, number, string][] }) => (
        <div className={styles.graphPreview}>
            {g.edges.length === 0 && <span className={styles.muted}>нет рёбер</span>}
            {g.edges.map(([u, v, el], i) => (
                <div key={i} className={styles.edgeRow}>
                    <span className={styles.nodeChip}>{labelForNode(g.nodes[u])}</span>
                    <span className={styles.edgeArrow}>—[{el}]→</span>
                    <span className={styles.nodeChip}>{labelForNode(g.nodes[v])}</span>
                </div>
            ))}
        </div>
    );

    const renderGaps = (gaps: GapCandidate[]) => (
        <div className={styles.gapsBlock}>
            <div className={styles.sectionTitle}>Кандидаты на новое знание ({gaps.length})</div>
            {gaps.length === 0 && <span className={styles.muted}>Пробелов не найдено</span>}
            {gaps.map((g, i) => (
                <div key={i} className={styles.gapCard}>
                    <code>{g.subject_text}</code>
                    <span className={styles.gapPredicate}>—[{g.predicate}]→</span>
                    <code>{g.object_text}</code>
                </div>
            ))}
        </div>
    );

    const renderCheckBadge = (check?: KnowledgeCheck) => {
        if (!check) return null;
        const map: Record<KnowledgeCheck['status'], { cls: string; text: string }> = {
            new: { cls: styles.badgeNew, text: 'новое' },
            exists: { cls: styles.badgeExists, text: 'есть в базе' },
            conflicts: { cls: styles.badgeConflicts, text: 'противоречит' },
        };
        const b = map[check.status];
        return <span className={`${styles.checkBadge} ${b.cls}`}>{b.text}</span>;
    };

    const renderStatement = (s: { subject_text: string; predicate: string; object_text: string }, check?: KnowledgeCheck) => (
        <div className={styles.generationStatement}>
            <code>{s.subject_text}</code>
            <span className={styles.gapPredicate}>—[{s.predicate}]→</span>
            <code>{s.object_text}</code>
            {renderCheckBadge(check)}
        </div>
    );

    const renderGenerationGroups = (methodLabel: string, groups: GenerationGroup[]) => (
        <div className={styles.generationList}>
            {groups.map((g, gi) => (
                <div key={gi} className={styles.generationCard}>
                    <div className={styles.generationHeader}>
                        <span className={styles.badgeOk}>{g.operation_label}</span>
                        <span className={styles.muted}>
                            источников: {g.provenance?.source_count ?? g.source_statements.length} · новых: {g.provenance?.new_count ?? g.new_statements.length}
                        </span>
                    </div>
                    {g.description && <div className={styles.generationDesc}>{g.description}</div>}
                    {g.source_statements.length > 0 && (
                        <>
                            <div className={styles.sectionTitleSmall}>Источники</div>
                            <div className={styles.sourceBlock}>
                                {g.source_statements.slice(0, 3).map((s, i) => (
                                    <div key={i} className={styles.sourceStatement}>
                                        {s.subject_text} —[{s.predicate}]→ {s.object_text}
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                    <div className={styles.sectionTitleSmall}>Новые утверждения</div>
                    {g.new_statements.map((s, i) => (
                        <div key={i} className={styles.newStatement}>
                            {renderStatement(s, s.check)}
                        </div>
                    ))}
                </div>
            ))}
        </div>
    );

    const renderGeneration = () => {
        if (!generation) return null;
        return (
            <div className={styles.contentCard}>
                <div className={styles.sectionTitle}>
                    Сгенерированное знание
                    {generationCorpus > 0 ? ` · корпус ${generationCorpus} статей / ${generationPool} утверждений` : ''}
                </div>
                <div className={styles.generationList}>
                    {generation.map((m) => (
                        <div key={m.method} className={styles.methodBlock}>
                            <div className={styles.methodHeader}>
                                <span className={styles.methodBadge}>{m.label}</span>
                                <span className={styles.muted}>новых: {m.count}</span>
                            </div>
                            {renderGenerationGroups(m.label, m.groups)}
                        </div>
                    ))}
                    {generation.length === 0 && <span className={styles.muted}>Новых знаний не получено</span>}
                </div>
            </div>
        );
    };

    return (
        <div className={styles.page}>
            <Header showSearch className={styles.header} />
            <main className={styles.main}>
                <aside className={styles.controls}>
                    <div className={styles.sectionTitle}>Корпус графа утверждений</div>

                    <label className={styles.field}>
                        <span>Порог поддержки (доля корпуса)</span>
                        <input
                            type="number"
                            step={0.05}
                            min={0.05}
                            max={1}
                            value={params.minSupport}
                            onChange={(e) => setParams({ ...params, minSupport: parseFloat(e.target.value) })}
                        />
                    </label>

                    <label className={styles.field}>
                        <span>Размер паттерна (узлов)</span>
                        <div className={styles.row}>
                            <input
                                type="number"
                                min={1}
                                max={8}
                                value={params.minSize}
                                onChange={(e) => setParams({ ...params, minSize: parseInt(e.target.value, 10) })}
                            />
                            <span className={styles.muted}>…</span>
                            <input
                                type="number"
                                min={2}
                                max={8}
                                value={params.maxSize}
                                onChange={(e) => setParams({ ...params, maxSize: parseInt(e.target.value, 10) })}
                            />
                        </div>
                    </label>

                    <label className={styles.field}>
                        <span>Лимиты графа статьи</span>
                        <div className={styles.row}>
                            <input
                                type="number"
                                min={10}
                                max={2000}
                                value={params.statementsPerDocCap}
                                title="Макс. утверждений на статью (сэмплинг)"
                                onChange={(e) => setParams({ ...params, statementsPerDocCap: parseInt(e.target.value, 10) })}
                            />
                            <span className={styles.muted}>утв.</span>
                            <input
                                type="number"
                                min={10}
                                max={5000}
                                value={params.maxNodes}
                                title="Макс. узлов графа статьи"
                                onChange={(e) => setParams({ ...params, maxNodes: parseInt(e.target.value, 10) })}
                            />
                            <span className={styles.muted}>узл.</span>
                        </div>
                    </label>

                    <label className={styles.field}>
                        <span>Нормализация предикатов</span>
                        <select
                            value={params.predicateMode}
                            onChange={(e) => setParams({ ...params, predicateMode: e.target.value as PatternMinerParams['predicateMode'] })}
                        >
                            {PREDICATE_MODES.map((m) => (
                                <option key={m.value} value={m.value}>{m.label}</option>
                            ))}
                        </select>
                    </label>

                    <label className={styles.fieldCheckbox}>
                        <input
                            type="checkbox"
                            checked={params.usefulOnly}
                            onChange={(e) => setParams({ ...params, usefulOnly: e.target.checked })}
                        />
                        <span>Только нетривиальные паттерны</span>
                    </label>

                    <button className={styles.primaryButton} onClick={handleMine} disabled={mining}>
                        {mining ? 'Майнинг…' : 'Выявить паттерны'}
                    </button>

                    <button className={styles.generateButton} onClick={handleGenerate} disabled={generating}>
                        {generating ? 'Генерация знаний…' : 'Сгенерировать знание'}
                    </button>

                    {generating && <div className={styles.muted}>Алгоритм обходит все утверждения БД всеми способами…</div>}

                    {corpusSize > 0 && (
                        <div className={styles.muted}>Корпус: статей {corpusSize}, паттернов {patterns.length}</div>
                    )}

                    {patterns.length > 0 && (
                        <>
                            <div className={styles.sectionTitle} style={{ marginTop: 16 }}>Паттерны</div>
                            <div className={styles.patternList}>
                                {patterns.map((p) => (
                                    <button
                                        key={p.id}
                                        className={`${styles.patternCard} ${selectedPattern?.id === p.id ? styles.patternCardActive : ''}`}
                                        onClick={() => setSelectedPattern(p)}
                                    >
                                        <div className={styles.patternCardHeader}>
                                            <span className={styles.patternSize}>{p.size} уз. · {p.edges_count} реб.</span>
                                            <span className={styles.patternSupport}>поддержка {patternSupportRatio(p)}</span>
                                        </div>
                                        <div className={styles.patternExamples}>
                                            {(p.examples ?? []).slice(0, 2).map((ex, i) => (
                                                <div key={i} className={styles.patternExample}>
                                                    {ex.subject_text} —[{ex.predicate}]→ {ex.object_text}
                                                </div>
                                            ))}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        </>
                    )}
                </aside>

                <section className={styles.content}>
                    {error && <div className={styles.errorBox}>{error}</div>}

                    <div className={styles.contentCard}>
                        <div className={styles.sectionTitle}>Целевой документ (для наложения паттерна)</div>
                        <div className={styles.row}>
                            <select
                                className={styles.docSelect}
                                value={selectedDocId}
                                onChange={(e) => setSelectedDocId(e.target.value)}
                            >
                                <option value="">— выберите документ —</option>
                                {documents.map((d) => (
                                    <option key={d.doc_id} value={d.doc_id}>
                                        {d.doc_id} ({d.statements_count} утверждений)
                                    </option>
                                ))}
                            </select>
                            <button className={styles.primaryButton} onClick={handleApply} disabled={applying || !selectedPattern}>
                                {applying ? 'Наложение…' : 'Наложить паттерн'}
                            </button>
                        </div>
                        {!selectedPattern && <div className={styles.muted}>Сначала выявите паттерны (кнопка «Выявить паттерны»).</div>}
                    </div>

                    {renderGeneration()}

                    {applyResult && selectedPattern && (
                        <div className={styles.contentCard}>
                            <div className={styles.sectionTitle}>Результат наложения</div>
                            <div className={styles.metaRow}>
                                Полных совпадений: <b>{applyResult.complete_matches}</b>
                                {' · '}Частичных: <b>{applyResult.partial_matches}</b>
                                {' · '}Узлов цели: <b>{applyResult.target_node_count}</b>
                                {' · '}Рёбер цели: <b>{applyResult.target_edge_count}</b>
                            </div>
                            {renderGaps(applyResult.gaps)}
                            <div className={styles.sectionTitle} style={{ marginTop: 16 }}>
                                Позиции паттерна в графе ({applyResult.embeddings.length})
                            </div>
                            <div className={styles.embeddingList}>
                                {applyResult.embeddings.map((e, i) => (
                                    <div key={i} className={styles.embeddingCard}>
                                        <div className={styles.embeddingHeader}>
                                            <span className={e.complete ? styles.badgeOk : styles.badgeGap}>
                                                {e.complete ? 'полное' : `не хватает ${e.missing_count}`}
                                            </span>
                                            <span className={styles.muted}>
                                                узлы: {Object.values(e.pattern_to_graph).join(', ')}
                                            </span>
                                        </div>
                                        {renderGraphPreview({
                                            nodes: selectedPattern.nodes,
                                            edges: e.missing_edges,
                                        })}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </section>
            </main>
        </div>
    );
};

export default PatternMinerPage;