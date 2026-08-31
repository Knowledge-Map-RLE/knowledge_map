import type { ArticleBlockData, BlockFieldDef, BlockTypeDef } from '../../model';
import { getBlockTypeDef } from '../blockTypes';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
    return UUID_RE.test(value);
}

const HIERARCHY_FIELD_KEYS: ReadonlySet<string> = new Set(['sequence', 'steps', 'findings']);

function parseUuidList(value: unknown): string[] {
    if (typeof value !== 'string' || !value.trim()) return [];
    try {
        const parsed = JSON.parse(value) as unknown;
        if (!Array.isArray(parsed)) return [];
        return parsed.map((v) => String(v).trim()).filter(Boolean);
    } catch {
        return value.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
    }
}

export interface BlockTree {
    depthOf: Map<string, number>;
    parentOf: Map<string, string | null>;
    childrenOf: Map<string, string[]>;
    chainOf: Map<string, string[]>;
}

export function buildBlockTree(blocks: ArticleBlockData[]): BlockTree {
    const sorted = [...blocks].sort((a, b) => a.order - b.order);
    const byId = new Set(sorted.map((b) => b.instanceId));

    const parentOf = new Map<string, string | null>();
    for (const b of sorted) parentOf.set(b.instanceId, null);

    for (const b of sorted) {
        const def: BlockTypeDef | undefined = getBlockTypeDef(b.blockType);
        if (!def) continue;
        for (const field of def.fields) {
            if (!HIERARCHY_FIELD_KEYS.has(field.key) || field.inputType !== 'uuid-list') continue;
            for (const ref of parseUuidList(b.data[field.key])) {
                if (!byId.has(ref)) continue;
                if (ref === b.instanceId) continue;
                if (parentOf.get(ref) === null) parentOf.set(ref, b.instanceId);
            }
        }
    }

    const childrenOf = new Map<string, string[]>();
    const roots: string[] = [];
    for (const b of sorted) {
        const parent = parentOf.get(b.instanceId) ?? null;
        if (parent === null) {
            roots.push(b.instanceId);
            continue;
        }
        const arr = childrenOf.get(parent);
        if (arr) arr.push(b.instanceId);
        else childrenOf.set(parent, [b.instanceId]);
    }

    const depthOf = new Map<string, number>();
    for (const id of roots) depthOf.set(id, 0);
    let progressed = true;
    while (progressed) {
        progressed = false;
        for (const b of sorted) {
            if (depthOf.has(b.instanceId)) continue;
            const parent = parentOf.get(b.instanceId);
            if (parent !== null && parent !== undefined && depthOf.has(parent)) {
                depthOf.set(b.instanceId, depthOf.get(parent)! + 1);
                progressed = true;
            }
        }
    }

    const chainOf = new Map<string, string[]>();
    for (const b of sorted) {
        const chain: string[] = [];
        let cursor: string | null = b.instanceId;
        const guard = new Set<string>();
        while (cursor && !guard.has(cursor)) {
            guard.add(cursor);
            chain.unshift(cursor);
            cursor = parentOf.get(cursor) ?? null;
        }
        chainOf.set(b.instanceId, chain);
    }

    return { depthOf, parentOf, childrenOf: childrenOf as Map<string, string[]>, chainOf };
}

export interface RefEntry {
    id: string;
    blockType?: number;
    label: string;
    chainText?: string;
}

export function blockLabel(block: ArticleBlockData): string {
    const def: BlockTypeDef | undefined = getBlockTypeDef(block.blockType);
    if (!def) return block.instanceId;

    const s = typeof block.data.subject === 'string' ? block.data.subject.trim() : '';
    const p = typeof block.data.predicate === 'string' ? block.data.predicate.trim() : '';
    const o = typeof block.data.object === 'string' ? block.data.object.trim() : '';
    if (s || p || o) return `${s || '?'} ${p ? `→ ${p}` : ''} ${o ? `→ ${o}` : ''}`.replace(/\s+/g, ' ').trim();

    const nameField: BlockFieldDef | undefined = def.fields.find(
        (f) => (f.inputType === 'text' || f.inputType === 'textarea')
            && typeof block.data[f.key] === 'string'
            && (block.data[f.key] as string).trim().length > 0,
    );
    if (nameField) return String(block.data[nameField.key]).trim();

    return `T${def.typeNumber} ${def.name}`;
}

