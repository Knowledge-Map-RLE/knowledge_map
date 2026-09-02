import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport, useViewportContainer } from '../../widgets/KnowledgeMap';
import type { ViewportRef } from '../../widgets/KnowledgeMap';
import Header from '../../widgets/Header';
import { BlockPalette } from './components/BlockPalette';
import { PatternNode } from './components/PatternNode';
import { PatternEdge } from './components/PatternEdge';
import { MatchOverlay } from './components/MatchOverlay';
import { UniquenessResult } from './components/UniquenessResult';
import { usePatternEditor } from './hooks/usePatternEditor';
import type { Port, BlockType } from './model';
import { BLOCK_DEFS, getBlockPorts } from './model';
import { checkPatternMatch } from '../../services/api/uniqueness';
import type { CheckPatternResponse } from '../../services/api/uniqueness';
import styles from './PatternEditor.module.css';

extend({ Container, Graphics, Text });

interface BlockDragState {
    id: string;
    startClientX: number;
    startClientY: number;
    originX: number;
    originY: number;
}

interface ConnectingState {
    srcPort: Port;
    fromX: number;
    fromY: number;
    toX: number;
    toY: number;
    startCX: number;
    startCY: number;
}

const ZOOM_STEP = 1.2;
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;

function formatConnectionLabel(
    blocks: Array<{ id: string; type: string; text: string }>,
    connections: Array<{ id: string; sourcePortId: string; targetPortId: string }>,
    connectionId: string
): string {
    const conn = connections.find((c) => c.id === connectionId);
    if (!conn) return '';
    const source = blocks.find((b) => conn.sourcePortId.startsWith(b.id));
    const target = blocks.find((b) => conn.targetPortId.startsWith(b.id));
    const name = (b?: { type: string; text: string }) =>
        b ? `${BLOCK_DEFS[b.type as BlockType].label}${b.text ? ` «${b.text}»` : ''}` : '?';
    return `${name(source)} → ${name(target)}`;
}

