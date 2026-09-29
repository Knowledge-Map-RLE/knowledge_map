import type { ArticleBlockData, KnowledgeStatement } from '../model';
type Term = { kind: 'concept' | 'assertion' | 'literal'; id?: string; value?: string; unit?: string };
type Data = { label?: string; subject: Term; predicate: { label: string }; object: Term | null; modality: string; negated: boolean; context: string };
export function canonicalStatements(blocks: ArticleBlockData[]): KnowledgeStatement[] {
    const lookup = new Map(blocks.map(b => [b.instanceId, b]));
    const resolve = (id: string, seen = new Set<string>()): string => {
        if (seen.has(id)) throw new Error('Cyclic assertion');
        const b = lookup.get(id);
        if (!b) throw new Error('Unresolved semantic reference');
        const d = b.data as unknown as Data;
        if (b.blockType === 'entity') return d.label || '';
        const next = new Set(seen).add(id);
        return term(d.subject, next) + ' → ' + (d.negated ? 'not ' : '') + d.predicate.label.replaceAll('_', ' ')
            + (d.object ? ' → ' + term(d.object, next) : '')
            + (d.modality !== 'asserted' ? ' [' + d.modality + ']' : '')
            + (d.context ? ' (' + d.context + ')' : '');
    };
    const term = (t: Term, seen = new Set<string>()): string => t.kind === 'literal'
        ? (t.value || '') + (t.unit ? ' ' + t.unit : '') : resolve(t.id || '', seen);
    return blocks.filter(b => b.blockType === 'statement').map(b => {
        const d = b.data as unknown as Data;
        return { id: b.instanceId, subject_text: term(d.subject),
            predicate: (d.modality !== 'asserted' ? '[' + d.modality + '] ' : '') + (d.negated ? 'not ' : '') + d.predicate.label,
            object_text: (d.object ? term(d.object) : '') + (d.context ? ' (' + d.context + ')' : ''),
            subject_type: 'concept', object_type: d.object?.kind === 'literal' ? 'literal' : 'concept',
            type: 'EXTRACTED', sourceBlockId: b.instanceId };
    });
}
