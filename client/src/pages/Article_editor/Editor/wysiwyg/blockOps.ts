import type { ArticleBlockData, AuthorInfo, BlockDataValue } from '../../model';
import { uuid8Str } from '../blockConverter';

export function sortBlocks(blocks: ArticleBlockData[]): ArticleBlockData[] {
    return [...blocks].sort((a, b) => a.order - b.order);
}

function reindex(blocks: ArticleBlockData[]): ArticleBlockData[] {
    return blocks.map((b, i) => (b.order === i ? b : { ...b, order: i }));
}

export interface InsertOptions {
    afterIndex?: number | null;
    blockType: number;
    instanceId?: string;
    author?: AuthorInfo;
    data?: Record<string, BlockDataValue>;
}

export function insertBlock(blocks: ArticleBlockData[], opts: InsertOptions): { next: ArticleBlockData[]; instanceId: string } {
    const sorted = sortBlocks(blocks);
    const instanceId = opts.instanceId ?? uuid8Str();
    const at = opts.afterIndex === null || opts.afterIndex === undefined ? sorted.length : Math.min(Math.max(opts.afterIndex + 1, 0), sorted.length);
    const block: ArticleBlockData = {
        instanceId,
        blockType: opts.blockType,
        data: opts.data ? { ...opts.data } : {},
        order: at,
        author: opts.author,
    };
    const next = [...sorted];
    next.splice(at, 0, block);
    return { next: reindex(next), instanceId };
}

export function removeBlocks(blocks: ArticleBlockData[], ids: readonly string[]): ArticleBlockData[] {
    const doomed = new Set(ids);
    return reindex(sortBlocks(blocks).filter((b) => !doomed.has(b.instanceId)));
}

export function moveBlock(blocks: ArticleBlockData[], fromIndex: number, toIndex: number): ArticleBlockData[] {
    const sorted = sortBlocks(blocks);
    if (fromIndex < 0 || fromIndex >= sorted.length) return sorted;
    const target = Math.min(Math.max(toIndex, 0), sorted.length - 1);
    if (fromIndex === target) return sorted;
    const next = [...sorted];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(target, 0, moved);
    return reindex(next);
}

export function duplicateBlock(blocks: ArticleBlockData[], instanceId: string, newInstanceId?: string): { next: ArticleBlockData[]; instanceId: string } {
    const sorted = sortBlocks(blocks);
    const index = sorted.findIndex((b) => b.instanceId === instanceId);
    if (index < 0) return { next: sorted, instanceId };
    const source = sorted[index];
    const clone: ArticleBlockData = {
        ...source,
        instanceId: newInstanceId ?? uuid8Str(),
        data: JSON.parse(JSON.stringify(source.data)) as Record<string, BlockDataValue>,
        order: index + 1,
    };
    const next = [...sorted];
    next.splice(index + 1, 0, clone);
    return { next: reindex(next), instanceId: clone.instanceId };
}

export function setBlockField(
    blocks: ArticleBlockData[],
    instanceId: string,
    fieldKey: string,
    value: BlockDataValue,
): ArticleBlockData[] {
    return blocks.map((b) =>
        b.instanceId === instanceId && b.data[fieldKey] !== value
            ? { ...b, data: { ...b.data, [fieldKey]: value } }
            : b,
    );
}

export function setBlockType(blocks: ArticleBlockData[], instanceId: string, blockType: number): ArticleBlockData[] {
    return blocks.map((b) => (b.instanceId === instanceId && b.blockType !== blockType ? { ...b, blockType } : b));
}
