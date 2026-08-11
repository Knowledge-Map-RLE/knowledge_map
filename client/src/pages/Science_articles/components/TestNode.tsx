import { Graphics, Container } from 'pixi.js';
import { extend } from '@pixi/react';
import { PixiText } from '../../../shared/pixi/PixiText';
import { useRef, useEffect } from 'react';
import { gsap } from 'gsap';

extend({ Graphics, Container });

export interface TestNodeProps {
  x?: number;
  y?: number;
  text?: string;
}

export function TestNode({ x = 0, y = 0, text = "Тестовая вершина" }: TestNodeProps) {
  const containerRef = useRef<Container>(null);

  useEffect(() => {
    if (containerRef.current) {
      // Анимация появления
      containerRef.current.alpha = 0;
      containerRef.current.scale.set(0.5);
      
      gsap.to(containerRef.current, { 
        alpha: 1, 
        scale: 1,
        duration: 1, 
        ease: 'back.out(1.7)' 
      });
    }
  }, []);

  const draw = (g: Graphics) => {
    g.clear();
    // Рисуем круг с градиентом
    g.circle(0, 0, 30);
    g.fill(0x3b82f6);

    // Добавляем обводку
    g.stroke({ width: 3, color: 0x1e40af });

    // Добавляем внутренний круг для эффекта
    g.circle(0, 0, 20);
    g.stroke({ width: 1, color: 0x60a5fa });
  };

  const drawText = (g: Graphics) => {
    g.clear();
    g.roundRect(-60, 40, 120, 30, 8);
    g.fill(0xffffff);
  };

  return (
    <container 
      ref={containerRef}
      x={x}
      y={y}
      eventMode="static"
      cursor="pointer"
    >
      <graphics draw={draw} />
      <graphics draw={drawText} />
      <PixiText
        text={text}
        anchor={{ x: 0.5, y: 0.5 }}
        x={0}
        y={55}
        style={{
          fontSize: 12,
          fill: 0x1f2937,
          fontWeight: 'bold',
          align: 'center'
        }}
      />
    </container>
  );
}