const PatternEditorPage: React.FC = () => {
    const editor = usePatternEditor();

    const canvasWrapRef = useRef<HTMLDivElement | null>(null);
    const [canvasEl, setCanvasEl] = useState<HTMLDivElement | null>(null);
    const canvasCbRef = useCallback((el: HTMLDivElement | null) => {
        canvasWrapRef.current = el;
        if (el) setCanvasEl(el);
    }, []);
    const viewportRef = useRef<ViewportRef | null>(null);
    const worldRef = useRef<Container | null>(null);

    const [pendingType, setPendingType] = useState<string | null>(null);
    const [blockDrag, setBlockDrag] = useState<BlockDragState | null>(null);
    const [connecting, setConnecting] = useState<ConnectingState | null>(null);
    const [scale, setScale] = useState(1);
    const [result, setResult] = useState<null | {
        matches: CheckPatternResponse['matches'];
        total: number;
        payloadEdges: { source_id: string; target_id: string; predicate_constraint: string }[];
    }>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null);

    /** Преобразует клиентские координаты мыши в мировые координаты canvas. */
    const worldFromClient = useCallback((clientX: number, clientY: number) => {
        const rect = canvasWrapRef.current?.getBoundingClientRect();
        const wc = worldRef.current;
        if (!rect || !wc) return { x: 0, y: 0 };
        return wc.toLocal({ x: clientX - rect.left, y: clientY - rect.top });
    }, []);

    const clientOf = useCallback((e: any) => {
        const rect = canvasWrapRef.current?.getBoundingClientRect();
        const cx = e.nativeEvent?.clientX ?? (rect ? rect.left + e.global.x : e.global.x);
        const cy = e.nativeEvent?.clientY ?? (rect ? rect.top + e.global.y : e.global.y);
        return { cx, cy };
    }, []);

    // Drag блока через DOM-слушатели (устойчиво к выходу указателя за пределы canvas)
    useEffect(() => {
        if (!blockDrag) return;
        const onMove = (e: PointerEvent) => {
            const w = worldFromClient(e.clientX, e.clientY);
            const start = worldFromClient(blockDrag.startClientX, blockDrag.startClientY);
            editor.updateBlockPosition(blockDrag.id, blockDrag.originX + (w.x - start.x), blockDrag.originY + (w.y - start.y));
        };
        const onUp = () => setBlockDrag(null);
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
        window.addEventListener('pointercancel', onUp);
        return () => {
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onUp);
            window.removeEventListener('pointercancel', onUp);
        };
    }, [blockDrag, editor, worldFromClient]);

    // Соединение портов через DOM-слушатели; цель определяется по близости к портам.
    useEffect(() => {
        if (!connecting) return;
        const onMove = (e: PointerEvent) => {
            const w = worldFromClient(e.clientX, e.clientY);
            setConnecting((prev) => (prev ? { ...prev, toX: w.x, toY: w.y } : prev));
        };
        const onUp = (e: PointerEvent) => {
            const srcPort = connecting.srcPort;
            // Игнорируем простой клик без перемещения.
            const moved = Math.hypot(e.clientX - connecting.startCX, e.clientY - connecting.startCY) > 4;

            let target: Port | null = null;
            if (moved) {
                const world = worldFromClient(e.clientX, e.clientY);
                let bestDist = 12 * 12;
                for (const b of editor.blocks) {
                    for (const ref of getBlockPorts(b)) {
                        if (ref.port.id === srcPort.id) continue;
                        const wx = b.x + ref.localX;
                        const wy = b.y + ref.localY;
                        const d2 = (world.x - wx) ** 2 + (world.y - wy) ** 2;
                        if (d2 <= bestDist) {
                            bestDist = d2;
                            target = ref.port;
                        }
                    }
                }
            }

            if (target) {
                const { connected, reason } = editor.connectPorts(srcPort, target);
                if (!connected && reason) {
                    setError(reason);
                    setTimeout(() => setError(null), 3000);
                }
            }
            setConnecting(null);
        };
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
        window.addEventListener('pointercancel', onUp);
        return () => {
            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onUp);
            window.removeEventListener('pointercancel', onUp);
        };
    }, [connecting, editor, worldFromClient]);

    // Обработка масштаба и подписка на события зумирования/панорамирования Viewport
    useEffect(() => {
        const sync = () => setScale(Math.round((viewportRef.current?.getScale?.() ?? 1) * 100) / 100);
        const timer = setTimeout(sync, 200);
        viewportRef.current?.on?.('zoomed', sync);
        viewportRef.current?.on?.('moved', sync);
        return () => {
            clearTimeout(timer);
            viewportRef.current?.off?.('zoomed', sync);
            viewportRef.current?.off?.('moved', sync);
        };
    }, [editor.blocks.length]);

    const handleCanvasPlace = useCallback(
        (x: number, y: number) => {
            if (pendingType) {
                editor.addBlock(pendingType as never, x - 20, y - 20);
                setPendingType(null);
            } else {
                editor.selectBlock(null);
                setSelectedConnectionId(null);
            }
        },
        [pendingType, editor]
    );

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            const type = e.dataTransfer.getData('application/pattern-block');
            if (!type) return;
            const pt = worldFromClient(e.clientX, e.clientY);
            editor.addBlock(type as never, pt.x - 20, pt.y - 20);
        },
        [editor, worldFromClient]
    );

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    }, []);

    const handlePaletteDragStart = useCallback((e: React.DragEvent, type: string) => {
        e.dataTransfer.setData('application/pattern-block', type);
        e.dataTransfer.effectAllowed = 'copy';
    }, []);

    const handleNodeDragStart = useCallback(
        (e: any, id: string) => {
            e.stopPropagation?.();
            const { cx, cy } = clientOf(e);
            const block = editor.blocks.find((b) => b.id === id);
            if (!block) return;
            setBlockDrag({ id, startClientX: cx, startClientY: cy, originX: block.x, originY: block.y });
        },
        [editor.blocks, clientOf]
    );

    const handlePortPointerDown = useCallback(
        (e: any, port: Port) => {
            e.stopPropagation?.();
            const { cx, cy } = clientOf(e);
            const srcBlock = editor.blocks.find((b) => b.id === port.blockId);
            const fromX = srcBlock ? srcBlock.x + port.x : port.x;
            const fromY = srcBlock ? srcBlock.y + port.y : port.y;
            setConnecting({ srcPort: port, fromX, fromY, toX: fromX, toY: fromY, startCX: cx, startCY: cy });
        },
        [editor.blocks, clientOf]
    );

    const handleSelectConnection = useCallback(
        (id: string) => {
            setSelectedConnectionId((prev) => (prev === id ? null : id));
            if (editor.selectedBlockId) editor.selectBlock(null);
        },
        [editor]
    );

    const handleDeleteConnection = useCallback(
        (id: string) => {
            editor.disconnect(id);
            setSelectedConnectionId(null);
        },
        [editor]
    );

    // Удаление выделенного блока или связи по Delete/Backspace
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key !== 'Delete' && e.key !== 'Backspace') return;
            const el = document.activeElement as HTMLElement | null;
            if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) return;
            if (editor.selectedBlockId) {
                e.preventDefault();
                editor.removeBlock(editor.selectedBlockId);
                setSelectedConnectionId(null);
            } else if (selectedConnectionId) {
                e.preventDefault();
                handleDeleteConnection(selectedConnectionId);
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [editor, selectedConnectionId, handleDeleteConnection]);

    const handleRunCheck = useCallback(async () => {
        const payload = editor.toGraphPayload();
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const response = await checkPatternMatch(payload);
            setResult({
                matches: response.matches ?? [],
                total: response.total_matches ?? 0,
                payloadEdges: payload.edges,
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Не удалось выполнить проверку');
        } finally {
            setLoading(false);
        }
    }, [editor]);

    const patternNodeLabels = useCallback(() => {
        const map: Record<string, string> = {};
        editor.blocks.forEach((b) => {
            map[b.id] = BLOCK_DEFS[b.type].label + (b.text ? `: ${b.text}` : '');
        });
        return map;
    }, [editor.blocks]);

    const handleNodeSelect = useCallback(
        (id: string) => {
            setSelectedConnectionId(null);
            editor.selectBlock(id);
        },
        [editor]
    );

    const selectedBlock = editor.blocks.find((b) => b.id === editor.selectedBlockId) ?? null;

    const zoomIn = useCallback(() => {
        const s = Math.min(ZOOM_MAX, (viewportRef.current?.getScale?.() ?? 1) * ZOOM_STEP);
        viewportRef.current?.setScale?.(s);
    }, []);
    const zoomOut = useCallback(() => {
        const s = Math.max(ZOOM_MIN, (viewportRef.current?.getScale?.() ?? 1) / ZOOM_STEP);
        viewportRef.current?.setScale?.(s);
    }, []);
    const zoomReset = useCallback(() => {
        viewportRef.current?.setScale?.(1);
    }, []);

    return (
        <div className={styles.page}>
            <Header showSearch={true} className={styles.header} />
            <main className={styles.main}>
                <BlockPalette onDragStart={handlePaletteDragStart} onPick={(t) => setPendingType(t as never)} pendingType={pendingType} />

                <div
                    ref={canvasCbRef}
                    className={styles.canvas}
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                >
                    {canvasEl && (
                    <Application resizeTo={canvasEl} backgroundColor={0xf5f5f5} antialias resolution={window.devicePixelRatio || 1} autoDensity>
                        <CanvasContent
                            blocks={editor.blocks}
                            connections={editor.connections}
                            selectedBlockId={editor.selectedBlockId}
                            selectedConnectionId={selectedConnectionId}
                            connecting={connecting}
                            onWorldReady={(c) => { worldRef.current = c; }}
                            onViewportRef={(r) => { viewportRef.current = r; }}
                            onCanvasClick={handleCanvasPlace}
                            onNodeDragStart={handleNodeDragStart}
                            onNodeSelect={handleNodeSelect}
                            onPortPointerDown={handlePortPointerDown}
                            onSelectConnection={handleSelectConnection}
                        />
                    </Application>
                    )}

                    <div className={styles.zoomControls}>
                        <button className={styles.zoomButton} onClick={zoomOut} title="Уменьшить">−</button>
                        <span className={styles.zoomPercent}>{Math.round(scale * 100)}%</span>
                        <button className={styles.zoomButton} onClick={zoomIn} title="Увеличить">+</button>
                        <button className={styles.zoomButton} onClick={zoomReset} title="Сбросить">⟳</button>
                    </div>
                </div>

                <aside className={styles.sidebar}>
                    <div className={styles.sidebarActions}>
                        <button className={styles.runButton} onClick={handleRunCheck} disabled={loading}>
                            {loading ? 'Проверка…' : 'Проверить уникальность'}
                        </button>
                        <button className={styles.resetButton} onClick={editor.reset}>
                            Очистить
                        </button>
                    </div>

                    {selectedBlock && (
                        <div className={styles.sidebarSection}>
                            <label className={styles.blockEditLabel}>
                                {BLOCK_DEFS[selectedBlock.type].label}
                            </label>
                            <input
                                className={styles.blockEditInput}
                                value={selectedBlock.text}
                                placeholder="Свойство / значение"
                                onChange={(e) => editor.updateBlockText(selectedBlock.id, e.target.value)}
                            />
                            <button className={styles.removeButton} onClick={() => editor.removeBlock(selectedBlock.id)}>
                                Удалить блок
                            </button>
                        </div>
                    )}

                    {selectedConnectionId && (
                        <div className={styles.sidebarSection}>
                            <label className={styles.blockEditLabel}>Связь</label>
                            <p className={styles.blockEditHint}>Связь {formatConnectionLabel(editor.blocks, editor.connections, selectedConnectionId)}</p>
                            <button
                                className={styles.removeButton}
                                onClick={() => handleDeleteConnection(selectedConnectionId)}
                            >
                                Удалить связь
                            </button>
                        </div>
                    )}

                    <div className={styles.sidebarSection}>
                        <UniquenessResult
                            result={null}
                            addResult={null}
                            loading={loading}
                            error={error}
                        />
                    </div>

                    <div className={styles.sidebarSection}>
                        <MatchOverlay
                            matches={result?.matches ?? []}
                            totalMatches={result?.total ?? 0}
                            patternNodeLabels={patternNodeLabels()}
                            patternEdges={result?.payloadEdges ?? []}
                            blocks={editor.blocks}
                        />
                    </div>
                </aside>
            </main>
        </div>
    );
};

