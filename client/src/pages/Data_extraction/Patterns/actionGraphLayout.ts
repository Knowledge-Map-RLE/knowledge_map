import type { BlockData, LinkData } from '../../../widgets/KnowledgeMap';
import type { ConfirmedActionNode, ConfirmedActionEdge } from '../../../services/api';

const SPACING_X = 380;
const SPACING_Y = 160;

/**
 * Computes x/y positions for Action nodes using Kahn's topological sort.
 * Nodes in the same topological column are stacked vertically.
 * Isolated nodes (no edges) are placed in column 0.
 */
export function computeActionGraphLayout(
    nodes: ConfirmedActionNode[],
    edges: ConfirmedActionEdge[],
): { blocks: BlockData[]; links: LinkData[] } {
    if (nodes.length === 0) {
        return { blocks: [], links: [] };
    }

    const nodeIds = nodes.map(n => n.uid);
    const inDegree: Record<string, number> = {};
    const outNeighbors: Record<string, string[]> = {};

    for (const id of nodeIds) {
        inDegree[id] = 0;
        outNeighbors[id] = [];
    }

    // Only use edges where both endpoints exist in nodes list
    const validEdges = edges.filter(e => inDegree[e.src_uid] !== undefined && inDegree[e.tgt_uid] !== undefined);

    for (const e of validEdges) {
        outNeighbors[e.src_uid].push(e.tgt_uid);
        inDegree[e.tgt_uid] += 1;
    }

    // Kahn's algorithm — assign column by layer
    const column: Record<string, number> = {};
    const queue: string[] = [];

    for (const id of nodeIds) {
        if (inDegree[id] === 0) {
            queue.push(id);
            column[id] = 0;
        }
    }

    const remaining = { ...inDegree };

    while (queue.length > 0) {
        const current = queue.shift()!;
        for (const neighbor of outNeighbors[current]) {
            column[neighbor] = Math.max(column[neighbor] ?? 0, (column[current] ?? 0) + 1);
            remaining[neighbor] -= 1;
            if (remaining[neighbor] === 0) {
                queue.push(neighbor);
            }
        }
    }

    // Assign any unvisited nodes (cycles) to column 0
    for (const id of nodeIds) {
        if (column[id] === undefined) {
            column[id] = 0;
        }
    }

    // Stack nodes within each column
    const rowInColumn: Record<string, number> = {};
    const colCount: Record<number, number> = {};
    for (const id of nodeIds) {
        const col = column[id];
        rowInColumn[id] = colCount[col] ?? 0;
        colCount[col] = (colCount[col] ?? 0) + 1;
    }

    const blocks: BlockData[] = nodes.map(n => ({
        id: n.uid,
        title: n.full_phrase || n.verb_text || n.verb,
        x: column[n.uid] * SPACING_X,
        y: rowInColumn[n.uid] * SPACING_Y,
        layer: column[n.uid],
        level: 0,
    }));

    const links: LinkData[] = validEdges.map(e => ({
        id: `${e.src_uid}-${e.tgt_uid}`,
        source_id: e.src_uid,
        target_id: e.tgt_uid,
    }));

    return { blocks, links };
}
