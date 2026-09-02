import React from 'react';
import { BLOCK_DEFS, BLOCK_ORDER } from '../model';

interface BlockPaletteProps {
    onDragStart: (e: React.DragEvent, type: string) => void;
    onPick?: (type: string) => void;
    pendingType?: string | null;
}

/**
 * Левая палитра блоков (Scratch-стиль).
 * Блок можно перетащить на canvas или кликнуть для размещения (режим ожидания).
 */
export const BlockPalette: React.FC<BlockPaletteProps> = ({ onDragStart, onPick, pendingType }) => {
    return (
        <div style={paletteStyle}>
            <h3 style={{ margin: '8px 0', fontSize: '14px' }}>Блоки паттерна</h3>
            {BLOCK_ORDER.map((type) => {
                const def = BLOCK_DEFS[type];
                const active = pendingType === type;
                return (
                    <div
                        key={type}
                        draggable
                        onDragStart={(e) => onDragStart(e, type)}
                        onClick={() => onPick?.(type)}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '8px',
                            margin: '6px 0',
                            border: `2px solid ${def.color}`,
                            borderRadius: '8px',
                            background: active ? '#fff8e1' : '#fff',
                            cursor: 'grab',
                            userSelect: 'none',
                            boxShadow: active ? '0 0 0 2px #FFEE58' : 'none',
                        }}
                    >
                        <svg width="40" height="30" viewBox="0 0 40 30">
                            <PatternIcon type={type} color={def.color} />
                        </svg>
                        <span style={{ fontSize: '12px', fontWeight: 500 }}>{def.label}</span>
                    </div>
                );
            })}
            <p style={{ fontSize: '10px', color: '#999', marginTop: '12px' }}>
                Перетащите блок на канвас или кликните по нему, затем кликните по канвасу.
                Порты-пазлы соединяются только совместимыми типами.
            </p>
        </div>
    );
};

const PatternIcon: React.FC<{ type: string; color: string }> = ({ type, color }) => {
    switch (type) {
        case 'statement':
            return <rect x="2" y="5" width="36" height="20" rx="4" fill={color} />;
        case 'concept':
            return <circle cx="20" cy="15" r="13" fill={color} />;
        case 'literal':
            return <polygon points="20,2 38,15 20,28 2,15" fill={color} />;
        case 'relation':
            return <polygon points="20,2 38,12 35,28 5,28 2,12" fill={color} />;
        case 'negation':
            return <polygon points="20,2 38,28 2,28" fill={color} />;
        case 'context':
            return <polygon points="8,2 32,2 38,15 32,28 8,28 2,15" fill={color} />;
        default:
            return <rect x="2" y="5" width="36" height="20" rx="4" fill={color} />;
    }
};

const paletteStyle: React.CSSProperties = {
    width: '160px',
    padding: '8px',
    borderRight: '1px solid #ddd',
    background: '#fafafa',
    overflowY: 'auto',
    height: '100%',
};
