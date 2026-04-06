import { useState, useEffect, useRef } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { extend } from '@pixi/react';
import type { ViewportRef } from '../Knowledge_map/Viewport';
import styles from '../Knowledge_map/Knowledge_map.module.css';

import { ArticlesRenderer } from './components/ArticlesRenderer';
import { useViewport } from '../../contexts/ViewportContext';
import { useKnowledgeMapLoader } from './hooks/useKnowledgeMapLoader';
import { KnowledgeMapRenderer } from './components/KnowledgeMapRenderer';

extend({ Container, Graphics, Text });

export default function Science_articles() {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<ViewportRef>(null);
  const { setViewportRef } = useViewport();

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [pixiReady, setPixiReady] = useState(false);

  // Регистрируем viewportRef в глобальном контексте
  useEffect(() => {
    const registerViewport = () => {
      if (viewportRef.current) setViewportRef(viewportRef);
    };
    registerViewport();
    const timer = setTimeout(registerViewport, 1000);
    return () => clearTimeout(timer);
  }, [setViewportRef]);

  // Карта знаний
  const {
    nodes: kmNodes,
    nodeMap: kmNodeMap,
    edges: kmEdges,
    isLoading: kmIsLoading,
    loadNextPage: kmLoadNextPage,
  } = useKnowledgeMapLoader(viewportRef);

  // Загружаем сразу при монтировании
  const kmLoadedRef = useRef(false);
  useEffect(() => {
    if (!kmLoadedRef.current) {
      kmLoadedRef.current = true;
      kmLoadNextPage();
    }
  }, [kmLoadNextPage]);

  // Инициализация PIXI
  useEffect(() => {
    const timer = setTimeout(() => setPixiReady(true), 500);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    containerRef.current?.focus();
  }, []);

  const selectedNode = selectedNodeId ? kmNodeMap.get(selectedNodeId) : null;

  // Заглушки для ArticlesRenderer (используем только как контейнер Pixi + Viewport)
  const noopRef = useRef(false);

  return (
    <main ref={containerRef} className={styles.knowledge_map} tabIndex={-1}>

      {/* Экран загрузки */}
      {(!pixiReady || (kmIsLoading && kmNodes.length === 0)) && (
        <div className={styles.экран_загрузки}>
          {!pixiReady ? 'Инициализация...' : 'Загрузка карты знаний...'}
        </div>
      )}

      {/* Единый Pixi-холст */}
      <ArticlesRenderer
        viewportRef={viewportRef}
        blocks={[]}
        blockMap={new Map()}
        links={[]}
        levels={[]}
        sublevels={[]}
        selectedBlocks={[]}
        selectedLinks={[]}
        currentMode={0 as any}
        isBlockContextMenuActive={false}
        blockRightClickRef={noopRef}
        instantBlockClickRef={noopRef}
        onCanvasClick={() => setSelectedNodeId(null)}
        onBlockClick={() => {}}
        onLinkClick={() => {}}
        onBlockPointerDown={() => {}}
        onBlockMouseEnter={() => {}}
        onBlockMouseLeave={() => {}}
        onArrowClick={() => {}}
        onArrowHover={() => {}}
        onBlockRightClick={() => {}}
        onSublevelClick={() => {}}
        backgroundColor={0x1a1a2e}
      >
        <KnowledgeMapRenderer
          nodes={kmNodes}
          edges={kmEdges}
          selectedNodeId={selectedNodeId}
          onNodeClick={(id) => setSelectedNodeId(prev => prev === id ? null : id)}
          viewportRef={viewportRef}
        />
      </ArticlesRenderer>

      {/* Статус-бар: над нижними панелями (100px) + gap(8px) + padding(10px) = 118px, левее левой панели */}
      <div style={{
        position: 'fixed', bottom: 126, left: 218, zIndex: 200,
        background: 'rgba(0,0,0,0.65)', color: '#ccc', borderRadius: 6,
        padding: '4px 10px', fontSize: 12, pointerEvents: 'none',
      }}>
        {kmIsLoading
          ? `Загрузка... (${kmNodes.length} нод)`
          : kmNodes.length === 0
            ? 'Нет данных карты знаний'
            : `Нод: ${kmNodes.length} | Рёбер: ${kmEdges.length}`}
      </div>

      {/* Панель деталей выбранной ноды: над нижними панелями, левее правой панели */}
      {selectedNode && (
        <div style={{
          position: 'fixed', bottom: 126, right: 218, width: 300,
          background: 'rgba(20,20,40,0.95)', color: '#fff', borderRadius: 10,
          padding: 16, zIndex: 200, boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
          fontSize: 13,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 14 }}>{selectedNode.verb_text || selectedNode.verb}</strong>
            <button onClick={() => setSelectedNodeId(null)} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: 16 }}>✕</button>
          </div>
          {selectedNode.subject && <div style={{ color: '#aaa', marginBottom: 4 }}>Субъект: <span style={{ color: '#fff' }}>{selectedNode.subject}</span></div>}
          {selectedNode.object  && <div style={{ color: '#aaa', marginBottom: 4 }}>Объект: <span style={{ color: '#fff' }}>{selectedNode.object}</span></div>}
          <div style={{ color: '#aaa', marginBottom: 8 }}>Встречается в <strong style={{ color: '#9C27B0' }}>{selectedNode.doc_count}</strong> статьях</div>
          {selectedNode.doc_ids.length > 0 && (
            <div>
              <div style={{ color: '#aaa', marginBottom: 4, fontSize: 11 }}>doc_id статей:</div>
              {selectedNode.doc_ids.map(did => (
                <div key={did} style={{ fontSize: 10, color: '#888', fontFamily: 'monospace' }}>{did}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </main>
  );
}
