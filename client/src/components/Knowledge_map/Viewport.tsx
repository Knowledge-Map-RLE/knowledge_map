import { useRef, useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { Container, Graphics, Point, FederatedPointerEvent } from 'pixi.js';
import { extend, useApplication, useTick } from '@pixi/react';
import type { ReactNode } from 'react';
// @ts-ignore
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
}

export const Viewport = forwardRef<ViewportRef, ViewportProps>(({ children, onCanvasClick }, ref) => {
  const containerRef = useRef<Container | null>(null);
  const gridRef = useRef<Graphics | null>(null);
  const tweensRef = useRef<gsap.core.Tween[]>([]);
  const { app } = useApplication();
  
  const [isDragging, setIsDragging] = useState(false);
  const dragWorld = useRef<Point | null>(null);

  // Панорамирование через DOM события
  useEffect(() => {
    const canvas = app.canvas as HTMLCanvasElement;
    
    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 2) return; // Только правая кнопка
      e.preventDefault();
      
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const cnt = containerRef.current;
      if (!cnt) return;
      
      const worldPoint = cnt.toLocal({ x: sx, y: sy });
      dragWorld.current = new Point(worldPoint.x, worldPoint.y);
      setIsDragging(true);
      canvas.style.cursor = 'grabbing';
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging || !containerRef.current || !dragWorld.current) return;
      
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
      setIsDragging(false);
      dragWorld.current = null;
      canvas.style.cursor = 'default';
    };

    const onContextMenu = (e: Event) => e.preventDefault();

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('contextmenu', onContextMenu);
    
    return () => {
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('contextmenu', onContextMenu);
    };
  }, [app.canvas, isDragging]);

  // Зум через DOM события
  useEffect(() => {
    const canvas = app.canvas as HTMLCanvasElement;
    
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const cnt = containerRef.current;
      if (!cnt) return;
      
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
    return () => canvas.removeEventListener('wheel', onWheel);
  }, [app.canvas]);

  // Динамическая сетка через useTick
  useTick(() => {
    const gfx = gridRef.current;
    const cnt = containerRef.current;
    if (!gfx || !cnt) return;
    
    const { width, height } = app.screen;
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
      if (!containerRef.current) return;
      
      // Убиваем предыдущие анимации
      tweensRef.current.forEach(tween => tween.kill());
      tweensRef.current = [];

      const cnt = containerRef.current;
      const duration = 1.2;

      // Центрируем на цели
      const newX = -targetX * cnt.scale.x + app.screen.width / 2;
      const newY = -targetY * cnt.scale.y + app.screen.height / 2;

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
  }));

  // Очистка анимаций
  useEffect(() => {
    return () => {
      tweensRef.current.forEach(tween => tween.kill());
      tweensRef.current = [];
    };
  }, []);

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
        x={app.screen.width / 2}
        y={app.screen.height / 2}
      >
        {children}
      </container>
    </>
  );
});