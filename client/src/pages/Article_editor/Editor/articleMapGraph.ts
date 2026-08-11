import type { ArticleBlockData, BlockDataValue } from '../model';
import type { BlockData, LinkData } from '../../../widgets/KnowledgeMap/types/types';
import { getBlockTypeDef } from './blockTypes';

// ─────────────────────────────────────────────────────────────────────────────
// Граф структурных блоков статьи + классификация исхода.
// Клиентский порт api/tools/pattern_probe/prototype_outcome.py.
// Узлы = ArticleBlock (все типы T1..T57), связи = uuid-ссылки в data блоков.
// Каждому узлу сопоставляется outcome (success/fail/partial/neutral):
//   T57 (находка)    — из evidence-классификации (полярность + роль группы);
//   T14 (эксперимент) — из вердикта по counts находок;
//   T38 (утверждение) — из связывания claims ↔ находки (стемминг + домены);
//   T7  (гипотеза)    — из вердикта исследования;
//   остальные         — нейтральные.
// ─────────────────────────────────────────────────────────────────────────────

export type NodeOutcome = 'success' | 'fail' | 'partial' | 'neutral';

export const OUTCOME_COLORS: Record<NodeOutcome, number> = {
    success: 0x22c55e,
    fail: 0xef4444,
    partial: 0xf59e0b,
    neutral: 0x9ca3af,
};

export interface ArticleMapNode extends BlockData {
    blockType: number;
    order: number;
    label: string;
    outcome: NodeOutcome;
    outcomeLabel: string;
    data: Record<string, BlockDataValue>;
}

export interface ArticleMapLink extends LinkData {
    field?: string;
}

export interface ArticleMapGraph {
    nodes: ArticleMapNode[];
    links: ArticleMapLink[];
    studyVerdict: string;
}

// ── Константы раскладки ──────────────────────────────────────────────────────
const SPACING_X = 300;
const SPACING_Y = 120;
const PADDING = 60;
const BLOCK_WIDTH = 200;
const BLOCK_HEIGHT = 75;

// ── Значения полей ───────────────────────────────────────────────────────────
function sval(data: Record<string, BlockDataValue>, key: string): string {
    const v = data[key];
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    return '';
}

function nval(data: Record<string, BlockDataValue>, key: string): number | null {
    const v = data[key];
    if (typeof v === 'number') return v;
    if (typeof v === 'string' && v.trim() !== '') {
        const n = Number(v.replace(',', '.'));
        return Number.isFinite(n) ? n : null;
    }
    return null;
}

function firstString(data: Record<string, BlockDataValue>): string {
    for (const v of Object.values(data)) {
        if (typeof v === 'string' && v.trim()) return v.trim();
    }
    return '';
}

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

function collectUuids(value: BlockDataValue): string[] {
    if (typeof value !== 'string') return [];
    const out: string[] = [];
    const str = value;
    let m: RegExpExecArray | null;
    while ((m = UUID_RE.exec(str)) !== null) {
        out.push(m[0]);
    }
    return out;
}

function parseUuidList(raw: string): string[] {
    if (!raw) return [];
    try {
        const p = JSON.parse(raw);
        if (Array.isArray(p)) return p.map(String).map(s => s.trim()).filter(Boolean);
    } catch { /* not a JSON list */ }
    return [];
}

function isRecord(v: unknown): v is Record<string, unknown> {
    return typeof v === 'object' && v !== null;
}

function parsePairs(raw: string): Array<{ groupRef: string; interventionRef: string }> {
    if (!raw) return [];
    try {
        const p = JSON.parse(raw);
        if (Array.isArray(p)) {
            return p
                .filter((x): x is Record<string, unknown> => isRecord(x))
                .map(x => ({
                    groupRef: String(x.groupRef ?? '').trim(),
                    interventionRef: String(x.interventionRef ?? '').trim(),
                }));
        }
    } catch { /* not a JSON list */ }
    return [];
}

function typeNameOf(blockType: number): string {
    return getBlockTypeDef(blockType)?.name ?? `T${blockType}`;
}

// ── Подписи блоков (с разрешением uuid-ссылок и защитой от циклов) ──────────
function resolveRefLabel(
    data: Record<string, BlockDataValue>,
    key: string,
    blocksById: Map<string, ArticleBlockData>,
    seen: Set<string>,
): string {
    const raw = sval(data, key).trim();
    if (!raw) return '';
    const target = blocksById.get(raw);
    if (!target) return raw;
    return blockShortLabel(target, blocksById, seen);
}

