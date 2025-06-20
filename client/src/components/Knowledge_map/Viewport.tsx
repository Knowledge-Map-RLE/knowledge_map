import { useRef, useState, useEffect, useCallback } from 'react';
import { Container, Graphics, Point, FederatedPointerEvent } from 'pixi.js';
import { extend, useApplication } from '@pixi/react';
import type { ReactNode } from 'react';

extend({ Container, Graphics, Point });

// Константы для сетки
const GRID_SIZE = 100;
const GRID_COLOR = 0xE0E0E0;
const GRID_ALPHA = 0.3;

interface ViewportProps {
  children: ReactNode;
  onCanvasClick?: (x: number, y: number) => void;
}

export function Viewport({ children, onCanvasClick }: ViewportProps) {
  const containerRef = useRef<Container | null>(null);
  const { app } = useApplication();
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const lastPositionRef = useRef({ x: 0, y: 0 });

  // Функция для отрисовки сетки
  const drawGrid = useCallback((g: Graphics) => {
    if (!app || !app.renderer) return;
    g.clear();
    g.lineStyle(1, GRID_COLOR, GRID_ALPHA);
    const viewWidth = app.screen.width;
    const viewHeight = app.screen.height;
    for (let x = 0; x <= viewWidth; x += GRID_SIZE) {
      g.moveTo(x, 0);
      g.lineTo(x, viewHeight);
    }
    for (let y = 0; y <= viewHeight; y += GRID_SIZE) {
      g.moveTo(0, y);
      g.lineTo(viewWidth, y);
    }
  }, [app]);

  // Обработчики перетаскивания
  const handlePointerDown = useCallback((event: FederatedPointerEvent) => {
    if (event.nativeEvent.button === 2) {
      setIsDragging(true);
      lastPositionRef.current = { x: event.global.x, y: event.global.y };
    }
  }, []);

  const handlePointerMove = useCallback((event: FederatedPointerEvent) => {
    if (!isDragging) return;
    const dx = event.global.x - lastPositionRef.current.x;
    const dy = event.global.y - lastPositionRef.current.y;
    setPosition(prev => ({ x: prev.x + dx, y: prev.y + dy }));
    lastPositionRef.current = { x: event.global.x, y: event.global.y };
  }, [isDragging]);

  const handlePointerUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Обновляем позицию контейнера
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scale.set(scale);
      containerRef.current.position.set(position.x, position.y);
    }
  }, [scale, position]);

  const handleWheel = useCallback((event: WheelEvent) => {
    event.preventDefault();
    const delta = event.deltaY;
    const scaleChange = delta > 0 ? 0.9 : 1.1;
    const newScale = Math.min(Math.max(scale * scaleChange, 0.1), 5);
    if (containerRef.current) {
      const mousePosition = event.clientX && event.clientY ? { x: event.clientX, y: event.clientY } : null;
      if (mousePosition) {
        const beforeTransform = { x: (mousePosition.x - position.x) / scale, y: (mousePosition.y - position.y) / scale };
        const afterTransform = { x: (mousePosition.x - position.x) / newScale, y: (mousePosition.y - position.y) / newScale };
        setPosition({
          x: position.x + (afterTransform.x - beforeTransform.x) * newScale,
          y: position.y + (afterTransform.y - beforeTransform.y) * newScale
        });
        setScale(newScale);
      }
    }
  }, [scale, position]);

  useEffect(() => {
    // Ждем, пока приложение и его рендерер будут полностью готовы
    if (!app || !app.renderer) {
      return;
    }
    
    const canvas = app.canvas;
    
    canvas.addEventListener('wheel', handleWheel);
    const handleContextMenu = (e: MouseEvent) => e.preventDefault();
    canvas.addEventListener('contextmenu', handleContextMenu);
    
    return () => {
      canvas.removeEventListener('wheel', handleWheel);
      canvas.removeEventListener('contextmenu', handleContextMenu);
    };
  }, [handleWheel, app]);

  const handleCanvasClick = useCallback((event: FederatedPointerEvent) => {
    if (onCanvasClick && containerRef.current) {
      const localPos = event.getLocalPosition(containerRef.current);
      onCanvasClick(localPos.x, localPos.y);
    }
  }, [onCanvasClick]);

  return (
    <container
      eventMode="static"
      interactive
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerUpOutside={handlePointerUp}
    >
      <graphics draw={drawGrid} eventMode="none" />
      <container ref={containerRef} eventMode='static' interactive>
        {/* Добавляем пустой фон для кликов */}
        <graphics 
          draw={g => {
            if(app && app.renderer) {
              g.beginFill(0,0);
              g.drawRect(-10000, -10000, 20000, 20000);
              g.endFill();
            }
          }}
          onClick={handleCanvasClick}
        />
        {children}
      </container>
    </container>
  );
} 