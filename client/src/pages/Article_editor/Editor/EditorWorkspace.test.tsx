import React from 'react';
import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import EditorWorkspace from './EditorWorkspace';
import type { ArticleBlockData } from '../model';

vi.mock('./PipelineVersions', () => ({
    default: () => <div data-testid="pipeline-versions" />,
}));

vi.mock('./wysiwyg/WysiwygEditor', () => ({
    default: () => <div data-testid="wysiwyg-editor" />,
}));

const blocks = [{
    schemaVersion: 2,
    instanceId: 'row-1',
    blockType: 'statement',
    order: 0,
    data: {
        subject: { kind: 'literal', value: 'aging' },
        predicate: { label: 'involves' },
        object: { kind: 'literal', value: 'metabolic stress' },
        modality: 'asserted',
        negated: false,
        context: 'background claim',
        provenance: { source_spans: [{ start: 12, end: 38 }] },
    },
}] as unknown as ArticleBlockData[];

function renderWorkspace(props: { isGold?: boolean; isGoldStandard?: boolean } = {}) {
    return render(
        <EditorWorkspace
            text="Article text"
            statements={[]}
            blocks={blocks}
            isParsing={false}
            parseProgress={null}
            parseError={null}
            onApplyBlocks={vi.fn()}
            onSave={vi.fn()}
            saveStatus="idle"
            articleUuid="article-1"
            {...props}
        />,
    );
}

describe('EditorWorkspace v2 GOLD rendering', () => {
    test.each([
        ['eval/gold', { isGold: true }],
        ['GOLD pipeline', { isGoldStandard: true }],
    ] as const)('%s shows document-style structural rows and provenance', (_name, props) => {
        const { container } = renderWorkspace(props);

        expect(screen.queryByTestId('pipeline-versions')).not.toBeInTheDocument();
        expect(container.querySelector('[data-pipeline-structural-row="row-1"]')).not.toBeNull();
        const rowsRoot = container.querySelector('[aria-label="Структурные строки"]');
        expect(rowsRoot?.firstElementChild?.className).toMatch(/wyDoc/);
        expect(screen.getByText('источник [12:38]')).toBeInTheDocument();
    });

    test('non-GOLD v2 articles retain pipeline version inspection', () => {
        renderWorkspace();

        expect(screen.getByTestId('pipeline-versions')).toBeInTheDocument();
        expect(screen.queryByLabelText('Структурные строки')).not.toBeInTheDocument();
    });
});