function blockShortLabel(
    block: ArticleBlockData,
    blocksById: Map<string, ArticleBlockData>,
    seen?: Set<string>,
): string {
    const guard = seen ?? new Set<string>();
    if (guard.has(block.instanceId)) {
        return `(ссылка ${block.instanceId.slice(0, 8)}…)`;
    }
    guard.add(block.instanceId);
    const d = block.data;
    const lab = (refKey: string): string => resolveRefLabel(d, refKey, blocksById, guard);
    switch (block.blockType) {
        case 57: {
            const param = sval(d, 'parameter').trim();
            const dir = sval(d, 'direction').trim();
            const grp = lab('subjectRef');
            return [param, dir, grp].filter(Boolean).join(' · ') || '(находка)';
        }
        case 14:
            return sval(d, 'experimentName').trim() || '(эксперимент)';
        case 55:
            return sval(d, 'groupName').trim() || '(группа)';
        case 38:
            return [sval(d, 'claimSubject'), sval(d, 'claimPredicate'), sval(d, 'claimObject')]
                .map(x => x.trim()).filter(Boolean).join(' ') || '(утверждение)';
        case 7:
            return sval(d, 'hypothesis').trim() || '(гипотеза)';
        case 27: {
            const p = nval(d, 'pValue');
            return p !== null ? `p = ${p}` : '(p-value)';
        }
        case 23:
            return sval(d, 'term').trim() || '(определение)';
        case 56:
            return sval(d, 'stepName').trim() || '(шаг)';
        case 2:
        case 22:
        case 54: {
            const s = lab('subject');
            const p = sval(d, 'predicate').trim();
            const o = lab('object');
            return [s, p, o].filter(Boolean).join(' → ') || '(триплет)';
        }
        default:
            return firstString(d) || `(${typeNameOf(block.blockType)})`;
    }
}

// ── Полярность параметра ─────────────────────────────────────────────────────
const HARM_KEYWORDS = [
    'фиброз', 'fibrosis', 'fibrot', 'сенесцент', 'сенесценц', 'senescen',
    'sasp', 'p16', 'p21', 'cdkn', 'h2ax', 'dna damage', 'поврежд',
    'воспал', 'inflamm', 'infiltrat', 'липоатроф', 'lipoatroph', 'тревожн', 'anxi',
    'апоптоз', 'apoptos', 'атроф', 'atroph', 'стресс', 'stress',
    'смертн', 'mortal', 'летальн', 'lethal', 'beta-gal', 'beta-galactosidase',
    'кахекс', 'cachex', 'деградац', 'degradat', 'дисфункц', 'dysfunc',
    'инсулинорезистентн', 'insulin resist', 'ожирен', 'obes', 'снижение', 'decline',
    'потеря', 'loss', 'impair', 'нарушен', 'нарушение', 'infilt',
    'mcp-1', 'mcp1', 'c5b', 'mac', 'abc', 'aab', 'm1', 'провоспалительн',
];

const BENEFIT_KEYWORDS = [
    'функц', 'function', 'активн', 'activity', 'скорост', 'speed',
    'сила', 'strength', 'grip', 'ротарод', 'rotarod', 'координац', 'coordination',
    'баланс', 'balance', 'закрыт', 'заживлен', 'healing', 'wound', 'регенерац',
    'regenerat', 'пролиферац', 'proliferat', 'целостност', 'integrity', 'сохран',
    'maintenance', 'устойчив', 'resilien', 'резилентн', 'mtec', 'тимус', 'thym',
    'разнообраз', 'diversity', 'численн', 'count', 'количеств', 'метабол', 'metabol',
    'гомеостаз', 'homeostas', 'выживаем', 'survival', 'теплопродукц', 'термоген',
    'thermogen', 'потреблен', 'consumption', 'расход', 'физическ', 'долголет',
    'longevity', 'продолжительность жизни', 'репликативн', 'антиоксидантн',
    'antioxidant', 'expenditure', 'm2', 'ил-4', 'il4',
];

const STRONG_BENEFIT_KEYWORDS = [
    'противовоспалительн', 'противовоспал', 'анти-воспалительн', 'антивоспал',
    'anti-inflamm',
];

function polarityOf(parameter: string): string | null {
    const t = (parameter || '').toLowerCase();
    if (STRONG_BENEFIT_KEYWORDS.some(k => t.includes(k))) return 'benefit';
    if (HARM_KEYWORDS.some(k => t.includes(k))) return 'harm';
    if (BENEFIT_KEYWORDS.some(k => t.includes(k))) return 'benefit';
    return null;
}

// ── Вид животных ─────────────────────────────────────────────────────────────
const SPECIES_MARKERS: Array<[string, string]> = [
    ['acomys russatus', 'russatus'],
    ['russatus', 'russatus'],
    ['spiny', 'russatus'],
    ['dimidiatus', 'dimidiatus'],
    ['c57bl', 'musculus'],
    ['musculus', 'musculus'],
    ['mus', 'musculus'],
    ['mouse', 'musculus'],
    ['мышь', 'musculus'],
];

