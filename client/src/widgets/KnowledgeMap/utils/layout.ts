import type { Block, Level, Sublevel } from '../../entities/block/model';

export function calculateBlockCoordinates(blocks: Block[], levels: Level[], sublevels: Sublevel[]): Block[] {
    return blocks.map(block => {
        const sublevel = sublevels.find(s => s.id === block.sublevel_id);
        if (!sublevel) return block;
        
        const level = levels.find(l => l.id === sublevel.level_id);
        if (!level) return block;
        
        const baseY = level.min_y ?? 0;
        const blockIndex = sublevel.block_ids.indexOf(block.id);
        
        return {
            ...block,
            y: baseY + (blockIndex + 1) * 100,
        };
    });
}

export function calculateLevelCoordinates(levels: Level[], blocks: Block[]): Level[] {
    if (blocks.length === 0) return levels;
    
    return levels.map(level => {
        const levelBlocks = blocks.filter(b => b.level === level.id);
        if (levelBlocks.length === 0) return level;
        
        const minX = Math.min(...levelBlocks.map(b => b.x));
        const maxX = Math.max(...levelBlocks.map(b => b.x + 200));
        const minY = Math.min(...levelBlocks.map(b => b.y));
        const maxY = Math.max(...levelBlocks.map(b => b.y + 100));
        
        return {
            ...level,
            min_x: minX - 50,
            max_x: maxX + 50,
            min_y: minY - 50,
            max_y: maxY + 50,
        };
    });
}

export function calculateSublevelCoordinates(sublevels: Sublevel[], blocks: Block[]): Sublevel[] {
    return sublevels.map(sublevel => {
        const sublevelBlocks = blocks.filter(b => 
            sublevel.block_ids.includes(b.id)
        );
        
        if (sublevelBlocks.length === 0) return sublevel;
        
        const minY = Math.min(...sublevelBlocks.map(b => b.y));
        const maxY = Math.max(...sublevelBlocks.map(b => b.y + 100));
        
        return {
            ...sublevel,
            min_y: minY - 10,
            max_y: maxY + 10,
        };
    });
}
