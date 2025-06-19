import { useRef, useState, useEffect } from 'react';
import { Container, Graphics, Point, FederatedPointerEvent } from 'pixi.js';
import { extend, useApplication } from '@pixi/react';
import type { ReactNode } from 'react';

extend({ Container, Graphics, Point });

interface ViewportProps {
  children: ReactNode;
  onCanvasClick?: (x: number, y: number) => void;
}

export function Viewport({ children, onCanvasClick }: ViewportProps) {
  const containerRef = useRef<Container | null>(null);
  const { app } = useApplication();
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    container.scale.set(scale);
    container.position.set(position.x, position.y);
  }, [scale, position]);

  const handleCanvasClick = (event: FederatedPointerEvent) => {
    if (onCanvasClick) {
      const worldPos = event.global;
      onCanvasClick(worldPos.x, worldPos.y);
    }
  };

  const handleWheel = (event: WheelEvent) => {
    event.preventDefault();
    const delta = event.deltaY;
    const scaleChange = delta > 0 ? 0.9 : 1.1;
    const newScale = Math.min(Math.max(scale * scaleChange, 0.1), 5);
    
    if (containerRef.current) {
      const mousePosition = event.clientX && event.clientY
        ? { x: event.clientX, y: event.clientY }
        : null;

      if (mousePosition) {
        const beforeTransform = {
          x: (mousePosition.x - position.x) / scale,
          y: (mousePosition.y - position.y) / scale
        };

        const afterTransform = {
          x: (mousePosition.x - position.x) / newScale,
          y: (mousePosition.y - position.y) / newScale
        };

        setPosition({
          x: position.x + (afterTransform.x - beforeTransform.x) * newScale,
          y: position.y + (afterTransform.y - beforeTransform.y) * newScale
        });
        setScale(newScale);
      }
    }
  };

  useEffect(() => {
    const canvas = app?.view;
    if (canvas) {
      canvas.addEventListener('wheel', handleWheel);
      return () => {
        canvas.removeEventListener('wheel', handleWheel);
      };
    }
  }, [scale, position, app]);

  return (
    <container
      ref={containerRef}
      interactive={false}
      eventMode="static"
      onClick={handleCanvasClick}
    >
      {children}
    </container>
  );
} 