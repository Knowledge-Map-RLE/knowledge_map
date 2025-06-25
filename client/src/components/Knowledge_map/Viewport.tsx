import { useRef, useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { Container, Graphics, Point, FederatedPointerEvent } from 'pixi.js';
import { extend, useApplication, useTick } from '@pixi/react';
import type { ReactNode } from 'react';
import { gsap } from 'gsap';

extend({ Container, Graphics, Point });

interface ViewportProps {
  children: ReactNode;
  onCanvasClick?: (x: number, y: number) => void;
  isBlockContextMenuActive?: boolean;
  blockRightClickRef?: React.RefObject<boolean>;
  instantBlockClickRef?: React.RefObject<boolean>;
  onBlockRightClickTime?: (time: number) => void;
}

export interface ViewportRef {
  focusOn: (x: number, y: number) => void;
  scale: number;
  position: { x: number; y: number };
  containerRef: Container | null;
  setBlockRightClickTime: (time: number) => void;
}

// TODO: исправить центрирование
export const Viewport = forwardRef<ViewportRef, ViewportProps>(({ children, onCanvasClick, isBlockContextMenuActive = false, blockRightClickRef, instantBlockClickRef, onBlockRightClickTime }, ref) => {
  const containerRef = useRef<Container | null>(null);
  const gridRef = useRef<Graphics | null>(null);
  const tweensRef = useRef<gsap.core.Tween[]>([]);
  const { app } = useApplication();
  const lastBlockRightClickTime = useRef<number>(0);
  
  const [isDragging, setIsDragging] = useState(false);
  const dragWorld = useRef<Point | null>(null);
  const [centerX, setCenterX] = useState(400);
  const [centerY, setCenterY] = useState(300);

  // DOM перетаскивание как запасной вариант
  useEffect(() => {
    if (!app) return;
    
    const timer = setTimeout(() => {
      if (!app || !app.renderer || !app.renderer.view) {
        return;
      }
      
      const canvas = app.canvas as HTMLCanvasElement;
      if (!canvas) {
        return;
      }
      
      // Глобальный блокировщик в capture фазе - срабатывает ДО ВСЕХ остальных обработчиков
      // Убираем capture blocker - он создавал конфликты

      const onPointerDown = (e: PointerEvent) => {
        if (e.button !== 2) return;
        
        const now = Date.now();
        console.log('DOM pointer down', e.button, 'contextMenuActive:', isBlockContextMenuActive, 'blockFlag:', blockRightClickRef?.current, 'instantFlag:', instantBlockClickRef?.current, 'time since last block click:', now - lastBlockRightClickTime.current);
        
        // ПЕРВАЯ ПРОВЕРКА: instant флаг - если блок уже отметился, то не запускаем перетаскивание
        if (instantBlockClickRef && instantBlockClickRef.current) {
          console.log('DOM: Blocking drag due to INSTANT block click flag');
          e.preventDefault();
          e.stopPropagation();
          return;
        }
        
        // Если активно контекстное меню блока, не запускаем перетаскивание
        if (isBlockContextMenuActive || (blockRightClickRef && blockRightClickRef.current)) {
          console.log('DOM: Blocking drag due to active context menu');
          e.preventDefault();
          e.stopPropagation();
          return;
        }
        
        // Проверяем время последнего правого клика по блоку - уменьшаем до 100ms для более точности
        if (now - lastBlockRightClickTime.current < 100) {
          console.log('DOM: Blocking drag due to recent block click');
          e.preventDefault();
          e.stopPropagation();
          return;
        }
        
        e.preventDefault();
        
        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const cnt = containerRef.current;
        if (!cnt) return;
        
        const worldPoint = cnt.toLocal({ x: sx, y: sy });
        dragWorld.current = new Point(worldPoint.x, worldPoint.y);
        setIsDragging(true);
        console.log('DOM: Started dragging');
      };

      const onPointerMove = (e: PointerEvent) => {
        if (!dragWorld.current || !containerRef.current || !isDragging) return;
        
        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const cnt = containerRef.current;
        
        const screenPos = cnt.toGlobal(dragWorld.current);
        cnt.position.x += sx - screenPos.x;
        cnt.position.y += sy - screenPos.y;
      };

      const onPointerUp = (e: PointerEvent) => {
        if (e.button !== 2) return;
        if (isDragging) {
          setIsDragging(false);
          dragWorld.current = null;
          console.log('DOM: Stopped dragging');
        }
      };
      
      const onContextMenu = (e: Event) => e.preventDefault();
      
      // Условно добавляем обработчики - НЕ добавляем если контекстное меню активно
      if (!isBlockContextMenuActive) {
        canvas.addEventListener('pointerdown', onPointerDown);
        canvas.addEventListener('pointermove', onPointerMove);
        canvas.addEventListener('pointerup', onPointerUp);
      }
      canvas.addEventListener('contextmenu', onContextMenu);
      
      return () => {
        canvas.removeEventListener('pointerdown', onPointerDown);
        canvas.removeEventListener('pointermove', onPointerMove);
        canvas.removeEventListener('pointerup', onPointerUp);
        canvas.removeEventListener('contextmenu', onContextMenu);
      };
    }, 500);
    
    return () => clearTimeout(timer);
  }, [app, isBlockContextMenuActive, blockRightClickRef, instantBlockClickRef, isDragging]);
  
  // Зум через DOM события
  useEffect(() => {
    if (!app) return;
    
    const timer = setTimeout(() => {
      if (!app || !app.renderer || !app.renderer.view) {
        return;
      }
      
      const canvas = app.canvas as HTMLCanvasElement;
      if (!canvas) {
        return;
      }
      
      const onWheel = (e: WheelEvent) => {
        e.preventDefault();
        const cnt = containerRef.current;
        if (!cnt) return;
        
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const oldScale = cnt.scale.x;
        const factor = Math.pow(1.001, -e.deltaY);
        const newScale = oldScale * factor;
        const world = cnt.toLocal({ x: mx, y: my });
        const worldPoint = new Point(world.x, world.y);
        
        cnt.scale.set(newScale);
        cnt.position.x -= worldPoint.x * (newScale - oldScale);
        cnt.position.y -= worldPoint.y * (newScale - oldScale);
      };
      
      canvas.addEventListener('wheel', onWheel, { passive: false });
      return () => {
        canvas.removeEventListener('wheel', onWheel);
      };
    }, 500);
    
    return () => clearTimeout(timer);
  }, [app]);

  // Динамическая сетка через useTick
  useTick(() => {
    if (!app) return;
    
    let screen;
    try {
      screen = app.screen;
    } catch {
      return;
    }
    
    if (!screen) return;
    
    const gfx = gridRef.current;
    const cnt = containerRef.current;
    if (!gfx || !cnt) return;
    
    const { width, height } = screen;
    const scale = cnt.scale.x;
    const pos = cnt.position;

    gfx.clear();
    
    // Фон
    gfx.rect(0, 0, width, height);
    gfx.fill(0xf5f5f5);

    // Динамический размер сетки
    let base = 100;
    const minPx = 30, maxPx = 100;
    let cell = base * scale;
    while (cell < minPx) { base *= 4; cell = base * scale; }
    while (cell > maxPx) { base /= 4; cell = base * scale; }
    
    const minor = base;
    const major = base * 5;

    const left = -pos.x / scale;
    const top = -pos.y / scale;
    const right = (width - pos.x) / scale;
    const bottom = (height - pos.y) / scale;

    // Мелкая сетка
    for (let x = Math.floor(left / minor) * minor; x < right; x += minor) {
      const sx = pos.x + x * scale;
      gfx.moveTo(sx, 0);
      gfx.lineTo(sx, height);
    }
    for (let y = Math.floor(top / minor) * minor; y < bottom; y += minor) {
      const sy = pos.y + y * scale;
      gfx.moveTo(0, sy);
      gfx.lineTo(width, sy);
    }
    gfx.stroke({ width: 1, color: 0xe0e0e0, alpha: 0.3 });

    // Крупная сетка
    for (let x = Math.floor(left / major) * major; x < right; x += major) {
      const sx = pos.x + x * scale;
      gfx.moveTo(sx, 0);
      gfx.lineTo(sx, height);
    }
    for (let y = Math.floor(top / major) * major; y < bottom; y += major) {
      const sy = pos.y + y * scale;
      gfx.moveTo(0, sy);
      gfx.lineTo(width, sy);
    }
    gfx.stroke({ width: 2, color: 0xdddddd });
  });

  // Обработка клика по canvas
  const handleCanvasClick = useCallback((event: FederatedPointerEvent) => {
    if (isDragging || !onCanvasClick || !containerRef.current) return;
    
    const localPoint = containerRef.current.toLocal(event.global);
    onCanvasClick(localPoint.x, localPoint.y);
  }, [isDragging, onCanvasClick]);

  // Обработчики перетаскивания через PIXI
  const handleBackgroundPointerDown = useCallback((event: any) => {
    console.log('Background pointer down:', event.button, event);
    
    if (event.button === 2) { // Правая кнопка мыши
      event.preventDefault();
      
      // Если активно контекстное меню блока, не запускаем перетаскивание
      if (isBlockContextMenuActive || (blockRightClickRef && blockRightClickRef.current)) {
        console.log('Blocking drag due to context menu');
        return;
      }
      
      const cnt = containerRef.current;
      if (!cnt) return;
      
      const worldPoint = cnt.toLocal(event.global);
      dragWorld.current = new Point(worldPoint.x, worldPoint.y);
      setIsDragging(true);
      console.log('Started dragging');
    } else if (event.button === 0) {
      // Левая кнопка для обычного клика
      if (onCanvasClick && !isDragging) {
        handleCanvasClick(event);
      }
    }
  }, [onCanvasClick, isDragging, isBlockContextMenuActive, blockRightClickRef, handleCanvasClick]);

  const handleBackgroundPointerMove = useCallback((event: any) => {
    if (!dragWorld.current || !containerRef.current || !isDragging) return;
    
    const cnt = containerRef.current;
    const screenPos = cnt.toGlobal(dragWorld.current);
    cnt.position.x += event.global.x - screenPos.x;
    cnt.position.y += event.global.y - screenPos.y;
  }, [isDragging]);

  const handleBackgroundPointerUp = useCallback((event: any) => {
    if (event.button === 2 && isDragging) {
      setIsDragging(false);
      dragWorld.current = null;
      console.log('Stopped dragging');
    }
  }, [isDragging]);

  // useImperativeHandle для focusOn
  useImperativeHandle(ref, () => ({
    focusOn: (targetX: number, targetY: number) => {
      if (!containerRef.current || !app) return;
      
      let screen;
      try {
        screen = app.screen;
      } catch {
        return;
      }
      
      if (!screen) return;
      
      // Убиваем предыдущие анимации
      tweensRef.current.forEach(tween => tween.kill());
      tweensRef.current = [];

      const cnt = containerRef.current;
      const duration = 1.2;

      // Центрируем на цели
      const newX = -targetX * cnt.scale.x + screen.width / 2;
      const newY = -targetY * cnt.scale.y + screen.height / 2;

      // Анимация позиции
      const positionTween = gsap.to(cnt.position, {
        x: newX,
        y: newY,
        duration,
        ease: "power3.inOut"
      });

      tweensRef.current.push(positionTween);
    },
    scale: containerRef.current?.scale.x || 1,
    position: containerRef.current?.position || { x: 0, y: 0 },
    containerRef: containerRef.current,
    setBlockRightClickTime: (time: number) => {
      lastBlockRightClickTime.current = time;
    },
  }));

  // Обновляем центр при изменении размеров экрана
  useEffect(() => {
    if (!app) return;
    
    let screen;
    try {
      screen = app.screen;
    } catch {
      return;
    }
    
    if (screen) {
      setCenterX(screen.width / 2);
      setCenterY(screen.height / 2);
    }
  }, [app]);

  return (
    <>
      <graphics 
        ref={gridRef}
        interactive={!!onCanvasClick}
        onPointerDown={onCanvasClick ? handleCanvasClick : undefined}
        draw={() => {}} 
      />
      <container
        ref={containerRef}
        interactive={false}
        x={centerX}
        y={centerY}
      >
        {children}
      </container>
    </>
  );
}); 