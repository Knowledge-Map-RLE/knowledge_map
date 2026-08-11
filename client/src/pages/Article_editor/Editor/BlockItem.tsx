import React, { useState, useCallback, useRef, useEffect } from 'react';
import type { ArticleBlock } from '../model';
import { highlightPython } from './blockUtils';
import styles from '../Article_editor.module.css';

interface BlockItemProps {
  block: ArticleBlock;
  index: number;
  totalBlocks: number;
  isHighlighted: boolean;
  onChange: (content: string) => void;
  onDragStart: (e: React.DragEvent) => void;
  onContextMenu: (e: React.MouseEvent) => void;
}

const TYPE_ICONS: Partial<Record<ArticleBlock['type'], string>> = {
  image: '\u{1F5BC}\uFE0F',
  table: '\u{1F4CA}',
  separator: '\u2014',
  code: '\u{1F4BB}',
  formula: '\u03A3',
  paragraph: '\u00B6',
};

const BlockItem: React.FC<BlockItemProps> = ({
  block, index, totalBlocks, isHighlighted, onChange,
  onDragStart, onContextMenu,
}) => {
  const [showCodeEdit, setShowCodeEdit] = useState(false);
  const [showFormulaPreview, setShowFormulaPreview] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [block.content]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
  }, [onChange]);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    onContextMenu(e);
  }, [onContextMenu]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter') {
      e.stopPropagation();
    }
  }, []);

  const textarea = (
    <textarea
      ref={textareaRef}
      className={`${styles.blockTextarea} ${block.type === 'code' ? styles.blockTextareaCode : ''} ${block.type === 'formula' ? styles.blockTextareaFormula : ''}`}
      value={block.content}
      onChange={handleChange}
      onKeyDown={handleKeyDown}
      placeholder={
        block.type === 'sentence' ? 'Введите предложение...'
        : block.type === 'paragraph' ? '\u00B6 Абзац'
        : block.type === 'code' ? 'Введите код Python...'
        : block.type === 'formula' ? 'Введите LaTeX формулу...'
        : '...'
      }
      spellCheck={false}
      rows={Math.max(1, block.content.split('\n').length)}
    />
  );

  const renderContent = () => {
    switch (block.type) {
      case 'code':
        return (
          <div className={styles.codeWrapper}>
            <div className={styles.codeBadge}>Python</div>
            {showCodeEdit || !block.content ? (
              textarea
            ) : (
              <div
                className={styles.codePreview}
                onClick={() => setShowCodeEdit(true)}
                dangerouslySetInnerHTML={{ __html: highlightPython(block.content) }}
              />
            )}
            {block.content && (
              <button
                className={styles.codeToggle}
                onClick={() => setShowCodeEdit((p) => !p)}
              >
                {showCodeEdit ? '\u25B6 Превью' : '\u270E Редактировать'}
              </button>
            )}
          </div>
        );

      case 'formula':
        return (
          <div className={styles.formulaWrapper}>
            {textarea}
            <button
              className={styles.formulaPreviewBtn}
              onClick={() => setShowFormulaPreview((p) => !p)}
            >
              {showFormulaPreview ? '\u25B2 Скрыть' : '\u03A3 Превью'}
            </button>
            {showFormulaPreview && block.content && (
              <div className={styles.formulaPreview}>
                {block.content}
              </div>
            )}
          </div>
        );

      case 'separator':
        return <hr className={styles.separatorLine} />;

      default:
        return textarea;
    }
  };

  return (
    <div
      className={`${styles.blockItem} ${isHighlighted ? styles.blockHighlighted : ''} ${block.type === 'paragraph' ? styles.blockItemParagraph : ''}`}
      onContextMenu={handleContextMenu}
    >
      <div
        className={styles.blockDragHandle}
        draggable
        onDragStart={onDragStart}
        title="Перетащить"
      >
        &#x2261;
      </div>

      <div className={`${styles.blockNumber} ${block.type === 'sentence' ? '' : styles.blockNumberIcon}`}>
        {block.type === 'sentence' ? index + 1 : TYPE_ICONS[block.type] || ''}
      </div>

      <div className={styles.blockContent}>
        {renderContent()}
      </div>
    </div>
  );
};

export default React.memo(BlockItem);