function detectSpecies(text: string | null | undefined): string | null {
    const t = (text ?? '').toLowerCase();
    for (const [marker, sp] of SPECIES_MARKERS) {
        if (t.includes(marker)) return sp;
    }
    return null;
}

// ── Роль группы ──────────────────────────────────────────────────────────────
function groupRole(purpose: string | null, species: string | null, label: string): string {
    const t = (purpose ?? '').toLowerCase();
    const lab = (label ?? '').toLowerCase();
    if (['резистентн', 'основная группа'].some(k => t.includes(k))) return 'resilient_aged';
    if (['возрастн', 'aged control'].some(k => t.includes(k))) return 'aged_other';
    if (['baseline', 'молод', 'контроль молод'].some(k => t.includes(k))) return 'young';
    if (['контроль', 'интервенц', 'intervention', 'control'].some(k => t.includes(k))) return 'intervention';
    if (lab.includes('aged') || lab.includes('возраст') || lab.includes('старен')) {
        return species === 'dimidiatus' || species === 'musculus' ? 'aged_other' : 'resilient_aged';
    }
    if (lab.includes('young') || lab.includes('молод') || lab.includes('baseline')) return 'young';
    return 'unknown';
}

// ── Значимость ───────────────────────────────────────────────────────────────
function isSignificant(sig: string | null, pvalue: number | null): boolean {
    const t = (sig ?? '').toLowerCase();
    if (t && (
        t.includes('non-significant') || t === 'trend' || t.includes('ns')
        || t.includes('не значим') || t.includes('недостоверн')
        || t.includes('не показа') || t.includes('не выявлено')
    )) {
        return false;
    }
    if (pvalue !== null) return pvalue < 0.05;
    return true;
}

// ── Стеммер / токены / домены (для claims) ───────────────────────────────────
const STOPWORDS = new Set([
    'в', 'и', 'на', 'с', 'по', 'для', 'при', 'у', 'к', 'от', 'о', 'из', 'за', 'во',
    'не', 'что', 'это', 'как', 'а', 'или', 'же', 'до', 'после', 'между', 'the', 'of',
    'and', 'in', 'with', 'to', 'for', 'on', 'vs', 'et', 'al', 'age', 'aged', 'y',
]);

const RU_SUFFIXES = [
    'ами', 'ыми', 'ие', 'ии', 'ья', 'ью', 'ия', 'ах', 'ам', 'ях',
    'ях', 'ом', 'им', 'ов', 'ев', 'ой', 'ый', 'ий', 'ое', 'ого',
    'его', 'их', 'ых', 'ую', 'ая', 'ем', 'ей', 'ин', 'ну', 'но', 'на',
];

const EN_SUFFIXES = ['ing', 'tion', 'ed', 'es', 'ly', 's'];

function normTokens(text: string): string[] {
    const toks: string[] = (text || '').toLowerCase().match(/[а-яёa-z0-9]+/g) || [];
    return toks.filter(t => !STOPWORDS.has(t) && t.length > 1);
}

function stem(word: string): string {
    let w = word.toLowerCase();
    let applied = false;
    for (const suf of RU_SUFFIXES) {
        if (w.length - suf.length >= 3 && w.endsWith(suf)) {
            w = w.slice(0, -suf.length);
            applied = true;
            break;
        }
    }
    if (!applied) {
        for (const suf of EN_SUFFIXES) {
            if (w.length - suf.length >= 3 && w.endsWith(suf)) {
                w = w.slice(0, -suf.length);
                break;
            }
        }
    }
    return w;
}

function stemTokens(text: string): string[] {
    return normTokens(text).map(stem).filter(t => t.length >= 3);
}

