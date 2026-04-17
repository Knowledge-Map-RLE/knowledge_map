export interface Annotation {
    id: number;
    labels: string[];
    text: string;
    color: string;
    range: { index: number; length: number };
}

export interface MarkdownEditorProps {
    value: string;
    onChange: (markdown: string) => void;
    onExportAnnotations?: (json: unknown) => void;
    onImportAnnotations?: (json: unknown) => void;
    onEditorReady?: (rootEl: HTMLElement) => void;
    readOnly?: boolean;
}

export const AVAILABLE_LABELS = [
    'Organization', 'Person', 'Disease', 'Drug', 'Treatment',
    'Datetime', 'Gene', 'Protein', 'Location', 'Event'
] as const;

export const LABEL_COLORS: Record<string, string> = {
    'Organization': '#FF6B6B',
    'Person': '#4ECDC4',
    'Disease': '#FFD93D',
    'Drug': '#95E1D3',
    'Treatment': '#F38181',
    'Datetime': '#AA96DA',
    'Gene': '#FCBAD3',
    'Protein': '#A8D8EA',
    'Location': '#FCE38A',
    'Event': '#C7CEEA'
};

export const DEFAULT_CUSTOM_COLOR = '#FFD93D';

export interface MarkdownEditorState {
    showLabelModal: boolean;
    selectedRange: { index: number; length: number } | null;
    selectedText: string;
    selectedLabels: string[];
    customColor: string;
    editingAnnotation: Annotation | null;
}
