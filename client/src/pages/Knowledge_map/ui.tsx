import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import type { CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { Container, Graphics } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport, Link } from '../../widgets/KnowledgeMap';
import type { ViewportRef } from '../../widgets/KnowledgeMap';
import { useViewport } from '../../shared/contexts';
import { getKnowledgeTriples, searchIsolatedTriples, rebuildDependencies } from '../../services/api';
import type {
  KnowledgeGraphBlock,
  KnowledgeGraphLink,
  KnowledgeTriple,
} from '../../services/api';
import { TripleBlock, TRIPLE_BLOCK_WIDTH } from './TripleBlock';
import GoalDecompositionPanel from './GoalDecompositionPanel';
import styles from './Knowledge_map.module.css';

extend({ Container, Graphics });

// Компонент левой панели: список изолированных триплетов + поиск (с 3 символов).
const IsolatedTriplesPanel = () => {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<KnowledgeTriple[]>([]);
  const [total, setTotal] = useState(0);
  const [isSearching, setIsSearching] = useState(false);
  const debounceRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const runSearch = useCallback(async (q: string, controller: AbortController) => {
    setIsSearching(true);
    try {
      const data = await searchIsolatedTriples(q, 0, 200);
      if (!data?.success) {
        setItems([]);
        setTotal(0);
        return;
      }
      setItems(data.items || []);
      setTotal(data.total_count ?? 0);
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      setItems([]);
      setTotal(0);
    } finally {
      setIsSearching(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (abortRef.current) abortRef.current.abort();

    const q = query.trim();
    const launch = (controller: AbortController) => {
      abortRef.current = controller;
      runSearch(q, controller);
    };

    if (q.length < 3) {
      const controller = new AbortController();
      launch(controller);
      return;
    }

    debounceRef.current = window.setTimeout(() => {
      const controller = new AbortController();
      launch(controller);
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [query, runSearch]);

  return (
    <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: 12, color: '#555', fontWeight: 600 }}>
        Триплеты без связей{total > 0 ? ` (${total})` : ''}
      </div>
      <input
        type="text"
        placeholder="Поиск от 3 символов..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{
          width: '100%',
          boxSizing: 'border-box',
          padding: '6px 8px',
          backgroundColor: '#ffffff',
          color: '#333',
          border: '1px solid #ccc',
          borderRadius: '4px',
          fontSize: '13px',
        }}
      />
      <div
        style={{
          flex: '1 1 0',
          minHeight: 0,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
          paddingRight: 2,
        }}
      >
        {isSearching ? (
          <div style={{ fontSize: 12, color: '#999', padding: '4px 8px' }}>Поиск...</div>
        ) : items.length === 0 ? (
          <div style={{ fontSize: 12, color: '#aaa', padding: '4px 8px' }}>
            {query.trim().length >= 3 ? 'Ничего не найдено' : 'Нет триплетов без связей'}
          </div>
        ) : (
          items.map((item) => (
            <div
              key={item.id}
              title={item.content}
              style={{
                padding: '5px 8px',
                backgroundColor: '#fff',
                border: '1px solid #eee',
                borderRadius: '4px',
                fontSize: '12px',
                lineHeight: 1.3,
              }}
            >
              <span
                style={{
                  display: 'block',
                  color: '#9ca3af',
                  fontSize: 10,
                  fontFamily: 'monospace',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {item.uid}
              </span>
              <span
                style={{
                  color: '#333',
                  whiteSpace: 'normal',
                  lineHeight: 1.4,
                }}
              >
                {item.subject_text} → {item.predicate} → {item.object_text}
              </span>
            </div>
          ))
        )}
      </div>
      {query.trim().length >= 3 && !isSearching && items.length > 0 && (
        <div style={{ fontSize: 11, color: '#888', padding: '0 8px' }}>
          Найдено {items.length} из {total}
        </div>
      )}
    </div>
  );
};

// Панель смежных (входящих/исходящих) блоков, появляющаяся при выделении блока.
const NeighborPanel: React.FC<{
  side: 'left' | 'right';
  title: string;
  items: KnowledgeGraphBlock[];
  onPick: (id: string) => void;
  panelRef: React.RefObject<HTMLDivElement | null>;
}> = ({ side, title, items, onPick, panelRef }) => {
  const posStyle = side === 'left' ? { left: 230 } : { right: 228 };
  return (
    <div
      ref={panelRef}
      style={{
        position: 'fixed',
        top: 84,
        width: 240,
        maxHeight: 'calc(100vh - 200px)',
        overflowY: 'auto',
        zIndex: 60,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: 10,
        backgroundColor: 'rgba(255, 255, 255, 0.97)',
        border: '1px solid #cbd5e1',
        borderRadius: 12,
        boxShadow: '0 2px 14px rgba(0,0,0,0.18)',
        ...posStyle,
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 600, color: '#555' }}>
        {title}{items.length > 0 ? ` (${items.length})` : ''}
      </div>
      {items.length === 0 ? (
        <div style={{ fontSize: 12, color: '#aaa', padding: '4px 8px' }}>Нет блоков</div>
      ) : (
        items.map((b) => (
          <div
            key={b.id}
            title={b.content}
            onClick={() => onPick(b.id)}
            style={{
              cursor: 'pointer',
              padding: '5px 8px',
              backgroundColor: '#fff',
              border: '1px solid #eee',
              borderRadius: 6,
              fontSize: 12,
              lineHeight: 1.35,
            }}
          >
            <span
              style={{
                display: 'block',
                color: '#9ca3af',
                fontSize: 10,
                fontFamily: 'monospace',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {b.uid}
            </span>
            <span style={{ color: '#333' }}>{b.content.split('\n').slice(1).join(' ') || b.content}</span>
          </div>
        ))
      )}
    </div>
  );
};

const DEPENDENCY_TYPE_META: { type: string; label: string; color: string }[] = [
  { type: 'causal', label: 'causal', color: '#16a34a' },
  { type: 'mechanistic', label: 'mechanistic', color: '#2563eb' },
  { type: 'logical', label: 'logical', color: '#7c3aed' },
  { type: 'evidential', label: 'evidential', color: '#d97706' },
  { type: 'goal_directed', label: 'goal_decomposition', color: '#ea580c' },
  { type: 'compositional', label: 'compositional', color: '#0d9488' },
];

interface DependencyControlsProps {
  links: KnowledgeGraphLink[];
  enabledDepTypes: Set<string>;
  onToggleType: (type: string) => void;
  onResetTypes: () => void;
  onRebuild: (useLlm: boolean) => void;
  isRebuilding: boolean;
}

/** Панель легенды/фильтров типов зависимостей и пересчёта графа. */
const DependencyControls = ({
  links,
  enabledDepTypes,
  onToggleType,
  onResetTypes,
  onRebuild,
  isRebuilding,
}: DependencyControlsProps) => {
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of links) {
      const t = l.metadata?.dependency_type || 'causal';
      m.set(t, (m.get(t) || 0) + 1);
    }
    return m;
  }, [links]);

  return (
    <div
      style={{
        position: 'absolute',
        top: 70,
        left: 240,
        zIndex: 30,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        backgroundColor: 'rgba(255,255,255,0.92)',
        border: '1px solid #e5e7eb',
        borderRadius: 10,
        padding: 10,
        boxShadow: '0 2px 10px rgba(0,0,0,0.08)',
        maxWidth: 220,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: '#333' }}>Типы зависимостей</span>
        <button
          onClick={onResetTypes}
          style={{
            fontSize: 11,
            border: '1px solid #d1d5db',
            background: '#fff',
            borderRadius: 6,
            padding: '2px 8px',
            cursor: 'pointer',
            color: '#555',
          }}
        >
          Все
        </button>
      </div>
      {DEPENDENCY_TYPE_META.map((d) => (
        <label
          key={d.type}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 12,
            color: '#333',
            cursor: 'pointer',
          }}
        >
          <input
            type="checkbox"
            checked={!enabledDepTypes.has(d.type)}
            onChange={() => onToggleType(d.type)}
            style={{ accentColor: d.color }}
          />
          <span
            style={{
              width: 10,
              height: 3,
              borderRadius: 2,
              backgroundColor: d.color,
              display: 'inline-block',
            }}
          />
          <span style={{ flex: 1 }}>{d.label}</span>
          <span style={{ color: '#9ca3af', fontSize: 11 }}>{counts.get(d.type) || 0}</span>
        </label>
      ))}
      <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button
          onClick={() => onRebuild(false)}
          disabled={isRebuilding}
          style={rebuildBtnStyle(isRebuilding)}
        >
          {isRebuilding ? 'Пересчёт...' : 'Пересчитать (rules)'}
        </button>
        <button
          onClick={() => onRebuild(true)}
          disabled={isRebuilding}
          style={rebuildBtnStyle(isRebuilding)}
        >
          Пересчитать (rules + LLM)
        </button>
      </div>
    </div>
  );
};

