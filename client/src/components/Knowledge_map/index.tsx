import { useState, useEffect, useRef } from 'react';
import { Container, Graphics, Text, FederatedPointerEvent } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport } from './Viewport';
import type { ViewportRef } from './Viewport';
import { Link } from './Link';
import { Level } from './Level';
import ModeIndicator from './ModeIndicator';
import { useKeyboardControlsWithProps } from './hooks/useKeyboardControls';
import { useDataLoading } from './hooks/useDataLoading';
import { useSelectionState } from './hooks/useSelectionState';
import { useActions } from './hooks/useActions';
import { createBlockAndLink } from '../../services/api';
import { EditMode } from './types';
import type { LinkCreationState, BlockData, LinkData } from './types';
import { BLOCK_WIDTH } from './constants';
import styles from './Knowledge_map.module.css';

extend({ Container, Graphics, Text });

export default function Knowledge_map() {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<ViewportRef>(null);

  const {
    blocks, links, levels, sublevels, isLoading, loadError, loadLayoutData,
    setBlocks, setLinks, setLevels, setSublevels
  } = useDataLoading();

  const {
    selectedBlocks, selectedLinks, handleBlockSelection, handleLinkSelection, clearSelection
  } = useSelectionState();

  const {
    handleCreateBlockOnSublevel, handleCreateLink, handleDeleteBlock, handleDeleteLink
  } = useActions({
    blocks, links, sublevels, setBlocks, setLinks, setSublevels, clearSelection
  });

  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  const [linkCreationState, setLinkCreationState] = useState<LinkCreationState>({ step: 'waiting' });
  const [pixiReady, setPixiReady] = useState(false);
  const [focusTargetId, setFocusTargetId] = useState<string | null>(null);

  useKeyboardControlsWithProps({
    setCurrentMode, setLinkCreationState, currentMode, linkCreationState
  });

  useEffect(() => { loadLayoutData(); }, [loadLayoutData]);
  useEffect(() => {
    const timer = setTimeout(() => setPixiReady(true), 500);
    return () => clearTimeout(timer);
  }, []);
  useEffect(() => { containerRef.current?.focus(); }, []);

  useEffect(() => {
    if (focusTargetId && blocks.length > 0) {
      const targetBlock = blocks.find(b => b.id === focusTargetId);
      if (targetBlock) {
        const targetX = targetBlock.x + BLOCK_WIDTH / 2;
        const targetY = targetBlock.y;
        viewportRef.current?.focusOn(targetX, targetY);
        setFocusTargetId(null);
      }
    }
  }, [blocks, focusTargetId]);

  const handleBlockClick = (blockId: string) => {
    const clickedBlock = blocks.find(block => block.id === blockId);
    if (!clickedBlock) return;
    switch (currentMode) {
      case EditMode.SELECT: handleBlockSelection(blockId); break;
      case EditMode.CREATE_LINKS:
        if (linkCreationState.step === 'selecting_source') {
          setLinkCreationState({ step: 'selecting_target', sourceBlock: clickedBlock });
        } else if (linkCreationState.step === 'selecting_target' && 'sourceBlock' in linkCreationState) {
          handleCreateLink(linkCreationState.sourceBlock.id, blockId);
          setLinkCreationState({ step: 'selecting_source' });
        }
        break;
      case EditMode.DELETE: handleDeleteBlock(blockId); break;
    }
  };

  const handleLinkClick = (linkId: string) => {
    switch (currentMode) {
      case EditMode.SELECT: handleLinkSelection(linkId); break;
      case EditMode.DELETE: handleDeleteLink(linkId); break;
    }
  };

  const handleSublevelClick = (sublevelId: number, x: number, y: number) => {
    if (currentMode === EditMode.CREATE_BLOCKS) {
      handleCreateBlockOnSublevel(x, y, sublevelId);
    }
  };

  const handleCanvasClick = () => {
    if (currentMode === EditMode.SELECT) clearSelection();
  }

  const handleAddBlock = async (sourceBlock: BlockData, targetLevel: number) => {
    try {
      const linkDirection = targetLevel < sourceBlock.level ? 'to_source' : 'from_source';
      const response = await createBlockAndLink(sourceBlock.id, linkDirection);

      if (!response.success || !response.new_block || !response.new_link) {
        console.error('Failed to create block and link:', response.error || 'Invalid response from server');
        return;
      }
      
      // Оптимистичное добавление с корректными, но временными координатами
      const newBlock: BlockData = {
        id: response.new_block.id,
        text: response.new_block.content || 'Новый блок',
        x: sourceBlock.x + (linkDirection === 'from_source' ? 150 : -150), // Временная позиция
        y: sourceBlock.y, // Временная позиция
        level: response.new_block.level,
        layer: response.new_block.layer ?? sourceBlock.layer ?? 0,
        sublevel: response.new_block.sublevel_id,
      };

      const newLink: LinkData = {
        id: response.new_link.id,
        source_id: response.new_link.source_id,
        target_id: response.new_link.target_id,
      };

      setBlocks(prev => [...prev, newBlock]);
      setLinks(prev => [...prev, newLink]);
      setFocusTargetId(newBlock.id);

      // Фоновое обновление для получения финальных координат от сервиса укладки
      setTimeout(() => {
         loadLayoutData();
      }, 100);

    } catch (error) {
      console.error('Error adding block and link:', error);
    }
  };

  if (loadError) {
    return (
      <div className={styles.knowledge_map} style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'red' }}>
        Ошибка загрузки: {loadError}
      </div>
    );
  }

  return (
    <div ref={containerRef} className={styles.knowledge_map} tabIndex={-1}>
      {(!pixiReady || isLoading) && (
          <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              backgroundColor: 'rgba(245, 245, 245, 0.8)',
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              zIndex: 1000,
              color: '#666',
              fontSize: '1.2rem',
          }}>
              {isLoading ? 'Обновление данных...' : 'Инициализация...'}
          </div>
      )}
      <Application width={window.innerWidth} height={window.innerHeight} backgroundColor={0xf5f5f5}>
        <Viewport ref={viewportRef} onCanvasClick={handleCanvasClick}>
                <container sortableChildren={true}>
            {links.map(link => (
              <Link
                key={link.id}
                linkData={link}
                blocks={blocks}
                isSelected={selectedLinks.includes(link.id)}
                onClick={() => handleLinkClick(link.id)}
              />
            ))}
            {levels.map(level => (
                    <Level
                      key={level.id}
                      levelData={level}
                      sublevels={sublevels}
                      blocks={blocks}
                      onSublevelClick={handleSublevelClick}
                      onBlockClick={handleBlockClick}
                      selectedBlocks={selectedBlocks}
                      currentMode={currentMode}
                      onAddBlock={handleAddBlock}
                    />
                  ))}
              </container>
            </Viewport>
          </Application>
      <ModeIndicator currentMode={currentMode} linkCreationStep={linkCreationState.step} />
    </div>
  );
}