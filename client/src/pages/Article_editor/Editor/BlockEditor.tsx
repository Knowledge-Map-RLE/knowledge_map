import React, { useState, useCallback, useRef, useEffect, memo } from 'react';
import BlockItem from './BlockItem';
import ContextMenu from './ContextMenu';
import { blocksToText, generateBlockId } from './blockUtils';
import { splitIntoBlocks } from '../../../services/api/article_editor';
import type { ArticleBlock, BlockType } from '../model';
import styles from '../Article_editor.module.css';

interface BlockEditorProps {
  text: string;
  onChange: (text: string) => void;
  onScroll?: (scrollTop: number, scrollHeight: number) => void;
  highlightContent?: string | null;
  readOnly?: boolean;
}

interface ContextMenuState {
  x: number;
  y: number;
  blockIndex: number;
}

const MemoizedBlockItem = memo(function MemoizedBlockItem({
  block, index, totalBlocks, isHighlighted,
  onEdit, onDragStart, onContextMenu,
}: {
  block: ArticleBlock; index: number; totalBlocks: number; isHighlighted: boolean;
  onEdit: (index: number, content: string) => void;
  onDragStart: (index: number) => void;
  onContextMenu: (e: React.MouseEvent, index: number) => void;
}) {
  const handleChange = useCallback((content: string) => onEdit(index, content), [index, onEdit]);
  const handleDragStart = useCallback(() => onDragStart(index), [index, onDragStart]);
  const handleContextMenu = useCallback((e: React.MouseEvent) => onContextMenu(e, index), [index, onContextMenu]);

  return (
    <BlockItem
      block={block}
      index={index}
      totalBlocks={totalBlocks}
      isHighlighted={isHighlighted}
      onChange={handleChange}
      onDragStart={handleDragStart}
      onContextMenu={handleContextMenu}
    />
  );
});