const rebuildBtnStyle = (disabled: boolean): CSSProperties => ({
  fontSize: 12,
  border: '1px solid #d1d5db',
  background: '#f9fafb',
  borderRadius: 6,
  padding: '5px 8px',
  cursor: disabled ? 'wait' : 'pointer',
  color: '#374151',
});

export const Knowledge_mapUI = () => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<ViewportRef>(null);
  const { setViewportRef } = useViewport();

  const [blocks, setBlocks] = useState<KnowledgeGraphBlock[]>([]);
  const [links, setLinks] = useState<KnowledgeGraphLink[]>([]);
  const [isolatedTotal, setIsolatedTotal] = useState(0);
  const [pixiReady, setPixiReady] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [leftPanelEl, setLeftPanelEl] = useState<HTMLElement | null>(null);
  const [enabledDepTypes, setEnabledDepTypes] = useState<Set<string>>(new Set());
  const [isRebuilding, setIsRebuilding] = useState(false);
  const userInteractedRef = useRef(false);
  const incomingPanelRef = useRef<HTMLDivElement | null>(null);
  const outgoingPanelRef = useRef<HTMLDivElement | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getKnowledgeTriples(200);
      if (!data?.success) {
        setLoadError('Не удалось загрузить карту триплетов');
        return;
      }
      setBlocks(data.blocks || []);
      setLinks(data.links || []);
      setIsolatedTotal(data.isolated_total ?? 0);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleRebuild = useCallback(async (useLlm: boolean) => {
    setIsRebuilding(true);
    try {
      await rebuildDependencies(useLlm);
      await loadData();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Ошибка пересчёта зависимостей');
    } finally {
      setIsRebuilding(false);
    }
  }, [loadData]);

  // Только связи выбранных типов зависимостей (пустое множество = все).
  const visibleLinks = useMemo(() => {
    if (enabledDepTypes.size === 0) return links;
    return links.filter((l) => enabledDepTypes.has(l.metadata?.dependency_type || 'causal'));
  }, [links, enabledDepTypes]);

  // Регистрируем viewportRef в глобальном контексте.
  useEffect(() => {
    const registerViewport = () => {
      if (viewportRef.current) {
        setViewportRef(viewportRef);
      }
    };
    registerViewport();
    const timer = setTimeout(registerViewport, 1000);
    return () => clearTimeout(timer);
  }, [setViewportRef, pixiReady]);

  // Находим левую панель оболочки KnowledgeMapUI.
  useEffect(() => {
    const leftEl = document.getElementById('km-left-panel');
    if (leftEl) setLeftPanelEl(leftEl);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);
  useEffect(() => {
    const timer = setTimeout(() => setPixiReady(true), 500);
    return () => clearTimeout(timer);
  }, []);
  useEffect(() => { containerRef.current?.focus(); }, []);

  // Блокируем раскомментирование контекстного меню браузера.
  useEffect(() => {
    const prevent = (e: MouseEvent) => e.preventDefault();
    containerRef.current?.addEventListener('contextmenu', prevent);
    return () => containerRef.current?.removeEventListener('contextmenu', prevent);
  }, []);

  // Автоцентрирование на центр данных при первой загрузке.
  useEffect(() => {
    if (blocks.length > 0 && !userInteractedRef.current) {
      const cx = blocks.reduce((s, b) => s + b.x, 0) / blocks.length;
      const cy = blocks.reduce((s, b) => s + b.y, 0) / blocks.length;
      setTimeout(() => {
        viewportRef.current?.focusOn(cx, cy);
      }, 100);
    }
  }, [blocks.length]);

  const blockMap = useMemo(() => {
    const m = new Map<string, KnowledgeGraphBlock>();
    blocks.forEach((b) => m.set(b.id, b));
    return m;
  }, [blocks]);

  // Входящие блоки (ссылки, указывающие на выбранный) и исходящие (со ссылкой на другие).
  const incomingBlocks = useMemo(() => {
    if (!selectedId) return [];
    const seen = new Set<string>();
    const result: KnowledgeGraphBlock[] = [];
    for (const link of visibleLinks) {
      if (link.target_id === selectedId) {
        const b = blockMap.get(link.source_id);
        if (b && !seen.has(b.id)) {
          seen.add(b.id);
          result.push(b);
        }
      }
    }
    return result;
  }, [visibleLinks, selectedId, blockMap]);

  const outgoingBlocks = useMemo(() => {
    if (!selectedId) return [];
    const seen = new Set<string>();
    const result: KnowledgeGraphBlock[] = [];
    for (const link of visibleLinks) {
      if (link.source_id === selectedId) {
        const b = blockMap.get(link.target_id);
        if (b && !seen.has(b.id)) {
          seen.add(b.id);
          result.push(b);
        }
      }
    }
    return result;
  }, [visibleLinks, selectedId, blockMap]);

  const handleNeighborPick = useCallback((id: string) => {
    const block = blockMap.get(id);
    if (!block) return;
    setSelectedId(id);
    viewportRef.current?.focusOn(block.x, block.y);
  }, [blockMap]);

  // Клик вне панелей смежных блоков закрывает их (снимает выделение).
  useEffect(() => {
    const onDocMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (incomingPanelRef.current?.contains(target)) return;
      if (outgoingPanelRef.current?.contains(target)) return;
      setSelectedId(null);
    };
    document.addEventListener('mousedown', onDocMouseDown, true);
    return () => document.removeEventListener('mousedown', onDocMouseDown, true);
  }, []);

  const handleViewportMove = useCallback(() => { userInteractedRef.current = true; }, []);

  if (loadError) {
    return (
      <div
        className={styles.knowledge_map}
        style={{ justifyContent: 'center', alignItems: 'center', color: 'red' }}
      >
        Ошибка загрузки: {loadError}
      </div>
    );
  }

  return (
    <main ref={containerRef} className={styles.knowledge_map} tabIndex={-1}>
      {(!pixiReady || isLoading) && (
        <div className={styles.экран_загрузки}>
          {isLoading ? 'Загрузка карты триплетов...' : 'Инициализация...'}
        </div>
      )}
      <Application
        width={window.innerWidth}
        height={window.innerHeight}
        backgroundColor={0xf5f5f5}
        antialias
        resolution={window.devicePixelRatio || 1}
        autoDensity
      >
        <Viewport
          ref={viewportRef}
          onCanvasClick={() => setSelectedId(null)}
          onDragStart={handleViewportMove}
        >
          <container sortableChildren={true}>
            <container zIndex={0} eventMode="none">
              {visibleLinks.map((link) => (
                <Link
                  key={link.id}
                  linkData={link}
                  blockMap={blockMap as any}
                  isSelected={false}
                  onClick={() => {}}
                  perfMode
                  blockWidth={TRIPLE_BLOCK_WIDTH}
                />
              ))}
            </container>
            <container zIndex={1}>
              {blocks.map((block) => (
                <TripleBlock
                  key={block.id}
                  id={block.id}
                  content={block.content}
                  x={block.x}
                  y={block.y}
                  isPlaceholder={block.metadata?.is_placeholder}
                  isGoal={block.metadata?.is_goal}
                  isPlan={block.metadata?.is_plan}
                  isSelected={selectedId === block.id}
                  onClick={setSelectedId}
                />
              ))}
            </container>
          </container>
        </Viewport>
      </Application>

      <DependencyControls
        links={links}
        enabledDepTypes={enabledDepTypes}
        onToggleType={(t) => {
          setEnabledDepTypes((prev) => {
            const next = new Set(prev);
            if (next.has(t)) next.delete(t);
            else next.add(t);
            return next;
          });
        }}
        onResetTypes={() => setEnabledDepTypes(new Set())}
        onRebuild={handleRebuild}
        isRebuilding={isRebuilding}
      />

      {selectedId && (
        <>
          <NeighborPanel
            side="left"
            title="Входящие блоки"
            items={incomingBlocks}
            onPick={handleNeighborPick}
            panelRef={incomingPanelRef}
          />
          <NeighborPanel
            side="right"
            title="Исходящие блоки"
            items={outgoingBlocks}
            onPick={handleNeighborPick}
            panelRef={outgoingPanelRef}
          />
        </>
      )}

      {leftPanelEl && createPortal(
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: '100%', height: '100%', minHeight: 0 }}>
          <div style={{ flex: '1 1 50%', minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <GoalDecompositionPanel onDecomposed={loadData} />
          </div>
          <div
            style={{
              flex: '1 1 50%',
              minHeight: 0,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              borderTop: '1px solid #e5e7eb',
              paddingTop: 10,
            }}
          >
            <IsolatedTriplesPanel />
          </div>
        </div>,
        leftPanelEl,
      )}
    </main>
  );
};

export default Knowledge_mapUI;
