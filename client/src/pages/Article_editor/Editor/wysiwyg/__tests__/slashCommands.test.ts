import { describe, expect, test } from 'vitest';
import { SLASH_COMMANDS, filterSlashCommands, type SlashCommand } from '../slashCommands';
import { BLOCK_TYPES } from '../../blockTypes';

const designations = (cmds: SlashCommand[]) => cmds.map((c) => c.designation);

describe('SLASH_COMMANDS', () => {
    test('покрывает все типы блоков с уникальными обозначениями', () => {
        expect(SLASH_COMMANDS.length).toBe(BLOCK_TYPES.length);
        const set = new Set(designations(SLASH_COMMANDS));
        expect(set.size).toBe(SLASH_COMMANDS.length);
    });
});

describe('filterSlashCommands', () => {
    test('точный алиас ставит команду на первое место', () => {
        const out = filterSlashCommands('triplet');
        expect(out[0]?.designation).toBe('statement');
    });

    test('русский алиас работает', () => {
        const out = filterSlashCommands('триплет');
        expect(out[0]?.designation).toBe('statement');
        expect(filterSlashCommands('цель')[0]?.designation).toBe('goal');
        expect(filterSlashCommands('утверждение')[0]?.designation).toBe('claim');
    });

    test('ведущий слэш и пробелы игнорируются', () => {
        expect(filterSlashCommands('/ meta')[0]?.designation).toBe('metadata');
        expect(filterSlashCommands('  goal ')[0]?.designation).toBe('goal');
    });

    test('префиксный поиск по имени', () => {
        const out = filterSlashCommands('гипо');
        expect(out.map((c) => c.designation)).toContain('hypothesis');
        expect(out[0]?.designation).toBe('hypothesis');
    });

    test('поиск по designation-ключу', () => {
        const out = filterSlashCommands('claim');
        expect(out[0]?.designation).toBe('claim');
    });

    test('пустой запрос возвращает полный список с учётом лимита', () => {
        const out = filterSlashCommands('', [], SLASH_COMMANDS.length + 10);
        expect(out.length).toBe(SLASH_COMMANDS.length);
    });

    test('недавние поднимаются при пустом запросе', () => {
        const recent = ['claim', 'experiment'];
        const out = filterSlashCommands('', recent);
        expect(designations(out).slice(0, 2)).toEqual(['claim', 'experiment']);
        // остальные — после недавних
        for (let i = 2; i < out.length; i++) {
            expect(['claim', 'experiment']).not.toContain(out[i].designation);
        }
    });

    test('недавние дают бонус только совпадающим по запросу командам', () => {
        const out = filterSlashCommands('шаг', ['finding']);
        expect(out[0]?.designation).toBe('experiment_step');
    });

    test('лимит результата', () => {
        expect(filterSlashCommands('', [], 5)).toHaveLength(5);
    });

    test('бессмысленный запрос даёт пустой результат', () => {
        expect(filterSlashCommands('zzzzzz')).toEqual([]);
    });

    test('fuzzy-подпоследовательность находит команду', () => {
        // «птл» — подпоследовательность «триплет»
        const out = filterSlashCommands('птл');
        expect(out.map((c) => c.designation)).toContain('statement');
    });
});