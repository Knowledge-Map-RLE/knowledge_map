import { useState, useEffect, useCallback, useRef } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Block } from './Block';
import { Viewport } from './Viewport';
import { Link } from './Link';
import ModeIndicator from './ModeIndicator';
import styles from './Knowledge_map.module.css';

extend({ Container, Graphics, Text });

export interface BlockData {
  id: string;
  text: string;
  x: number;
  y: number;
  level: number;
  layer: number;
}

export interface LinkData {
  id: string;
  fromId: string;
  toId: string;
}

export enum EditMode {
  SELECT = 'SELECT',
  CREATE_BLOCKS = 'CREATE_BLOCKS', 
  CREATE_LINKS = 'CREATE_LINKS',
  DELETE = 'DELETE'
}

export default function Knowledge_map() {
  // Ref для container чтобы установить фокус
  const containerRef = useRef<HTMLDivElement>(null);

  // Тестовые данные
  const [blocks, setBlocks] = useState<BlockData[]>([
    {
      id: '1',
      text: 'Основы программирования',
      x: -250,
      y: 0,
      level: 1,
      layer: 1
    },
    {
      id: '2',
      text: 'JavaScript',
      x: 0,
      y: 0,
      level: 1,
      layer: 1
    },
    {
      id: '3',
      text: 'React',
      x: 250,
      y: 0,
      level: 1,
      layer: 1
    }
  ]);

  const [links, setLinks] = useState<LinkData[]>([
    {
      id: 'link1',
      fromId: '1',
      toId: '2'
    },
    {
      id: 'link2',
      fromId: '2',
      toId: '3'
    }
  ]);

  const [selectedBlocks, setSelectedBlocks] = useState<string[]>([]);
  const [selectedLinks, setSelectedLinks] = useState<string[]>([]);
  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  
  // Для режима создания связей
  const [linkCreationState, setLinkCreationState] = useState<{ step: 'waiting' | 'first_selected' }>({ step: 'waiting' });
  const [firstBlockForLink, setFirstBlockForLink] = useState<string | null>(null);

  const [pixiReady, setPixiReady] = useState(false);

  // Добавить перед handleKeyDown (примерно после useState):
  const pressedKeys = useRef<Set<string>>(new Set());

  // Задержка для полной инициализации PixiJS
  useEffect(() => {
    const timer = setTimeout(() => {
      setPixiReady(true);
    }, 500); // Даем время PixiJS полностью инициализироваться

    return () => clearTimeout(timer);
  }, []);

  // Установка фокуса на контейнер при монтировании
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.focus();
    }
  }, []);

  // Проверка, есть ли фокус на полях ввода
  const isInputFocused = useCallback(() => {
    const activeElement = document.activeElement;
    return activeElement && (
      activeElement.tagName === 'INPUT' || 
      activeElement.tagName === 'TEXTAREA' ||
      activeElement.contentEditable === 'true'
    );
  }, []);

  // Обработка клавиш для смены режимов - ИСПРАВЛЕНО: разная логика для разных режимов
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Игнорируем автоповтор клавиш
      if (e.repeat) return;
      
      // Проверяем, что клавиша еще не нажата
      if (pressedKeys.current.has(e.code)) return;
      pressedKeys.current.add(e.code);

      console.log('KeyDown:', e.code, 'Current mode:', currentMode);

      // Escape всегда возвращает в режим SELECT и сбрасывает создание связей
      if (e.code === 'Escape') {
        setCurrentMode(EditMode.SELECT);
        setLinkCreationState({ step: 'waiting' });
        return;
      }

      // Логика переключения режимов
      switch (e.code) {
        case 'KeyQ':
          setCurrentMode(EditMode.CREATE_BLOCKS);
          setLinkCreationState({ step: 'waiting' });
          break;
        case 'KeyW':
          setCurrentMode(EditMode.CREATE_LINKS);
          setLinkCreationState({ step: 'waiting' });
          break;
        case 'KeyE':
          setCurrentMode(EditMode.DELETE);
          setLinkCreationState({ step: 'waiting' });
          break;
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      // Удаляем клавишу из набора нажатых
      pressedKeys.current.delete(e.code);
      
      console.log('KeyUp:', e.code, 'Current mode:', currentMode);

      // Для всех режимов возвращаемся в SELECT при отпускании клавиши
      switch (e.code) {
        case 'KeyQ':
          if (currentMode === EditMode.CREATE_BLOCKS) {
            setCurrentMode(EditMode.SELECT);
          }
          break;
        case 'KeyW':
          if (currentMode === EditMode.CREATE_LINKS) {
            setCurrentMode(EditMode.SELECT);
            // Сбрасываем состояние создания связи при выходе из режима
            setLinkCreationState({ step: 'waiting' });
          }
          break;
        case 'KeyE':
          if (currentMode === EditMode.DELETE) {
            setCurrentMode(EditMode.SELECT);
          }
          break;
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keyup', handleKeyUp);
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [isInputFocused, currentMode]); // Добавили currentMode в зависимости

  // Логирование изменения режима
  useEffect(() => {
    console.log('Current mode changed to:', currentMode);
  }, [currentMode]);

  // Обработка клика по блоку в зависимости от режима
  const handleBlockClick = (blockId: string) => {
    console.log('Block clicked:', blockId, 'Current mode:', currentMode, 'Link creation step:', linkCreationState.step);
    
    switch (currentMode) {
      case EditMode.SELECT:
        setSelectedBlocks(prev => 
          prev.includes(blockId) 
            ? prev.filter(id => id !== blockId)
            : [...prev, blockId]
        );
        break;

      case EditMode.CREATE_LINKS:
        console.log('Processing link creation...');
        if (linkCreationState.step === 'waiting') {
          console.log('Selecting first block for link:', blockId);
          setFirstBlockForLink(blockId);
          setSelectedBlocks([blockId]);
          setLinkCreationState({ step: 'first_selected' });
        } else if (linkCreationState.step === 'first_selected' && firstBlockForLink) {
          if (blockId !== firstBlockForLink) {
            console.log('Creating link from', firstBlockForLink, 'to', blockId);
            handleCreateLink(firstBlockForLink, blockId);
            // После создания связи возвращаемся к ожиданию следующей связи
            setLinkCreationState({ step: 'waiting' });
            setFirstBlockForLink(null);
            setSelectedBlocks([]);
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
        setSelectedLinks(prev => 
          prev.includes(linkId) 
            ? prev.filter(id => id !== linkId)
            : [...prev, linkId]
        );
        break;

      case EditMode.DELETE:
        handleDeleteLink(linkId);
        break;
    }
  };

  // Создание нового блока
  const handleCreateBlock = async (x: number, y: number) => {
    if (currentMode !== EditMode.CREATE_BLOCKS) return;

    try {
      console.log(`Creating block at (${x}, ${y})`);
      
      const mockServerResponse = {
        id: Date.now().toString(),
        text: 'Новый блок',
        x: Math.round(x / 50) * 50,
        y: Math.round(y / 50) * 50,
        level: Math.round(y / 150),
        layer: 1
      };
      
      setBlocks(prev => [...prev, mockServerResponse]);
      console.log('Block created:', mockServerResponse);
      
    } catch (error) {
      console.error('Ошибка при создании блока:', error);
    }
  };

  // Создание связи
  const handleCreateLink = async (fromId: string, toId: string) => {
    try {
      console.log(`Creating link ${fromId} -> ${toId}`);
      
      const mockServerResponse = {
        id: `link_${Date.now()}`,
        fromId,
        toId
      };
      
      setLinks(prev => [...prev, mockServerResponse]);
      console.log('Link created:', mockServerResponse);
      
    } catch (error) {
      console.error('Ошибка при создании связи:', error);
    }
  };

  // Удаление блока
  const handleDeleteBlock = async (blockId: string) => {
    try {
      console.log(`Deleting block ${blockId}`);
      
      setBlocks(prev => prev.filter(block => block.id !== blockId));
      setLinks(prev => prev.filter(link => 
        link.fromId !== blockId && link.toId !== blockId
      ));
      setSelectedBlocks(prev => prev.filter(id => id !== blockId));
      
      console.log('Block deleted:', blockId);
      
    } catch (error) {
      console.error('Ошибка при удалении блока:', error);
    }
  };

  // Удаление связи
  const handleDeleteLink = async (linkId: string) => {
    try {
      console.log(`Deleting link ${linkId}`);
      
      setLinks(prev => prev.filter(link => link.id !== linkId));
      setSelectedLinks(prev => prev.filter(id => id !== linkId));
      
      console.log('Link deleted:', linkId);
      
    } catch (error) {
      console.error('Ошибка при удалении связи:', error);
    }
  };

  // Создание карты блоков для поиска
  const blocksMap = new Map<string, BlockData>();
  blocks.forEach(block => {
    blocksMap.set(block.id, block);
  });

  // Обработка клика по контейнеру для установки фокуса
  const handleContainerClick = () => {
    if (containerRef.current) {
      containerRef.current.focus();
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
      className={styles.knowledge_map}
      tabIndex={0}
      onMouseDown={handleContainerClick}
      style={{ outline: 'none' }}
    >
      {/* Индикатор текущего режима */}
      <ModeIndicator 
        currentMode={currentMode}
        linkCreationStep={linkCreationState.step}
        firstBlockForLink={firstBlockForLink}
      />
      
      <Application 
        width={window.innerWidth} 
        height={window.innerHeight}
        backgroundColor={0xf8fafc}
        resizeTo={window}
        preference="webgl"
      >
        <Viewport 
          onCanvasClick={handleCreateBlock}
          blocks={blocks}
        >
          {/* Рендерим связи */}
          {links.map(link => {
            const fromBlock = blocksMap.get(link.fromId);
            const toBlock = blocksMap.get(link.toId);
            
            if (!fromBlock || !toBlock) return null;
            
            return (
              <Link 
                key={link.id}
                linkData={link}
                fromBlock={fromBlock}
                toBlock={toBlock}
                isSelected={selectedLinks.includes(link.id)}
                onLinkClick={handleLinkClick}
              />
            );
          })}
          
          {/* Рендерим блоки */}
          {blocks.map(block => (
            <Block 
              key={block.id}
              blockData={block}
              isSelected={selectedBlocks.includes(block.id)}
              onBlockClick={handleBlockClick}
              isFirstForLink={firstBlockForLink === block.id}
            />
          ))}
        </Viewport>
      </Application>
    </div>
  );
}