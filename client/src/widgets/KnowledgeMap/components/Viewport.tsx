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
  onDragStart?: () => void;
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
export const Viewport = forwardRef<ViewportRef, ViewportProps>(({ children, onCanvasClick, onDragStart, isBlockContextMenuActive = false, blockRightClickRef, instantBlockClickRef, onBlockRightClickTime }, ref) => {
  const containerRef = useRef<Container | null>(null);
  const gridRef = useRef<Graphics | null>(null);
  const tweensRef = useRef<gsap.core.Tween[]>([]);
  const listenersRef = useRef<Record<'moved' | 'zoomed', Set<() => void>>>({ moved: new Set(), zoomed: new Set() });
  const { app } = useApplication();
  const lastBlockRightClickTime = useRef<number>(0);
  const isDraggingRef = useRef<boolean>(false);
  const cancelActiveDragRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    // При открытии контекстного меню принудительно завершаем возможный активный драг
    if (isBlockContextMenuActive) {
      cancelActiveDragRef.current?.();
    }
  }, [isBlockContextMenuActive]);

  const [isDragging, setIsDragging] = useState(false);
  const [centerX, setCenterX] = useState(400);
  const [centerY, setCenterY] = useState(300);

  const emit = useCallback((event: 'moved' | 'zoomed') => {
    const set = listenersRef.current[event];
    set.forEach(fn => {
      try { fn(); } catch {}
    });
  }, []);

  // Зум через DOM события (wheel), перетаскивание — DOM pointer events с pointer capture
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

      // --- Перетаскивание камеры правой кнопкой (DOM pointer events) ---
      // Драг включается ТОЛЬКО после смещения указателя на порог (DRAG_THRESHOLD).
      // Поэтому простой правый клик по блоку (открытие меню) не входит в состояние
      // перетаскивания и не может «залипнуть». pointer capture гарантирует доставку
      // pointerup при отпускании вне canvas, а pointercancel/blur/window-pointerup
      // (capture-фаза, до любых блокировщиков) обрывают залипание в любом сценарии.
      const DRAG_THRESHOLD = 5;
      let activePointerId: number | null = null;
      let pendingDrag: { startX: number; startY: number; pointerId: number } | null = null;
      let lastScreen = { x: 0, y: 0 };

      const onCanvasPointerDown = (e: PointerEvent) => {
        if (e.button !== 2) return;
        e.preventDefault();
        const cnt = containerRef.current;
        if (!cnt) return;
        // Клавиатура блока: не стартуем драг сразу после открытия меню (защита от «прыжка»).
        // Меню само закрывается по mousedown вне него или явно в onDragStart.
        if (blockRightClickRef && blockRightClickRef.current) {
          return;
        }
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        pendingDrag = { startX: mx, startY: my, pointerId: e.pointerId };
      };

      const engageDrag = (e: PointerEvent) => {
        if (!pendingDrag) return;
        const rect = canvas.getBoundingClientRect();
        lastScreen = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        isDraggingRef.current = true;
        setIsDragging(true);
        activePointerId = pendingDrag.pointerId;
        try { canvas.setPointerCapture(pendingDrag.pointerId); } catch { /* ignore */ }
        // Драг начат — закрываем контекстное меню, если оно открыто
        onDragStart?.();
      };

      const onCanvasPointerMove = (e: PointerEvent) => {
        if (!isDraggingRef.current) {
          if (!pendingDrag) return;
          const rect = canvas.getBoundingClientRect();
          const mx = e.clientX - rect.left;
          const my = e.clientY - rect.top;
          if (Math.hypot(mx - pendingDrag.startX, my - pendingDrag.startY) < DRAG_THRESHOLD) {
            return;
          }
          engageDrag(e);
        }
        const cnt = containerRef.current;
        if (!cnt) return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const dx = mx - lastScreen.x;
        const dy = my - lastScreen.y;
        lastScreen = { x: mx, y: my };
        cnt.position.x += dx;
        cnt.position.y += dy;
        emit('moved');
      };

      const endCanvasDrag = () => {
        if (!isDraggingRef.current && !pendingDrag) return;
        isDraggingRef.current = false;
        pendingDrag = null;
        setIsDragging(false);
        if (activePointerId !== null) {
          try { canvas.releasePointerCapture(activePointerId); } catch { /* ignore */ }
        }
        activePointerId = null;
      };

      cancelActiveDragRef.current = endCanvasDrag;

      const onPointerEnd = () => endCanvasDrag();
      const onPointerCancel = (e: PointerEvent) => {
        if (activePointerId === null || activePointerId === e.pointerId) endCanvasDrag();
      };

      canvas.addEventListener('wheel', onWheel, { passive: false });
      canvas.addEventListener('contextmenu', onContextMenu);
      // capture-фаза: драг должен работать даже когда страницы вешают блокировщики
      // событий на canvas при открытом контекстном меню (stopImmediatePropagation
      // в bubble/целевой фазе не сможет глушить наши обработчики)
      canvas.addEventListener('pointerdown', onCanvasPointerDown, { capture: true });
      canvas.addEventListener('pointermove', onCanvasPointerMove, { capture: true });
      canvas.addEventListener('pointerup', onPointerEnd, { capture: true });
      canvas.addEventListener('pointercancel', onPointerCancel, { capture: true });
      window.addEventListener('blur', endCanvasDrag);
      // capture-фаза: завершаем драг ДО блокировщиков (например, контекстного меню)
      window.addEventListener('pointerup', onPointerEnd, true);

      return () => {
        canvas.removeEventListener('wheel', onWheel);
        canvas.removeEventListener('contextmenu', onContextMenu);
        canvas.removeEventListener('pointerdown', onCanvasPointerDown, { capture: true });
        canvas.removeEventListener('pointermove', onCanvasPointerMove, { capture: true });
        canvas.removeEventListener('pointerup', onPointerEnd, { capture: true });
        canvas.removeEventListener('pointercancel', onPointerCancel, { capture: true });
        window.removeEventListener('blur', endCanvasDrag);
        window.removeEventListener('pointerup', onPointerEnd, true);
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

  // Обработчики перетаскивания через PIXI (левая кнопка — только клик/создание)
  const handleBackgroundPointerDown = useCallback((event: any) => {
    // Правая кнопка: перетаскивание обрабатывается DOM-слушателями на canvas
    // (см. useEffect ниже) — единая точка входа с pointer capture.
    if (event.button === 2) {
      return;
    }
    if (event.button === 0) {
      // Левая кнопка для обычного клика
      if (onCanvasClick && !isDraggingRef.current) {
        handleCanvasClick(event);
      }
    }
  }, [onCanvasClick, handleCanvasClick]);

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