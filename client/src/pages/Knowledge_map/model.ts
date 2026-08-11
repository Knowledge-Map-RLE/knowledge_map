import type { BlockData, LinkData } from '../../widgets/KnowledgeMap';

export interface Knowledge_mapProps {
    externalBlocks?: BlockData[];
    externalLinks?: LinkData[];
    embedded?: boolean;
}
