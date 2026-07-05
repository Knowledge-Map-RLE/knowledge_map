import { Graphics, Text, Container } from 'pixi.js';
import { extend } from '@pixi/react';
import { useCallback, useEffect, useRef, memo } from 'react';
import type { BlockData } from '../../../widgets/KnowledgeMap/types/types';

extend({ Container, Graphics, Text });

const BLOCK_WIDTH = 200;
const BLOCK_HEIGHT = 75;

interface ArticleBlockProps {
  blockData: BlockData;
}

function extractTriplet(title: string): [string, string, string] {
  const parts = title.split(' → ');
  return [parts[0] ?? '', parts[1] ?? '', parts[2] ?? ''];
}

function shortId(uuid: string): string {
  return uuid.length > 8 ? uuid.slice(0, 8) + '…' : uuid;
}

export const ArticleBlock = memo(function ArticleBlock({ blockData }: ArticleBlockProps) {
  const { id, title, x, y } = blockData;
  const [subject, predicate, object] = extractTriplet(title);
  const containerRef = useRef<Container>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.x = x;
      containerRef.current.y = y;
    }
  }, [x, y]);

  const drawBg = useCallback((g: Graphics) => {
    g.clear();
    g.roundRect(-BLOCK_WIDTH / 2, -BLOCK_HEIGHT / 2, BLOCK_WIDTH, BLOCK_HEIGHT, 8);
    g.fill(0xffffff);
    g.stroke({ width: 2, color: 0x6366f1 });
  }, []);

  return (
    <container ref={containerRef} zIndex={1}>
      <pixiGraphics draw={drawBg} />
      <pixiText
        text={subject.slice(0, 30)}
        x={0}
        y={-BLOCK_HEIGHT / 2 + 14}
        anchor={0.5}
        style={{ fontSize: 11, fill: 0x059669, fontWeight: '600' } as any}
      />
      <pixiText
        text={predicate.slice(0, 30)}
        x={0}
        y={-BLOCK_HEIGHT / 2 + 30}
        anchor={0.5}
        style={{ fontSize: 10, fill: 0x6366f1, fontStyle: 'italic' } as any}
      />
      <pixiText
        text={object.slice(0, 30)}
        x={0}
        y={-BLOCK_HEIGHT / 2 + 46}
        anchor={0.5}
        style={{ fontSize: 11, fill: 0xd97706, fontWeight: '600' } as any}
      />
      <pixiText
        text={shortId(id)}
        x={BLOCK_WIDTH / 2 - 4}
        y={BLOCK_HEIGHT / 2 - 4}
        anchor={{ x: 1, y: 1 }}
        style={{ fontSize: 8, fill: 0x9ca3af } as any}
      />
    </container>
  );
});