export function sortBlocksByOrder(blocks: ArticleBlockData[]): ArticleBlockData[] {
    return [...blocks].sort((a, b) => a.order - b.order);
}

/**
 * Резолвит UUID в человекочитаемую метку блока (рекурсивно по subject/object,
 * с защитой от циклов). Если значение не UUID или блока нет — возвращает как есть.
 */
function buildResolvedLabel(
    uuid: string,
    blockById: Map<string, ArticleBlockData>,
    visited: Set<string>,
): string {
    if (!isUuid(uuid) || visited.has(uuid)) return uuid;
    const blk = blockById.get(uuid);
    if (!blk) return uuid;
    visited.add(uuid);
    const label = blockLabelResolved(blk, blockById, visited);
    visited.delete(uuid);
    return label;
}

function blockLabelResolved(
    block: ArticleBlockData,
    blockById: Map<string, ArticleBlockData>,
    visited: Set<string>,
): string {
    const def: BlockTypeDef | undefined = getBlockTypeDef(block.blockType);
    if (!def) return block.instanceId;

    const s = typeof block.data.subject === 'string' ? block.data.subject.trim() : '';
    const p = typeof block.data.predicate === 'string' ? block.data.predicate.trim() : '';
    const o = typeof block.data.object === 'string' ? block.data.object.trim() : '';
    if (s || p || o) {
        const sl = isUuid(s) ? buildResolvedLabel(s, blockById, visited) : s;
        const ol = isUuid(o) ? buildResolvedLabel(o, blockById, visited) : o;
        return `${sl || '?'} ${p ? `→ ${p}` : ''} ${ol ? `→ ${ol}` : ''}`.replace(/\s+/g, ' ').trim();
    }

    const nameField: BlockFieldDef | undefined = def.fields.find(
        (f) => (f.inputType === 'text' || f.inputType === 'textarea')
            && typeof block.data[f.key] === 'string'
            && (block.data[f.key] as string).trim().length > 0,
    );
    if (nameField) return String(block.data[nameField.key]).trim();

    return `T${def.typeNumber} ${def.name}`;
}

export function buildRefIndex(
    blocks: ArticleBlockData[],
    tree: BlockTree,
): Map<string, RefEntry> {
    const blockById = new Map<string, ArticleBlockData>();
    const sorted = sortBlocksByOrder(blocks);
    for (const b of sorted) blockById.set(b.instanceId, b);

    // Два прохода: сначала все метки, затем chainText — иначе resolveChainText
    // для блоков, идущих раньше своих родителей по order, не находит метки
    // и подставляет голые instanceId. Резолв UUID в subject/object выполняется
    // рекурсивно (как в blockConverter.buildBlockLabel): «{SEQn}/{Bn}»-ссылки,
    // пришедшие от LLM после резолва, превращаются в человекочитаемый текст.
    const index = new Map<string, RefEntry>();
    for (const b of sorted) {
        index.set(b.instanceId, {
            id: b.instanceId,
            blockType: b.blockType,
            label: blockLabel(b),
            chainText: '',
        });
    }
    for (const b of sorted) {
        const entry = index.get(b.instanceId);
        if (!entry) continue;
        entry.label = blockLabelResolved(b, blockById, new Set<string>());
    }
    for (const b of sorted) {
        const entry = index.get(b.instanceId);
        if (!entry) continue;
        entry.chainText = resolveChainText(b.instanceId, tree, index);
    }
    return index;
}

export function resolveChainText(
    instanceId: string,
    tree: BlockTree,
    refIndex: Map<string, RefEntry>,
): string {
    const chain = tree.chainOf.get(instanceId);
    if (!chain || chain.length === 0) return refIndex.get(instanceId)?.label ?? instanceId;
    return chain
        .map((id) => refIndex.get(id)?.label ?? id)
        .join(' → ');
}
