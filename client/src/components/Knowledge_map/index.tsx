import { useState, useEffect, useRef } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Block } from './Block';
import { Viewport } from './Viewport';
import { Link } from './Link';
import { Level } from './Level';
import { Sublevel } from './Sublevel';
import ModeIndicator from './ModeIndicator';
import { useKeyboardControls } from './hooks/useKeyboardControls';
import { useDataLoading } from './hooks/useDataLoading';
import { useSelectionState } from './hooks/useSelectionState';
import { useActions } from './hooks/useActions';
import { EditMode } from './types';
import type { BlockData, LinkData, LevelData, SublevelData, LinkCreationState } from './types';
import styles from './Knowledge_map.module.css';

extend({ Container, Graphics, Text });

// Константы для расчета координат
const SUBLEVEL_SPACING = 200; // Расстояние между подуровнями в пикселях
const LAYER_SPACING = 250; // Расстояние между слоями в пикселях

// Цвета для уровней (из Python файла)
const LEVEL_COLORS = [0x4682b4, 0x20b2aa, 0xfa8072, 0xf0e68c, 0xdda0dd, 0xd3d3d3, 0xe0ffff, 0xe6e6fa];

// Цвета для подуровней
const SUBLEVEL_COLORS = [0xadd8e6, 0x90ee90, 0xf08080, 0xffffe0, 0xffc0cb, 0xd3d3d3, 0xe0ffff, 0xe6e6fa, 0xffe4e1, 0xf0fff0];

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
  const [firstBlockForLink, setFirstBlockForLink] = useState<string | null>(null);
  const [pixiReady, setPixiReady] = useState(false);

  // Подключаем управление клавиатурой
  useKeyboardControls({
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

  // Логирование изменения режима
  useEffect(() => {
    console.log('Current mode changed to:', currentMode);
  }, [currentMode]);

  // Отладочный эффект для отслеживания изменений в links
  useEffect(() => {
    console.log('Links array updated:', links);
  }, [links]);

  // Обработка клика по блоку в зависимости от режима
  const handleBlockClick = (blockId: string) => {
    console.log('Block clicked:', blockId, 'Current mode:', currentMode, 'Link creation step:', linkCreationState.step);
    
    switch (currentMode) {
      case EditMode.SELECT:
        handleBlockSelection(blockId);
        break;

      case EditMode.CREATE_LINKS:
        // Выделяем блок в любом случае
        handleBlockSelection(blockId);
        
        if (linkCreationState.step === 'waiting') {
          setFirstBlockForLink(blockId);
          setLinkCreationState({ step: 'first_selected' });
          console.log('First block selected for link:', blockId);
        } else if (linkCreationState.step === 'first_selected') {
          if (firstBlockForLink && firstBlockForLink !== blockId) {
            console.log('Creating link from', firstBlockForLink, 'to', blockId);
            handleCreateLink(firstBlockForLink, blockId);
            setFirstBlockForLink(null);
            setLinkCreationState({ step: 'waiting' });
            clearSelection(); // Очищаем выделение после создания связи
            console.log('Current links after creation:', links);
          } else {
            console.log('Cannot create link to the same block');
          }
        }
        break;

      case EditMode.DELETE:
        handleDeleteBlock(blockId);
        break;

      case EditMode.CREATE_BLOCKS:
        // В режиме создания блоков клик по существующему блоку ничего не делает
        console.log('Block click ignored in CREATE_BLOCKS mode');
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

  // Обработчики наведения на уровни и подуровни
  const handleLevelHover = (level: LevelData | null) => {
    // Обработка наведения на уровень
  };

  const handleSublevelHover = (sublevel: SublevelData | null) => {
    // Обработка наведения на подуровень
  };

  // Обработка клика по подуровню для создания блока
  const handleSublevelClick = (sublevelId: number, x: number, y: number) => {
    if (currentMode === EditMode.CREATE_BLOCKS) {
      handleCreateBlockOnSublevel(x, y, sublevelId);
    }
  };

  // Обработчики событий клавиатуры для div контейнера
  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Пустая функция, так как основная логика обрабатывается в useEffect
  };

  const handleKeyUp = (e: React.KeyboardEvent) => {
    // Пустая функция, так как основная логика обрабатывается в useEffect
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
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
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
                      onLevelHover={handleLevelHover}
                      onSublevelHover={handleSublevelHover}
                      onSublevelClick={handleSublevelClick}
                      onBlockClick={(blockId) => handleBlockSelection(blockId)}
                      onBlockHover={(block) => {/* Обработка наведения на блок */}}
                      selectedBlocks={selectedBlocks}
                    />
                  ))}
                </container>

                {/* Контейнер для связей */}
                <container zIndex={3}>
                  {(() => {
                    console.log('Rendering links container, links:', links);
                    return links.map((link) => {
                      console.log('Rendering link:', link);
                      return (
                        <Link
                          key={link.id}
                          linkData={link}
                          blocks={blocks}
                          isSelected={selectedLinks.includes(link.id)}
                          onClick={() => handleLinkClick(link.id)}
                        />
                      );
                    });
                  })()}
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