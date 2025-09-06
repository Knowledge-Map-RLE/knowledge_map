import { useState, useEffect } from 'react';
import { useViewport } from '../../contexts/ViewportContext';

export default function ViewportCoordinates() {
  console.log('ViewportCoordinates component is rendering!');
  console.log('Current URL:', window.location.pathname);
  
  const { viewportRef } = useViewport();
  const [coordinates, setCoordinates] = useState({ x: 0, y: 0, scale: 1 });

  useEffect(() => {
    console.log('ViewportCoordinates useEffect triggered, viewportRef:', !!viewportRef?.current);
    
    const updateCoordinates = () => {
      if (!viewportRef?.current) {
        console.log('No viewport ref available');
        setCoordinates({ x: 0, y: 0, scale: 1 });
        return;
      }

      const viewport = viewportRef.current;
      const worldCenter = viewport.getWorldCenter();
      
      console.log('Updating coordinates, worldCenter:', worldCenter, 'scale:', viewport.scale);
      
      if (worldCenter) {
        const newCoords = {
          x: Math.round(worldCenter.x),
          y: Math.round(worldCenter.y),
          scale: Math.round(viewport.scale * 100) / 100
        };
        console.log('Setting new coordinates:', newCoords);
        setCoordinates(newCoords);
      }
    };

    // Обновляем каждые 100мс
    const interval = setInterval(updateCoordinates, 100);

    // Подписываемся на события viewport
    const handleViewportChange = () => {
      console.log('Viewport change event triggered');
      updateCoordinates();
    };

    if (viewportRef?.current) {
      console.log('Subscribing to viewport events');
      viewportRef.current.on?.('moved', handleViewportChange);
      viewportRef.current.on?.('zoomed', handleViewportChange);
    } else {
      console.log('No viewport ref to subscribe to events');
    }

    return () => {
      console.log('Cleaning up ViewportCoordinates');
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
    </div>
  );
}
