import { useState, useEffect, useCallback, useRef } from 'react';
import { Container, Graphics, Text } from 'pixi.js';
import { Application, extend } from '@pixi/react';
import { Block } from './Block';
import { Viewport } from './Viewport';
import { Link } from './Link';
import { Level, LevelData } from './Level';
import { Sublevel, SublevelData } from './Sublevel';
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
  sublevelId?: number; // Привязка к подуровню
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

// Цвета для уровней (из Python файла)
const LEVEL_COLORS = [0x4682b4, 0x20b2aa, 0xfa8072, 0xf0e68c, 0xdda0dd, 0xd3d3d3, 0xe0ffff, 0xe6e6fa];

// Цвета для подуровней
const SUBLEVEL_COLORS = [0xadd8e6, 0x90ee90, 0xf08080, 0xffffe0, 0xffc0cb, 0xd3d3d3, 0xe0ffff, 0xe6e6fa, 0xffe4e1, 0xf0fff0];

export default function Knowledge_map() {
  // Ref для container чтобы установить фокус
  const containerRef = useRef<HTMLDivElement>(null);

  // Состояние для данных карты знаний
  const [blocks, setBlocks] = useState<BlockData[]>([
    {
      id: '1',
      text: 'Основы программирования',
      x: -250,
      y: 0,
      level: 0,
      layer: 0,
      sublevelId: 0
    },
    {
      id: '2', 
      text: 'JavaScript',
      x: 0,
      y: 0,
      level: 0,
      layer: 1,
      sublevelId: 0
    },
    {
      id: '3',
      text: 'React',
      x: 250,
      y: 0,
      level: 0,
      layer: 2,
      sublevelId: 0
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

  // Состояние для уровней и подуровней (будет получаться с сервера)
  const [levels, setLevels] = useState<LevelData[]>([]);
  const [sublevels, setSublevels] = useState<SublevelData[]>([]);

  const [selectedBlocks, setSelectedBlocks] = useState<string[]>([]);
  const [selectedLinks, setSelectedLinks] = useState<string[]>([]);
  const [currentMode, setCurrentMode] = useState<EditMode>(EditMode.SELECT);
  
  // Для режима создания связей
  const [linkCreationState, setLinkCreationState] = useState<{ step: 'waiting' | 'first_selected' }>({ step: 'waiting' });
  const [firstBlockForLink, setFirstBlockForLink] = useState<string | null>(null);

  const [pixiReady, setPixiReady] = useState(false);

  // Добавить перед handleKeyDown (примерно после useState):
  const pressedKeys = useRef<Set<string>>(new Set());

  // Загрузка данных с сервера
  useEffect(() => {
    // Имитация запроса к серверу для получения layout данных
    const loadLayoutData = async () => {
      try {
        // TODO: заменить на реальный API запрос
        // const response = await fetch('/api/knowledge-map/layout');
        // const layoutData = await response.json();
        
        // Пока используем моковые данные, основанные на текущих блоках
        const mockLayoutData = generateMockLayoutData(blocks, links);
        
        setLevels(mockLayoutData.levels);
        setSublevels(mockLayoutData.sublevels);
        setBlocks(mockLayoutData.blocks);
        
      } catch (error) {
        console.error('Ошибка при загрузке layout данных:', error);
      }
    };

    loadLayoutData();
  }, []); // Загружаем один раз при монтировании

  // Функция для генерации моковых данных layout'а
  const generateMockLayoutData = (blocksData: BlockData[], linksData: LinkData[]) => {
    // Создаем подуровни на основе Y координат блоков
    const sublevelMap = new Map<number, { y: number, blockIds: string[], minX: number, maxX: number }>();
    
    blocksData.forEach(block => {
      const sublevelY = Math.round(block.y / 100) * 100; // Группируем по 100 пикселей
      if (!sublevelMap.has(sublevelY)) {
        sublevelMap.set(sublevelY, {
          y: sublevelY,
          blockIds: [],
          minX: block.x,
          maxX: block.x
        });
      }
      
      const sublevel = sublevelMap.get(sublevelY)!;
      sublevel.blockIds.push(block.id);
      sublevel.minX = Math.min(sublevel.minX, block.x - 100);
      sublevel.maxX = Math.max(sublevel.maxX, block.x + 100);
    });

    // Создаем подуровни
    const sublevelsList: SublevelData[] = Array.from(sublevelMap.entries()).map(([sublevelY, data], index) => ({
      id: index,
      y: sublevelY,
      blockIds: data.blockIds,
      minX: data.minX,
      maxX: data.maxX,
      color: SUBLEVEL_COLORS[index % SUBLEVEL_COLORS.length],
      levelId: Math.floor(index / 2) // Группируем по 2 подуровня в уровень
    }));

    // Создаем уровни
    const levelMap = new Map<number, { sublevelIds: number[], minX: number, maxX: number, minY: number, maxY: number }>();
    
    sublevelsList.forEach(sublevel => {
      if (!levelMap.has(sublevel.levelId)) {
        levelMap.set(sublevel.levelId, {
          sublevelIds: [],
          minX: sublevel.minX,
          maxX: sublevel.maxX,
          minY: sublevel.y,
          maxY: sublevel.y
        });
      }
      
      const level = levelMap.get(sublevel.levelId)!;
      level.sublevelIds.push(sublevel.id);
      level.minX = Math.min(level.minX, sublevel.minX);
      level.maxX = Math.max(level.maxX, sublevel.maxX);
      level.minY = Math.min(level.minY, sublevel.y);
      level.maxY = Math.max(level.maxY, sublevel.y);
    });

    const levelsList: LevelData[] = Array.from(levelMap.entries()).map(([levelId, data]) => ({
      id: levelId,
      sublevelIds: data.sublevelIds,
      minX: data.minX,
      maxX: data.maxX,
      minY: data.minY,
      maxY: data.maxY,
      color: LEVEL_COLORS[levelId % LEVEL_COLORS.length]
    }));

    // Обновляем блоки с привязкой к подуровням
    const updatedBlocks = blocksData.map(block => {
      const sublevel = sublevelsList.find(sl => sl.blockIds.includes(block.id));
      return {
        ...block,
        sublevelId: sublevel?.id
      };
    });

    return {
      levels: levelsList,
      sublevels: sublevelsList,
      blocks: updatedBlocks
    };
  };

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

  // Обработка клавиш для смены режимов
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
  }, [isInputFocused, currentMode]);

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
        if (linkCreationState.step === 'waiting') {
          setFirstBlockForLink(blockId);
          setLinkCreationState({ step: 'first_selected' });
          console.log('First block selected for link:', blockId);
        } else if (linkCreationState.step === 'first_selected') {
          if (firstBlockForLink && firstBlockForLink !== blockId) {
            handleCreateLink(firstBlockForLink, blockId);
            setFirstBlockForLink(null);
            setLinkCreationState({ step: 'waiting' });
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

  // Обработка наведения на уровень
  const handleLevelHover = (levelId: number, isHovered: boolean) => {
    console.log(`Level ${levelId} ${isHovered ? 'hovered' : 'unhovered'}`);
  };

  // Обработка наведения на подуровень
  const handleSublevelHover = (sublevelId: number, isHovered: boolean) => {
    console.log(`Sublevel ${sublevelId} ${isHovered ? 'hovered' : 'unhovered'}`);
  };

  // Обработка клика по подуровню для создания блока
  const handleSublevelClick = (sublevelId: number, x: number, y: number) => {
    if (currentMode === EditMode.CREATE_BLOCKS) {
      handleCreateBlockOnSublevel(x, y, sublevelId);
    }
  };

  // Создание нового блока на подуровне
  const handleCreateBlockOnSublevel = async (x: number, y: number, sublevelId: number) => {
    try {
      console.log(`Creating block at (${x}, ${y}) on sublevel ${sublevelId}`);
      
      const sublevel = sublevels.find(sl => sl.id === sublevelId);
      if (!sublevel) {
        console.error('Sublevel not found:', sublevelId);
        return;
      }

      const mockServerResponse = {
        id: Date.now().toString(),
        text: 'Новый блок',
        x: Math.round(x / 50) * 50,
        y: sublevel.y, // Используем Y координату подуровня
        level: sublevel.levelId,
        layer: Math.round(x / 250), // Приблизительный расчет слоя
        sublevelId: sublevelId
      };
      
      setBlocks(prev => [...prev, mockServerResponse]);
      
      // Обновляем подуровень
      setSublevels(prev => prev.map(sl => 
        sl.id === sublevelId 
          ? { ...sl, blockIds: [...sl.blockIds, mockServerResponse.id] }
          : sl
      ));
      
      console.log('Block created on sublevel:', mockServerResponse);
      
    } catch (error) {
      console.error('Ошибка при создании блока на подуровне:', error);
    }
  };

  // Создание нового блока (оригинальный метод для клика по canvas)
  const handleCreateBlock = async (x: number, y: number) => {
    if (currentMode !== EditMode.CREATE_BLOCKS) return;

    // Находим ближайший подуровень
    const nearestSublevel = sublevels.reduce((nearest, sublevel) => {
      const distance = Math.abs(sublevel.y - y);
      const nearestDistance = Math.abs(nearest.y - y);
      return distance < nearestDistance ? sublevel : nearest;
    }, sublevels[0]);

    if (nearestSublevel) {
      handleCreateBlockOnSublevel(x, nearestSublevel.y, nearestSublevel.id);
    } else {
      // Если подуровней нет, создаем обычным способом
      try {
        console.log(`Creating block at (${x}, ${y})`);
        
        const mockServerResponse = {
          id: Date.now().toString(),
          text: 'Новый блок',
          x: Math.round(x / 50) * 50,
          y: Math.round(y / 50) * 50,
          level: Math.round(y / 150),
          layer: 1,
          sublevelId: undefined
        };
        
        setBlocks(prev => [...prev, mockServerResponse]);
        console.log('Block created:', mockServerResponse);
        
      } catch (error) {
        console.error('Ошибка при создании блока:', error);
      }
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
      
      // Обновляем подуровни
      setSublevels(prev => prev.map(sl => ({
        ...sl,
        blockIds: sl.blockIds.filter(id => id !== blockId)
      })));
      
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
          {/* Рендерим уровни (на заднем плане) */}
          {levels.map(level => (
            <Level
              key={`level-${level.id}`}
              levelData={level}
              onLevelHover={handleLevelHover}
            />
          ))}

          {/* Рендерим подуровни (поверх уровней) */}
          {sublevels.map(sublevel => (
            <Sublevel
              key={`sublevel-${sublevel.id}`}
              sublevelData={sublevel}
              onSublevelHover={handleSublevelHover}
              onSublevelClick={handleSublevelClick}
            />
          ))}
          
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
          
          {/* Рендерим блоки (на переднем плане) */}
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