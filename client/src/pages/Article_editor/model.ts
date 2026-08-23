import type { ReactNode } from 'react';

export type ArticleEditorTab = 'editor' | 'graph' | 'patterns' | 'chat';

export type BlockType = 'sentence' | 'image' | 'table' | 'separator' | 'code' | 'formula' | 'paragraph';

export interface ArticleBlock {
  id: string;
  type: BlockType;
  content: string;
  order: number;
}

export interface AuthorInfo {
    uid: string;
    login: string;
    nickname: string;
}

export interface KnowledgeArticle {
    uid: string;
    title?: string;
    original_filename?: string;
    text?: string;
    statements?: KnowledgeStatement[];
    processing_status?: string;
    is_processed?: boolean;
    created_at?: string;
    updated_at?: string;
    author?: AuthorInfo;
}

export interface KnowledgeStatement {
    id: string;
    subject_text: string;
    predicate: string;
    object_text: string;
    confidence?: number;
    sentence_text?: string;
    sort_order?: number;
    type?: string;
    subject_type?: string;
    object_type?: string;
    sourceBlockId?: string;
    author?: AuthorInfo;
}

export interface StatementSelection {
    index: number;
    statement: KnowledgeStatement;
    range?: { start: number; end: number };
}

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

// ═══════════════════════════════════════════════════════════════════
// Structured Block System — типы для блочного редактора статей
// ═══════════════════════════════════════════════════════════════════

export type FieldInputType =
    | 'text'
    | 'textarea'
    | 'number'
    | 'checkbox'
    | 'select'
    | 'key-value-list'
    | 'tag-list'
    | 'text-list'
    | 'uuid-ref'
    | 'pair-list'
    | 'uuid-list'
    | 'image-upload';

export interface BlockFieldDef {
    key: string;
    label: string;
    inputType: FieldInputType;
    placeholder?: string;
    addLabel?: string;
    options?: string[];
    required?: boolean;
    helpText?: string;
    uuidRefs?: Array<{ id: string; label: string }>;
    uuidRefBlockTypes?: number[];
    pairGroupBlockTypes?: number[];
    pairInterventionBlockTypes?: number[];
}

export interface BlockTypeDef {
    typeNumber: number;
    name: string;
    icon: ReactNode;
    color: string;
    fields: BlockFieldDef[];
    canAddMultiple: boolean;
    description?: string;
    layout?: 'row' | 'column' | 'yaml';
}

export type BlockDataValue = string | boolean | number | Record<string, string> | null;

export interface ArticleBlockData {
    instanceId: string;
    blockType: number;
    data: Record<string, BlockDataValue>;
    order: number;
    author?: AuthorInfo;
}

export interface DerivedTriplet {
    id: string;
    subject_text: string;
    predicate: string;
    object_text: string;
    sourceBlockId: string;
    sourceBlockType: number;
    type: 'FACT' | 'META';
    subject_type: 'concept' | 'statement';
    object_type: 'concept' | 'statement' | 'literal';
    confidence: number;
}