const BlockEditor: React.FC<BlockEditorProps> = ({
  text, onChange, onScroll, highlightContent, readOnly = false,
}) => {
  const [blocks, setBlocks] = useState<ArticleBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [highlightBlockId, setHighlightBlockId] = useState<string | null>(null);
  const [hoverZoneIndex, setHoverZoneIndex] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const prevTextRef = useRef<string>(text);
  const initialLoadDone = useRef(false);
  const zoneTimer = useRef<number | null>(null);
  const BLOCKS_KEY = useRef<string>('');

  const loadBlocks = useCallback(async (sourceText: string) => {
    if (!sourceText.trim()) {
      setBlocks([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const result = await splitIntoBlocks(sourceText);
      if (result.success && Array.isArray(result.blocks)) {
        const mapped: ArticleBlock[] = result.blocks.map((b: any, i: number) => ({
          id: b.id || generateBlockId(),
          type: b.type as BlockType,
          content: b.content || '',
          order: b.order ?? i,
        }));
        setBlocks(mapped);
        BLOCKS_KEY.current = sourceText.slice(0, 100);
      } else {
        console.error('splitIntoBlocks returned success=false:', result);
        setBlocks([]);
      }
    } catch (err) {
      console.error('splitIntoBlocks failed:', err);
      setBlocks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialLoadDone.current) return;
    if (!text.trim()) {
      initialLoadDone.current = true;
      setLoading(false);
      return;
    }
    initialLoadDone.current = true;
    loadBlocks(text);
  }, [text]);

  const internalChangeRef = useRef(false);

  useEffect(() => {
    if (!initialLoadDone.current) return;
    if (internalChangeRef.current) {
      internalChangeRef.current = false;
      const newText = blocksToText(blocks);
      prevTextRef.current = newText;
      onChange(newText);
      return;
    }
    if (text === prevTextRef.current) return;
    const currentText = blocksToText(blocks);
    if (text !== currentText) {
      loadBlocks(text);
    }
    prevTextRef.current = text;
  }, [text, blocks, onChange, loadBlocks]);

  const renumber = useCallback((newBlocks: ArticleBlock[]): ArticleBlock[] => {
    return newBlocks.map((b, i) => ({ ...b, order: i }));
  }, []);

  const handleEdit = useCallback((index: number, content: string) => {
    setBlocks((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], content };
      return next;
    });
    internalChangeRef.current = true;
  }, []);

  const handleAddBlock = useCallback((afterIndex: number) => {
    setBlocks((prev) => {
      const newBlock: ArticleBlock = {
        id: generateBlockId(),
        type: 'paragraph',
        content: '',
        order: afterIndex + 1,
      };
      const next = [...prev];
      next.splice(afterIndex + 1, 0, newBlock);
      return renumber(next);
    });
    internalChangeRef.current = true;
  }, [renumber]);

  const handleDeleteBlock = useCallback((index: number) => {
    setBlocks((prev) => {
      const next = prev.filter((_, i) => i !== index);
      if (next.length === 0) return next;
      return renumber(next);
    });
    setContextMenu(null);
    internalChangeRef.current = true;
  }, [renumber]);

  const handleMoveUp = useCallback((index: number) => {
    if (index === 0) return;
    setBlocks((prev) => {
      const next = [...prev];
      [next[index - 1], next[index]] = [next[index], next[index - 1]];
      return renumber(next);
    });
    internalChangeRef.current = true;
  }, [renumber]);

  const handleMoveDown = useCallback((index: number) => {
    setBlocks((prev) => {
      if (index >= prev.length - 1) return prev;
      const next = [...prev];
      [next[index], next[index + 1]] = [next[index + 1], next[index]];
      return renumber(next);
    });
    internalChangeRef.current = true;
  }, [renumber]);

  const handleDragStart = useCallback((index: number) => {
    setDragIndex(index);
  }, []);

  const handleDrop = useCallback((targetIndex: number) => {
    if (dragIndex === null || dragIndex === targetIndex) {
      setDragIndex(null);
      return;
    }
    setBlocks((prev) => {
      const next = [...prev];
      const [moved] = next.splice(dragIndex, 1);
      const adjustedTarget = dragIndex < targetIndex ? targetIndex - 1 : targetIndex;
      next.splice(adjustedTarget, 0, moved);
      return renumber(next);
    });
    setDragIndex(null);
    internalChangeRef.current = true;
  }, [dragIndex, renumber]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleContextMenu = useCallback((e: React.MouseEvent, index: number) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, blockIndex: index });
  }, []);

  const closeContextMenu = useCallback(() => setContextMenu(null), []);

  useEffect(() => {
    if (highlightContent) {
      const idx = blocks.findIndex(
        (b) => b.content.includes(highlightContent) || highlightContent.includes(b.content),
      );
      setHighlightBlockId(idx >= 0 ? blocks[idx].id : null);
    } else {
      setHighlightBlockId(null);
    }
  }, [highlightContent, blocks]);

  const handleScroll = useCallback(() => {
    const el = listRef.current;
    if (el && onScroll) {
      onScroll(el.scrollTop, el.scrollHeight);
    }
  }, [onScroll]);

  const handleZoneMouseEnter = useCallback((index: number) => {
    if (zoneTimer.current) clearTimeout(zoneTimer.current);
    setHoverZoneIndex(index);
  }, []);

  const handleZoneMouseLeave = useCallback(() => {
    zoneTimer.current = window.setTimeout(() => {
      setHoverZoneIndex(null);
    }, 150);
  }, []);

  const handleZoneClick = useCallback((index: number) => {
    handleAddBlock(index - 1);
    setHoverZoneIndex(null);
  }, [handleAddBlock]);

  const renderInsertZone = (zoneIndex: number) => {
    const isHovered = hoverZoneIndex === zoneIndex;
    return (
      <div
        className={styles.insertZone}
        onMouseEnter={() => handleZoneMouseEnter(zoneIndex)}
        onMouseLeave={handleZoneMouseLeave}
        onDragOver={handleDragOver}
        onDrop={() => {
          if (dragIndex !== null) handleDrop(zoneIndex);
        }}
      >
        {isHovered && (
          <button
            className={styles.insertButton}
            onClick={() => handleZoneClick(zoneIndex)}
            title="Добавить пункт"
          >
            +
          </button>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af', fontSize: 13 }}>
        Загрузка блоков...
      </div>
    );
  }

  if (blocks.length === 0) {
    return (
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }} ref={listRef}>
        <div style={{ textAlign: 'center', color: '#9ca3af', fontSize: 13, padding: 24 }}>
          Текст отсутствует. Начните вводить текст или загрузите документ.
        </div>
      </div>
    );
  }

  return (
    <div
      ref={listRef}
      className={styles.blockList}
      onScroll={handleScroll}
    >
      {renderInsertZone(0)}

      {blocks.map((block, i) => (
        <div key={block.id}>
          <MemoizedBlockItem
            block={block}
            index={i}
            totalBlocks={blocks.length}
            isHighlighted={block.id === highlightBlockId}
            onEdit={handleEdit}
            onDragStart={handleDragStart}
            onContextMenu={handleContextMenu}
          />
          {renderInsertZone(i + 1)}
        </div>
      ))}

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          blockIndex={contextMenu.blockIndex}
          totalBlocks={blocks.length}
          onDelete={handleDeleteBlock}
          onMoveUp={handleMoveUp}
          onMoveDown={handleMoveDown}
          onClose={closeContextMenu}
        />
      )}
    </div>
  );
};

export default BlockEditor;