const DOMAIN_KEYWORDS: Record<string, string[]> = {
    thymus: ['тимус', 'mtec', 'тимическ', 'thym'],
    liver: ['печен', 'hepato', 'печеночн'],
    muscle: ['мышц', 'gastrocnemius', 'muscle', 'скелет'],
    adipose: ['жиров', 'vat', 'sat ', 'adipocy', 'висцеральн'],
    behavior: ['open field', 'rearing', 't-maze', 'циркад', 'тревожн', 'двигательн',
        'поведенч', 'ротарод', 'rotarod', 'сила захвата', 'координац', 'баланс',
        'латентность', 'дистанция', 'центр'],
    inflammation: ['воспал', 'цитокин', 'sasp', 'inflamm', 'интерлейкин', 'il-1', 'il-2',
        'il-4', 'il-6', 'tnf', 'nf-kb', 'infiltr', 'маркер'],
    senescence: ['сенесцент', 'senescen', 'p16', 'p21', 'cdkn', 'h2ax', 'клеточное старение'],
    transcription: ['транскрипт', 'rna', 'деген', 'degen', 'deg', 'экспресси', 'экспрессии',
        'экспрессия', 'ген', 'генов'],
    proteostasis: ['автофаг', 'cma', 'аугофаг', 'протеостаз', 'агрег'],
    regeneration: ['регенерац', 'заживл', 'закрыт ушн', 'репаративн'],
    serum: ['сыворотк', 'serum'],
    fibrosis: ['фиброз', 'fibros'],
    proliferation: ['пролиферац', 'proliferat'],
};

function domainOf(text: string): Set<string> {
    const t = (text || '').toLowerCase();
    const out = new Set<string>();
    for (const [d, keys] of Object.entries(DOMAIN_KEYWORDS)) {
        if (keys.some(k => t.includes(k))) out.add(d);
    }
    return out;
}

function intersectionSize(a: string[], b: string[]): number {
    const setB = new Set(b);
    let n = 0;
    for (const x of a) if (setB.has(x)) n++;
    return n;
}

function intersects(a: Set<string>, b: Set<string>): boolean {
    for (const x of a) if (b.has(x)) return true;
    return false;
}

// ── Внутренние модели ────────────────────────────────────────────────────────
interface FindingRec {
    uid: string;
    parameter: string;
    direction: string;
    groupLabel: string;
    comparison: string | null;
    significance: string | null;
    pvalue: number | null;
    evidence: string;
    polarity: string | null;
    role: string;
    experiment: string | null;
}

interface ExpRec {
    name: string;
    expType: string | null;
    findings: string[];
    control: string[];
    exp: string[];
    counts: Record<string, number>;
    verdict: string;
}

interface ClaimRec {
    key: string;
    subject: string;
    predicate: string;
    object: string;
    negated: boolean;
    confidence: number;
    outcome: string;
    domain: Set<string>;
    generic: boolean;
    experimentLink: string | null;
    linked: Array<{ uid: string; score: number }>;
}

// ── Классификация находки ────────────────────────────────────────────────────
function classifyFinding(f: FindingRec, purposeByGroup: Map<string, string>): void {
    f.polarity = polarityOf(f.parameter);
    const species = detectSpecies(f.groupLabel);
    const purpose = purposeByGroup.get(f.groupLabel) ?? null;
    f.role = groupRole(purpose, species, f.groupLabel);
    const sig = isSignificant(f.significance, f.pvalue);
    const cmpSpecies = detectSpecies(f.comparison);

    let favorable: Set<string> | null = null;
    if (f.polarity === 'harm') favorable = new Set(['понижено в']);
    else if (f.polarity === 'benefit') favorable = new Set(['повышено в']);

    if (f.direction === 'без изменений в') {
        f.evidence = 'support';
        return;
    }
    if (f.role === 'intervention') {
        if (!favorable) { f.evidence = 'unknown'; return; }
        if (favorable.has(f.direction)) f.evidence = sig ? 'support' : 'weak_support';
        else f.evidence = sig ? 'contradict' : 'weak_contradict';
        return;
    }
    if (f.role === 'resilient_aged') {
        const vsYoung = cmpSpecies === species
            && (!f.comparison || ['young', 'молод', 'baseline'].some(k => (f.comparison ?? '').toLowerCase().includes(k)));
        const vsOtherSpecies = Boolean(cmpSpecies) && cmpSpecies !== species;
        if (!vsYoung && !vsOtherSpecies) {
            // нет явного сравнения — опираемся на назначение группы
            if (!favorable) { f.evidence = 'unknown'; return; }
            if (favorable.has(f.direction)) f.evidence = sig ? 'support' : 'weak_support';
            else f.evidence = sig ? 'contradict' : 'weak_contradict';
            return;
        }
        if (!favorable) { f.evidence = 'unknown'; return; }
        if (favorable.has(f.direction)) f.evidence = sig ? 'support' : 'weak_support';
        else f.evidence = sig ? 'contradict' : 'weak_contradict';
        return;
    }
    if (f.role === 'aged_other') {
        if (f.polarity === 'benefit' && f.direction === 'понижено в') f.evidence = 'context_support';
        else if (f.polarity === 'harm' && f.direction === 'повышено в') f.evidence = 'context_support';
        else f.evidence = 'context';
        return;
    }
    if (f.role === 'young') {
        f.evidence = 'context';
        return;
    }
    f.evidence = 'unknown';
}

