import { useRef, useState, useEffect, useCallback, forwardRef, useImperativeHandle, createContext, useContext } from 'react';
import { Container, Graphics, Point, FederatedPointerEvent } from 'pixi.js';
import { extend, useApplication, useTick } from '@pixi/react';
import type { ReactNode } from 'react';
import { gsap } from 'gsap';

extend({ Container, Graphics, Point });

// Контекст для передачи ссылки на контейнер потомкам
export const ViewportContainerContext = createContext<React.RefObject<Container | null>>({ current: null });
export const useViewportContainer = () => useContext(ViewportContainerContext);

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
  getWorldCenter: () => { x: number; y: number } | null;
  getWorldBounds?: () => { left: number; top: number; right: number; bottom: number } | null;
  getScreenSize?: () => { width: number; height: number } | null;
  on?: (event: 'moved' | 'zoomed', handler: () => void) => void;
  off?: (event: 'moved' | 'zoomed', handler: () => void) => void;
  setScale?: (scale: number) => void;
  getScale?: () => number;
}

// TODO: исправить центрирование
export const Viewport = forwardRef<ViewportRef, ViewportProps>(({ children, onCanvasClick, isBlockContextMenuActive = false, blockRightClickRef, instantBlockClickRef, onBlockRightClickTime }, ref) => {
  const containerRef = useRef<Container | null>(null);
  const gridRef = useRef<Graphics | null>(null);
  const tweensRef = useRef<gsap.core.Tween[]>([]);
  const listenersRef = useRef<Record<'moved' | 'zoomed', Set<() => void>>>({ moved: new Set(), zoomed: new Set() });
  const { app } = useApplication();
  const lastBlockRightClickTime = useRef<number>(0);
  const isDraggingRef = useRef<boolean>(false);

  const [isDragging, setIsDragging] = useState(false);
  const dragWorld = useRef<Point | null>(null);
  const [centerX, setCenterX] = useState(400);
  const [centerY, setCenterY] = useState(300);

  const emit = useCallback((event: 'moved' | 'zoomed') => {
    const set = listenersRef.current[event];
    set.forEach(fn => {
      try { fn(); } catch {}
    });
  }, []);

  // Зум через DOM события (wheel) — перетаскивание через Pixi (graphics onPointerDown)
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
        emit('zoomed');
        emit('moved');
      };

      const onContextMenu = (e: Event) => e.preventDefault();

      canvas.addEventListener('wheel', onWheel, { passive: false });
      canvas.addEventListener('contextmenu', onContextMenu);
      
      // --- DEBUG: слушаем pointerdown на canvas напрямую ---
      const debugCanvasPointerDown = (e: PointerEvent) => {
        console.log('[DEBUG] Canvas pointerdown:', e.button, 'at', e.clientX, e.clientY);
      };
      const debugCanvasPointerMove = (e: PointerEvent) => {
        if (isDraggingRef.current && dragWorld.current) {
          console.log('[DEBUG] Canvas pointermove drag at', e.clientX, e.clientY);
          const cnt = containerRef.current;
          if (!cnt) return;
          const rect = canvas.getBoundingClientRect();
          const mx = e.clientX - rect.left;
          const my = e.clientY - rect.top;
          const worldX = dragWorld.current.x;
          const worldY = dragWorld.current.y;
          cnt.position.x = mx - worldX * cnt.scale.x;
          cnt.position.y = my - worldY * cnt.scale.y;
          emit('moved');
        }
      };
      const debugCanvasPointerDownDrag = (e: PointerEvent) => {
        console.log('[DEBUG] pointerdown drag handler:', e.button, 'isDragging:', isDraggingRef.current);
        if (e.button === 2) {
          e.preventDefault();
          const cnt = containerRef.current;
          if (!cnt) { console.log('[DEBUG] NO containerRef'); return; }
          const rect = canvas.getBoundingClientRect();
          const mx = e.clientX - rect.left;
          const my = e.clientY - rect.top;
          const world = cnt.toLocal({ x: mx, y: my } as any);
          dragWorld.current = new Point(world.x, world.y);
          isDraggingRef.current = true;
          setIsDragging(true);
          console.log('[DEBUG] Started dragging at', world.x, world.y, 'scale:', cnt.scale.x, 'pos:', cnt.position.x, cnt.position.y);
        }
      };
      const debugCanvasPointerUp = (e: PointerEvent) => {
        if (e.button === 2 && isDraggingRef.current) {
          isDraggingRef.current = false;
          setIsDragging(false);
          dragWorld.current = null;
          console.log('[DEBUG] Stopped dragging');
          emit('moved');
        }
      };
      
      canvas.addEventListener('pointerdown', debugCanvasPointerDown);
      canvas.addEventListener('pointerdown', debugCanvasPointerDownDrag);
      canvas.addEventListener('pointermove', debugCanvasPointerMove);
      canvas.addEventListener('pointerup', debugCanvasPointerUp);
      
      return () => {
        canvas.removeEventListener('wheel', onWheel);
        canvas.removeEventListener('contextmenu', onContextMenu);
        canvas.removeEventListener('pointerdown', debugCanvasPointerDown);
        canvas.removeEventListener('pointerdown', debugCanvasPointerDownDrag);
        canvas.removeEventListener('pointermove', debugCanvasPointerMove);
        canvas.removeEventListener('pointerup', debugCanvasPointerUp);
      };
    }, 500);

    return () => clearTimeout(timer);
  }, [app, emit]);

  // Динамическая сетка через useTick + обновление курсора
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

    // Обновляем курсор
    gfx.cursor = isDraggingRef.current ? 'grabbing' : 'grab';

    gfx.clear();
    
    // Фон: закрашиваем только при изменении размера или масштаба (минимизация заливок)
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
    console.log('Background pointer down:', event.button);

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
      isDraggingRef.current = true;
      setIsDragging(true);
      console.log('Started dragging');
    } else if (event.button === 0) {
      // Левая кнопка для обычного клика
      if (onCanvasClick && !isDraggingRef.current) {
        handleCanvasClick(event);
      }
    }
  }, [onCanvasClick, isBlockContextMenuActive, blockRightClickRef, handleCanvasClick]);

  const handleBackgroundPointerMove = useCallback((event: any) => {
    if (!dragWorld.current || !containerRef.current || !isDraggingRef.current) return;

    const cnt = containerRef.current;
    const screenPos = cnt.toGlobal(dragWorld.current);
    cnt.position.x += event.global.x - screenPos.x;
    cnt.position.y += event.global.y - screenPos.y;
    emit('moved');
  }, [emit]);

  const handleBackgroundPointerUp = useCallback((event: any) => {
    if (event.button === 2 && isDraggingRef.current) {
      isDraggingRef.current = false;
      setIsDragging(false);
      dragWorld.current = null;
      console.log('Stopped dragging');
      emit('moved');
    }
  }, [emit]);

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
    get scale() { return containerRef.current?.scale.x ?? 1; },
    get position() { return containerRef.current?.position ?? { x: 0, y: 0 }; },
    containerRef: containerRef.current,
    setBlockRightClickTime: (time: number) => {
      lastBlockRightClickTime.current = time;
    },
    setScale: (scale: number) => {
      const cnt = containerRef.current;
      if (!cnt) return;
      const oldScale = cnt.scale.x;
      cnt.scale.set(scale);
      // Эмитим события для подписчиков
      emit('zoomed');
      if (oldScale !== scale) {
        emit('moved');
      }
    },
    getWorldCenter: () => {
      if (!app || !containerRef.current) return null;
      let screen;
      try { screen = app.screen; } catch { return null; }
      if (!screen) return null;
      const cnt = containerRef.current;
      const centerScreenX = screen.width / 2;
      const centerScreenY = screen.height / 2;
      const world = cnt.toLocal({ x: centerScreenX, y: centerScreenY } as any);
      return { x: world.x, y: world.y };
    },
    getWorldBounds: () => {
      if (!app || !containerRef.current) return null;
      let screen;
      try { screen = app.screen; } catch { return null; }
      if (!screen) return null;
      const cnt = containerRef.current;
      const scale = cnt.scale.x;
      const pos = cnt.position;
      const left = -pos.x / scale;
      const top = -pos.y / scale;
      const right = (screen.width - pos.x) / scale;
      const bottom = (screen.height - pos.y) / scale;
      return { left, top, right, bottom };
    },
    getScreenSize: () => {
      if (!app) return null;
      let screen;
      try { screen = app.screen; } catch { return null; }
      if (!screen) return null;
      return { width: screen.width, height: screen.height };
    },
    on: (event: 'moved' | 'zoomed', handler: () => void) => {
      listenersRef.current[event].add(handler);
    },
    off: (event: 'moved' | 'zoomed', handler: () => void) => {
      listenersRef.current[event].delete(handler);
    },
    getScale: () => containerRef.current?.scale.x ?? 1,
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
    <ViewportContainerContext.Provider value={containerRef}>
      <graphics
        ref={gridRef}
        eventMode="static"
        cursor="grab"
        onPointerDown={handleBackgroundPointerDown}
        onPointerMove={handleBackgroundPointerMove}
        onPointerUp={handleBackgroundPointerUp}
        onPointerUpOutside={handleBackgroundPointerUp}
        draw={() => {}}
      />
      <container
        ref={containerRef}
        interactive={false}
        x={0}
        y={0}
      >
        {children}
      </container>
    </ViewportContainerContext.Provider>
  );
}); 