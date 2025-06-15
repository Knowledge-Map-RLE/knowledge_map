import React, { useRef, useState, useEffect } from 'react';
import { Container, Graphics, Point, FederatedPointerEvent } from 'pixi.js';
import { extend, useApplication, useTick } from '@pixi/react';
import type { BlockData } from './index';

extend({ Container, Graphics, Point });

interface ViewportProps {
  children: React.ReactNode;
  onCanvasClick?: (x: number, y: number) => void;
  blocks?: BlockData[];
}

export function Viewport({ children, onCanvasClick, blocks }: ViewportProps) {
  const viewRef = useRef<Container>(null);
  const gridRef = useRef<Graphics>(null);
  const { app } = useApplication();
  
  const [isDragging, setDragging] = useState(false);
  const [appReady, setAppReady] = useState(false);
  const dragWorld = useRef<Point | null>(null);

  // Проверяем готовность приложения с интервалом
  useEffect(() => {
    if (!app) return;

    // Проверяем каждые 100мс готовность приложения
    const checkAppReady = () => {
      try {
        // Пытаемся получить доступ к canvas и renderer
        if (app.canvas && app.renderer && app.renderer.width > 0 && app.renderer.height > 0) {
          setAppReady(true);
          return true;
        }
      } catch (error) {
        // Игнорируем ошибки - приложение еще не готово
      }
      return false;
    };

    // Проверяем сразу
    if (checkAppReady()) return;

    // Если не готово, проверяем периодически
    const interval = setInterval(() => {
      if (checkAppReady()) {
        clearInterval(interval);
      }
    }, 100);

    return () => clearInterval(interval);
  }, [app]);

  // Центрируем viewport при готовности
  useEffect(() => {
    if (!appReady || !app) return;
    
    const cnt = viewRef.current;
    if (!cnt) return;
    
    try {
      const width = app.renderer.width;
      const height = app.renderer.height;
      
      cnt.position.x = width / 2;
      cnt.position.y = height / 2;
    } catch (error) {
      console.warn('Failed to center viewport:', error);
    }
  }, [app, appReady]);

  // Обработка панорамирования (ПКМ)
  useEffect(() => {
    if (!appReady || !app) return;
    
    let view: HTMLCanvasElement;
    
    try {
      view = app.canvas as HTMLCanvasElement;
      if (!view) return;
    } catch (error) {
      console.warn('Canvas not ready for pan handling:', error);
      return;
    }
    
    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 2) return;
      e.preventDefault();
      
      const rect = view.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const cnt = viewRef.current;
      
      if (!cnt) return;
      
      const localPoint = cnt.toLocal({ x: sx, y: sy });
      dragWorld.current = new Point(localPoint.x, localPoint.y);
      setDragging(true);
      view.style.cursor = 'grabbing';
    };
    
    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging || !viewRef.current || !dragWorld.current) return;
      
      const rect = view.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const cnt = viewRef.current;
      const screenPos = cnt.toGlobal(dragWorld.current);
      
      cnt.position.x += sx - screenPos.x;
      cnt.position.y += sy - screenPos.y;
    };
    
    const onPointerUp = (e: PointerEvent) => {
      if (e.button !== 2) return;
      setDragging(false);
      dragWorld.current = null;
      view.style.cursor = 'default';
    };
    
    const onContextMenu = (e: Event) => e.preventDefault();

    view.addEventListener('pointerdown', onPointerDown);
    view.addEventListener('pointermove', onPointerMove);
    view.addEventListener('pointerup', onPointerUp);
    view.addEventListener('contextmenu', onContextMenu);
    
    return () => {
      view.removeEventListener('pointerdown', onPointerDown);
      view.removeEventListener('pointermove', onPointerMove);
      view.removeEventListener('pointerup', onPointerUp);
      view.removeEventListener('contextmenu', onContextMenu);
    };
  }, [appReady, app, isDragging]);

  // Зуммирование
  useEffect(() => {
    if (!appReady || !app) return;
    
    let view: HTMLCanvasElement;
    
    try {
      view = app.canvas as HTMLCanvasElement;
      if (!view) return;
    } catch (error) {
      console.warn('Canvas not ready for zoom handling:', error);
      return;
    }
    
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const cnt = viewRef.current;
      if (!cnt) return;
      
      const rect = view.getBoundingClientRect();
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
    
    view.addEventListener('wheel', onWheel, { passive: false });
    
    return () => view.removeEventListener('wheel', onWheel);
  }, [appReady, app]);

  // Обработка клика
  const handleCanvasClick = (event: FederatedPointerEvent) => {
    if (isDragging || !onCanvasClick || !appReady) return;
    
    if (event.nativeEvent && (event.nativeEvent as PointerEvent).button !== 0) return;
    
    const cnt = viewRef.current;
    if (!cnt) return;
    
    const localPoint = cnt.toLocal(event.global);
    onCanvasClick(localPoint.x, localPoint.y);
  };

  // Динамическая сетка
  useTick(() => {
    if (!appReady) return;
    
    const gfx = gridRef.current;
    const cnt = viewRef.current;
    if (!gfx || !cnt || !app) return;
    
    let width: number, height: number;
    
    try {
      width = app.renderer.width;
      height = app.renderer.height;
      
      if (!width || !height) return;
    } catch (error) {
      return; // Renderer не готов
    }

    const scale = cnt.scale.x;
    const pos = cnt.position;

    gfx.clear();
    gfx.rect(0, 0, width, height);
    gfx.fill(0xf8fafc);

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
    gfx.stroke({ width: 1, color: 0xe5e7eb });

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
    gfx.stroke({ width: 2, color: 0xd1d5db });
  });

  // Показываем простой индикатор загрузки пока приложение не готово
  if (!appReady) {
    return (
      <pixiContainer>
        {/* Ждем готовности приложения */}
      </pixiContainer>
    );
  }

  return (
    <>
      <pixiGraphics 
        ref={gridRef} 
        interactive={!!onCanvasClick}
        onPointerDown={onCanvasClick ? handleCanvasClick : undefined}
        draw={() => {}} 
      />
      
      <pixiContainer 
        ref={viewRef}
        interactive={false}
      >
        {children}
      </pixiContainer>
    </>
  );
} 