// ── Связывание claims ↔ находки ──────────────────────────────────────────────
function linkClaims(
    claims: ClaimRec[],
    findings: FindingRec[],
    findingByUid: Map<string, FindingRec>,
    experiments: Map<string, ExpRec>,
): void {
    for (const c of claims) {
        const cText = `${c.subject} ${c.object}`;
        c.domain = domainOf(cText);
        c.generic = c.domain.size === 0;
        const cTokens = stemTokens(cText);
        for (const f of findings) {
            const pToks = stemTokens(f.parameter);
            const expToks = stemTokens(f.experiment ?? '');
            const paramOverlap = intersectionSize(cTokens, pToks);
            const expOverlap = intersectionSize(cTokens, expToks);
            if (paramOverlap >= 1 || expOverlap >= 2) {
                c.linked.push({ uid: f.uid, score: Math.round((paramOverlap + 0.3 * expOverlap) * 100) / 100 });
            }
        }
        c.linked.sort((a, b) => b.score - a.score);

        const expCounts = new Map<string, number>();
        for (const { uid } of c.linked) {
            const f = findingByUid.get(uid);
            if (!f) continue;
            if (f.experiment && ['support', 'weak_support', 'context_support', 'contradict', 'weak_contradict'].includes(f.evidence)) {
                expCounts.set(f.experiment, (expCounts.get(f.experiment) ?? 0) + 1);
            }
        }
        if (expCounts.size > 0) {
            let bestName: string | null = null;
            let bestCount = -1;
            for (const [name, cnt] of expCounts) {
                if (cnt > bestCount) {
                    bestCount = cnt;
                    bestName = name;
                }
            }
            c.experimentLink = bestName;
        } else {
            let bestName: string | null = null;
            let bestScore = 0;
            for (const name of experiments.keys()) {
                const ov = intersectionSize(cTokens, stemTokens(name));
                if (ov >= 2 && ov > bestScore) {
                    bestScore = ov;
                    bestName = name;
                }
            }
            c.experimentLink = bestName;
        }
    }
}

// ── Вердикты ──────────────────────────────────────────────────────────────────
function verdictFromCounts(counts: Record<string, number>): string {
    const sup = (counts.support ?? 0) + (counts.weak_support ?? 0) * 0.6;
    const con = (counts.contradict ?? 0) + (counts.weak_contradict ?? 0) * 0.6;
    if (con > 0 && con >= sup) return 'не подтвердилась';
    if (sup > 0 && con === 0) return 'подтвердилась';
    if (sup > 0 && con > 0) return 'частично подтвердилась';
    return 'недостаточно данных';
}

function claimVerdict(
    c: ClaimRec,
    findingByUid: Map<string, FindingRec>,
    experiments: Map<string, ExpRec>,
    studyOk: boolean,
): string {
    const direct: FindingRec[] = [];
    for (const { uid } of c.linked) {
        const f = findingByUid.get(uid);
        if (!f) continue;
        const pOverlap = intersectionSize(stemTokens(`${c.subject} ${c.object}`), stemTokens(f.parameter));
        if (pOverlap < 1) continue;
        if (c.generic || intersects(c.domain, domainOf(f.parameter))) direct.push(f);
    }
    const eSup = direct.filter(f => f.evidence === 'support' || f.evidence === 'context_support').length;
    const eCon = direct.filter(f => f.evidence === 'contradict' || f.evidence === 'weak_contradict').length;
    if (direct.length > 0 && (eSup > 0 || eCon > 0)) {
        if (eCon >= eSup) return 'contradicted';
        if (eCon === 0) return 'supported';
        return 'partially supported';
    }
    if (c.experimentLink) {
        const exp = experiments.get(c.experimentLink);
        if (exp) {
            if (exp.verdict === 'подтвердилась') return 'supported (по эксперименту)';
            if (exp.verdict === 'не подтвердилась') return 'contradicted (по эксперименту)';
            if (exp.verdict === 'частично подтвердилась') return 'partially supported (по эксперименту)';
        }
    }
    if (c.generic && studyOk) return 'supported (агрегация исследования)';
    return 'unverified';
}

function studyVerdictText(experiments: ExpRec[], claims: ClaimRec[]): string {
    const claimsSupported = claims.filter(c => c.outcome.startsWith('supported')).length;
    const claimsContradicted = claims.filter(c => c.outcome.startsWith('contradicted')).length;
    if (claimsContradicted && claimsContradicted >= claimsSupported) return 'гипотеза не подтвердилась';
    if (claimsSupported && !claimsContradicted) return 'гипотеза подтвердилась';
    if (claimsSupported) return 'гипотеза частично подтвердилась';
    return 'недостаточно данных для вывода';
}

