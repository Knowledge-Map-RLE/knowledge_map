import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { PatternMatchData } from '../../../services/api/uniqueness';
import type { PatternBlockInstance } from '../model';
import { BLOCK_DEFS } from '../model';

interface MatchOverlayProps {
    matches: PatternMatchData[];
    totalMatches: number;
    patternNodeLabels: Record<string, string>;
    patternEdges: {
        source_id: string;
        target_id: string;
        predicate_constraint: string;
    }[];
    blocks: PatternBlockInstance[];
}

interface ChainSegment {
    nodes: string[];
    preds: string[];
}

const panelStyle: React.CSSProperties = {
    padding: '12px',
    border: '2px solid #9C27B0',
    borderRadius: '8px',
    background: '#fff',
    fontSize: '13px',
};

const uidStyles = {
    UID_CSS: `
        .uid-chip { position: relative; display: inline-flex; align-items: center; cursor: default; }
        .uid-tooltip {
            position: fixed;
            z-index: 10000;
            min-width: 180px;
            max-width: 420px;
            background: #1f2937;
            color: #f9fafb;
            border: 1px solid #374151;
            border-radius: 8px;
            padding: 8px 10px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.35);
            font-size: 11px;
            text-align: left;
        }
        .uid-tooltip::before {
            content: '';
            position: absolute;
            top: -6px;
            left: var(--arrow-x, 16px);
            border: 6px solid transparent;
            border-bottom-color: #1f2937;
        }
        .uid-tooltip-title { font-weight: 600; color: #e5e7eb; margin-bottom: 4px; }
        .uid-tooltip-count { color: #9ca3af; font-size: 10px; margin-bottom: 4px; }
        .uid-tooltip-list { max-height: 140px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
        .uid-row { display: flex; align-items: center; gap: 6px; }
        .uid-row code { font-size: 10px; color: #d1d5db; word-break: break-all; flex: 1; }
        .uid-copy {
            flex: 0 0 auto;
            background: #374151;
            color: #e5e7eb;
            border: 1px solid #4b5563;
            border-radius: 4px;
            padding: 1px 6px;
            font-size: 10px;
            cursor: pointer;
        }
        .uid-copy:hover { background: #4b5563; }
        .uid-copied { background: #059669; border-color: #059669; }
    `,
};

/** Содержимое тултипа со списком UUID и кнопками копирования. */
const UidList: React.FC<{ title: string; uids: string[] }> = ({ title, uids }) => {
    const [copied, setCopied] = useState<string | null>(null);

    const copy = useCallback((uid: string) => {
        navigator.clipboard.writeText(uid).catch(() => undefined);
        setCopied(uid);
        window.setTimeout(() => setCopied((c) => (c === uid ? null : c)), 1200);
    }, []);

    if (!uids || uids.length === 0) {
        return (
            <>
                <div className="uid-tooltip-title">{title}</div>
                <div className="uid-tooltip-count">нет привязанных утверждений</div>
            </>
        );
    }

    return (
        <>
            <div className="uid-tooltip-title">{title}</div>
            <div className="uid-tooltip-count">найдено: {uids.length}</div>
            <div className="uid-tooltip-list">
                {uids.map((uid) => (
                    <div className="uid-row" key={uid}>
                        <code>{uid}</code>
                        <button
                            className={`uid-copy ${copied === uid ? 'uid-copied' : ''}`}
                            onClick={(e) => {
                                e.stopPropagation();
                                copy(uid);
                            }}
                            title="Скопировать UUID"
                        >
                            {copied === uid ? '✓' : '⧉'}
                        </button>
                    </div>
                ))}
            </div>
        </>
    );
};

interface UidTooltipProps {
    anchor: HTMLElement;
    title: string;
    uids: string[];
    onMouseEnter: () => void;
    onMouseLeave: () => void;
}

/**
 * Тултип, отрендеренный через portal в document.body с position: fixed.
 * Не обрезается контейнерами (overflow у пунктов/сайдбара) и всегда поверх списка.
 */
