import type { ArticleBlockData, BlockDataValue, BlockFieldDef, BlockTypeDef, DerivedTriplet, KnowledgeStatement } from '../model';
import { getBlockTypeDef } from './blockTypes';

export function uuid8Str(): string {
    const now = Date.now();
    const ts_us = BigInt(now) * 1000n + BigInt(Math.floor(Math.random() * 1000));
    const rand = new Uint8Array(7);
    crypto.getRandomValues(rand);
    const b = new Uint8Array(16);
    for (let i = 0; i < 8; i++) b[i] = Number((ts_us >> BigInt(56 - i * 8)) & 0xFFn);
    b[6] = (b[6] & 0x0F) | 0x80;
    b[8] = 0x80 | (rand[0] & 0x3F);
    b[9] = rand[0];
    for (let i = 0; i < 6; i++) b[10 + i] = rand[1 + i];
    const hex = Array.from(b).map(n => n.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function fact(
    subject: string,
    predicate: string,
    object: string,
    sourceBlockId: string,
    sourceBlockType: number,
    confidence = 1.0,
): DerivedTriplet {
    return {
        id: uuid8Str(),
        subject_text: subject.trim(),
        predicate: predicate.trim(),
        object_text: object.trim(),
        sourceBlockId,
        sourceBlockType,
        type: 'FACT',
        subject_type: 'concept',
        object_type: 'concept',
        confidence,
    };
}

function meta(
    subject: string,
    predicate: string,
    object: string,
    sourceBlockId: string,
    sourceBlockType: number,
): DerivedTriplet {
    return {
        id: uuid8Str(),
        subject_text: subject.trim(),
        predicate: predicate.trim(),
        object_text: object.trim(),
        sourceBlockId,
        sourceBlockType,
        type: 'META',
        subject_type: 'concept',
        object_type: 'concept',
        confidence: 1.0,
    };
}

function splitLines(val: string | boolean): string[] {
    if (typeof val !== 'string') return [];
    return val.split('\n').map((s) => s.trim()).filter(Boolean);
}

function kvPairs(val: string | boolean | number | Record<string, string> | null): Array<{ key: string; value: string }> {
    if (val && typeof val === 'object') {
        return Object.entries(val).map(([key, value]) => ({ key, value: String(value) }));
    }
    if (typeof val !== 'string') return [];
    return val.split('\n').map((s) => s.trim()).filter(Boolean).map((line) => {
        const idx = line.indexOf(':');
        if (idx < 0) return { key: line, value: '' };
        return { key: line.slice(0, idx).trim(), value: line.slice(idx + 1).trim() };
    });
}

function str(val: Record<string, BlockDataValue>, key: string): string {
    const v = val[key];
    if (typeof v === 'string') return v.trim();
    if (typeof v === 'number' && !Number.isNaN(v)) return String(v);
    return '';
}

function bool(val: Record<string, BlockDataValue>, key: string): boolean {
    return val[key] === true || val[key] === 'true';
}

function findNameField(def: BlockTypeDef, data: Record<string, BlockDataValue>): BlockFieldDef | undefined {
    const nonEmptyText = (f: BlockFieldDef): boolean =>
        typeof data[f.key] === 'string' && (data[f.key] as string).trim();
    for (const k of ['name', 'title', 'subject', 'term']) {
        const f = def.fields.find((f) => f.key === k && nonEmptyText(f));
        if (f) return f;
    }
    return def.fields.find(nonEmptyText);
}

// ═══════════════════════════════════════════════════════════════════
// Конвертеры для каждого типа блока
// ═══════════════════════════════════════════════════════════════════

type ConverterFn = (block: ArticleBlockData) => DerivedTriplet[];

const converters: Record<number, ConverterFn> = {
    // T1: Метаданные
    1: (b) => {
        const triplets: DerivedTriplet[] = [];
        const doi = str(b.data, 'doi');
        const title = str(b.data, 'title');
        const authors = str(b.data, 'authors');
        if (doi) triplets.push(fact('Статья', 'DOI', doi, b.instanceId, b.blockType));
        if (title) triplets.push(fact('Статья', 'название статьи', title, b.instanceId, b.blockType));
        if (authors) {
            const authorList = authors.split(/[\n,;]/).map((s: string) => s.trim()).filter(Boolean);
            for (const author of authorList) {
                triplets.push(fact('Статья', 'авторы', author, b.instanceId, b.blockType));
            }
        }
        return triplets;
    },

    // T2: Цель исследования (s/p/o триплет)
    2: (b) => {
        const s = str(b.data, 'subject');
        const p = str(b.data, 'predicate');
        const o = str(b.data, 'object');
        if (!s && !p && !o) {
            const legacy = str(b.data, 'objective');
            return legacy ? [fact('Исследование', 'цель', legacy, b.instanceId, b.blockType)] : [];
        }
        return (s && p && o) ? [fact(s, p, o, b.instanceId, b.blockType)] : [];
    },

    // T3: Свободный текст → 0 triplets
    3: () => [],

    // T4: Прямой триплет
    4: (b) => {
        const s = str(b.data, 'subject');
        const p = str(b.data, 'predicate');
        const o = str(b.data, 'object');
        return (s && p && o) ? [fact(s, p, o, b.instanceId, b.blockType)] : [];
    },

    // T5: Первичная конечная точка
    5: (b) => {
        const v = str(b.data, 'endpoint');
        return v ? [fact('Исследование', 'первая конечная точка', v, b.instanceId, b.blockType)] : [];
    },

    // T6: Вторичные конечные точки
    6: (b) => {
        const lines = splitLines(b.data.endpoints);
        return lines.map((ep) => fact('Исследование', 'вторичная конечная точка', ep, b.instanceId, b.blockType));
    },

    // T7: Гипотеза
    7: (b) => {
        const h = str(b.data, 'hypothesis');
        if (!h) return [];
        const triplets = [fact('Исследование', 'гипотеза', h, b.instanceId, b.blockType)];
        const reason = str(b.data, 'disproofExplanation');
        if (reason) triplets.push(meta('Гипотеза: ' + h, 'требует опровежения потому что', reason, b.instanceId, b.blockType));
        return triplets;
    },

    // T8: Предпосылки
    8: (b) => {
        return splitLines(b.data.prerequisites).map((p) =>
            fact(p, 'предпосылка', 'Исследование', b.instanceId, b.blockType)
        );
    },

    // T9: Ожидания
    9: (b) => {
        const v = str(b.data, 'expectations');
        return v ? [fact('Исследование', 'ожидает', v, b.instanceId, b.blockType)] : [];
    },

    // T10: Знания-зависимости
    10: (b) => {
        return splitLines(b.data.knowledgeDeps).map((dep) =>
            fact('Исследование', 'опирается на', dep, b.instanceId, b.blockType)
        );
    },

    // T11: Дизайн исследования
    11: (b) => {
        const triplets: DerivedTriplet[] = [];
        const studyType = str(b.data, 'studyType');
        if (studyType) triplets.push(fact('Исследование', 'тип', studyType, b.instanceId, b.blockType));
        if (bool(b.data, 'randomization')) triplets.push(fact('Исследование', 'рандомизировано', 'да', b.instanceId, b.blockType));
        if (bool(b.data, 'blinding')) triplets.push(fact('Исследование', 'ослеплено', 'да', b.instanceId, b.blockType));
        return triplets;
    },

    // T12: Материалы
    12: (b) => {
        const v = str(b.data, 'materials');
        return v ? [fact('Исследование', 'материалы', v, b.instanceId, b.blockType)] : [];
    },

    // T13: Методы
    13: (b) => {
        const triplets: DerivedTriplet[] = [];
        const methods = str(b.data, 'methods');
        if (methods) triplets.push(fact('Исследование', 'методы', methods, b.instanceId, b.blockType));
        const meas = str(b.data, 'measurementMethods');
        if (meas) triplets.push(fact('Исследование', 'методы измерения', meas, b.instanceId, b.blockType));
        return triplets;
    },

    // T14: Эксперимент
    14: (b) => {
        const triplets: DerivedTriplet[] = [];
        const name = str(b.data, 'experimentName');
        const expType = str(b.data, 'experimentType');
        const outcomes = str(b.data, 'outcomes');
        const steps = str(b.data, 'steps');
        const duration = str(b.data, 'duration');
        const expKey = name || `Эксперимент (${expType || 'без названия'})`;

        if (name) triplets.push(fact('Исследование', 'эксперимент', name, b.instanceId, b.blockType));
        if (expType) triplets.push(fact(expKey, 'тип', expType, b.instanceId, b.blockType));
        if (outcomes) {
            const outcomeList = outcomes.split(/[\n,;]/).map((s: string) => s.trim()).filter(Boolean);
            for (const outcome of outcomeList) {
                triplets.push(fact(expKey, 'измеряемые показатели', outcome, b.instanceId, b.blockType));
            }
        }
        if (steps) {
            try {
                const stepList = JSON.parse(steps);
                if (Array.isArray(stepList)) {
                    for (const su of stepList) {
                        const stepUuid = typeof su === 'string' ? su.trim() : '';
                        if (stepUuid) triplets.push(fact(b.instanceId, 'шаг', stepUuid, b.instanceId, b.blockType));
                    }
                }
            } catch {}
        }
        const findings = str(b.data, 'findings');
        if (findings) {
            try {
                const findingList = JSON.parse(findings);
                if (Array.isArray(findingList)) {
                    for (const f of findingList) {
                        const findingUuid = typeof f === 'string' ? f.trim() : '';
                        if (findingUuid) triplets.push(fact(b.instanceId, 'результат', findingUuid, b.instanceId, b.blockType));
                    }
                }
            } catch {}
        }
        if (duration) triplets.push(fact(expKey, 'длительность', duration, b.instanceId, b.blockType));

        const makePairs = (raw: string, role: string) => {
            try {
                const pairs = JSON.parse(raw);
                if (!Array.isArray(pairs)) return;
                for (const pair of pairs) {
                    const g = typeof pair.groupRef === 'string' ? pair.groupRef.trim() : '';
                    const iv = typeof pair.interventionRef === 'string' ? pair.interventionRef.trim() : '';
                    if (g) {
                        triplets.push(fact(b.instanceId, role, g, b.instanceId, b.blockType));
                        if (iv) triplets.push(fact(g, 'получает', iv, b.instanceId, b.blockType));
                    }
                }
            } catch {}
        };

        makePairs(str(b.data, 'experimentalPairs'), 'экспериментальная группа');
        makePairs(str(b.data, 'controlPairs'), 'контрольная группа');

        return triplets;
    },

    // T15: Критерии включения/исключения
    15: (b) => {
        const triplets: DerivedTriplet[] = [];
        const inc = str(b.data, 'inclusionCriteria');
        if (inc) triplets.push(fact('Исследование', 'критерии включения', inc, b.instanceId, b.blockType));
        const exc = str(b.data, 'exclusionCriteria');
        if (exc) triplets.push(fact('Исследование', 'критерии исключения', exc, b.instanceId, b.blockType));
        return triplets;
    },

    // T16: Биологический механизм
    16: (b) => {
        const v = str(b.data, 'mechanism');
        return v ? [fact('Исследование', 'биологический механизм', v, b.instanceId, b.blockType)] : [];
    },

    // T17: Объект воздействия
    17: (b) => {
        const triplets: DerivedTriplet[] = [];
        const targets: Array<[string, string]> = [
            ['cell', 'клетка'],
            ['tissue', 'ткань'],
            ['organ', 'орган'],
            ['pathway', 'биологический путь'],
            ['substanceLevel', 'уровень вещества'],
        ];
        for (const [key, label] of targets) {
            const v = str(b.data, key);
            if (v) triplets.push(fact('Исследование', 'объект воздействия: ' + label, v, b.instanceId, b.blockType));
        }
        return triplets;
    },

    // T18: Интервенция
    18: (b) => {
        const triplets: DerivedTriplet[] = [];
        const intervention = str(b.data, 'intervention');
        if (intervention) triplets.push(fact('Исследование', 'интервенция', intervention, b.instanceId, b.blockType));
        const dosage = str(b.data, 'dosage');
        if (dosage) triplets.push(fact('Исследование', 'дозировка', dosage, b.instanceId, b.blockType));
        const regimen = str(b.data, 'dosageRegimen');
        if (regimen) triplets.push(fact('Исследование', 'режим дозировки', regimen, b.instanceId, b.blockType));
        return triplets;
    },

    // T19: Животная модель
    19: (b) => {
        const triplets: DerivedTriplet[] = [];
        const species = str(b.data, 'species');
        if (species) triplets.push(fact('Исследование', 'вид животного', species, b.instanceId, b.blockType));
        const timeline = str(b.data, 'timeline');
        if (timeline) triplets.push(fact('Исследование', 'временная шкала модели', timeline, b.instanceId, b.blockType));
        const conditions = str(b.data, 'conditions');
        if (conditions) triplets.push(fact('Исследование', 'условия содержания модели', conditions, b.instanceId, b.blockType));
        return triplets;
    },

    // T21: Логика исследователя
    21: (b) => {
        const v = str(b.data, 'logic');
        return v ? [fact('Исследование', 'логика', v, b.instanceId, b.blockType)] : [];
    },

    // T22: Сущность (s/p/o триплет)
    22: (b) => {
        const s = str(b.data, 'subject');
        const p = str(b.data, 'predicate');
        const o = str(b.data, 'object');
        return (s && p && o) ? [fact(s, p, o, b.instanceId, b.blockType)] : [];
    },

    // T23: Определение понятия
    23: (b) => {
        const term = str(b.data, 'term');
        const def = str(b.data, 'definition');
        return (term && def) ? [fact(term, 'определяется как', def, b.instanceId, b.blockType)] : [];
    },

    // T24: Предположения
    24: (b) => {
        return splitLines(b.data.assumptions).map((a) =>
            fact('Исследование', 'предполагает', a, b.instanceId, b.blockType)
        );
    },

    // T25: Размер выборки
    25: (b) => {
        const v = str(b.data, 'sampleSize');
        return v ? [fact('Исследование', 'размер выборки', 'n=' + v, b.instanceId, b.blockType)] : [];
    },

    // T26: Источники данных
    26: (b) => {
        return splitLines(b.data.dataSources).map((ds) =>
            fact('Исследование', 'источник данных', ds, b.instanceId, b.blockType)
        );
    },

    // T27: p-value
    27: (b) => {
        const v = str(b.data, 'pValue');
        return v ? [fact('Исследование', 'p-value', v, b.instanceId, b.blockType)] : [];
    },

    // T28: Дисперсия
    28: (b) => {
        const v = str(b.data, 'variance');
        return v ? [fact('Исследование', 'дисперсия', v, b.instanceId, b.blockType)] : [];
    },

    // T29: Размер эффекта
    29: (b) => {
        const v = str(b.data, 'effectSize');
        if (!v) return [];
        const effectType = str(b.data, 'effectType');
        const label = effectType ? `размер эффекта (${effectType})` : 'размер эффекта';
        return [fact('Исследование', label, v, b.instanceId, b.blockType)];
    },

    // T30: Мощность исследования
    30: (b) => {
        const v = str(b.data, 'power');
        return v ? [fact('Исследование', 'мощность', v, b.instanceId, b.blockType)] : [];
    },

    // T31: Доверительный интервал
    31: (b) => {
        const lower = str(b.data, 'ciLower');
        const upper = str(b.data, 'ciUpper');
        if (!lower && !upper) return [];
        const level = str(b.data, 'ciLevel') || '95%';
        return [fact('Исследование', `доверительный интервал ${level}`, `[${lower}, ${upper}]`, b.instanceId, b.blockType)];
    },

    // T32: Числа с названиями
    32: (b) => {
        return kvPairs(b.data.namedNumbers).map(({ key, value }) =>
            fact(key, 'величина', value, b.instanceId, b.blockType)
        );
    },

    // T33: Формулы
    33: (b) => {
        const triplets: DerivedTriplet[] = [];
        const name = str(b.data, 'formulaName');
        const latex = str(b.data, 'formulaLatex');
        if (latex) {
            const label = name || 'Формула';
            triplets.push(meta(label, 'определяет', latex, b.instanceId, b.blockType));
        }
        const vars = kvPairs(b.data.formulaVariables);
        for (const { key, value } of vars) {
            triplets.push(meta(name || 'Формула', 'переменная', `${key} = ${value}`, b.instanceId, b.blockType));
        }
        return triplets;
    },

    // T34: Каузальные графы (DAG)
    34: (b) => {
        const desc = str(b.data, 'dagDescription');
        return desc ? [meta('Каузальный граф', 'описывает', desc, b.instanceId, b.blockType)] : [];
    },

    // T35: Критерии идентифицируемости Дж.Перла
    35: (b) => {
        const v = str(b.data, 'criteria');
        return v ? [fact('Исследование', 'критерии идентифицируемости', v, b.instanceId, b.blockType)] : [];
    },

    // T36: Результаты
    36: (b) => {
        const triplets: DerivedTriplet[] = [];
        const results = str(b.data, 'results');
        if (results) triplets.push(fact('Исследование', 'результаты', results, b.instanceId, b.blockType));
        const summary = str(b.data, 'resultsSummary');
        if (summary) triplets.push(fact('Исследование', 'краткое описание результатов', summary, b.instanceId, b.blockType));
        return triplets;
    },

    // T37: Статистическая обработка
    37: (b) => {
        const triplets: DerivedTriplet[] = [];
        const proc = str(b.data, 'statProcessing');
        if (proc) triplets.push(fact('Исследование', 'статистическая обработка', proc, b.instanceId, b.blockType));
        const comp = str(b.data, 'expectationsComparison');
        if (comp) triplets.push(fact('Исследование', 'сопоставление с ожиданиями', comp, b.instanceId, b.blockType));
        return triplets;
    },

    // T38: Утверждения
    38: (b) => {
        const s = str(b.data, 'claimSubject');
        const p = str(b.data, 'claimPredicate');
        const o = str(b.data, 'claimObject');
        if (!s || !p || !o) return [];
        const negated = bool(b.data, 'isNegated');
        const predicate = negated ? `не ${p}` : p;
        const notes = str(b.data, 'confidenceNotes');
        const confidence = notes ? 0.8 : 1.0;
        const triplets = [fact(s, predicate, o, b.instanceId, b.blockType, confidence)];
        if (notes) triplets.push(meta(s, 'уверенность', notes, b.instanceId, b.blockType));
        return triplets;
    },

    // T39: Ограничения исследования
    39: (b) => {
        const v = str(b.data, 'limitations');
        return v ? [fact('Исследование', 'ограничения', v, b.instanceId, b.blockType)] : [];
    },

    // T40: Побочные выводы/гипотезы
    40: (b) => {
        const v = str(b.data, 'sideFindings');
        return v ? [fact('Исследование', 'побочные выводы', v, b.instanceId, b.blockType)] : [];
    },

    // T41: Сопутствующие эффекты
    41: (b) => {
        const v = str(b.data, 'sideEffects');
        return v ? [fact('Исследование', 'побочные эффекты', v, b.instanceId, b.blockType)] : [];
    },

    // T42: Утверждения после исследования
    42: (b) => {
        const triplets: DerivedTriplet[] = [];
        const claims = str(b.data, 'postClaims');
        if (claims) {
            splitLines(claims).forEach((line) => {
                triplets.push(fact('После исследования', 'утверждает', line, b.instanceId, b.blockType));
            });
        }
        const comp = str(b.data, 'comparisonWithExpectations');
        if (comp) triplets.push(fact('Исследование', 'сравнение результатов с ожиданиями', comp, b.instanceId, b.blockType));
        return triplets;
    },

    // T43: Оставшиеся вопросы
    43: (b) => {
        const v = str(b.data, 'openQuestions');
        return v ? [fact('Исследование', 'открытые вопросы', v, b.instanceId, b.blockType)] : [];
    },

    // T44: Новизна
    44: (b) => {
        const v = str(b.data, 'novelty');
        return v ? [fact('Исследование', 'новизна', v, b.instanceId, b.blockType)] : [];
    },

    // T45: Версии
    45: (b) => {
        return kvPairs(b.data.versions).map(({ key, value }) =>
            fact('Исследование', `версия: ${key}`, value, b.instanceId, b.blockType)
        );
    },

    // T46: Предложения для будущих исследований
    46: (b) => {
        return splitLines(b.data.futureResearch).map((r) =>
            fact('Исследование', 'предложение для будущих исследований', r, b.instanceId, b.blockType)
        );
    },

    // T47: Связи с предыдущими исследованиями
    47: (b) => {
        return splitLines(b.data.references).map((ref) =>
            fact('Исследование', 'ссылается на', ref, b.instanceId, b.blockType)
        );
    },

    // T48: Связь со старением
    48: (b) => {
        const v = str(b.data, 'agingConnection');
        return v ? [fact('Исследование', 'связь со старением', v, b.instanceId, b.blockType)] : [];
    },

    // T49: Изображение
    49: (b) => {
        const triplets: DerivedTriplet[] = [];
        const imageKey = str(b.data, 'imageKey');
        if (imageKey) triplets.push(fact('Исследование', 'изображение', imageKey, b.instanceId, b.blockType));
        const caption = str(b.data, 'caption');
        if (caption && imageKey) triplets.push(fact(imageKey, 'подпись', caption, b.instanceId, b.blockType));
        for (const ref of splitLines(b.data.imageRefs)) {
            triplets.push(fact('Исследование', 'изображение', ref, b.instanceId, b.blockType));
        }
        return triplets;
    },

    // T50: Код
    50: (b) => {
        const lang = str(b.data, 'codeLanguage');
        const code = str(b.data, 'code');
        if (!code) return [];
        return [fact('Исследование', `код (${lang || 'неизвестный язык'})`, code, b.instanceId, b.blockType)];
    },

    // T51: Источники финансирования
    51: (b) => {
        return splitLines(b.data.funding).map((f) =>
            fact('Исследование', 'источник финансирования', f, b.instanceId, b.blockType)
        );
    },

    // T52: Конфликт интересов
    52: (b) => {
        const v = str(b.data, 'conflictOfInterest');
        return v ? [fact('Исследование', 'конфликт интересов', v, b.instanceId, b.blockType)] : [];
    },

    // T53: Информационная ценность
    53: (b) => {
        const triplets: DerivedTriplet[] = [];
        const fields: Array<[string, string]> = [
            ['uncertaintyReduced', 'уменьшило неопределённость'],
            ['hypothesesExcluded', 'исключило гипотезы'],
            ['hypothesesProbabilized', 'сделало гипотезы вероятнее'],
            ['newHypotheses', 'породило новые гипотезы'],
            ['nextExperiment', 'следующий оптимальный эксперимент'],
        ];
        for (const [key, label] of fields) {
            const v = str(b.data, key);
            if (v) triplets.push(fact('Исследование', label, v, b.instanceId, b.blockType));
        }
        return triplets;
    },

    // T54: Действие (s/p/o триплет)
    54: (b) => {
        const s = str(b.data, 'subject');
        const p = str(b.data, 'predicate');
        const o = str(b.data, 'object');
        return (s && p && o) ? [fact(s, p, o, b.instanceId, b.blockType)] : [];
    },

    // T55: Группа животных
    55: (b) => {
        const triplets: DerivedTriplet[] = [];
        const name = str(b.data, 'groupName');
        if (name) triplets.push(fact('Исследование', 'группа животных', name, b.instanceId, b.blockType));
        const n = str(b.data, 'n');
        if (n) triplets.push(fact(name || 'Группа', 'размер выборки', n, b.instanceId, b.blockType));
        const purpose = str(b.data, 'purpose');
        if (purpose) triplets.push(fact(name || 'Группа', 'назначение', purpose, b.instanceId, b.blockType));
        return triplets;
    },

    // T56: Шаг эксперимента
    56: (b) => {
        const triplets: DerivedTriplet[] = [];
        const stepName = str(b.data, 'stepName');
        if (stepName) triplets.push(fact(b.instanceId, 'шаг', stepName, b.instanceId, b.blockType));
        const details = str(b.data, 'details');
        if (details) triplets.push(fact(stepName || 'Шаг', 'детали', details, b.instanceId, b.blockType));
        const duration = str(b.data, 'duration');
        if (duration) triplets.push(fact(stepName || 'Шаг', 'длительность шага', duration, b.instanceId, b.blockType));
        return triplets;
    },

    // T57: Результат (находка)
    57: (b) => {
        const triplets: DerivedTriplet[] = [];
        const parameter = str(b.data, 'parameter');
        if (!parameter) return [];
        const direction = str(b.data, 'direction');
        const subjectRef = str(b.data, 'subjectRef');
        const comparisonRef = str(b.data, 'comparisonRef');
        const significance = str(b.data, 'significance');
        const pValue = str(b.data, 'pValue');
        const figureRef = str(b.data, 'figureRef');
        const detail = str(b.data, 'detail');

        const dirMap: Record<string, string> = {
            'повышено': 'повышено в',
            'понижено': 'понижено в',
            'без изменений': 'без изменений в',
            'тренд': 'тренд в',
        };
        const predicate = dirMap[direction] || 'изменено в';
        const target = subjectRef || 'исследовании';
        triplets.push(fact(parameter, predicate, target, b.instanceId, b.blockType));
        if (comparisonRef) triplets.push(meta(parameter, 'по сравнению с', comparisonRef, b.instanceId, b.blockType));
        if (significance) triplets.push(meta(parameter, 'значимость', significance, b.instanceId, b.blockType));
        if (pValue) triplets.push(meta(parameter, 'p-value', pValue, b.instanceId, b.blockType));
        if (figureRef) triplets.push(meta(parameter, 'рисунок', figureRef, b.instanceId, b.blockType));
        if (detail) triplets.push(meta(parameter, 'детали', detail, b.instanceId, b.blockType));
        return triplets;
    },
};

// ═══════════════════════════════════════════════════════════════════
// Основная функция: блоки → триплеты
// ═══════════════════════════════════════════════════════════════════

export function blocksToStatements(
    blocks: ArticleBlockData[],
    articleUuid?: string,
    existingStatements?: KnowledgeStatement[],
): DerivedTriplet[] {
    const idMap = new Map<string, string[]>();
    if (existingStatements) {
        for (const stmt of existingStatements) {
            if (!stmt.id || !stmt.sourceBlockId) continue;
            const arr = idMap.get(stmt.sourceBlockId);
            if (arr) arr.push(stmt.id);
            else idMap.set(stmt.sourceBlockId, [stmt.id]);
        }
    }

    const allTriplets: DerivedTriplet[] = [];
    const sorted = [...blocks].sort((a, b) => a.order - b.order);

    for (const block of sorted) {
        const converter = converters[block.blockType];
        if (converter) {
            const blockTriplets = converter(block);
            const ids = idMap.get(block.instanceId);
            if (ids) {
                for (let i = 0; i < blockTriplets.length; i++) {
                    if (i < ids.length) blockTriplets[i].id = ids[i];
                }
            }
            allTriplets.push(...blockTriplets);
        }
    }

    const blockNameMap = new Map<string, string>();
    for (const b of blocks) {
        const def = getBlockTypeDef(b.blockType);
        if (!def) continue;
        const nameField = findNameField(def, b.data);
        if (nameField) blockNameMap.set(b.instanceId, (b.data[nameField.key] as string).trim());
    }

    const refMap = new Map<string, string>();
    for (const t of allTriplets) {
        refMap.set(t.sourceBlockId, blockNameMap.get(t.sourceBlockId) ?? t.subject_text);
        refMap.set(t.id, t.subject_text);
    }
    for (const b of blocks) {
        const name = blockNameMap.get(b.instanceId);
        if (name) refMap.set(b.instanceId, name);
    }
    if (existingStatements) {
        for (const s of existingStatements) {
            if (s.id) refMap.set(s.id, s.subject_text);
        }
    }
    for (const t of allTriplets) {
        const sRes = refMap.get(t.subject_text);
        if (sRes) t.subject_text = sRes;
        if (t.predicate === 'результат') continue;
        const oRes = refMap.get(t.object_text);
        if (oRes) t.object_text = oRes;
    }

    if (articleUuid) {
        for (const t of allTriplets) {
            if (t.subject_text === 'Статья') {
                t.subject_text = articleUuid;
            }
        }
    }

    if (existingStatements) {
        const existingMap = new Map<string, string>();
        for (const s of existingStatements) {
            if (!s.id) continue;
            const key = `${s.subject_text}\u0000${s.predicate}\u0000${s.object_text}`;
            if (!existingMap.has(key)) existingMap.set(key, s.id);
        }
        for (const t of allTriplets) {
            const id = existingMap.get(`${t.subject_text}\u0000${t.predicate}\u0000${t.object_text}`);
            if (id) t.id = id;
        }
    }

    return allTriplets;
}

// ═══════════════════════════════════════════════════════════════════
// Обратная функция: триплеты → блоки (fallback для загрузки)
// ═══════════════════════════════════════════════════════════════════

export function statementsToBlocks(statements: KnowledgeStatement[]): ArticleBlockData[] {
    const blocks: ArticleBlockData[] = [];
    let order = 0;

    const metadataDois: string[] = [];
    const metadataTitles: string[] = [];
    const metadataAuthors: string[] = [];

    for (const stmt of statements) {
        const subj = stmt.subject_text;
        const pred = stmt.predicate;
        const obj = stmt.object_text;

        // Skip article triple and containment links
        if (pred === 'является' && obj === 'научная статья') continue;
        if (pred === 'содержит') continue;

        // Метаданные: Статья → DOI/название/авторы
        if (subj === 'Статья' && pred === 'DOI') {
            metadataDois.push(obj);
            continue;
        }
        if (subj === 'Статья' && pred === 'название статьи') {
            metadataTitles.push(obj);
            continue;
        }
        if (subj === 'Статья' && pred === 'авторы') {
            metadataAuthors.push(obj);
            continue;
        }

        // Цель исследования (legacy: Исследование → цель → X)
        if (subj === 'Исследование' && pred === 'цель') {
            blocks.push({
                instanceId: `imp-${order}`,
                blockType: 2,
                data: { subject: subj, predicate: pred, object: obj },
                order: order++,
            });
            continue;
        }

        // Гипотеза
        if (pred === 'гипотеза') {
            blocks.push({
                instanceId: `imp-${order}`,
                blockType: 7,
                data: { hypothesis: obj },
                order: order++,
            });
            continue;
        }

        // Утверждения с confidence notes
        if (pred === 'уверенность') {
            continue;
        }

        // Дизайн исследования
        if (subj === 'Исследование' && pred === 'тип') {
            blocks.push({
                instanceId: `imp-${order}`,
                blockType: 11,
                data: { studyType: obj },
                order: order++,
            });
            continue;
        }

        if (subj === 'Исследование' && pred === 'рандомизировано') {
            const existing = blocks.find((b) => b.blockType === 11);
            if (existing) {
                existing.data.randomization = obj === 'да';
            } else {
                blocks.push({
                    instanceId: `imp-${order}`,
                    blockType: 11,
                    data: { randomization: obj === 'да' },
                    order: order++,
                });
            }
            continue;
        }

        if (subj === 'Исследование' && pred === 'ослеплено') {
            const existing = blocks.find((b) => b.blockType === 11);
            if (existing) {
                existing.data.blinding = obj === 'да';
            } else {
                blocks.push({
                    instanceId: `imp-${order}`,
                    blockType: 11,
                    data: { blinding: obj === 'да' },
                    order: order++,
                });
            }
            continue;
        }

        // Прямой триплет (fallback)
        blocks.push({
            instanceId: `imp-${order}`,
            blockType: 4,
            data: { subject: subj, predicate: pred, object: obj },
            order: order++,
        });
    }

    // Собираем метаданные в один блок
    if (metadataDois.length || metadataTitles.length || metadataAuthors.length) {
        blocks.unshift({
            instanceId: `imp-meta`,
            blockType: 1,
            data: {
                doi: metadataDois.join('; '),
                title: metadataTitles.join('; '),
                authors: metadataAuthors.join('\n'),
            },
            order: 0,
        });
        // Пересчитываем порядок
        blocks.forEach((b, i) => { b.order = i; });
    }

    return blocks;
}

// ═══════════════════════════════════════════════════════════════════
// Генерация текста из блоков (backward compat)
// ═══════════════════════════════════════════════════════════════════

export function blocksToText(blocks: ArticleBlockData[], articleUuid?: string): string {
    const lines: string[] = [];
    const sorted = [...blocks].sort((a, b) => a.order - b.order);

    if (articleUuid) {
        lines.push(`${articleUuid} → является → научная статья`);
    }

    for (const block of sorted) {
        const d = block.data;
        switch (block.blockType) {
            case 1: {
                const parts: string[] = [];
                if (d.doi) parts.push(`DOI: ${d.doi}`);
                if (d.title) parts.push(`Title: ${d.title}`);
                if (d.authors) parts.push(`Authors: ${d.authors}`);
                if (parts.length) lines.push(parts.join(' | '));
                break;
            }
            case 3:
                if (d.content) lines.push(String(d.content));
                break;
            case 4:
                if (d.subject && d.predicate && d.object) {
                    lines.push(`${d.subject} → ${d.predicate} → ${d.object}`);
                }
                break;
            default: {
                const parts: string[] = [];
                for (const val of Object.values(d)) {
                    if (typeof val === 'string' && val.trim()) parts.push(val.trim());
                }
                if (parts.length) lines.push(parts.join(' '));
                break;
            }
        }
    }

    return lines.join('\n\n');
}

// ═══════════════════════════════════════════════════════════════════
// Генерация Markdown с резолвом UUID в древо триплетов
// ═══════════════════════════════════════════════════════════════════

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;


function getArticleTitle(blocks: ArticleBlockData[]): string {
    for (const b of blocks) {
        if (b.blockType === 1) {
            const t = b.data.title;
            if (typeof t === 'string' && t.trim()) return t.trim();
        }
    }
    return '';
}

function isUuid(s: string): boolean {
    return UUID_RE.test(s);
}

export function statementsToResolvedText(
    statements: KnowledgeStatement[],
    blocks: ArticleBlockData[],
    articleUuid?: string,
    existingStatements?: KnowledgeStatement[],
): string {
    const title = getArticleTitle(blocks);

    const blockById = new Map<string, ArticleBlockData>();
    for (const b of blocks) if (b.instanceId) blockById.set(b.instanceId, b);

    const stmtById = new Map<string, KnowledgeStatement>();
    const stmtsBySourceBlockId = new Map<string, KnowledgeStatement[]>();
    const stmtsBySubjectPredicate = new Map<string, KnowledgeStatement>();
    const stmtsBySourcePredicate = new Map<string, KnowledgeStatement>();
    const stmtBySubject = new Map<string, KnowledgeStatement>();
    for (const s of statements) {
        if (s.id) stmtById.set(s.id, s);
        if (s.sourceBlockId) {
            const arr = stmtsBySourceBlockId.get(s.sourceBlockId);
            if (arr) arr.push(s);
            else stmtsBySourceBlockId.set(s.sourceBlockId, [s]);
            if (s.predicate) {
                const key = `${s.sourceBlockId}\u0000${s.predicate}`;
                if (!stmtsBySourcePredicate.has(key)) stmtsBySourcePredicate.set(key, s);
            }
        }
        if (s.subject_text && s.predicate) {
            const key = `${s.subject_text}\u0000${s.predicate}`;
            if (!stmtsBySubjectPredicate.has(key)) stmtsBySubjectPredicate.set(key, s);
            if (s.object_text && !stmtBySubject.has(s.subject_text)) stmtBySubject.set(s.subject_text, s);
        }
    }

    // ---- uuidMap: statement id / sourceBlockId → statement ----
    const uuidMap = new Map<string, KnowledgeStatement>();
    for (const s of statements) {
        if (s.id) uuidMap.set(s.id, s);
        if (s.sourceBlockId) uuidMap.set(s.sourceBlockId, s);
    }

    // ---- blockLabelMap: block instanceId → human-readable chain ----
    const blockLabelMap = new Map<string, string>();
    function buildBlockLabel(uuid: string): string {
        const existing = blockLabelMap.get(uuid);
        if (existing !== undefined) return existing;
        const blk = blockById.get(uuid);
        if (!blk) return uuid;
        blockLabelMap.set(uuid, uuid);
        const sub = blk.data.subject as string | undefined;
        const pred = blk.data.predicate as string | undefined;
        const obj = blk.data.object as string | undefined;
        if (sub && pred && obj) {
            const sl = isUuid(sub) ? buildBlockLabel(sub) : sub;
            const ol = isUuid(obj) ? buildBlockLabel(obj) : obj;
            const label = `${sl} → ${pred} → ${ol}`;
            blockLabelMap.set(uuid, label);
            return label;
        }
        const name = blk.data.name as string | undefined;
        if (name) { blockLabelMap.set(uuid, name); return name; }
        const def = getBlockTypeDef(blk.blockType);
        if (def) {
            const nameField = findNameField(def, blk.data);
            if (nameField) {
                const label = blk.data[nameField.key] as string;
                blockLabelMap.set(uuid, label);
                return label;
            }
        }
        blockLabelMap.delete(uuid);
        return uuid;
    }
    for (const b of blocks) {
        if (b.instanceId) buildBlockLabel(b.instanceId);
    }

    // ---- resolveField: resolve UUID to full text chain (visited-guarded) ----
    const panicSearchStmt = (uuid: string): KnowledgeStatement | undefined => {
        const direct = stmtById.get(uuid);
        if (direct) return direct;
        if (existingStatements) {
            for (const s of existingStatements) {
                if (s.id === uuid || s.sourceBlockId === uuid) return s;
            }
        }
        return undefined;
    };

    const panicSearchBlockLabel = (uuid: string, visited: Set<string>): string | undefined => {
        const blk = blockById.get(uuid);
        if (!blk) return undefined;
        if (visited.has(uuid)) return uuid;
        visited.add(uuid);
        const sub = blk.data.subject as string | undefined;
        const pred = blk.data.predicate as string | undefined;
        const obj = blk.data.object as string | undefined;
        if (sub && pred && obj) {
            const sl = isUuid(sub) ? resolveField(sub, visited) : sub;
            const ol = isUuid(obj) ? resolveField(obj, visited) : obj;
            visited.delete(uuid);
            return `${sl} → ${pred} → ${ol}`;
        }
        const name = blk.data.name as string | undefined;
        visited.delete(uuid);
        if (name) return name;
        return uuid;
    };

    const resolveField = (text: string, visited: Set<string>): string => {
        if (!isUuid(text) || visited.has(text)) return text;
        const stmt = uuidMap.get(text);
        if (stmt) {
            visited.add(text);
            const sub = resolveField(stmt.subject_text, visited);
            const obj = resolveField(stmt.object_text, visited);
            visited.delete(text);
            return `${sub} → ${stmt.predicate} → ${obj}`;
        }
        const bl = blockLabelMap.get(text);
        if (bl !== undefined && bl !== text) return bl;
        const panicStmt = panicSearchStmt(text);
        if (panicStmt) {
            visited.add(text);
            const sub = resolveField(panicStmt.subject_text, visited);
            const obj = resolveField(panicStmt.object_text, visited);
            visited.delete(text);
            return `${sub} → ${panicStmt.predicate} → ${obj}`;
        }
        const panicBl = panicSearchBlockLabel(text, visited);
        if (panicBl !== undefined && panicBl !== text) return panicBl;
        return text;
    };

    // ---- group statements ----
    const goalStatements: KnowledgeStatement[] = [];
    const articleStatements: KnowledgeStatement[] = [];
    const otherStatements: KnowledgeStatement[] = [];

    for (const stmt of statements) {
        if (!stmt.id) continue;
        if (stmt.predicate === 'содержит') continue;
        if (stmt.predicate === 'является' && stmt.object_text === 'научная статья') continue;
        if (stmt.predicate === 'цель') {
            goalStatements.push(stmt);
        } else if (stmt.subject_text === articleUuid) {
            articleStatements.push(stmt);
        } else {
            otherStatements.push(stmt);
        }
    }

    // ---- YAML metadata ----
    let yamlTitle = title || '';
    const doiSet = new Set<string>();
    const authorSet = new Set<string>();

    for (const stmt of articleStatements) {
        if (stmt.predicate === 'название статьи' && stmt.object_text) {
            yamlTitle = stmt.object_text;
        } else if (stmt.predicate === 'DOI' && stmt.object_text) {
            doiSet.add(stmt.object_text);
        } else if (stmt.predicate === 'авторы' && stmt.object_text) {
            authorSet.add(stmt.object_text);
        }
    }

    const yamlLines: string[] = ['---'];
    if (doiSet.size > 0) {
        const doid = [...doiSet][0];
        yamlLines.push(`doi: "${doid.replace(/"/g, '\\"')}"`);
    }
    if (authorSet.size > 0) {
        yamlLines.push(`authors: "${[...authorSet].map(a => a.replace(/"/g, '\\"')).join(', ')}"`);
    }
    yamlLines.push('---');

    const parts: string[] = [yamlLines.join('\n')];
    if (yamlTitle) parts.push(`# ${yamlTitle}`);

    // ---- helpers ----
    const flatten = (chain: string): string => {
        const segs = chain.split(/\s*→\s*/);
        const out: string[] = [];
        for (let i = 0; i < segs.length; i++) {
            if (i % 2 === 0) {
                out.push(segs[i]);
            } else {
                const first = segs[i].trim().split(/\s+/)[0];
                if (segs[i].trim() !== first) out.push(first);
            }
        }
        const t = out.join(' ');
        return t.charAt(0).toUpperCase() + t.slice(1) + '.';
    };

    const extendChain = (chain: string): string => {
        let current = chain;
        const visited = new Set<string>();
        for (;;) {
            const segs = current.split(/\s*→\s*/);
            const last = segs[segs.length - 1].trim();
            if (!last || visited.has(last) || isUuid(last)) break;
            visited.add(last);
            const s = stmtBySubject.get(last);
            if (!s) break;
            const blk = s.sourceBlockId ? blockById.get(s.sourceBlockId) : undefined;
            const dataObj = blk?.data?.object as string | undefined;
            const obj = isUuid(dataObj)
                ? resolveField(dataObj, new Set<string>())
                : s.object_text;
            current += ` → ${s.predicate} → ${obj}`;
        }
        return current;
    };

    const resolveGoal = (gs: KnowledgeStatement): string => {
        const gb = gs.sourceBlockId ? blockById.get(gs.sourceBlockId) : undefined;
        const targetUuid = gb?.data?.object as string | undefined;
        if (isUuid(targetUuid)) {
            const bl = blockLabelMap.get(targetUuid);
            if (bl !== undefined) return bl;
            const resolved = resolveField(targetUuid, new Set<string>());
            if (resolved !== targetUuid) return extendChain(resolved);
        }
        if (isUuid(gs.object_text)) {
            const resolved = resolveField(gs.object_text, new Set<string>());
            if (resolved !== gs.object_text) return extendChain(resolved);
        }
        return extendChain(gs.object_text);
    };

    for (const [i, gs] of goalStatements.entries()) {
        parts.push(`Цель ${i + 1}: ${flatten(resolveGoal(gs))}`);
    }

    // ---- experiments ----
    const experimentStatements = statements.filter(s => s.predicate === 'эксперимент' && s.sourceBlockId);
    if (experimentStatements.length > 0) {
        const dirPredMap: Record<string, string> = {
            'повышено': 'повышено в',
            'понижено': 'понижено в',
            'без изменений': 'без изменений в',
            'тренд': 'тренд в',
        };
        const renderFinding = (uuid: string): string => {
            const blk = blockById.get(uuid);
            if (!blk) return resolveField(uuid, new Set<string>());
            if (blk.blockType === 57) {
                const d = blk.data;
                const parameter = typeof d.parameter === 'string' ? d.parameter.trim() : '';
                if (!parameter) return resolveField(uuid, new Set<string>());
                const direction = typeof d.direction === 'string' ? dirPredMap[d.direction] : '';
                const subjRef = typeof d.subjectRef === 'string' ? d.subjectRef : '';
                const group = subjRef
                    ? (blockLabelMap.get(subjRef) || resolveField(subjRef, new Set<string>()))
                    : '';
                const compRef = typeof d.comparisonRef === 'string' ? d.comparisonRef : '';
                const comp = compRef
                    ? (blockLabelMap.get(compRef) || resolveField(compRef, new Set<string>()))
                    : '';
                const pvRef = typeof d.pValue === 'string' ? d.pValue : '';
                const pvBlock = pvRef ? blockById.get(pvRef) : undefined;
                const pv = str(pvBlock?.data ?? {}, 'pValue');
                const fig = typeof d.figureRef === 'string' ? d.figureRef.trim() : '';
                let line = parameter;
                if (direction) line += ` ${direction}`;
                if (group) line += ` ${group}`;
                if (comp) line += ` (по сравнению с ${comp})`;
                const extras: string[] = [];
                if (pv) extras.push(`p=${pv}`);
                if (fig) extras.push(fig);
                if (extras.length) line += ` — ${extras.join(', ')}`;
                const detail = typeof d.detail === 'string' ? d.detail.trim() : '';
                if (detail) line += ` — ${detail}`;
                return line;
            }
            return resolveField(uuid, new Set<string>());
        };
        for (const es of experimentStatements) {
            const expName = es.object_text;
            const expBlockId = es.sourceBlockId!;
            const expRelated = (stmtsBySourceBlockId.get(expBlockId) ?? []).filter(s => s.id !== es.id);

            const typeStmt = expRelated.find(s => s.predicate === 'тип');
            const outcomesStmts = expRelated.filter(s => s.predicate === 'измеряемые показатели');
            const stepStmts = expRelated.filter(s => s.predicate === 'шаг');
            const durationStmt = expRelated.find(s => s.predicate === 'длительность');
            const expGroupStmts = expRelated.filter(s => s.predicate === 'экспериментальная группа');
            const ctrlGroupStmts = expRelated.filter(s => s.predicate === 'контрольная группа');
            const expGettingStatements = (stmtsBySourceBlockId.get(expBlockId) ?? []);

            const expLines: string[] = [`## Эксперимент: ${expName}`];
            if (typeStmt) expLines.push(`**Тип:** ${typeStmt.object_text}  `);
            if (outcomesStmts.length > 0) {
                expLines.push(`**Измеряемые показатели:** ${outcomesStmts.map(os => os.object_text).join(', ')}  `);
            }
            if (durationStmt) expLines.push(`**Длительность:** ${durationStmt.object_text}  `);

            const renderGroups = (groupStmts: KnowledgeStatement[]): string[] => {
                return groupStmts.map(gs => {
                    const groupUuid = gs.object_text;
                    const groupResolved = resolveField(groupUuid, new Set<string>());
                    const interventionStmt = expGettingStatements.find(
                        s => s.predicate === 'получает' && s.subject_text === groupUuid
                    );
                    if (interventionStmt) {
                        const ivResolved = resolveField(interventionStmt.object_text, new Set<string>());
                        return `- ${groupResolved} → получает → ${ivResolved}`;
                    }
                    return `- ${groupResolved} — интервенций нет, наблюдательное исследование`;
                });
            };

            if (expGroupStmts.length > 0) {
                expLines.push('', '**Экспериментальные группы:**');
                expLines.push(...renderGroups(expGroupStmts));
            }
            if (ctrlGroupStmts.length > 0) {
                expLines.push('', '**Контрольные группы:**');
                expLines.push(...renderGroups(ctrlGroupStmts));
            }
            if (stepStmts.length > 0) {
                expLines.push('', '**Последовательность:**', '');
                stepStmts.forEach((ss, idx) => {
                    const stepUuid = ss.object_text;
                    const stepLabel = blockLabelMap.get(stepUuid) || resolveField(stepUuid, new Set<string>());
                    const stepBlockId = isUuid(stepUuid) ? stepUuid : undefined;
                    const detailStmt = stepBlockId
                        ? stmtsBySourcePredicate.get(`${stepBlockId}\u0000детали`)
                        : stmtsBySubjectPredicate.get(`${stepLabel}\u0000детали`);
                    const stepDurationStmt = stepBlockId
                        ? stmtsBySourcePredicate.get(`${stepBlockId}\u0000длительность шага`)
                        : stmtsBySubjectPredicate.get(`${stepLabel}\u0000длительность шага`);
                    let line = `${idx + 1}. ${stepLabel}`;
                    if (stepDurationStmt) line += ` (${stepDurationStmt.object_text})`;
                    expLines.push(line);
                    if (detailStmt) expLines.push(`   - ${detailStmt.object_text}`);
                });
                expLines.push('');
            }

            const findingStmts = expRelated.filter(s => s.predicate === 'результат');
            if (findingStmts.length > 0) {
                expLines.push('', '**Результаты (находки):**');
                for (const fs of findingStmts) {
                    expLines.push(`- ${renderFinding(fs.object_text)}`);
                }
                expLines.push('');
            }

            parts.push(expLines.join('\n'));
        }
    }

    // ---- remaining blocks (not already rendered above) ----
    // Types 1 (metadata→YAML), 2 (goals), 14 (experiments) and their children
    // 18 (interventions), 27 (p-value), 55 (groups), 56 (steps), 57 (findings)
    // are rendered elsewhere; the rest are emitted here in a separate section.
    const hasAnyValue = (data: Record<string, BlockDataValue>): boolean => {
        for (const v of Object.values(data)) {
            if (typeof v === 'string' && v.trim()) return true;
        }
        return false;
    };
    const renderRemainingBlock = (blk: ArticleBlockData): string[] => {
        const d = blk.data;
        if (blk.blockType === 19) {
            const species = str(d, 'species');
            if (!species) return [];
            const lines = [`- **${species}**`];
            const timeline = str(d, 'timeline');
            if (timeline) lines.push(`  - Временная шкала: ${timeline}`);
            const conditions = str(d, 'conditions');
            if (conditions) lines.push(`  - Условия: ${conditions}`);
            return lines;
        }
        if (blk.blockType === 22 || blk.blockType === 54) {
            const s = str(d, 'subject');
            const p = str(d, 'predicate');
            const o = str(d, 'object');
            if (!s || !p || !o) return [];
            const sl = resolveField(s, new Set<string>());
            const ol = resolveField(o, new Set<string>());
            return [`- ${sl} → ${p} → ${ol}`];
        }
        if (blk.blockType === 23) {
            const term = str(d, 'term');
            const def = str(d, 'definition');
            return (term && def) ? [`- **${term}** — ${def}`] : [];
        }
        if (blk.blockType === 38) {
            const s = str(d, 'claimSubject');
            const p = str(d, 'claimPredicate');
            const o = str(d, 'claimObject');
            if (!s || !p || !o) return [];
            const neg = bool(d, 'isNegated') ? 'не ' : '';
            const notes = str(d, 'confidenceNotes');
            const line = `- **${s}** ${neg}${p} **${o}**`;
            return notes ? [line, `  - Уверенность: ${notes}`] : [line];
        }
        if (blk.blockType === 7) {
            const h = str(d, 'hypothesis');
            if (!h) return [];
            const exp = str(d, 'disproofExplanation');
            const line = `- **Гипотеза:** ${h}`;
            return exp ? [line, `  - Обоснование: ${exp}`] : [line];
        }
        if (blk.blockType === 16) {
            const m = str(d, 'mechanism');
            return m ? [`- **Механизм:** ${m}`] : [];
        }
        if (blk.blockType === 39) {
            const l = str(d, 'limitations');
            return l ? splitLines(l).map((x) => `- ${x}`) : [];
        }
        if (blk.blockType === 40) {
            const f = str(d, 'sideFindings');
            return f ? splitLines(f).map((x) => `- ${x}`) : [];
        }
        if (blk.blockType === 44) {
            const n = str(d, 'novelty');
            return n ? [`- **Новизна:** ${n}`] : [];
        }
        if (blk.blockType === 46) {
            const f = str(d, 'futureResearch');
            return f ? splitLines(f).map((x) => `- ${x}`) : [];
        }
        if (blk.blockType === 47) {
            const r = str(d, 'references');
            return r ? splitLines(r).map((x) => `- ${x}`) : [];
        }
        if (blk.blockType === 48) {
            const a = str(d, 'agingConnection');
            return a ? [`- **Связь со старением:** ${a}`] : [];
        }
        if (blk.blockType === 37) {
            const p = str(d, 'statProcessing');
            if (!p) return [];
            const lines = [`- **Статистическая обработка:** ${p}`];
            const comp = str(d, 'expectationsComparison');
            if (comp) lines.push(`  - Сопоставление с ожиданиями: ${comp}`);
            return lines;
        }
        if (blk.blockType === 51) {
            const f = str(d, 'funding');
            return f ? [`- **Финансирование:** ${f}`] : [];
        }
        const values: string[] = [];
        for (const v of Object.values(d)) {
            if (typeof v === 'string' && v.trim()) values.push(v.trim());
        }
        return values.length ? [`- ${values.join(' | ')}`] : [];
    };
    const remainingBlocks = blocks
        .filter((b) => ![1, 2, 14, 18, 27, 55, 56, 57].includes(b.blockType) && hasAnyValue(b.data))
        .sort((a, b) => a.order - b.order);
    if (remainingBlocks.length > 0) {
        const byType = new Map<number, ArticleBlockData[]>();
        for (const blk of remainingBlocks) {
            const arr = byType.get(blk.blockType);
            if (arr) arr.push(blk);
            else byType.set(blk.blockType, [blk]);
        }
        const sections: string[] = [];
        for (const [type, blks] of byType) {
            const def = getBlockTypeDef(type);
            const title = def ? def.name : `Блок ${type}`;
            const lines: string[] = [`## ${title}`, ''];
            for (const blk of blks) lines.push(...renderRemainingBlock(blk));
            lines.push('');
            sections.push(lines.join('\n'));
        }
        parts.push(sections.join('\n\n'));
    }

    return parts.join('\n\n');
}