// ── Маппинг на outcome узла ───────────────────────────────────────────────────
const EVIDENCE_LABELS: Record<string, string> = {
    support: 'поддержано',
    weak_support: 'слабая поддержка',
    context_support: 'контекстно поддержано',
    context: 'контекст',
    contradict: 'противоречит',
    weak_contradict: 'слабое противоречие',
    unknown: 'не определено',
};

function evidenceToOutcome(ev: string): NodeOutcome {
    if (ev === 'support' || ev === 'weak_support' || ev === 'context_support') return 'success';
    if (ev === 'contradict' || ev === 'weak_contradict') return 'fail';
    return 'neutral';
}

function verdictToOutcome(v: string): NodeOutcome {
    if (v === 'подтвердилась') return 'success';
    if (v === 'частично подтвердилась') return 'partial';
    if (v === 'не подтвердилась') return 'fail';
    return 'neutral';
}

function claimOutcomeToNode(o: string): NodeOutcome {
    if (o.startsWith('supported')) return 'success';
    if (o.startsWith('contradicted')) return 'fail';
    if (o.startsWith('partially')) return 'partial';
    return 'neutral';
}

// ── Сборка графа ─────────────────────────────────────────────────────────────
export function buildArticleMapGraph(blocks: ArticleBlockData[]): ArticleMapGraph {
    const sorted = [...blocks].sort((a, b) => a.order - b.order);
    const byId = new Map(sorted.map(b => [b.instanceId, b] as const));

    // Реестры групп
    const groups = new Map<string, { purpose: string; n: string; species: string | null }>();
    const findingUidToParam = new Map<string, string>();
    for (const b of sorted) {
        if (b.blockType === 55) {
            const name = sval(b.data, 'groupName').trim();
            if (!name) continue;
            const speciesRef = sval(b.data, 'speciesRef').trim();
            const speciesBlock = speciesRef ? byId.get(speciesRef) : undefined;
            const speciesText = speciesBlock ? sval(speciesBlock.data, 'species').trim() || firstString(speciesBlock.data) : '';
            groups.set(name, {
                purpose: sval(b.data, 'purpose').trim(),
                n: sval(b.data, 'n').trim(),
                species: detectSpecies(speciesText),
            });
        }
        if (b.blockType === 57) {
            const param = sval(b.data, 'parameter').trim();
            if (param) findingUidToParam.set(b.instanceId, param);
        }
    }

    // Находки (T57)
    const findings: FindingRec[] = [];
    const findingByUid = new Map<string, FindingRec>();
    const directionMap: Record<string, string> = {
        'повышено': 'повышено в',
        'понижено': 'понижено в',
        'без изменений': 'без изменений в',
        'тренд': 'тренд в',
        'увеличено': 'повышено в',
        'снижено': 'понижено в',
    };
    for (const b of sorted) {
        if (b.blockType !== 57) continue;
        const param = sval(b.data, 'parameter').trim();
        const direction = directionMap[sval(b.data, 'direction').trim()] ?? '';
        if (!param || !direction) continue;
        let pvalue: number | null = null;
        const pvRef = sval(b.data, 'pValue').trim();
        if (pvRef) {
            const p27 = byId.get(pvRef);
            if (p27 && p27.blockType === 27) {
                const pv = nval(p27.data, 'pValue');
                if (pv !== null) pvalue = pv;
            }
        }
        const f: FindingRec = {
            uid: b.instanceId,
            parameter: param,
            direction,
            groupLabel: resolveRefLabel(b.data, 'subjectRef', byId, new Set([b.instanceId])),
            comparison: resolveRefLabel(b.data, 'comparisonRef', byId, new Set([b.instanceId])) || null,
            significance: sval(b.data, 'significance').trim() || null,
            pvalue,
            evidence: 'unknown',
            polarity: null,
            role: 'unknown',
            experiment: null,
        };
        findings.push(f);
        findingByUid.set(b.instanceId, f);
    }

    // Эксперименты (T14)
    const experiments = new Map<string, ExpRec>();
    const expByFindingUid = new Map<string, string>();
    for (const b of sorted) {
        if (b.blockType !== 14) continue;
        const name = sval(b.data, 'experimentName').trim();
        if (!name) continue;
        const exp: ExpRec = {
            name,
            expType: sval(b.data, 'experimentType').trim() || null,
            findings: parseUuidList(sval(b.data, 'findings')),
            control: [],
            exp: [],
            counts: {},
            verdict: 'недостаточно данных',
        };
        for (const p of parsePairs(sval(b.data, 'controlPairs'))) if (p.groupRef) exp.control.push(p.groupRef);
        for (const p of parsePairs(sval(b.data, 'experimentalPairs'))) if (p.groupRef) exp.exp.push(p.groupRef);
        experiments.set(name, exp);
        for (const fuid of exp.findings) expByFindingUid.set(fuid, name);
    }
    for (const f of findings) f.experiment = expByFindingUid.get(f.uid) ?? null;

    // Claims (T38) и гипотеза (T7)
    const claims: ClaimRec[] = [];
    const claimByKey = new Map<string, ClaimRec>();
    for (const b of sorted) {
        if (b.blockType !== 38) continue;
        const subj = sval(b.data, 'claimSubject').trim();
        const pred = sval(b.data, 'claimPredicate').trim();
        const obj = sval(b.data, 'claimObject').trim();
        if (!subj || !pred || !obj) continue;
        const neg = b.data.isNegated === true || b.data.isNegated === 'true' || b.data.isNegated === '1' || b.data.isNegated === 'on';
        const notes = sval(b.data, 'confidenceNotes').trim();
        const predicate = (neg ? 'не ' : '') + pred;
        const rec: ClaimRec = {
            key: `${subj}|${predicate}|${obj}`,
            subject: subj,
            predicate,
            object: obj,
            negated: neg,
            confidence: notes ? 0.8 : 1.0,
            outcome: 'unverified',
            domain: new Set(),
            generic: false,
            experimentLink: null,
            linked: [],
        };
        claims.push(rec);
        claimByKey.set(rec.key, rec);
    }
    let hypothesisBlock: ArticleBlockData | null = null;
    for (const b of sorted) {
        if (b.blockType === 7) {
            hypothesisBlock = b;
            break;
        }
    }

    // Классификация находок
    const purposeByGroup = new Map<string, string>();
    for (const [name, g] of groups) purposeByGroup.set(name, g.purpose);
    for (const f of findings) classifyFinding(f, purposeByGroup);

    // Вердикты экспериментов
    const expCounts = new Map<string, Record<string, number>>();
    for (const f of findings) {
        const key = f.experiment ?? '(без эксперимента)';
        const d = expCounts.get(key) ?? {};
        d[f.evidence] = (d[f.evidence] ?? 0) + 1;
        expCounts.set(key, d);
    }
    for (const [name, counts] of expCounts) {
        let exp = experiments.get(name);
        if (!exp) {
            exp = { name, expType: null, findings: [], control: [], exp: [], counts: {}, verdict: 'недостаточно данных' };
            experiments.set(name, exp);
        }
        exp.counts = counts;
        exp.verdict = verdictFromCounts(counts);
    }

    // Связывание claims и их вердикты
    linkClaims(claims, findings, findingByUid, experiments);
    const expList = [...experiments.values()];
    const studyOk = expList.filter(e => e.verdict === 'подтвердилась').length
        > expList.filter(e => e.verdict === 'не подтвердилась').length;
    for (const c of claims) c.outcome = claimVerdict(c, findingByUid, experiments, studyOk);
    const verdict = studyVerdictText(expList, claims);

    // Связи (uuid-ссылки в data блоков)
    const links: ArticleMapLink[] = [];
    const seen = new Set<string>();
    for (const b of sorted) {
        for (const [field, value] of Object.entries(b.data)) {
            for (const target of collectUuids(value)) {
                if (target === b.instanceId) continue;
                if (!byId.has(target)) continue;
                const key = `${b.instanceId}::${target}`;
                if (seen.has(key)) continue;
                seen.add(key);
                links.push({ id: key, source_id: b.instanceId, target_id: target, field });
            }
        }
    }

    // Раскладка (по колонкам = глубина от корней)
    const inDeg = new Map<string, number>();
    const outN = new Map<string, string[]>();
    for (const n of sorted) {
        inDeg.set(n.instanceId, 0);
        outN.set(n.instanceId, []);
    }
    for (const l of links) {
        if (inDeg.has(l.source_id) && inDeg.has(l.target_id)) {
            outN.get(l.source_id)!.push(l.target_id);
            inDeg.set(l.target_id, (inDeg.get(l.target_id) ?? 0) + 1);
        }
    }
    const column = new Map<string, number>();
    const remaining = new Map(inDeg);
    const queue: string[] = [];
    for (const n of sorted) {
        if ((inDeg.get(n.instanceId) ?? 0) === 0) {
            queue.push(n.instanceId);
            column.set(n.instanceId, 0);
        }
    }
    while (queue.length > 0) {
        const cur = queue.shift()!;
        for (const nb of outN.get(cur) ?? []) {
            column.set(nb, Math.max(column.get(nb) ?? 0, (column.get(cur) ?? 0) + 1));
            remaining.set(nb, (remaining.get(nb) ?? 0) - 1);
            if ((remaining.get(nb) ?? 0) === 0) queue.push(nb);
        }
    }
    for (const n of sorted) if (!column.has(n.instanceId)) column.set(n.instanceId, 0);

    const rowInColumn = new Map<string, number>();
    const colCount = new Map<number, number>();
    for (const n of sorted) {
        const col = column.get(n.instanceId) ?? 0;
        rowInColumn.set(n.instanceId, colCount.get(col) ?? 0);
        colCount.set(col, (colCount.get(col) ?? 0) + 1);
    }

    const nodes: ArticleMapNode[] = sorted.map(b => {
        const col = column.get(b.instanceId) ?? 0;
        const row = rowInColumn.get(b.instanceId) ?? 0;
        const outcome = outcomeForBlock(b, findingByUid, experiments, claimByKey, hypothesisBlock, verdict);
        const label = blockShortLabel(b, byId);
        return {
            id: b.instanceId,
            blockType: b.blockType,
            order: b.order,
            label,
            outcome: outcome.outcome,
            outcomeLabel: outcome.label,
            data: b.data,
            title: label,
            x: col * SPACING_X + PADDING + BLOCK_WIDTH / 2,
            y: row * SPACING_Y + PADDING + BLOCK_HEIGHT / 2,
            layer: col,
            level: 0,
        };
    });

    return { nodes, links, studyVerdict: verdict };
}

