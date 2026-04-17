/**
 * DependencyNgramTable — таблица dependency n-gram паттернов из Neo4j.
 * Два режима: «Цепочки» (абстрактные токены) и «Контекст» (цепочки предложений).
 */
import { useState, useCallback } from 'react';
import { getDependencyNgrams, getPatternContext } from '../../../services/api';
import type { DependencyNgramResponse, PatternContextResponse } from '../../../services/api';
import s from './DependencyNgramTable.module.css';

type ViewMode = 'chains' | 'context';

export default function DependencyNgramTable() {
    const [data, setData] = useState<DependencyNgramResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [maxDepth, setMaxDepth] = useState(5);
    const [limitPerN, setLimitPerN] = useState(50);
    const [activeSection, setActiveSection] = useState<string>('unigrams');
    const [viewMode, setViewMode] = useState<ViewMode>('chains');

    // Контекст: key = sig_hash, value = {loading, instances: {node_ids, sentences}[]}
    const [contextCache, setContextCache] = useState<Record<string, { loading: boolean; instances: PatternContextResponse[] }>>({});

    const runAnalysis = async () => {
        setLoading(true);
        setError(null);
        setContextCache({});
        try {
            const result = await getDependencyNgrams(maxDepth, limitPerN);
            setData(result);
            if (result.unigrams.length === 0) {
                const firstNgram = Object.keys(result.n_grams)[0];
                if (firstNgram) setActiveSection(firstNgram);
                else if (result.cross_doc.length > 0) setActiveSection('cross_doc');
            } else {
                setActiveSection('unigrams');
            }
        } catch (err: any) {
            setError(err.message || 'Ошибка загрузки паттернов');
        } finally {
            setLoading(false);
        }
    };

    const loadContext = useCallback(async (sigHash: string, exemplars: number[][]) => {
        if (contextCache[sigHash]) return;
        setContextCache(prev => ({ ...prev, [sigHash]: { loading: true, instances: [] } }));

        const instances: PatternContextResponse[] = [];
        for (const chain of exemplars) {
            try {
                const ctx = await getPatternContext(chain);
                instances.push(ctx);
            } catch {
                // Пропускаем ошибки отдельных цепочек
            }
        }

        setContextCache(prev => ({ ...prev, [sigHash]: { loading: false, instances } }));
    }, [contextCache]);

    const formatChain = (chain: string[][]) => {
        if (!chain || chain.length === 0) return '—';
        const parts = chain.map(([tok, dep]) => `${tok} (${dep})`);
        const lastHead = chain[chain.length - 1]?.[2];
        if (lastHead) parts.push(lastHead);
        return parts.join(' → ');
    };

    const formatLongChain = (texts: string[], relTypes: string[]) => {
        if (!texts || texts.length === 0) return '—';
        const parts: string[] = [];
        for (let i = 0; i < relTypes.length && i < texts.length - 1; i++) {
            parts.push(`${texts[i]} (${relTypes[i]})`);
        }
        parts.push(texts[texts.length - 1]);
        return parts.join(' → ');
    };

    const sections = data ? ['unigrams', ...Object.keys(data.n_grams), 'long_chains', 'cross_doc'].filter(
        (key) => {
            if (key === 'cross_doc') return data.cross_doc.length > 0;
            if (key === 'long_chains') return data.long_chains && data.long_chains.length > 0;
            return true;
        }
    ) : [];

    // Render context accordion for a single pattern
    const renderContextAccordion = (sigHash: string, exemplars: number[][], cnt: number) => {
        const cache = contextCache[sigHash];
        const hasExemplars = exemplars && exemplars.length > 0;

        return (
            <details className={s.accordion} onToggle={(e) => {
                const details = e.currentTarget;
                if (details.open && !cache && hasExemplars) {
                    loadContext(sigHash, exemplars);
                }
            }}>
                <summary className={s.accordionSummary}>
                    <span className={s.accordionIcon}>▶</span>
                    <span>{cnt} instances</span>
                </summary>
                <div className={s.accordionContent}>
                    {!hasExemplars && <p className={s.empty}>Нет доступных экземпляров для этого паттерна.</p>}
                    {cache?.loading && (
                        <div className={s.loading}>
                            <div className={s.spinner}></div>
                            <p>Загрузка контекста...</p>
                        </div>
                    )}
                    {cache && !cache.loading && cache.instances.map((inst, i) => (
                        <div key={i} className={s.instanceRow}>
                            <span className={s.chainNumber}>#{i + 1}</span>
                            <div className={s.sentenceChain}>
                                {inst.sentences.map((sent, j) => (
                                    <div key={j} className={s.sentence}>
                                        {sent || <em className={s.noSentence}>нет предложения</em>}
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </details>
        );
    };

    return (
        <div className={s.container}>
            {/* Controls */}
            <div className={s.controls}>
                <div className={s.controlGroup}>
                    <label htmlFor="maxDepth">Глубина (1-10):</label>
                    <input
                        id="maxDepth"
                        type="number"
                        min={1}
                        max={10}
                        value={maxDepth}
                        onChange={(e) => setMaxDepth(Math.max(1, Math.min(10, parseInt(e.target.value) || 5)))}
                        className={s.numberInput}
                    />
                </div>
                <div className={s.controlGroup}>
                    <label htmlFor="limitPerN">Лимит на N:</label>
                    <input
                        id="limitPerN"
                        type="number"
                        min={10}
                        max={1000}
                        value={limitPerN}
                        onChange={(e) => setLimitPerN(Math.max(10, Math.min(1000, parseInt(e.target.value) || 50)))}
                        className={s.numberInput}
                    />
                </div>
                <div className={s.modeToggle}>
                    <button
                        className={`${s.modeBtn} ${viewMode === 'chains' ? s.active : ''}`}
                        onClick={() => setViewMode('chains')}
                    >
                        Цепочки
                    </button>
                    <button
                        className={`${s.modeBtn} ${viewMode === 'context' ? s.active : ''}`}
                        onClick={() => setViewMode('context')}
                    >
                        Контекст
                    </button>
                </div>
                <button
                    onClick={runAnalysis}
                    disabled={loading}
                    className={s.analyzeButton}
                >
                    {loading ? 'Анализ...' : 'Анализировать'}
                </button>
            </div>

            {/* Loading */}
            {loading && (
                <div className={s.loading}>
                    <div className={s.spinner}></div>
                    <p>Поиск dependency n-gram паттернов в Neo4j...</p>
                    <p className={s.hint}>Это может занять несколько секунд при большом количестве данных</p>
                </div>
            )}

            {/* Error */}
            {error && <div className={s.error}><p>Ошибка: {error}</p></div>}

            {/* Results */}
            {data && !loading && (
                <div className={s.results}>
                    {/* Section tabs */}
                    <div className={s.sectionTabs}>
                        {sections.map((section) => (
                            <button
                                key={section}
                                className={`${s.sectionTab} ${activeSection === section ? s.active : ''}`}
                                onClick={() => setActiveSection(section)}
                            >
                                {section === 'unigrams' ? '1-граммы' :
                                 section === 'cross_doc' ? 'Кросс-док' :
                                 section === 'long_chains' ? 'Длинные' :
                                 section.replace('-grams', '-граммы')}
                            </button>
                        ))}
                    </div>

                    {/* Table */}
                    <div className={s.tableWrapper}>
                        {activeSection === 'unigrams' && (
                            <table className={s.table}>
                                <thead>
                                    <tr>
                                        <th>Тип</th>
                                        <th>POS</th>
                                        <th>Lemma</th>
                                        <th>Частота</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.unigrams.map((row, i) => (
                                        <tr key={i}>
                                            <td><span className={`${s.posTag} ${s[`type_${row.node_type?.toLowerCase()}`] || ''}`}>{row.node_type || '—'}</span></td>
                                            <td><span className={s.posTag}>{row.pos || '—'}</span></td>
                                            <td>{row.lemma || '—'}</td>
                                            <td className={s.count}>{row.cnt}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}

                        {activeSection !== 'unigrams' && activeSection !== 'cross_doc' && activeSection !== 'long_chains' && data.n_grams[activeSection] && (
                            <table className={s.table}>
                                <thead>
                                    <tr>
                                        <th style={{ width: viewMode === 'context' ? '50%' : '70%' }}>Паттерн (цепочка)</th>
                                        <th>Частота</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.n_grams[activeSection].map((row, i) => (
                                        <tr key={i}>
                                            {viewMode === 'context' ? (
                                                <>
                                                    <td>{formatChain(row.chain)}</td>
                                                    <td className={s.count}>
                                                        {renderContextAccordion(row.sig_hash, row.exemplars || [], row.cnt)}
                                                    </td>
                                                </>
                                            ) : (
                                                <>
                                                    <td className={s.chainCell} title={formatChain(row.chain)}>
                                                        {formatChain(row.chain)}
                                                    </td>
                                                    <td className={s.count}>{row.cnt}</td>
                                                </>
                                            )}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}

                        {activeSection === 'long_chains' && data.long_chains && data.long_chains.length > 0 && (
                            <table className={s.table}>
                                <thead>
                                    <tr>
                                        <th style={{ width: viewMode === 'context' ? '50%' : '70%' }}>Паттерн</th>
                                        <th>Глубина</th>
                                        <th>Частота</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.long_chains.map((row, i) => (
                                        <tr key={i}>
                                            {viewMode === 'context' ? (
                                                <>
                                                    <td>{formatLongChain(row.texts, row.deps)}</td>
                                                    <td>{row.depth}</td>
                                                    <td className={s.count}>
                                                        {renderContextAccordion(row.sig_hash, row.exemplars || [], row.cnt)}
                                                    </td>
                                                </>
                                            ) : (
                                                <>
                                                    <td className={s.chainCell} title={formatLongChain(row.texts, row.deps)}>
                                                        {formatLongChain(row.texts, row.deps)}
                                                    </td>
                                                    <td>{row.depth}</td>
                                                    <td className={s.count}>{row.cnt}</td>
                                                </>
                                            )}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}

                        {activeSection === 'cross_doc' && (
                            <table className={s.table}>
                                <thead>
                                    <tr>
                                        <th style={{ width: '60%' }}>Паттерн (леммы)</th>
                                        <th>Глубина</th>
                                        <th>Частота</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {data.cross_doc.map((row, i) => (
                                        <tr key={i}>
                                            <td className={s.chainCell} title={row.lemmas.join(' → ')}>
                                                {row.lemmas.join(' → ')}
                                            </td>
                                            <td>{row.depth}</td>
                                            <td className={s.count}>{row.cnt}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}

                        {data.unigrams.length === 0 &&
                         Object.keys(data.n_grams).length === 0 &&
                         (!data.long_chains || data.long_chains.length === 0) &&
                         data.cross_doc.length === 0 && (
                            <div className={s.empty}>
                                <p>Паттерны не найдены. Убедитесь что в Neo4j есть данные LexicalUnit с связями DEPENDS_ON.</p>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
