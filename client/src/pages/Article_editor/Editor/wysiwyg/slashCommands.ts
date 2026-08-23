import { BLOCK_TYPES } from '../blockTypes';

const ALIASES: Record<number, string[]> = {
    1: ['meta', 'metadata', 'метаданные', 'doi', 'статья'],
    2: ['goal', 'цель', 'aim'],
    3: ['text', 'текст', 'paragraph', 'абзац', 'проза'],
    4: ['triplet', 'триплет', 'тройка', 'fact', 'факт'],
    5: ['endpoint', 'primary endpoint', 'первичная точка', 'конечная точка'],
    6: ['secondary endpoints', 'вторичные точки'],
    7: ['hypothesis', 'гипотеза'],
    8: ['prerequisites', 'предпосылки'],
    9: ['expectations', 'ожидания'],
    10: ['deps', 'зависимости', 'knowledge deps'],
    11: ['design', 'дизайн', 'study design'],
    12: ['materials', 'материалы'],
    13: ['methods', 'методы'],
    14: ['experiment', 'эксперимент', 'exp'],
    15: ['criteria', 'критерии', 'inclusion', 'исключение'],
    16: ['mechanism', 'механизм', 'биология'],
    17: ['target', 'мишень', 'объект воздействия'],
    18: ['intervention', 'интервенция', 'вмешательство', 'treatment'],
    19: ['animal model', 'животная модель', 'вид', 'species'],
    21: ['logic', 'логика'],
    22: ['entity', 'сущность', 'concept', 'концепт'],
    23: ['definition', 'определение', 'term', 'термин'],
    24: ['assumptions', 'предположения'],
    25: ['sample size', 'выборка', 'n'],
    26: ['data sources', 'источники'],
    27: ['pvalue', 'p-value', 'p'],
    28: ['variance', 'дисперсия'],
    29: ['effect size', 'эффект'],
    30: ['power', 'мощность'],
    31: ['ci', 'confidence interval', 'доверительный интервал'],
    32: ['numbers', 'числа'],
    33: ['formula', 'формула', 'latex'],
    34: ['dag', 'граф', 'causal', 'каузальный'],
    35: ['pearl', 'перл', 'идентифицируемость'],
    36: ['results', 'результаты'],
    37: ['stats', 'статистика', 'stat processing'],
    38: ['statement', 'claim', 'утверждение'],
    39: ['limitations', 'ограничения'],
    40: ['side findings', 'побочные выводы'],
    41: ['side effects', 'побочные эффекты'],
    42: ['post claims', 'после исследования'],
    43: ['open questions', 'вопросы'],
    44: ['novelty', 'новизна'],
    45: ['versions', 'версии'],
    46: ['future research', 'будущее', 'перспективы'],
    47: ['references', 'ссылки', 'библиография'],
    48: ['aging', 'старение'],
    49: ['image', 'изображение', 'картинка', 'figure', 'рисунок'],
    50: ['code', 'код'],
    51: ['funding', 'финансирование', 'грант'],
    52: ['conflict of interest', 'конфликт интересов'],
    53: ['value', 'ценность', 'информация'],
    54: ['action', 'действие'],
    55: ['group', 'группа животных'],
    56: ['step', 'шаг'],
    57: ['result', 'finding', 'результат', 'находка'],
};

export interface SlashCommand {
    typeNumber: number;
    name: string;
    description: string;
    keywords: string[];
}

export const SLASH_COMMANDS: SlashCommand[] = BLOCK_TYPES.map((t) => ({
    typeNumber: t.typeNumber,
    name: t.name,
    description: t.description ?? '',
    keywords: [
        t.name.toLowerCase(),
        ...(ALIASES[t.typeNumber] ?? []),
        String(t.typeNumber),
    ],
}));

function subsequenceScore(query: string, target: string): number {
    let qi = 0;
    let score = 0;
    let lastHit = -2;
    for (let ti = 0; ti < target.length && qi < query.length; ti++) {
        if (target[ti] === query[qi]) {
            score += ti === lastHit + 1 ? 3 : 1;
            if (ti === 0 || target[ti - 1] === ' ') score += 4;
            lastHit = ti;
            qi++;
        }
    }
    return qi === query.length ? score : -1;
}

function commandScore(cmd: SlashCommand, q: string): number {
    let best = -1;
    for (const kw of cmd.keywords) {
        if (kw === q) {
            best = Math.max(best, 10000);
        } else if (kw.startsWith(q)) {
            best = Math.max(best, 5000 - Math.min(kw.length, 100));
        } else if (kw.includes(q)) {
            best = Math.max(best, 2000);
        } else {
            const s = subsequenceScore(q, kw);
            if (s > best) best = s * 10;
        }
    }
    if (/^\d+$/.test(q) && String(cmd.typeNumber).startsWith(q)) {
        best = Math.max(best, 8000);
    }
    return best;
}

export function filterSlashCommands(
    rawQuery: string,
    recentTypes: readonly number[] = [],
    limit = 30,
): SlashCommand[] {
    const q = rawQuery.trim().toLowerCase().replace(/^\//, '').trim();
    const scored: Array<{ cmd: SlashCommand; score: number }> = [];
    for (const cmd of SLASH_COMMANDS) {
        let score: number;
        if (q) {
            score = commandScore(cmd, q);
            const idx = recentTypes.indexOf(cmd.typeNumber);
            if (idx >= 0 && score > 0) score += Math.max(0, 40 - idx);
        } else {
            const idx = recentTypes.indexOf(cmd.typeNumber);
            score = idx >= 0 ? recentTypes.length - idx + 1 : 0;
        }
        if (!q || score > 0) {
            scored.push({ cmd, score });
        }
    }
    scored.sort((a, b) => b.score - a.score || a.cmd.typeNumber - b.cmd.typeNumber);
    return scored.slice(0, limit).map((s) => s.cmd);
}
