import { Graphics, Container, Text } from 'pixi.js';
import { extend } from '@pixi/react';
import type { ActionNode as ActionNodeData } from '../hooks/useKnowledgeMapLoader';

extend({ Graphics, Container, Text });

const ACTION_COLORS: Record<string, number> = {
  result:    0xFF5722,  // оранжево-красный
  mechanism: 0x9C27B0,  // фиолетовый
  action:    0x2196F3,  // синий
};

const BORDER_COLOR = 0x000000;
const NODE_WIDTH  = 160;
const NODE_HEIGHT = 60;
const RADIUS      = 8;

interface ActionNodeProps {
  node: ActionNodeData;
  isSelected?: boolean;
  onClick?: (nodeId: string) => void;
}

export function ActionNode({ node, isSelected = false, onClick }: ActionNodeProps) {
  const fillColor = ACTION_COLORS[node.action_class] ?? ACTION_COLORS.action;
  const borderWidth = Math.min(1 + node.doc_count, 5);  // толще = популярнее

  const label = node.verb_text
    ? `${node.verb_text}${node.object ? ' ' + node.object : ''}`
    : node.content;

  const truncated = label.length > 24 ? label.slice(0, 22) + '…' : label;

  const draw = (g: Graphics) => {
    g.clear();
    // Фон
    g.beginFill(fillColor, isSelected ? 1.0 : 0.85);
    g.drawRoundedRect(-NODE_WIDTH / 2, -NODE_HEIGHT / 2, NODE_WIDTH, NODE_HEIGHT, RADIUS);
    g.endFill();
    // Рамка
    g.lineStyle({ width: isSelected ? borderWidth + 1 : borderWidth, color: isSelected ? 0xFFFFFF : BORDER_COLOR, alpha: 0.6 });
    g.drawRoundedRect(-NODE_WIDTH / 2, -NODE_HEIGHT / 2, NODE_WIDTH, NODE_HEIGHT, RADIUS);
  };

  const drawBadge = (g: Graphics) => {
    if (node.doc_count <= 1) return;
    g.clear();
    g.beginFill(0xFFFFFF, 0.9);
    g.drawCircle(NODE_WIDTH / 2 - 6, -NODE_HEIGHT / 2 + 6, 10);
    g.endFill();
  };

  return (
    <container
      x={node.x}
      y={node.y}
      eventMode="static"
      cursor="pointer"
      onPointerDown={() => onClick?.(node.id)}
    >
      <graphics draw={draw} />
      <text
        text={truncated}
        anchor={{ x: 0.5, y: 0.5 }}
        x={0}
        y={0}
        style={{
          fontSize: 11,
          fill: 0xffffff,
          fontWeight: 'bold',
          align: 'center',
          wordWrap: true,
          wordWrapWidth: NODE_WIDTH - 8,
        }}
      />
      {/* Badge doc_count */}
      {node.doc_count > 1 && (
        <>
          <graphics draw={drawBadge} />
          <text
            text={String(node.doc_count)}
            anchor={{ x: 0.5, y: 0.5 }}
            x={NODE_WIDTH / 2 - 6}
            y={-NODE_HEIGHT / 2 + 6}
            style={{ fontSize: 9, fill: 0x333333, fontWeight: 'bold' }}
          />
        </>
      )}
    </container>
  );
}
