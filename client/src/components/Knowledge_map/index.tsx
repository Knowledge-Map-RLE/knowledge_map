import { useState, useEffect, useRef } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Viewport } from './Viewport';
import { Link } from './Link';
import { Level } from './Level';
import ModeIndicator from './ModeIndicator';
import { useKeyboardControlsWithProps } from './hooks/useKeyboardControls';
import { useDataLoading } from './hooks/useDataLoading';
import { useSelectionState } from './hooks/useSelectionState';
import { useActions } from './hooks/useActions';
import { EditMode } from './types';
import type { LinkCreationState, BlockData } from './types';
import { BLOCK_WIDTH } from './constants';
import styles from './Knowledge_map.module.css';

extend({ Container, Graphics, Text });

export default function Knowledge_map() {
  // Ref для container чтобы установить фокус
  const containerRef = useRef<HTMLDivElement>(null);

  // Состояния из хуков
  const {
    blocks,
    links,
    levels,
    sublevels,
    isLoading,
    loadError,
    loadLayoutData,
    setBlocks,
    setLinks,
    setLevels,
    setSublevels
  } = useDataLoading();

  const {
    selectedBlocks,
    selectedLinks,
    handleBlockSelection,
    handleLinkSelection,
    clearSelection
  } = useSelectionState();

  const {
    handleCreateBlock,
    handleCreateBlockOnSublevel,
    handleCreateLink,
    handleDeleteBlock,
    handleDeleteLink
  } = useActions({
    blocks,
    links,
    sublevels,
    setBlocks,
    setLinks,
    setSublevels,
    clearSelection
  });

  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  const [linkCreationState, setLinkCreationState] = useState<LinkCreationState>({ step: 'waiting' });
  const [pixiReady, setPixiReady] = useState(false);

  // Подключаем управление клавиатурой
  useKeyboardControlsWithProps({
    setCurrentMode,
    setLinkCreationState,
    currentMode,
    linkCreationState
  });

  // Загрузка данных при монтировании
  useEffect(() => {
    loadLayoutData();
  }, [loadLayoutData]);

  // Задержка для полной инициализации PixiJS
  useEffect(() => {
    const timer = setTimeout(() => {
      setPixiReady(true);
    }, 500);

    return () => clearTimeout(timer);
  }, []);

  // Установка фокуса на контейнер при монтировании
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.focus();
    }
  }, []);

  useEffect(() => {
    console.log('Knowledge_map currentMode changed:', currentMode);
  }, [currentMode]);

  // Обработка клика по блоку
  const handleBlockClick = (blockId: string) => {
    const clickedBlock = blocks.find(block => block.id === blockId);
    if (!clickedBlock) return;

    switch (currentMode) {
      case EditMode.SELECT:
        handleBlockSelection(blockId);
        break;

      case EditMode.CREATE_LINKS:
        if (linkCreationState.step === 'selecting_source') {
          setLinkCreationState({ 
            step: 'selecting_target',
            sourceBlock: clickedBlock
          });
        } else if (linkCreationState.step === 'selecting_target' && 'sourceBlock' in linkCreationState) {
          handleCreateLink(linkCreationState.sourceBlock.id, blockId);
          setLinkCreationState({ step: 'selecting_source' });
        }
        break;

      case EditMode.DELETE:
        handleDeleteBlock(blockId);
        break;
    }
  };

  // Обработка клика по связи
  const handleLinkClick = (linkId: string) => {
    switch (currentMode) {
      case EditMode.SELECT:
        handleLinkSelection(linkId);
        break;

      case EditMode.DELETE:
        handleDeleteLink(linkId);
        break;
    }
  };

  // Обработка клика по подуровню для создания блока
  const handleSublevelClick = (sublevelId: number, x: number, y: number) => {
    if (currentMode === EditMode.CREATE_BLOCKS) {
      handleCreateBlockOnSublevel(x, y, sublevelId);
    }
  };

  // Обработка добавления блока через стрелки
  const handleAddBlock = async (sourceBlock: BlockData, targetLevel: number) => {
    console.log('handleAddBlock called:', { sourceBlock, targetLevel });
    
    // Находим подуровень на целевом уровне
    const targetSublevel = sublevels.find(
      sublevel => sublevel.level === targetLevel && 
      sublevel.min_y <= sourceBlock.y && 
      sublevel.max_y >= sourceBlock.y
    );

    console.log('Found target sublevel:', targetSublevel);
    if (!targetSublevel) {
      console.error('Target sublevel not found');
      return;
    }

    // Создаем новый блок
    const newX = targetLevel < sourceBlock.level ? 
      sourceBlock.x - BLOCK_WIDTH * 2 : 
      sourceBlock.x + BLOCK_WIDTH * 2;

    console.log('Creating new block at:', { x: newX, y: sourceBlock.y, sublevelId: targetSublevel.id });
    const newBlock = await handleCreateBlockOnSublevel(
      newX,
      sourceBlock.y,
      targetSublevel.id
    );

    console.log('New block created:', newBlock);
    // Создаем связь между блоками
    if (newBlock) {
      if (targetLevel < sourceBlock.level) {
        // Связь от нового блока к текущему
        console.log('Creating link from new block to source:', { from: newBlock.id, to: sourceBlock.id });
        await handleCreateLink(newBlock.id, sourceBlock.id);
      } else {
        // Связь от текущего блока к новому
        console.log('Creating link from source to new block:', { from: sourceBlock.id, to: newBlock.id });
        await handleCreateLink(sourceBlock.id, newBlock.id);
      }
    }
  };

  if (!pixiReady) {
    return (
      <div className={styles.knowledge_map}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center', 
          height: '100vh',
          color: '#666'
        }}>
          Инициализация PixiJS...
        </div>
      </div>
    );
  }

  return (
    <div 
      ref={containerRef}
      className={styles.container} 
      tabIndex={0}
    >
      {isLoading && (
        <div className={styles.overlay}>
          <div className={styles.loader}>Загрузка...</div>
        </div>
      )}
      
      {loadError && (
        <div className={styles.overlay}>
          <div className={styles.error}>
            <h3>Ошибка</h3>
            <p>{loadError}</p>
            <button onClick={loadLayoutData}>Повторить</button>
          </div>
        </div>
      )}
      
      {!isLoading && !loadError && pixiReady && (
        <>
          <Application
            width={window.innerWidth}
            height={window.innerHeight}
            backgroundColor={0xffffff}
            resizeTo={window}
          >
            <Viewport>
              <container>
                {/* Контейнер для уровней */}
                <container sortableChildren={true}>
                  {levels.map((level) => (
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

                {/* Контейнер для связей */}
                <container zIndex={3}>
                  {links.map((link) => (
                    <Link
                      key={link.id}
                      linkData={link}
                      blocks={blocks}
                      isSelected={selectedLinks.includes(link.id)}
                      onClick={() => handleLinkClick(link.id)}
                    />
                  ))}
                </container>
              </container>
            </Viewport>
          </Application>
          
          <ModeIndicator 
            currentMode={currentMode} 
            linkCreationStep={linkCreationState.step}
          />
        </>
      )}
    </div>
  );
}