const UidTooltip: React.FC<UidTooltipProps> = ({ anchor, title, uids, onMouseEnter, onMouseLeave }) => {
    const ref = useRef<HTMLDivElement>(null);
    const [tick, setTick] = useState(0);

    // Пересчёт позиции при скролле/ресайзе, пока тултип открыт.
    useEffect(() => {
        const repos = () => setTick((t) => t + 1);
        window.addEventListener('scroll', repos, true);
        window.addEventListener('resize', repos);
        return () => {
            window.removeEventListener('scroll', repos, true);
            window.removeEventListener('resize', repos);
        };
    }, []);

    useLayoutEffect(() => {
        if (!anchor || !ref.current) return;
        const a = anchor.getBoundingClientRect();
        const t = ref.current.getBoundingClientRect();
        const gap = 8;
        let top = a.bottom + gap;
        if (top + t.height > window.innerHeight - gap) {
            top = Math.max(gap, a.top - t.height - gap);
        }
        let left = a.left;
        if (left + t.width > window.innerWidth - gap) {
            left = Math.max(gap, window.innerWidth - t.width - gap);
        }
        const el = ref.current;
        el.style.top = `${top}px`;
        el.style.left = `${left}px`;
        el.style.setProperty('--arrow-x', `${Math.max(16, Math.min(a.left + a.width / 2 - left, t.width - 24))}px`);
        el.style.visibility = 'visible';
    }, [anchor, tick]);

    return createPortal(
        <div
            ref={ref}
            className="uid-tooltip"
            style={{ visibility: 'hidden' }}
            onMouseEnter={onMouseEnter}
            onMouseLeave={onMouseLeave}
        >
            <UidList title={title} uids={uids} />
        </div>,
        document.body
    );
};

/** Управление hover: тултип закрывается с небольшой задержкой, чтобы можно было кликнуть в нём. */
function useHoverTooltip() {
    const [open, setOpen] = useState(false);
    const closeTimer = useRef<number | null>(null);

    const cancelClose = useCallback(() => {
        if (closeTimer.current !== null) {
            window.clearTimeout(closeTimer.current);
            closeTimer.current = null;
        }
    }, []);

    const scheduleClose = useCallback(() => {
        cancelClose();
        closeTimer.current = window.setTimeout(() => setOpen(false), 150);
    }, [cancelClose]);

    const openTooltip = useCallback(() => {
        cancelClose();
        setOpen(true);
    }, [cancelClose]);

    return { open, openTooltip, scheduleClose, cancelClose };
}

interface UidChipProps {
    label: string;
    pillStyle: React.CSSProperties;
    uids: string[];
    uidTitle: string;
}

const UidChip: React.FC<UidChipProps> = ({ label, pillStyle, uids, uidTitle }) => {
    const anchorRef = useRef<HTMLSpanElement>(null);
    const { open, openTooltip, scheduleClose, cancelClose } = useHoverTooltip();

    return (
        <span
            ref={anchorRef}
            className="uid-chip"
            style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', cursor: 'default' }}
            onMouseEnter={openTooltip}
            onMouseLeave={scheduleClose}
        >
            <span style={pillStyle}>{label}</span>
            {open && anchorRef.current && (
                <UidTooltip
                    anchor={anchorRef.current}
                    title={uidTitle}
                    uids={uids}
                    onMouseEnter={cancelClose}
                    onMouseLeave={scheduleClose}
                />
            )}
        </span>
    );
};

