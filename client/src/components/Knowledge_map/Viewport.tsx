import { useRef, useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { Container, Graphics, Point, FederatedPointerEvent } from 'pixi.js';
import { extend, useApplication, useTick } from '@pixi/react';
import type { ReactNode } from 'react';
import { gsap } from 'gsap';

extend({ Container, Graphics, Point });

interface ViewportProps {
  children: ReactNode;
  onCanvasClick?: (x: number, y: number) => void;
}

export interface ViewportRef {
  focusOn: (x: number, y: number) => void;
  scale: number;
  position: { x: number; y: number };
  containerRef: Container | null;
}

export const Viewport = forwardRef<ViewportRef, ViewportProps>(({ children, onCanvasClick }, ref) => {
  const containerRef = useRef<Container | null>(null);
  const gridRef = useRef<Graphics | null>(null);
  const tweensRef = useRef<gsap.core.Tween[]>([]);
  const { app } = useApplication();
  
  const [isDragging, setIsDragging] = useState(false);
  const dragWorld = useRef<Point | null>(null);
  const [centerX, setCenterX] = useState(400);
  const [centerY, setCenterY] = useState(300);

  // Панорамирование через PIXI события
  useEffect(() => {
    if (!app || !containerRef.current || !gridRef.current) return;
    
    console.log('Настраиваем PIXI события для панорамирования');
    
    const grid = gridRef.current;
    
    // Делаем grid интерактивным для захвата всех событий
    grid.interactive = true;
    grid.hitArea = app.screen;
    
    const onPointerDown = (e: FederatedPointerEvent) => {
      if (e.nativeEvent.button !== 2) return;
      if ('preventDefault' in e.nativeEvent) {
        e.nativeEvent.preventDefault();
      }
      
      const cnt = containerRef.current;
      if (!cnt) return;
      
      const worldPoint = cnt.toLocal(e.global);
      dragWorld.current = new Point(worldPoint.x, worldPoint.y);
      setIsDragging(true);
      
      if (app.canvas) {
        (app.canvas as HTMLCanvasElement).style.cursor = 'grabbing';
      }
      console.log('Начинаем перетаскивание через PIXI');
    };

    const onPointerMove = (e: FederatedPointerEvent) => {
      if (!isDragging || !containerRef.current || !dragWorld.current) return;
      
      const cnt = containerRef.current;
      const screenPos = cnt.toGlobal(dragWorld.current);
      cnt.position.x += e.global.x - screenPos.x;
      cnt.position.y += e.global.y - screenPos.y;
    };

    const onPointerUp = (e: FederatedPointerEvent) => {
      if (e.nativeEvent.button !== 2) return;
      setIsDragging(false);
      dragWorld.current = null;
      
      if (app.canvas) {
        (app.canvas as HTMLCanvasElement).style.cursor = 'default';
      }
      console.log('Заканчиваем перетаскивание через PIXI');
    };

    const onRightClick = (e: FederatedPointerEvent) => {
      if ('preventDefault' in e.nativeEvent) {
        e.nativeEvent.preventDefault();
      }
    };

    grid.on('pointerdown', onPointerDown);
    grid.on('pointermove', onPointerMove);
    grid.on('pointerup', onPointerUp);
    grid.on('pointerupoutside', onPointerUp);
    grid.on('rightclick', onRightClick);
    
    return () => {
      grid.off('pointerdown', onPointerDown);
      grid.off('pointermove', onPointerMove);
      grid.off('pointerup', onPointerUp);
      grid.off('pointerupoutside', onPointerUp);
      grid.off('rightclick', onRightClick);
      console.log('Отвязываем PIXI события панорамирования');
    };
  }, [app, isDragging]);
  
  // Зум через DOM события (оставляем как есть, так как wheel event лучше работает через DOM)
  useEffect(() => {
    if (!app) return;
    
    const timer = setTimeout(() => {
      // Проверяем готовность app более тщательно
      if (!app || !app.renderer || !app.renderer.view) {
        console.warn('PIXI Application не готов для привязки событий зума');
        return;
      }
      
      const canvas = app.canvas as HTMLCanvasElement;
      if (!canvas) {
        console.warn('Canvas не готов для привязки событий зума');
        return;
      }
      
      console.log('Привязываем события зума к canvas');
      
      const onWheel = (e: WheelEvent) => {
        e.preventDefault();
        const cnt = containerRef.current;
        if (!cnt) return;
        
        console.log('Обрабатываем зум:', e.deltaY);
        
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const oldScale = cnt.scale.x;
        const factor = Math.pow(1.001, -e.deltaY);
        const newScale = Math.min(Math.max(oldScale * factor, 0.1), 5);
        const world = cnt.toLocal({ x: mx, y: my });
        const worldPoint = new Point(world.x, world.y);
        
        cnt.scale.set(newScale);
        cnt.position.x -= worldPoint.x * (newScale - oldScale);
        cnt.position.y -= worldPoint.y * (newScale - oldScale);
      };
      
      canvas.addEventListener('wheel', onWheel, { passive: false });
      return () => {
        canvas.removeEventListener('wheel', onWheel);
        console.log('Отвязываем события зума');
      };
    }, 500); // Увеличиваем задержку до 500мс
    
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