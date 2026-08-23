import { describe, expect, test } from 'vitest';
import { SLASH_COMMANDS, filterSlashCommands, type SlashCommand } from '../slashCommands';
import { BLOCK_TYPES } from '../../blockTypes';

const typeNumbers = (cmds: SlashCommand[]) => cmds.map((c) => c.typeNumber);

describe('SLASH_COMMANDS', () => {
    test('покрывает все типы блоков с уникальными номерами', () => {
        expect(SLASH_COMMANDS.length).toBe(BLOCK_TYPES.length);
        const set = new Set(typeNumbers(SLASH_COMMANDS));
        expect(set.size).toBe(SLASH_COMMANDS.length);
    });
});

describe('filterSlashCommands', () => {
    test('точный алиас ставит команду на первое место', () => {
        const out = filterSlashCommands('triplet');
        expect(out[0]?.typeNumber).toBe(4);
    });

    test('русский алиас работает', () => {
        const out = filterSlashCommands('триплет');
        expect(out[0]?.typeNumber).toBe(4);
        expect(filterSlashCommands('цель')[0]?.typeNumber).toBe(2);
        expect(filterSlashCommands('утверждение')[0]?.typeNumber).toBe(38);
    });

    test('ведущий слэш и пробелы игнорируются', () => {
        expect(filterSlashCommands('/ meta')[0]?.typeNumber).toBe(1);
        expect(filterSlashCommands('  goal ')[0]?.typeNumber).toBe(2);
    });

    test('префиксный поиск по имени', () => {
        const out = filterSlashCommands('гипо');
        expect(out.map((c) => c.typeNumber)).toContain(7);
        expect(out[0]?.typeNumber).toBe(7);
    });

    test('числовой запрос находит по номеру типа', () => {
        const out = filterSlashCommands('38');
        expect(out[0]?.typeNumber).toBe(38);
    });

    test('пустой запрос возвращает полный список с учётом лимита', () => {
        const out = filterSlashCommands('', [], SLASH_COMMANDS.length + 10);
        expect(out.length).toBe(SLASH_COMMANDS.length);
    });

    test('недавние поднимаются при пустом запросе', () => {
        const recent = [38, 14];
        const out = filterSlashCommands('', recent);
        expect(typeNumbers(out).slice(0, 2)).toEqual([38, 14]);
        // остальные — после недавних
        for (let i = 2; i < out.length; i++) {
            expect([38, 14]).not.toContain(out[i].typeNumber);
        }
    });

    test('недавние дают бонус только совпадающим по запросу командам', () => {
        const out = filterSlashCommands('шаг', [57]);
        expect(out[0]?.typeNumber).toBe(56);
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
        expect(out.map((c) => c.typeNumber)).toContain(4);
    });
});
