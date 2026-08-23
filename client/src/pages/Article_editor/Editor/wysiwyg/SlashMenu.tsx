import React from 'react';
import type { SlashCommand } from './slashCommands';
import { getBlockTypeDef } from '../blockTypes';
import styles from '../../Article_editor.module.css';

interface SlashMenuProps {
    items: SlashCommand[];
    selectedIdx: number;
    top: number;
    left: number;
    onSelect: (cmd: SlashCommand) => void;
    onHover: (idx: number) => void;
}

const MENU_WIDTH = 340;
const MENU_MAX_HEIGHT = 320;

function clampPosition(top: number, left: number, itemCount: number): { top: number; left: number } {
    const height = Math.min(itemCount * 34 + 12, MENU_MAX_HEIGHT);
    return {
        top: Math.max(8, Math.min(top, window.innerHeight - height - 8)),
        left: Math.max(8, Math.min(left, window.innerWidth - MENU_WIDTH - 8)),
    };
}

const SlashMenu: React.FC<SlashMenuProps> = ({ items, selectedIdx, top, left, onSelect, onHover }) => {
    const itemRefs = React.useRef<Array<HTMLButtonElement | null>>([]);
    React.useEffect(() => {
        itemRefs.current[selectedIdx]?.scrollIntoView({ block: 'nearest' });
    }, [selectedIdx]);

    if (items.length === 0) return null;
    const pos = clampPosition(top, left, items.length);

    return (
        <div
            className={styles.wySlashMenu}
            style={{ position: 'fixed', top: pos.top, left: pos.left, width: MENU_WIDTH, maxHeight: MENU_MAX_HEIGHT }}
        >
            {items.map((cmd, idx) => {
                const def = getBlockTypeDef(cmd.typeNumber);
                return (
                    <button
                        key={cmd.typeNumber}
                        ref={(el) => { itemRefs.current[idx] = el; }}
                        type="button"
                        className={`${styles.wySlashItem} ${idx === selectedIdx ? styles.wySlashItemActive : ''}`}
                        onMouseEnter={() => onHover(idx)}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => onSelect(cmd)}
                    >
                        <span
                            className={styles.wySlashDot}
                            style={{ background: def?.color ?? '#94a3b8' }}
                        />
                        <span className={styles.wySlashName}>/{def?.name ?? cmd.name}</span>
                        <span className={styles.wySlashDesc}>{cmd.description}</span>
                    </button>
                );
            })}
        </div>
    );
};

export default React.memo(SlashMenu);
