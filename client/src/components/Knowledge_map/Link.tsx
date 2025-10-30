import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useMemo, memo } from 'react';
import type { LinkData, BlockData } from './types';
import { BLOCK_WIDTH } from './constants';

extend({ Graphics });

export interface LinkProps {
  linkData: LinkData;
  blocks?: BlockData[];
  blockMap?: Map<string, BlockData>;
  isSelected: boolean;
  onClick: () => void;
  perfMode?: boolean;
}

export const Link = memo(function Link({ linkData, blocks, blockMap, isSelected, onClick, perfMode: _perfMode = false }: LinkProps) {
  const source_block = (blockMap ? blockMap.get(linkData.source_id) : undefined) || (blocks || []).find(block => block.id === linkData.source_id);
  const target_block = (blockMap ? blockMap.get(linkData.target_id) : undefined) || (blocks || []).find(block => block.id === linkData.target_id);

  const pathPoints = useMemo(() => {
    if (linkData.polyline && linkData.polyline.length >= 2) {
      return linkData.polyline;
    }

    if (!source_block || !target_block) {
      return [] as { x: number; y: number }[];
    }

    return [
      { x: source_block.x + BLOCK_WIDTH / 2, y: source_block.y },
      { x: target_block.x - BLOCK_WIDTH / 2, y: target_block.y },
    ];
  }, [linkData.polyline, source_block?.x, source_block?.y, target_block?.x, target_block?.y]);

  const draw = useCallback((g: Graphics) => {
    g.clear();

    if (pathPoints.length < 2) {
      return;
    }

    const lineColor = isSelected ? 0xff0000 : 0x8a2be2;
    const lineWidth = 5;

    g.moveTo(pathPoints[0].x, pathPoints[0].y);
    for (let i = 1; i < pathPoints.length; i++) {
      g.lineTo(pathPoints[i].x, pathPoints[i].y);
    }
    g.stroke({ width: lineWidth, color: lineColor, cap: 'round', join: 'round' });

    const lastPoint = pathPoints[pathPoints.length - 1];
    const preLastPoint = pathPoints[pathPoints.length - 2];
    const dx = lastPoint.x - preLastPoint.x;
    const dy = lastPoint.y - preLastPoint.y;
    const lineAngle = Math.atan2(dy, dx);
    const arrowLength = 15;
    const arrowAngle = Math.PI / 6;

    const arrowPoint1 = {
      x: lastPoint.x - arrowLength * Math.cos(lineAngle + arrowAngle),
      y: lastPoint.y - arrowLength * Math.sin(lineAngle + arrowAngle),
    };

    const arrowPoint2 = {
      x: lastPoint.x - arrowLength * Math.cos(lineAngle - arrowAngle),
      y: lastPoint.y - arrowLength * Math.sin(lineAngle - arrowAngle),
    };

    g.moveTo(lastPoint.x, lastPoint.y);
    g.lineTo(arrowPoint1.x, arrowPoint1.y);
    g.lineTo(arrowPoint2.x, arrowPoint2.y);
    g.closePath();
    g.fill({ color: lineColor });
  }, [isSelected, pathPoints]);

  if (!source_block || !target_block) {
    return null;
  }

  return (
    <pixiGraphics
      draw={draw}
      eventMode="static"
      cursor="pointer"
      onClick={onClick}
      zIndex={10}
    />
  );
});