function outcomeForBlock(
    block: ArticleBlockData,
    findingByUid: Map<string, FindingRec>,
    experiments: Map<string, ExpRec>,
    claimByKey: Map<string, ClaimRec>,
    hypothesisBlock: ArticleBlockData | null,
    verdict: string,
): { outcome: NodeOutcome; label: string } {
    switch (block.blockType) {
        case 57: {
            const f = findingByUid.get(block.instanceId);
            if (!f) break;
            return { outcome: evidenceToOutcome(f.evidence), label: EVIDENCE_LABELS[f.evidence] ?? f.evidence };
        }
        case 14: {
            const name = sval(block.data, 'experimentName').trim();
            const exp = name ? experiments.get(name) : undefined;
            if (!exp) break;
            return { outcome: verdictToOutcome(exp.verdict), label: exp.verdict };
        }
        case 38: {
            const subj = sval(block.data, 'claimSubject').trim();
            const pred = sval(block.data, 'claimPredicate').trim();
            const obj = sval(block.data, 'claimObject').trim();
            const neg = block.data.isNegated === true || block.data.isNegated === 'true' || block.data.isNegated === '1' || block.data.isNegated === 'on';
            const predicate = (neg ? 'не ' : '') + pred;
            const c = claimByKey.get(`${subj}|${predicate}|${obj}`);
            if (!c) break;
            return { outcome: claimOutcomeToNode(c.outcome), label: c.outcome };
        }
        case 7:
            if (hypothesisBlock && block.instanceId === hypothesisBlock.instanceId) {
                const outcome: NodeOutcome = verdict.includes('не подтвердилась') ? 'fail'
                    : verdict.includes('частично') ? 'partial'
                        : verdict.includes('подтвердилась') ? 'success' : 'neutral';
                return { outcome, label: verdict };
            }
            break;
        default:
            break;
    }
    return { outcome: 'neutral', label: '' };
}