interface CanvasContentProps {
    blocks: ReturnType<typeof usePatternEditor>['blocks'];
    connections: ReturnType<typeof usePatternEditor>['connections'];
    selectedBlockId: string | null;
    selectedConnectionId: string | null;
    connecting: ConnectingState | null;
    onWorldReady: (c: Container | null) => void;
    onViewportRef: (r: ViewportRef) => void;
    onCanvasClick: (x: number, y: number) => void;
    onNodeDragStart: (e: any, id: string) => void;
    onNodeSelect: (id: string) => void;
    onPortPointerDown: (e: any, port: Port) => void;
    onSelectConnection: (id: string) => void;
}

const CanvasContent: React.FC<CanvasContentProps> = ({
    blocks,
    connections,
    selectedBlockId,
    selectedConnectionId,
    connecting,
    onWorldReady,
    onViewportRef,
    onCanvasClick,
    onNodeDragStart,
    onNodeSelect,
    onPortPointerDown,
    onSelectConnection,
}) => {
    const viewportRef = useRef<ViewportRef | null>(null);

    const handleViewportRef = useCallback(
        (r: ViewportRef) => {
            viewportRef.current = r;
            onViewportRef(r);
        },
        [onViewportRef]
    );

    return (
        <Viewport ref={handleViewportRef} onCanvasClick={onCanvasClick}>
            <EditorContent
                blocks={blocks}
                connections={connections}
                selectedBlockId={selectedBlockId}
                selectedConnectionId={selectedConnectionId}
                connecting={connecting}
                onWorldReady={onWorldReady}
                onNodeDragStart={onNodeDragStart}
                onNodeSelect={onNodeSelect}
                onPortPointerDown={onPortPointerDown}
                onSelectConnection={onSelectConnection}
            />
        </Viewport>
    );
};

