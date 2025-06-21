import { useRef, useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { Container, Graphics, Point, FederatedPointerEvent } from 'pixi.js';
import { extend, useApplication } from '@pixi/react';
import type { ReactNode } from 'react';
// @ts-ignore
import { gsap } from 'gsap';

extend({ Container, Graphics, Point });

// Константы для сетки
const GRID_SIZE = 100;
const GRID_COLOR = 0xE0E0E0;
const GRID_ALPHA = 0.3;

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
  const tweensRef = useRef<gsap.core.Tween[]>([]);
  const { app } = useApplication();
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const lastPositionRef = useRef({ x: 0, y: 0 });

  // Функция для отрисовки сетки
  const drawGrid = useCallback((g: Graphics) => {
    if (!app || !app.renderer) return;

    const viewWidth = app.screen.width;
    const viewHeight = app.screen.height;

    // Очищаем и перерисовываем, только если размеры изменились
    // или если графика не была инициализирована
    if ((g as any)._width !== viewWidth || (g as any)._height !== viewHeight) {
        g.clear();
        g.stroke({ width: 1, color: GRID_COLOR, alpha: GRID_ALPHA });
        for (let x = 0; x <= viewWidth; x += GRID_SIZE) {
            g.moveTo(x, 0);
            g.lineTo(x, viewHeight);
        }
        for (let y = 0; y <= viewHeight; y += GRID_SIZE) {
            g.moveTo(0, y);
            g.lineTo(viewWidth, y);
        }
        // Сохраняем текущие размеры в самом объекте графики
        (g as any)._width = viewWidth;
        (g as any)._height = viewHeight;
    }
  }, [app]);

  // Обработчики перетаскивания
  const handlePointerDown = useCallback((event: FederatedPointerEvent) => {
    if (event.nativeEvent.button === 2) {
      // Останавливаем любую текущую анимацию, если пользователь начинает перетаскивать
      gsap.killTweensOf(position);
      setIsDragging(true);
      lastPositionRef.current = { x: event.global.x, y: event.global.y };
    }
  }, [position]);

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

  // Эффект для очистки анимаций при размонтировании
  useEffect(() => {
    return () => {
      tweensRef.current.forEach(tween => tween.kill());
      tweensRef.current = [];
    };
  }, []);

  useImperativeHandle(ref, () => ({
    focusOn: (targetX: number, targetY: number) => {
      if (!app.screen || !containerRef.current) return;
      
      // Убиваем предыдущие анимации, чтобы избежать конфликтов
      tweensRef.current.forEach(tween => tween.kill());
      tweensRef.current = [];

      const targetScale = 1; // Можно сделать настраиваемым
      const duration = 1.2; // Длительность анимации в секундах

      // Центрируем камеру на цели
      const newX = (app.screen.width / 2) - (targetX * targetScale);
      const newY = (app.screen.height / 2) - (targetY * targetScale);

      // Анимируем scale
      const scaleTween = gsap.to(containerRef.current.scale, {
        x: targetScale,
        y: targetScale,
        duration,
        ease: "power3.inOut",
        onUpdate: () => {
            if (containerRef.current) { // Защита от null
                setScale(containerRef.current.scale.x);
            }
        }
      });
      
      // Создаем прокси-объект для анимации позиции
      const positionProxy = { x: position.x, y: position.y };

      // Анимируем прокси-объект
      const positionTween = gsap.to(positionProxy, {
        x: newX,
        y: newY,
        duration,
        ease: "power3.inOut",
        onUpdate: () => {
          // Обновляем состояние React на каждом кадре
          setPosition({ x: positionProxy.x, y: positionProxy.y });
        }
      });

      // Сохраняем новые анимации в ref
      tweensRef.current.push(scaleTween, positionTween);
    },
    scale,
    position,
  }));

  const handleWheel = useCallback((event: WheelEvent) => {
    event.preventDefault();
    // Останавливаем любую текущую анимацию, если пользователь начинает масштабировать
    gsap.killTweensOf(position);
    if (containerRef.current) {
      gsap.killTweensOf(containerRef.current.scale);
    }

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
              g.fill({color: 0, alpha: 0});
              g.rect(-10000, -10000, 20000, 20000);
            }
          }}
          onClick={handleCanvasClick}
        />
        {children}
      </container>
    </container>
  );
}); 