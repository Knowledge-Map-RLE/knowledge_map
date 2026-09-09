import { Graphics } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useMemo, memo } from 'react';
import type { LinkData, BlockData } from '../types';
import { BLOCK_WIDTH } from '../constants';

extend({ Graphics });

export interface LinkProps {
  linkData: LinkData;
  blocks?: BlockData[];
  blockMap?: Map<string, BlockData>;
  isSelected: boolean;
  onClick: () => void;
  perfMode?: boolean;
  color?: number;
  alpha?: number;
  blockWidth?: number;
}

type LineDash = { dash: number; gap: number } | null;

interface DependencyStyle {
  color: number;
  alpha: number;
  width: number;
  dash: LineDash;
}

const DEPENDENCY_STYLES: Record<string, DependencyStyle> = {
  causal: { color: 0x16a34a, alpha: 1.0, width: 5, dash: null },
  mechanistic: { color: 0x2563eb, alpha: 1.0, width: 4, dash: { dash: 12, gap: 6 } },
  logical: { color: 0x7c3aed, alpha: 1.0, width: 4, dash: null },
  evidential: { color: 0xd97706, alpha: 1.0, width: 4, dash: { dash: 4, gap: 5 } },
  goal_directed: { color: 0xea580c, alpha: 1.0, width: 6, dash: null },
  compositional: { color: 0x0d9488, alpha: 1.0, width: 4, dash: { dash: 10, gap: 4 } },
};

/** Возвращает конфигурацию линии для dependency type. */
function resolveDependencyStyle(metadata?: LinkData['metadata']): DependencyStyle {
  const depType = typeof metadata?.dependency_type === 'string' ? metadata.dependency_type : undefined;
  const style = (depType && DEPENDENCY_STYLES[depType]) || { color: 0x8a2be2, alpha: 1.0, width: 5, dash: null };
  const confidence = typeof metadata?.confidence === 'number' ? metadata.confidence : 1.0;
  const confAlpha = 0.55 + 0.45 * Math.min(1, Math.max(0, confidence));
  return { ...style, alpha: style.alpha * confAlpha };
}

/**
 * Рисует ломаную с произвольным пунктиром (кастомный dash), поскольку PixiJS
 * Graphics не поддерживает dashed line из коробки. Сегменты линий чередуются
 * с пропусками по накопленному расстоянию.
 */
function strokeDashed(g: Graphics, points: Array<{ x: number; y: number }>, width: number, color: number, alpha: number, dash: number, gap: number) {
  const segments: Array<[{ x: number; y: number }, { x: number; y: number }]> = [];
  for (let i = 0; i < points.length - 1; i++) {
    segments.push([points[i], points[i + 1]]);
  }
  if (segments.length === 0) return;

  const strokeStyle = { width, color, alpha, cap: 'round' as const, join: 'round' as const };

  // Пробегаем по сегментам с накопленным расстоянием.
  for (const [p0, p1] of segments) {
    const dx = p1.x - p0.x;
    const dy = p1.y - p0.y;
    const segLen = Math.sqrt(dx * dx + dy * dy);
    if (segLen === 0) continue;
    const unitX = dx / segLen;
    const unitY = dy / segLen;

    let dist = 0;
    while (dist < segLen) {
      const dashStart = dist;
      const dashEnd = Math.min(dashStart + dash, segLen);
      g.moveTo(p0.x + unitX * dashStart, p0.y + unitY * dashStart);
      g.lineTo(p0.x + unitX * dashEnd, p0.y + unitY * dashEnd);
      g.stroke(strokeStyle);
      dist = dashEnd + gap;
    }
  }
}

export const Link = memo(function Link({ linkData, blocks, blockMap, isSelected, onClick, perfMode = false, color, alpha = 1, blockWidth = BLOCK_WIDTH }: LinkProps) {
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
      { x: source_block.x + blockWidth / 2, y: source_block.y },
      { x: target_block.x - blockWidth / 2, y: target_block.y },
    ];
  }, [linkData.polyline, source_block?.x, source_block?.y, target_block?.x, target_block?.y, blockWidth]);

  const style = useMemo(() => resolveDependencyStyle(linkData.metadata), [linkData.metadata]);

  const draw = useCallback((g: Graphics) => {
    g.clear();

    if (pathPoints.length < 2) {
      return;
    }

    const lineColor = color ?? (isSelected ? 0xef4444 : style.color);
    const lineAlpha = color !== undefined ? alpha : style.alpha;
    const lineWidth = style.width;
    const dash = style.dash;

    if (dash) {
      strokeDashed(g, pathPoints, lineWidth, lineColor, lineAlpha, dash.dash, dash.gap);
    } else {
      g.moveTo(pathPoints[0].x, pathPoints[0].y);
      for (let i = 1; i < pathPoints.length; i++) {
        g.lineTo(pathPoints[i].x, pathPoints[i].y);
      }
      g.stroke({ width: lineWidth, color: lineColor, alpha: lineAlpha, cap: 'round', join: 'round' });
    }

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
    g.fill({ color: lineColor, alpha: lineAlpha });
  }, [isSelected, pathPoints, color, alpha, style]);

  if (!source_block || !target_block) {
    return null;
  }

  return (
    <pixiGraphics
      draw={draw}
      eventMode={perfMode ? 'none' : 'static'}
      cursor={perfMode ? undefined : 'pointer'}
      onClick={perfMode ? undefined : onClick}
      zIndex={10}
    />
  );
});