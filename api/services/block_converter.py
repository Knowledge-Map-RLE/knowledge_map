"""Каноническая конвертация структурных блоков статьи в триплеты (statements).

Серверный порт ``client/src/pages/Article_editor/Editor/blockConverter.ts`` —
единственный источник истины для вывода триплетов из блоков. Клиентский
конвертер остаётся только как «превью» при редактировании; авторитетные данные
(на load/save) всегда считаются сервером.

Вход: ``blocks`` — список блоков вида
``{"instanceId", "blockType", "data", "order"}``.
Выход: список триплетов вида
``{"id", "subject_text", "predicate", "object_text", "sourceBlockId",
 "sourceBlockType", "type", "subject_type", "object_type", "confidence"}``.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.uuid8 import uuid8_str

# Поля-кандидаты на «имя» блока (порядок как в findNameField клиента).
_NAME_CANDIDATES = ("name", "title", "subject", "term")

# Поля блока по типу — для findNameField (fallback на первое непустое текстовое).
_BLOCK_FIELDS: Dict[int, List[str]] = {
    1: ["doi", "title", "authors"],
    2: ["subject", "predicate", "object"],
    3: ["content"],
    4: ["subject", "predicate", "object"],
    5: ["endpoint"],
    6: ["endpoints"],
    7: ["hypothesis", "disproofExplanation", "sequence"],
    8: ["prerequisites"],
    9: ["expectations"],
    10: ["knowledgeDeps"],
    11: ["studyType", "randomization", "blinding"],
    12: ["materials"],
    13: ["methods", "measurementMethods"],
    14: ["experimentName", "experimentType", "outcomes", "steps", "findings",
         "duration", "experimentalPairs", "controlPairs"],
    15: ["inclusionCriteria", "exclusionCriteria"],
    16: ["mechanism", "sequence"],
    17: ["cell", "tissue", "organ", "pathway", "substanceLevel"],
    18: ["intervention", "dosage", "dosageRegimen"],
    19: ["species", "timeline", "conditions"],
    21: ["logic"],
    22: ["subject", "predicate", "object", "sequence"],
    23: ["term", "definition", "sequence"],
    24: ["assumptions"],
    25: ["sampleSize"],
    26: ["dataSources"],
    27: ["pValue"],
    28: ["variance"],
    29: ["effectSize", "effectType"],
    30: ["power"],
    31: ["ciLower", "ciUpper", "ciLevel"],
    32: ["namedNumbers"],
    33: ["formulaName", "formulaLatex", "formulaVariables"],
    34: ["dagDescription", "dagData"],
    35: ["criteria"],
    36: ["results", "resultsSummary"],
    37: ["statProcessing", "expectationsComparison", "sequence"],
    38: ["claimSubject", "claimPredicate", "claimObject", "confidenceNotes",
         "isNegated", "sequence"],
    39: ["limitations", "sequence"],
    40: ["sideFindings", "sequence"],
    41: ["sideEffects"],
    42: ["postClaims", "comparisonWithExpectations"],
    43: ["openQuestions"],
    44: ["novelty", "sequence"],
    45: ["versions"],
    46: ["futureResearch", "sequence"],
    47: ["references", "sequence"],
    48: ["agingConnection"],
    49: ["imageKey", "caption", "imageRefs"],
    50: ["codeLanguage", "code"],
    51: ["funding"],
    52: ["conflictOfInterest"],
    53: ["uncertaintyReduced", "hypothesesExcluded", "hypothesesProbabilized",
         "newHypotheses", "nextExperiment"],
    54: ["subject", "predicate", "object", "sequence"],
    55: ["groupName", "speciesRef", "n", "conditions", "purpose"],
    56: ["stepName", "details", "duration", "sequence"],
    57: ["parameter", "subjectRef", "comparisonRef", "direction", "significance",
         "pValue", "figureRef", "detail", "sequence"],
}


# ═══════════════════════════════════════════════════════════════════
# Вспомогательные функции (порт из blockConverter.ts)
# ═══════════════════════════════════════════════════════════════════

def fact(
    subject: str,
    predicate: str,
    obj: str,
    source_block_id: str,
    source_block_type: int,
    confidence: float = 1.0,
) -> Dict[str, Any]:
    return {
        "id": uuid8_str(),
        "subject_text": subject.strip(),
        "predicate": predicate.strip(),
        "object_text": obj.strip(),
        "sourceBlockId": source_block_id,
        "sourceBlockType": source_block_type,
        "type": "FACT",
        "subject_type": "concept",
        "object_type": "concept",
        "confidence": confidence,
    }


def meta(
    subject: str,
    predicate: str,
    obj: str,
    source_block_id: str,
    source_block_type: int,
) -> Dict[str, Any]:
    return {
        "id": uuid8_str(),
        "subject_text": subject.strip(),
        "predicate": predicate.strip(),
        "object_text": obj.strip(),
        "sourceBlockId": source_block_id,
        "sourceBlockType": source_block_type,
        "type": "META",
        "subject_type": "concept",
        "object_type": "concept",
        "confidence": 1.0,
    }


def _str(val: Dict[str, Any], key: str) -> str:
    v = val.get(key)
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    return ""


def split_lines(val: Any) -> List[str]:
    if not isinstance(val, str):
        return []
    return [s.strip() for s in val.split("\n") if s.strip()]


def kv_pairs(val: Any) -> List[Tuple[str, str]]:
    if isinstance(val, dict):
        return [(str(k), str(v)) for k, v in val.items()]
    if not isinstance(val, str):
        return []
    pairs: List[Tuple[str, str]] = []
    for line in val.split("\n"):
        line = line.strip()
        if not line:
            continue
        idx = line.find(":")
        if idx < 0:
            pairs.append((line, ""))
        else:
            pairs.append((line[:idx].strip(), line[idx + 1:].strip()))
    return pairs


def _bool(val: Dict[str, Any], key: str) -> bool:
    return val.get(key) is True or val.get(key) == "true"


def sequence_uuids(block: Dict[str, Any]) -> List[str]:
    raw = _str(block.get("data") or {}, "sequence")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except (ValueError, TypeError):
        return []
    return []


def sequence_triplets(
    block: Dict[str, Any], triplets: List[Dict[str, Any]]
) -> None:
    """Связующий триплет «{блок} → последовательность → {триплет-блок}»."""
    for uid in sequence_uuids(block):
        triplets.append(
            fact(block["instanceId"], "последовательность", uid,
                 block["instanceId"], block["blockType"])
        )


def find_name_field(block_type: int, data: Dict[str, Any]) -> Optional[str]:
    """Имя блока: кандидаты name/title/subject/term, иначе первое непустое."""
    fields = _BLOCK_FIELDS.get(block_type, [])

    def non_empty(key: str) -> bool:
        v = data.get(key)
        return isinstance(v, str) and v.strip()

    for key in _NAME_CANDIDATES:
        if key in fields and non_empty(key):
            return key
    for key in fields:
        if non_empty(key):
            return key
    return None


# ═══════════════════════════════════════════════════════════════════
# Конвертеры блоков в триплеты (порт converters из blockConverter.ts)
# ═══════════════════════════════════════════════════════════════════

ConverterFn = Callable[[Dict[str, Any]], List[Dict[str, Any]]]


def _converters() -> Dict[int, ConverterFn]:
    c: Dict[int, ConverterFn] = {}

    # T1: Метаданные
    def t1(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        data = b["data"]
        doi = _str(data, "doi")
        title = _str(data, "title")
        authors = _str(data, "authors")
        if doi:
            out.append(fact("Статья", "DOI", doi, b["instanceId"], b["blockType"]))
        if title:
            out.append(fact("Статья", "название статьи", title, b["instanceId"], b["blockType"]))
        if authors:
            for author in re.split(r"[\n,;]", authors):
                author = author.strip()
                if author:
                    out.append(fact("Статья", "авторы", author, b["instanceId"], b["blockType"]))
        return out

    # T2: Цель исследования (s/p/o)
    def t2(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = b["data"]
        s, p, o = _str(data, "subject"), _str(data, "predicate"), _str(data, "object")
        if not s and not p and not o:
            legacy = _str(data, "objective")
            return [fact("Исследование", "цель", legacy, b["instanceId"], b["blockType"])] if legacy else []
        return [fact(s, p, o, b["instanceId"], b["blockType"])] if s and p and o else []

    # T3: Свободный текст → 0 триплетов
    c[3] = lambda b: []

    # T4: Прямой триплет
    def t4(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = b["data"]
        s, p, o = _str(data, "subject"), _str(data, "predicate"), _str(data, "object")
        return [fact(s, p, o, b["instanceId"], b["blockType"])] if s and p and o else []

    # T5: Первичная конечная точка
    def t5(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "endpoint")
        return [fact("Исследование", "первая конечная точка", v, b["instanceId"], b["blockType"])] if v else []

    # T6: Вторичные конечные точки
    def t6(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [fact("Исследование", "вторичная конечная точка", ep, b["instanceId"], b["blockType"])
                for ep in split_lines(b["data"].get("endpoints"))]

    # T7: Гипотеза
    def t7(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        h = _str(b["data"], "hypothesis")
        if h:
            out.append(fact("Исследование", "гипотеза", h, b["instanceId"], b["blockType"]))
            reason = _str(b["data"], "disproofExplanation")
            if reason:
                out.append(meta("Гипотеза: " + h, "требует опровежения потому что", reason,
                                b["instanceId"], b["blockType"]))
        sequence_triplets(b, out)
        return out

    # T8: Предпосылки
    def t8(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [fact(p, "предпосылка", "Исследование", b["instanceId"], b["blockType"])
                for p in split_lines(b["data"].get("prerequisites"))]

    # T9: Ожидания
    def t9(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "expectations")
        return [fact("Исследование", "ожидает", v, b["instanceId"], b["blockType"])] if v else []

    # T10: Знания-зависимости
    def t10(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [fact("Исследование", "опирается на", dep, b["instanceId"], b["blockType"])
                for dep in split_lines(b["data"].get("knowledgeDeps"))]

    # T11: Дизайн исследования
    def t11(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        study_type = _str(b["data"], "studyType")
        if study_type:
            out.append(fact("Исследование", "тип", study_type, b["instanceId"], b["blockType"]))
        if _bool(b["data"], "randomization"):
            out.append(fact("Исследование", "рандомизировано", "да", b["instanceId"], b["blockType"]))
        if _bool(b["data"], "blinding"):
            out.append(fact("Исследование", "ослеплено", "да", b["instanceId"], b["blockType"]))
        return out

    # T12: Материалы
    def t12(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "materials")
        return [fact("Исследование", "материалы", v, b["instanceId"], b["blockType"])] if v else []

    # T13: Методы
    def t13(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        methods = _str(b["data"], "methods")
        if methods:
            out.append(fact("Исследование", "методы", methods, b["instanceId"], b["blockType"]))
        meas = _str(b["data"], "measurementMethods")
        if meas:
            out.append(fact("Исследование", "методы измерения", meas, b["instanceId"], b["blockType"]))
        return out

    # T14: Эксперимент
    def t14(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        data = b["data"]
        name = _str(data, "experimentName")
        exp_type = _str(data, "experimentType")
        outcomes = _str(data, "outcomes")
        steps = _str(data, "steps")
        findings = _str(data, "findings")
        duration = _str(data, "duration")
        exp_key = name or f"Эксперимент ({exp_type or 'без названия'})"

        if name:
            out.append(fact("Исследование", "эксперимент", name, b["instanceId"], b["blockType"]))
        if exp_type:
            out.append(fact(exp_key, "тип", exp_type, b["instanceId"], b["blockType"]))
        if outcomes:
            for outcome in re.split(r"[\n,;]", outcomes):
                outcome = outcome.strip()
                if outcome:
                    out.append(fact(exp_key, "измеряемые показатели", outcome, b["instanceId"], b["blockType"]))
        if steps:
            try:
                step_list = json.loads(steps)
                if isinstance(step_list, list):
                    for su in step_list:
                        if not isinstance(su, str):
                            continue
                        step_uuid = su.strip()
                        if step_uuid:
                            out.append(fact(b["instanceId"], "шаг", step_uuid, b["instanceId"], b["blockType"]))
            except (ValueError, TypeError):
                pass
        if findings:
            try:
                finding_list = json.loads(findings)
                if isinstance(finding_list, list):
                    for f in finding_list:
                        if not isinstance(f, str):
                            continue
                        finding_uuid = f.strip()
                        if finding_uuid:
                            out.append(fact(b["instanceId"], "результат", finding_uuid, b["instanceId"], b["blockType"]))
            except (ValueError, TypeError):
                pass
        if duration:
            out.append(fact(exp_key, "длительность", duration, b["instanceId"], b["blockType"]))

        def make_pairs(raw: str, role: str) -> None:
            try:
                pairs = json.loads(raw)
                if not isinstance(pairs, list):
                    return
                for pair in pairs:
                    if not isinstance(pair, dict):
                        continue
                    g = pair.get("groupRef") if isinstance(pair.get("groupRef"), str) else ""
                    iv = pair.get("interventionRef") if isinstance(pair.get("interventionRef"), str) else ""
                    g = g.strip()
                    iv = iv.strip()
                    if g:
                        out.append(fact(b["instanceId"], role, g, b["instanceId"], b["blockType"]))
                        if iv:
                            out.append(fact(g, "получает", iv, b["instanceId"], b["blockType"]))
            except (ValueError, TypeError):
                pass

        make_pairs(_str(data, "experimentalPairs"), "экспериментальная группа")
        make_pairs(_str(data, "controlPairs"), "контрольная группа")
        return out

    # T15: Критерии включения/исключения
    def t15(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        inc = _str(b["data"], "inclusionCriteria")
        if inc:
            out.append(fact("Исследование", "критерии включения", inc, b["instanceId"], b["blockType"]))
        exc = _str(b["data"], "exclusionCriteria")
        if exc:
            out.append(fact("Исследование", "критерии исключения", exc, b["instanceId"], b["blockType"]))
        return out

    # T16: Биологический механизм
    def t16(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "mechanism")
        out = [fact("Исследование", "биологический механизм", v, b["instanceId"], b["blockType"])] if v else []
        sequence_triplets(b, out)
        return out

    # T17: Объект воздействия
    def t17(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for key, label in (("cell", "клетка"), ("tissue", "ткань"), ("organ", "орган"),
                           ("pathway", "биологический путь"), ("substanceLevel", "уровень вещества")):
            v = _str(b["data"], key)
            if v:
                out.append(fact("Исследование", "объект воздействия: " + label, v,
                                b["instanceId"], b["blockType"]))
        return out

    # T18: Интервенция
    def t18(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        intervention = _str(b["data"], "intervention")
        if intervention:
            out.append(fact("Исследование", "интервенция", intervention, b["instanceId"], b["blockType"]))
        dosage = _str(b["data"], "dosage")
        if dosage:
            out.append(fact("Исследование", "дозировка", dosage, b["instanceId"], b["blockType"]))
        regimen = _str(b["data"], "dosageRegimen")
        if regimen:
            out.append(fact("Исследование", "режим дозировки", regimen, b["instanceId"], b["blockType"]))
        return out

    # T19: Животная модель
    def t19(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        species = _str(b["data"], "species")
        if species:
            out.append(fact("Исследование", "вид животного", species, b["instanceId"], b["blockType"]))
        timeline = _str(b["data"], "timeline")
        if timeline:
            out.append(fact("Исследование", "временная шкала модели", timeline, b["instanceId"], b["blockType"]))
        conditions = _str(b["data"], "conditions")
        if conditions:
            out.append(fact("Исследование", "условия содержания модели", conditions, b["instanceId"], b["blockType"]))
        return out

    # T21: Логика исследователя
    def t21(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "logic")
        return [fact("Исследование", "логика", v, b["instanceId"], b["blockType"])] if v else []

    # T22: Сущность (s/p/o)
    def t22(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = b["data"]
        s, p, o = _str(data, "subject"), _str(data, "predicate"), _str(data, "object")
        out = [fact(s, p, o, b["instanceId"], b["blockType"])] if s and p and o else []
        sequence_triplets(b, out)
        return out

    # T23: Определение понятия
    def t23(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        term = _str(b["data"], "term")
        definition = _str(b["data"], "definition")
        if term and definition:
            out.append(fact(term, "определяется как", definition, b["instanceId"], b["blockType"]))
        sequence_triplets(b, out)
        return out

    # T24: Предположения
    def t24(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [fact("Исследование", "предполагает", a, b["instanceId"], b["blockType"])
                for a in split_lines(b["data"].get("assumptions"))]

    # T25: Размер выборки
    def t25(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "sampleSize")
        return [fact("Исследование", "размер выборки", "n=" + v, b["instanceId"], b["blockType"])] if v else []

    # T26: Источники данных
    def t26(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [fact("Исследование", "источник данных", ds, b["instanceId"], b["blockType"])
                for ds in split_lines(b["data"].get("dataSources"))]

    # T27: p-value
    def t27(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "pValue")
        return [fact("Исследование", "p-value", v, b["instanceId"], b["blockType"])] if v else []

    # T28: Дисперсия
    def t28(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "variance")
        return [fact("Исследование", "дисперсия", v, b["instanceId"], b["blockType"])] if v else []

    # T29: Размер эффекта
    def t29(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "effectSize")
        if not v:
            return []
        effect_type = _str(b["data"], "effectType")
        label = f"размер эффекта ({effect_type})" if effect_type else "размер эффекта"
        return [fact("Исследование", label, v, b["instanceId"], b["blockType"])]

    # T30: Мощность исследования
    def t30(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "power")
        return [fact("Исследование", "мощность", v, b["instanceId"], b["blockType"])] if v else []

    # T31: Доверительный интервал
    def t31(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        lower = _str(b["data"], "ciLower")
        upper = _str(b["data"], "ciUpper")
        if not lower and not upper:
            return []
        level = _str(b["data"], "ciLevel") or "95%"
        return [fact("Исследование", f"доверительный интервал {level}",
                     f"[{lower}, {upper}]", b["instanceId"], b["blockType"])]

    # T32: Числа с названиями
    def t32(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [fact(key, "величина", value, b["instanceId"], b["blockType"])
                for key, value in kv_pairs(b["data"].get("namedNumbers"))]

    # T33: Формулы
    def t33(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        name = _str(b["data"], "formulaName")
        latex = _str(b["data"], "formulaLatex")
        if latex:
            label = name or "Формула"
            out.append(meta(label, "определяет", latex, b["instanceId"], b["blockType"]))
        for key, value in kv_pairs(b["data"].get("formulaVariables")):
            out.append(meta(name or "Формула", "переменная", f"{key} = {value}",
                            b["instanceId"], b["blockType"]))
        return out

    # T34: Каузальные графы (DAG)
    def t34(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        desc = _str(b["data"], "dagDescription")
        return [meta("Каузальный граф", "описывает", desc, b["instanceId"], b["blockType"])] if desc else []

    # T35: Критерии идентифицируемости Дж.Перла
    def t35(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "criteria")
        return [fact("Исследование", "критерии идентифицируемости", v, b["instanceId"], b["blockType"])] if v else []

    # T36: Результаты
    def t36(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        results = _str(b["data"], "results")
        if results:
            out.append(fact("Исследование", "результаты", results, b["instanceId"], b["blockType"]))
        summary = _str(b["data"], "resultsSummary")
        if summary:
            out.append(fact("Исследование", "краткое описание результатов", summary,
                            b["instanceId"], b["blockType"]))
        return out

    # T37: Статистическая обработка
    def t37(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        p = _str(b["data"], "statProcessing")
        if p:
            out.append(fact("Исследование", "статистическая обработка", p, b["instanceId"], b["blockType"]))
        comp = _str(b["data"], "expectationsComparison")
        if comp:
            out.append(fact("Исследование", "сопоставление с ожиданиями", comp, b["instanceId"], b["blockType"]))
        sequence_triplets(b, out)
        return out

    # T38: Утверждения
    def t38(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = b["data"]
        s = _str(data, "claimSubject")
        p = _str(data, "claimPredicate")
        o = _str(data, "claimObject")
        if not s or not p or not o:
            return []
        negated = _bool(data, "isNegated")
        predicate = f"не {p}" if negated else p
        notes = _str(data, "confidenceNotes")
        confidence = 0.8 if notes else 1.0
        out = [fact(s, predicate, o, b["instanceId"], b["blockType"], confidence)]
        if notes:
            out.append(meta(s, "уверенность", notes, b["instanceId"], b["blockType"]))
        sequence_triplets(b, out)
        return out

    # T39: Ограничения исследования
    def t39(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "limitations")
        out = [fact("Исследование", "ограничения", v, b["instanceId"], b["blockType"])] if v else []
        sequence_triplets(b, out)
        return out

    # T40: Побочные выводы/гипотезы
    def t40(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "sideFindings")
        out = [fact("Исследование", "побочные выводы", v, b["instanceId"], b["blockType"])] if v else []
        sequence_triplets(b, out)
        return out

    # T41: Сопутствующие эффекты
    def t41(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "sideEffects")
        return [fact("Исследование", "побочные эффекты", v, b["instanceId"], b["blockType"])] if v else []

    # T42: Утверждения после исследования
    def t42(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        claims = _str(b["data"], "postClaims")
        if claims:
            for line in split_lines(claims):
                out.append(fact("После исследования", "утверждает", line, b["instanceId"], b["blockType"]))
        comp = _str(b["data"], "comparisonWithExpectations")
        if comp:
            out.append(fact("Исследование", "сравнение результатов с ожиданиями", comp,
                            b["instanceId"], b["blockType"]))
        return out

    # T43: Оставшиеся вопросы
    def t43(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "openQuestions")
        return [fact("Исследование", "открытые вопросы", v, b["instanceId"], b["blockType"])] if v else []

    # T44: Новизна
    def t44(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "novelty")
        out = [fact("Исследование", "новизна", v, b["instanceId"], b["blockType"])] if v else []
        sequence_triplets(b, out)
        return out

    # T45: Версии
    def t45(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [fact("Исследование", f"версия: {key}", value, b["instanceId"], b["blockType"])
                for key, value in kv_pairs(b["data"].get("versions"))]

    # T46: Предложения для будущих исследований
    def t46(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = [fact("Исследование", "предложение для будущих исследований", r,
                    b["instanceId"], b["blockType"])
               for r in split_lines(b["data"].get("futureResearch"))]
        sequence_triplets(b, out)
        return out

    # T47: Связи с предыдущими исследованиями
    def t47(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = [fact("Исследование", "ссылается на", ref, b["instanceId"], b["blockType"])
               for ref in split_lines(b["data"].get("references"))]
        sequence_triplets(b, out)
        return out

    # T48: Связь со старением
    def t48(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "agingConnection")
        return [fact("Исследование", "связь со старением", v, b["instanceId"], b["blockType"])] if v else []

    # T49: Изображение
    def t49(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        image_key = _str(b["data"], "imageKey")
        if image_key:
            out.append(fact("Исследование", "изображение", image_key, b["instanceId"], b["blockType"]))
        caption = _str(b["data"], "caption")
        if caption and image_key:
            out.append(fact(image_key, "подпись", caption, b["instanceId"], b["blockType"]))
        for ref in split_lines(b["data"].get("imageRefs")):
            out.append(fact("Исследование", "изображение", ref, b["instanceId"], b["blockType"]))
        return out

    # T50: Код
    def t50(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        lang = _str(b["data"], "codeLanguage")
        code = _str(b["data"], "code")
        if not code:
            return []
        return [fact("Исследование", f"код ({lang or 'неизвестный язык'})", code,
                     b["instanceId"], b["blockType"])]

    # T51: Источники финансирования
    def t51(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [fact("Исследование", "источник финансирования", f, b["instanceId"], b["blockType"])
                for f in split_lines(b["data"].get("funding"))]

    # T52: Конфликт интересов
    def t52(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        v = _str(b["data"], "conflictOfInterest")
        return [fact("Исследование", "конфликт интересов", v, b["instanceId"], b["blockType"])] if v else []

    # T53: Информационная ценность
    def t53(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for key, label in (("uncertaintyReduced", "уменьшило неопределённость"),
                           ("hypothesesExcluded", "исключило гипотезы"),
                           ("hypothesesProbabilized", "сделало гипотезы вероятнее"),
                           ("newHypotheses", "породило новые гипотезы"),
                           ("nextExperiment", "следующий оптимальный эксперимент")):
            v = _str(b["data"], key)
            if v:
                out.append(fact("Исследование", label, v, b["instanceId"], b["blockType"]))
        return out

    # T54: Действие (s/p/o)
    def t54(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = b["data"]
        s, p, o = _str(data, "subject"), _str(data, "predicate"), _str(data, "object")
        out = [fact(s, p, o, b["instanceId"], b["blockType"])] if s and p and o else []
        sequence_triplets(b, out)
        return out

    # T55: Группа животных
    def t55(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        name = _str(b["data"], "groupName")
        if name:
            out.append(fact("Исследование", "группа животных", name, b["instanceId"], b["blockType"]))
        n = _str(b["data"], "n")
        if n:
            out.append(fact(name or "Группа", "размер выборки", n, b["instanceId"], b["blockType"]))
        purpose = _str(b["data"], "purpose")
        if purpose:
            out.append(fact(name or "Группа", "назначение", purpose, b["instanceId"], b["blockType"]))
        return out

    # T56: Шаг эксперимента
    def t56(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        step_name = _str(b["data"], "stepName")
        if step_name:
            out.append(fact(b["instanceId"], "шаг", step_name, b["instanceId"], b["blockType"]))
        details = _str(b["data"], "details")
        if details:
            out.append(fact(step_name or "Шаг", "детали", details, b["instanceId"], b["blockType"]))
        duration = _str(b["data"], "duration")
        if duration:
            out.append(fact(step_name or "Шаг", "длительность шага", duration, b["instanceId"], b["blockType"]))
        sequence_triplets(b, out)
        return out

    # T57: Результат (находка)
    def t57(b: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        data = b["data"]
        parameter = _str(data, "parameter")
        if not parameter:
            return []
        direction = _str(data, "direction")
        subject_ref = _str(data, "subjectRef")
        comparison_ref = _str(data, "comparisonRef")
        significance = _str(data, "significance")
        p_value = _str(data, "pValue")
        figure_ref = _str(data, "figureRef")
        detail = _str(data, "detail")

        dir_map = {
            "повышено": "повышено в",
            "понижено": "понижено в",
            "без изменений": "без изменений в",
            "тренд": "тренд в",
        }
        predicate = dir_map.get(direction, "изменено в")
        target = subject_ref or "исследовании"
        out.append(fact(parameter, predicate, target, b["instanceId"], b["blockType"]))
        if comparison_ref:
            out.append(meta(parameter, "по сравнению с", comparison_ref, b["instanceId"], b["blockType"]))
        if significance:
            out.append(meta(parameter, "значимость", significance, b["instanceId"], b["blockType"]))
        if p_value:
            out.append(meta(parameter, "p-value", p_value, b["instanceId"], b["blockType"]))
        if figure_ref:
            out.append(meta(parameter, "рисунок", figure_ref, b["instanceId"], b["blockType"]))
        if detail:
            out.append(meta(parameter, "детали", detail, b["instanceId"], b["blockType"]))
        sequence_triplets(b, out)
        return out

    c[1] = t1
    c[2] = t2
    c[4] = t4
    c[5] = t5
    c[6] = t6
    c[7] = t7
    c[8] = t8
    c[9] = t9
    c[10] = t10
    c[11] = t11
    c[12] = t12
    c[13] = t13
    c[14] = t14
    c[15] = t15
    c[16] = t16
    c[17] = t17
    c[18] = t18
    c[19] = t19
    c[21] = t21
    c[22] = t22
    c[23] = t23
    c[24] = t24
    c[25] = t25
    c[26] = t26
    c[27] = t27
    c[28] = t28
    c[29] = t29
    c[30] = t30
    c[31] = t31
    c[32] = t32
    c[33] = t33
    c[34] = t34
    c[35] = t35
    c[36] = t36
    c[37] = t37
    c[38] = t38
    c[39] = t39
    c[40] = t40
    c[41] = t41
    c[42] = t42
    c[43] = t43
    c[44] = t44
    c[45] = t45
    c[46] = t46
    c[47] = t47
    c[48] = t48
    c[49] = t49
    c[50] = t50
    c[51] = t51
    c[52] = t52
    c[53] = t53
    c[54] = t54
    c[55] = t55
    c[56] = t56
    c[57] = t57
    return c


CONVERTERS: Dict[int, ConverterFn] = _converters()


# ═══════════════════════════════════════════════════════════════════
# Основная функция: блоки → триплеты
# ═══════════════════════════════════════════════════════════════════

def _statement_key(s: Dict[str, Any]) -> str:
    return f"{s.get('subject_text', '')}\u0000{s.get('predicate', '')}\u0000{s.get('object_text', '')}"


def blocks_to_statements(
    blocks: Sequence[Dict[str, Any]],
    article_uuid: Optional[str] = None,
    existing_statements: Optional[Sequence[Dict[str, Any]]] = None,
    resolve_refs: bool = True,
) -> List[Dict[str, Any]]:
    """Порт ``blocksToStatements`` из blockConverter.ts (канонический).

    ``existing_statements`` — сохранённые стейтменты статьи (с полем ``id``),
    для сохранения стабильных id при повторных конвертациях.
    """
    id_map: Dict[str, List[str]] = {}
    if existing_statements:
        for stmt in existing_statements:
            sid = stmt.get("id")
            block_id = stmt.get("sourceBlockId")
            if not sid or not block_id:
                continue
            id_map.setdefault(block_id, []).append(sid)

    all_triplets: List[Dict[str, Any]] = []
    sorted_blocks = sorted(blocks, key=lambda b: int(b.get("order", 0)))

    for block in sorted_blocks:
        converter = CONVERTERS.get(int(block.get("blockType", 0)))
        if not converter:
            continue
        block_triplets = converter(block)
        ids = id_map.get(block.get("instanceId"))
        if ids:
            for i in range(min(len(block_triplets), len(ids))):
                block_triplets[i]["id"] = ids[i]
        all_triplets.extend(block_triplets)

    # blockNameMap: instanceId → имя блока (для резолва UUID-ссылок)
    block_name_map: Dict[str, str] = {}
    for block in blocks:
        name_field = find_name_field(int(block.get("blockType", 0)), block.get("data") or {})
        if name_field:
            value = block["data"].get(name_field)
            if isinstance(value, str):
                block_name_map[block["instanceId"]] = value.strip()

    ref_map: Dict[str, str] = {}
    for t in all_triplets:
        ref_map[t["sourceBlockId"]] = block_name_map.get(t["sourceBlockId"], t["subject_text"])
        ref_map[t["id"]] = t["subject_text"]
    for block in blocks:
        name = block_name_map.get(block["instanceId"])
        if name:
            ref_map[block["instanceId"]] = name
    if existing_statements:
        for s in existing_statements:
            if s.get("id"):
                ref_map[s["id"]] = s.get("subject_text", "")

    if resolve_refs:
        for t in all_triplets:
            s_res = ref_map.get(t["subject_text"])
            if s_res:
                t["subject_text"] = s_res
            if t["predicate"] not in ("результат", "шаг"):
                o_res = ref_map.get(t["object_text"])
                if o_res:
                    t["object_text"] = o_res

    if article_uuid:
        for t in all_triplets:
            if t["subject_text"] == "Статья":
                t["subject_text"] = article_uuid

    if existing_statements:
        existing_map: Dict[str, str] = {}
        for s in existing_statements:
            if not s.get("id"):
                continue
            key = _statement_key(s)
            if key not in existing_map:
                existing_map[key] = s["id"]
        for t in all_triplets:
            existing_id = existing_map.get(_statement_key(t))
            if existing_id:
                t["id"] = existing_id

    return all_triplets


def blocks_to_statements_raw(
    blocks: Sequence[Dict[str, Any]],
    article_uuid: Optional[str] = None,
    existing_statements: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Триплеты без резолва UUID-ссылок (для панели «Триплеты»)."""
    return blocks_to_statements(
        blocks, article_uuid=article_uuid,
        existing_statements=existing_statements,
        resolve_refs=False,
    )