const NodeChip: React.FC<{ label: string; color: string; uids: string[]; uidTitle: string }> = ({ label, color, uids, uidTitle }) => (
    <UidChip
        label={label}
        uids={uids}
        uidTitle={uidTitle}
        pillStyle={{
            background: color,
            color: '#fff',
            borderRadius: '6px',
            padding: '4px 8px',
            fontSize: '11px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        }}
    />
);

const PredChip: React.FC<{ label: string; uids: string[] }> = ({ label, uids }) => (
    <UidChip
        label={label}
        uids={uids}
        uidTitle="UUID утверждений (Statement)"
        pillStyle={{
            background: '#fff',
            color: '#9C27B0',
            border: '1px dashed #9C27B0',
            borderRadius: '6px',
            padding: '3px 7px',
            fontSize: '11px',
            fontWeight: 600,
            whiteSpace: 'nowrap',
        }}
    />
);

const Arrow: React.FC = () => (
    <span style={{ color: '#999', fontSize: '14px', margin: '0 2px' }}>→</span>
);

/** Строит цепочки (последовательности узлов с предикатами между ними) из паттерна. */
function buildChains(
    p2g: Record<string, string>,
    edges: MatchOverlayProps['patternEdges']
): ChainSegment[] {
    const out: Record<string, typeof edges> = {};
    const indeg: Record<string, number> = {};
    for (const e of edges) {
        if (!(e.source_id in p2g) || !(e.target_id in p2g)) continue;
        (out[e.source_id] = out[e.source_id] ?? []).push(e);
        indeg[e.target_id] = (indeg[e.target_id] ?? 0) + 1;
        indeg[e.source_id] = indeg[e.source_id] ?? 0;
    }

    const nodes = new Set<string>(Object.keys(p2g));
    const used = new Set<string>();
    const chains: ChainSegment[] = [];

    const visit = (start: string) => {
        const arr = [start];
        const preds: string[] = [];
        let cur = start;
        while (out[cur] && out[cur].length > 0) {
            const e = out[cur][0];
            preds.push(e.predicate_constraint);
            cur = e.target_id;
            arr.push(cur);
        }
        arr.forEach((n) => used.add(n));
        if (arr.length > 0) chains.push({ nodes: arr, preds });
    };

    for (const n of nodes) if ((indeg[n] ?? 0) === 0) visit(n);
    for (const n of nodes) if (!used.has(n)) visit(n);

    return chains;
}

/**
 * Визуализация совпадений паттерна в виде структурных строк (subject -[pred]-> object).
 * Каждый найденный элемент — «прямоугольник» узла или связи; при наведении показывает
 * UUID утверждений, где элемент выступает субъектом/объектом, и UUID самих утверждений.
 */
export const MatchOverlay: React.FC<MatchOverlayProps> = ({ matches, totalMatches, patternNodeLabels, patternEdges, blocks }) => {
    const blockTypeById = useCallback(() => {
        const map: Record<string, string> = {};
        blocks.forEach((b) => {
            map[b.id] = b.type;
        });
        return map;
    }, [blocks]);

    if (!matches || matches.length === 0) {
        return (
            <div style={panelStyle}>
                <h4 style={{ margin: '0 0 8px' }}>Результаты поиска</h4>
                <div style={{ fontSize: '12px', color: '#999' }}>
                    Совпадений не найдено — паттерн уникален в графе.
                </div>
            </div>
        );
    }

    const types = blockTypeById();
    return (
        <div style={panelStyle}>
            <style>{uidStyles.UID_CSS}</style>
            <h4 style={{ margin: '0 0 8px' }}>
                Результаты поиска — {totalMatches}{' '}
                {totalMatches === 1 ? 'совпадение' : totalMatches < 5 ? 'совпадения' : 'совпадений'}
            </h4>

            {matches.slice(0, 10).map((m, idx) => {
                const chains = buildChains(m.pattern_to_graph, patternEdges);
                const subjUids = (patternNodeId: string) => m.node_uids?.[patternNodeId]?.as_subject ?? [];
                const objUids = (patternNodeId: string) => m.node_uids?.[patternNodeId]?.as_object ?? [];

                return (
                    <div
                        key={idx}
                        style={{
                            border: '1px solid #e0e0e0',
                            borderRadius: '6px',
                            padding: '8px',
                            margin: '6px 0',
                            background: '#fafafa',
                            overflowX: 'auto',
                        }}
                    >
                        <div style={{ fontSize: '11px', fontWeight: 600, color: '#666', marginBottom: '6px' }}>
                            Совпадение #{idx + 1}
                        </div>

                        {chains.map((chain, ci) => (
                            <div
                                key={ci}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    flexWrap: 'wrap',
                                    gap: '2px',
                                    padding: '2px 0',
                                }}
                            >
                                {chain.nodes.map((pid, ni) => {
                                    const type = types[pid];
                                    const color = type && type in BLOCK_DEFS ? BLOCK_DEFS[type as keyof typeof BLOCK_DEFS].color : '#666';
                                    const isSubject = ni < chain.nodes.length - 1 || chain.nodes.length === 1;
                                    const isObject = ni > 0;

                                    const uids = isSubject && !isObject ? subjUids(pid) : isObject && !isSubject ? objUids(pid) : [...subjUids(pid), ...objUids(pid)];
                                    const uidTitle =
                                        isSubject && !isObject
                                            ? 'UUID концептов-субъектов'
                                            : isObject && !isSubject
                                              ? 'UUID концептов-объектов'
                                              : 'UUID концептов (субъект/объект)';

                                    return (
                                        <React.Fragment key={pid}>
                                            {ni > 0 && chain.preds[ni - 1] !== undefined && (
                                                <>
                                                    <PredChip
                                                        label={chain.preds[ni - 1] || 'связь'}
                                                        uids={
                                                            m.edge_uids?.[
                                                                `${m.pattern_to_graph[chain.nodes[ni - 1]]}->${m.pattern_to_graph[pid]}`
                                                            ] ?? []
                                                        }
                                                    />
                                                    <Arrow />
                                                </>
                                            )}
                                            <NodeChip
                                                label={patternNodeLabels[pid] ?? pid}
                                                color={color}
                                                uids={uids}
                                                uidTitle={uidTitle}
                                            />
                                        </React.Fragment>
                                    );
                                })}
                            </div>
                        ))}
                    </div>
                );
            })}
        </div>
    );
};