// ── Подграф подсветки при hover (BFS по неориентированным рёбрам) ────────────
export function collectSubgraph(
    graph: ArticleMapGraph,
    startId: string,
    maxDepth = 2,
): { nodes: Set<string>; links: Set<string> } {
    const adj = new Map<string, string[]>();
    const linkByPair = new Map<string, string>();
    for (const l of graph.links) {
        const a = adj.get(l.source_id) ?? [];
        a.push(l.target_id);
        adj.set(l.source_id, a);
        const b = adj.get(l.target_id) ?? [];
        b.push(l.source_id);
        adj.set(l.target_id, b);
        linkByPair.set(`${l.source_id}::${l.target_id}`, l.id);
        linkByPair.set(`${l.target_id}::${l.source_id}`, l.id);
    }
    const nodes = new Set<string>([startId]);
    const links = new Set<string>();
    let frontier = [startId];
    for (let depth = 0; depth < maxDepth && frontier.length > 0; depth++) {
        const next: string[] = [];
        for (const cur of frontier) {
            for (const nb of adj.get(cur) ?? []) {
                const lid = linkByPair.get(`${cur}::${nb}`);
                if (lid) links.add(lid);
                if (!nodes.has(nb)) {
                    nodes.add(nb);
                    next.push(nb);
                }
            }
        }
        frontier = next;
    }
    return { nodes, links };
}
