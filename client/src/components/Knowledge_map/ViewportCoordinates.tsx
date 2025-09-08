import { useState, useEffect } from 'react';
import { useViewport } from '../../contexts/ViewportContext';
import { useDataLoading } from './hooks/useDataLoading';

export default function ViewportCoordinates() {
  
  const { viewportRef } = useViewport();
  const { blocks, isLoading } = useDataLoading();
  const [coordinates, setCoordinates] = useState({ x: 0, y: 0, scale: 1 });

  useEffect(() => {
    
    const updateCoordinates = () => {
      if (!viewportRef?.current) {
        setCoordinates({ x: 0, y: 0, scale: 1 });
        return;
      }

      const viewport = viewportRef.current;
      const worldCenter = viewport.getWorldCenter();
      
      
      if (worldCenter) {
        const newCoords = {
          x: Math.round(worldCenter.x),
          y: Math.round(worldCenter.y),
          scale: Math.round(viewport.scale * 100) / 100
        };
        setCoordinates(newCoords);
      }
    };

    // Обновляем каждые 100мс
    const interval = setInterval(updateCoordinates, 100);

    // Подписываемся на события viewport
    const handleViewportChange = () => {
      updateCoordinates();
    };

    if (viewportRef?.current) {
      viewportRef.current.on?.('moved', handleViewportChange);
      viewportRef.current.on?.('zoomed', handleViewportChange);
    } else {
      }

    return () => {
      clearInterval(interval);
      if (viewportRef?.current) {
        viewportRef.current.off?.('moved', handleViewportChange);
        viewportRef.current.off?.('zoomed', handleViewportChange);
      }
    };
  }, [viewportRef]);

  // Простой статичный блок для тестирования
  return (
    <div 
      style={{
        position: 'fixed',
        top: '20px',
        right: '20px',
        background: 'rgba(255, 0, 0, 0.9)',
        color: 'white',
        padding: '12px',
        borderRadius: '8px',
        zIndex: 999999,
        fontSize: '14px',
        fontFamily: 'Arial, sans-serif',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
        border: '2px solid white',
        pointerEvents: 'none'
      }}
    >
      <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>КООРДИНАТЫ</div>
      <div>X: {coordinates.x}</div>
      <div>Y: {coordinates.y}</div>
      <div>Scale: {coordinates.scale}</div>
      <div>Viewport: {viewportRef?.current ? 'OK' : 'NULL'}</div>
      <div>Position: {viewportRef?.current?.position ? `${Math.round(viewportRef.current.position.x)}, ${Math.round(viewportRef.current.position.y)}` : 'N/A'}</div>
      <div style={{ fontSize: '12px', marginTop: '8px', color: '#ccc' }}>
        Блоков: {blocks.length} {isLoading && '(загрузка...)'}
      </div>
      <div style={{ fontSize: '12px', color: '#ccc' }}>
        Автозагрузка при перемещении (1с)
      </div>
      <div style={{ fontSize: '10px', color: '#999', marginTop: '4px' }}>
        Проверьте консоль для логов
      </div>
    </div>
  );
}