interface EditorContentProps {
    blocks: ReturnType<typeof usePatternEditor>['blocks'];
    connections: ReturnType<typeof usePatternEditor>['connections'];
    selectedBlockId: string | null;
    selectedConnectionId: string | null;
    connecting: ConnectingState | null;
    onWorldReady: (c: Container | null) => void;
    onNodeDragStart: (e: any, id: string) => void;
    onNodeSelect: (id: string) => void;
    onPortPointerDown: (e: any, port: Port) => void;
    onSelectConnection: (id: string) => void;
}

const EditorContent: React.FC<EditorContentProps> = ({
    blocks,
    connections,
    selectedBlockId,
    selectedConnectionId,
    connecting,
    onWorldReady,
    onNodeDragStart,
    onNodeSelect,
    onPortPointerDown,
    onSelectConnection,
}) => {
    const worldContainer = useViewportContainer();

    useEffect(() => {
        onWorldReady(worldContainer.current);
    }, [worldContainer, onWorldReady]);

    return (
        <>
            {connections.map((conn) => {
                const sourceBlock = blocks.find((b) => conn.sourcePortId.startsWith(b.id));
                const targetBlock = blocks.find((b) => conn.targetPortId.startsWith(b.id));
                if (!sourceBlock || !targetBlock) return null;
                const sx = sourceBlock.x + sourceBlock.width;
                const sy = sourceBlock.y + sourceBlock.height / 2;
                const tx = targetBlock.x;
                const ty = targetBlock.y + targetBlock.height / 2;
                return (
                    <PatternEdge
                        key={conn.id}
                        id={conn.id}
                        sx={sx}
                        sy={sy}
                        tx={tx}
                        ty={ty}
                        selected={selectedConnectionId === conn.id}
                        interactive
                        onSelect={onSelectConnection}
                    />
                );
            })}

            {connecting && (
                <PatternEdge
                    sx={connecting.fromX}
                    sy={connecting.fromY}
                    tx={connecting.toX}
                    ty={connecting.toY}
                    color={0xffee58}
                    dashed
                />
            )}

            {blocks.map((b) => (
                <PatternNode
                    key={b.id}
                    id={b.id}
                    type={b.type}
                    x={b.x}
                    y={b.y}
                    width={b.width}
                    height={b.height}
                    text={b.text}
                    selected={selectedBlockId === b.id}
                    onDragStart={onNodeDragStart}
                    onSelect={onNodeSelect}
                    onPortPointerDown={onPortPointerDown}
                />
            ))}
        </>
    );
};

export default PatternEditorPage;
