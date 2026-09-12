import { BLOCK_TYPES } from '../blockTypes';

const ALIASES: Record<string, string[]> = {
    metadata: ['meta', 'metadata', 'метаданные', 'doi', 'статья'],
    goal: ['goal', 'цель', 'aim'],
    text: ['text', 'текст', 'paragraph', 'абзац', 'проза'],
    statement: ['triplet', 'триплет', 'тройка', 'fact', 'факт'],
    hypothesis: ['hypothesis', 'гипотеза'],
    prerequisite: ['prerequisites', 'предпосылки'],
    expectations: ['expectations', 'ожидания'],
    research_design: ['design', 'дизайн', 'study design', 'endpoint', 'primary endpoint', 'secondary endpoints', 'конечные точки'],
    material: ['materials', 'материалы'],
    method: ['methods', 'методы'],
    experiment: ['experiment', 'эксперимент', 'exp'],
    inclusion_exclusion_criteria: ['criteria', 'критерии', 'inclusion', 'исключение'],
    biological_mechanism: ['mechanism', 'механизм', 'биология'],
    impact_goal: ['target', 'мишень', 'объект воздействия'],
    intervention: ['intervention', 'интервенция', 'вмешательство', 'treatment'],
    animal_model: ['animal model', 'животная модель', 'вид', 'species'],
    entity: ['entity', 'сущность', 'concept', 'концепт'],
    definition: ['definition', 'определение', 'term', 'термин'],
    assumptions: ['assumptions', 'предположения'],
    sample_size: ['sample size', 'выборка', 'n'],
    data_source: ['data sources', 'источники'],
    probability_value: ['pvalue', 'p-value', 'p'],
    variance: ['variance', 'дисперсия'],
    effect_size: ['effect size', 'эффект'],
    statistical_power: ['power', 'мощность'],
    confidence_interval: ['ci', 'confidence interval', 'доверительный интервал'],
    magnitude_value: ['numbers', 'числа'],
    formula: ['formula', 'формула', 'latex'],
    causal_graph: ['dag', 'граф', 'causal', 'каузальный'],
    identifiability_criteria: ['pearl', 'перл', 'идентифицируемость'],
    result: ['results', 'результаты'],
    statistical_processing: ['stats', 'статистика', 'stat processing'],
    claim: ['statement', 'claim', 'утверждение'],
    limitations: ['limitations', 'ограничения'],
    side_findings: ['side findings', 'побочные выводы'],
    side_effects: ['side effects', 'побочные эффекты'],
    post_claims: ['post claims', 'после исследования'],
    open_questions: ['open questions', 'вопросы'],
    novelty: ['novelty', 'новизна'],
    versions: ['versions', 'версии'],
    future_research_suggestions: ['future research', 'будущее', 'перспективы'],
    reference: ['references', 'ссылки', 'библиография'],
    link_with_aging: ['aging', 'старение'],
    image: ['image', 'изображение', 'картинка', 'figure', 'рисунок'],
    code: ['code', 'код'],
    funding: ['funding', 'финансирование', 'грант'],
    interest_conflict: ['conflict of interest', 'конфликт интересов'],
    scientific_knowledge_value: ['value', 'ценность', 'информация'],
    action: ['action', 'действие'],
    animal_group: ['group', 'группа животных'],
    experiment_step: ['step', 'шаг'],
    finding: ['result', 'finding', 'результат', 'находка'],
    relation: ['relation', 'связь', 'причинно-следственная', 'зависимость'],
    temporal_relation: ['temporal', 'временная', 'последовательность', 'раньше', 'позже'],
};

export interface SlashCommand {
    designation: string;
    name: string;
    description: string;
    keywords: string[];
}

export const SLASH_COMMANDS: SlashCommand[] = BLOCK_TYPES.map((t) => ({
    designation: t.designation,
    name: t.name,
    description: t.description ?? '',
    keywords: [
        t.name.toLowerCase(),
        ...(ALIASES[t.designation] ?? []),
        t.designation,
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
    return best;
}

export function filterSlashCommands(
    rawQuery: string,
    recentDesignations: readonly string[] = [],
    limit = SLASH_COMMANDS.length,
): SlashCommand[] {
    const q = rawQuery.trim().toLowerCase().replace(/^\//, '').trim();
    const scored: Array<{ cmd: SlashCommand; score: number }> = [];
    for (const cmd of SLASH_COMMANDS) {
        let score: number;
        if (q) {
            score = commandScore(cmd, q);
            const idx = recentDesignations.indexOf(cmd.designation);
            if (idx >= 0 && score > 0) score += Math.max(0, 40 - idx);
        } else {
            const idx = recentDesignations.indexOf(cmd.designation);
            score = idx >= 0 ? recentDesignations.length - idx + 1 : 0;
        }
        if (!q || score > 0) {
            scored.push({ cmd, score });
        }
    }
    scored.sort((a, b) => b.score - a.score || a.cmd.name.localeCompare(b.cmd.name));
    return scored.slice(0, limit).map((s) => s.cmd);
}