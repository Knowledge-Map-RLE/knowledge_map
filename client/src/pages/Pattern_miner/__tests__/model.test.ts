import { describe, expect, test } from 'vitest';
import {
    KNOWLEDGE_METHOD_LABEL_RU,
    CHECK_STATUS_LABEL_RU,
    labelForNode,
} from '../model';

describe('model helpers for knowledge generation', () => {
    test('method labels cover all four methods', () => {
        expect(KNOWLEDGE_METHOD_LABEL_RU.pattern).toBe('Паттерн');
        expect(KNOWLEDGE_METHOD_LABEL_RU.logical).toBe('Логическая операция');
        expect(KNOWLEDGE_METHOD_LABEL_RU.syllogism).toBe('Силлогизм');
        expect(KNOWLEDGE_METHOD_LABEL_RU.thinking).toBe('Операция мышления');
    });

    test('check status labels', () => {
        expect(CHECK_STATUS_LABEL_RU.new.label).toBe('новое');
        expect(CHECK_STATUS_LABEL_RU.exists.tone).toBe('exists');
        expect(CHECK_STATUS_LABEL_RU.conflicts.tone).toBe('conflicts');
    });

    test('labelForNode keeps original semantics', () => {
        expect(labelForNode('concept')).toBe('Концепт');
        expect(labelForNode('ST|increases|a|b')).toBe('ST:increases');
        expect(labelForNode('anything')).toBe('anything');
    });
});