export type BlockType = 'statement' | 'concept' | 'literal' | 'relation' | 'negation' | 'context';

export type PortType = 'input' | 'output';

export type DataType = 'STATEMENT' | 'CONCEPT' | 'LITERAL' | 'ANY';

export interface Port {
    id: string;
    blockId: string;
    type: PortType;
    dataTypes: DataType[];
    x: number;
    y: number;
}

export interface PatternBlockDef {
    type: BlockType;
    label: string;
    color: string;
    shape: 'rounded-rect' | 'circle' | 'diamond' | 'pentagon' | 'triangle' | 'hexagon';
    inputPorts: { id: string; dataTypes: DataType[] }[];
    outputPorts: { id: string; dataTypes: DataType[] }[];
}

export interface PatternBlockInstance {
    id: string;
    type: BlockType;
    x: number;
    y: number;
    width: number;
    height: number;
    text: string;
    predicate?: string;
}

export interface Connection {
    id: string;
    sourcePortId: string;
    targetPortId: string;
}

export interface CanConnectResult {
    compatible: boolean;
    reason?: string;
}

export const BLOCK_DEFS: Record<BlockType, PatternBlockDef> = {
    statement: {
        type: 'statement',
        label: 'Утверждение',
        color: '#2196F3',
        shape: 'rounded-rect',
        inputPorts: [{ id: 'stmt-in', dataTypes: ['ANY'] }],
        outputPorts: [{ id: 'stmt-out', dataTypes: ['CONCEPT', 'LITERAL'] }],
    },
    concept: {
        type: 'concept',
        label: 'Концепт',
        color: '#4CAF50',
        shape: 'circle',
        inputPorts: [],
        outputPorts: [{ id: 'concept-out', dataTypes: ['STATEMENT', 'ANY'] }],
    },
    literal: {
        type: 'literal',
        label: 'Литерал',
        color: '#FF9800',
        shape: 'diamond',
        inputPorts: [],
        outputPorts: [{ id: 'literal-out', dataTypes: ['STATEMENT', 'ANY'] }],
    },
    relation: {
        type: 'relation',
        label: 'Связь',
        color: '#9C27B0',
        shape: 'pentagon',
        inputPorts: [{ id: 'rel-in', dataTypes: ['CONCEPT', 'STATEMENT', 'LITERAL', 'ANY'] }],
        outputPorts: [{ id: 'rel-out', dataTypes: ['STATEMENT', 'ANY'] }],
    },
    negation: {
        type: 'negation',
        label: 'Отрицание',
        color: '#F44336',
        shape: 'triangle',
        inputPorts: [{ id: 'neg-in', dataTypes: ['STATEMENT', 'ANY'] }],
        outputPorts: [{ id: 'neg-out', dataTypes: ['STATEMENT', 'ANY'] }],
    },
    context: {
        type: 'context',
        label: 'Контекст',
        color: '#607D8B',
        shape: 'hexagon',
        inputPorts: [{ id: 'ctx-in', dataTypes: ['STATEMENT', 'ANY'] }],
        outputPorts: [{ id: 'ctx-out-1', dataTypes: ['ANY'] }, { id: 'ctx-out-2', dataTypes: ['ANY'] }],
    },
};

export const BLOCK_ORDER: BlockType[] = [
    'statement', 'concept', 'literal', 'relation', 'negation', 'context',
];

export function isPortCompatible(source: Port, target: Port): CanConnectResult {
    if (source.blockId === target.blockId) {
        return {
            compatible: false,
            reason: 'Нельзя соединить блок с самим собой',
        };
    }

    const sourceDatatypes = source.dataTypes;
    const targetDatatypes = target.dataTypes;

    const overlap = sourceDatatypes.some(
        (dt) => targetDatatypes.includes(dt) || targetDatatypes.includes('ANY')
    ) || targetDatatypes.some((dt) => sourceDatatypes.includes('ANY'));

    if (!overlap) {
        return {
            compatible: false,
            reason: 'Типы данных портов несовместимы',
        };
    }

    return { compatible: true };
}

let idCounter = 0;
export function genId(prefix = 'id'): string {
    idCounter += 1;
    return `${prefix}-${Date.now()}-${idCounter}`;
}

export interface BlockPortRef {
    port: Port;
    localX: number;
    localY: number;
}

/** Возвращает все порты блока с их локальными координатами (внутри блока). */
export function getBlockPorts(block: Pick<PatternBlockInstance, 'id' | 'type' | 'width' | 'height'>): BlockPortRef[] {
    const def = BLOCK_DEFS[block.type];
    const cy = block.height / 2;
    const refs: BlockPortRef[] = [];
    for (const p of def.inputPorts) {
        refs.push({
            port: {
                id: `${block.id}:input-${p.id}`,
                blockId: block.id,
                type: 'input',
                dataTypes: p.dataTypes,
                x: 0,
                y: cy,
            },
            localX: 0,
            localY: cy,
        });
    }
    for (const p of def.outputPorts) {
        refs.push({
            port: {
                id: `${block.id}:output-${p.id}`,
                blockId: block.id,
                type: 'output',
                dataTypes: p.dataTypes,
                x: block.width,
                y: cy,
            },
            localX: block.width,
            localY: cy,
        });
    }
    return refs;
}
