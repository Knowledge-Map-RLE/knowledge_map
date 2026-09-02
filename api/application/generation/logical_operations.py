"""
Генерация знаний: логические операции над утверждениями.

Операции работают над списком утверждений (триплетов) одной статьи/корпуса и
порождают новые утверждения в соответствии с законами логики:

  * Transitivity (гипотетический силлогизм):  A→B и B→C  ⇒  A→C
  * Contraposition: условное 'A→B' эквивалентно обратному отрицанию 'not B → not A'
  * PredicateInference (обращение/инверсия): для симметричных предикатов
    'A affects B' ⇒ 'B affected-by A' (по таблице обратимых предикатов)
  * Conjunction (конъюнкция посылок): из A и B ⇒ комбинированное утверждение
  * Negation: предикат → отрицательная форма (для проверки/вывода отрицания)
  * ChainInference (цепочка причинности): A→B, B→C ⇒ причинная связь A→C
    с приоритетом предикатов причины/следствия.

Каждая операция оформлена отдельным классом с единым интерфейсом:
  name, label, run(statements, limit) → генератор результатов.
"""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional, Sequence

from application.generation.provenance import LOGICAL
from application.generation.provenance import build_knowledge_result
from application.generation.statements import negated_form, unique_triplets

# Предикаты, для которых есть "обратное" направление (predicate → reverse predicate).
_REVERSE_PREDICATES = {
    "affects": "is affected by",
    "causes": "is caused by",
    "activates": "is activated by",
    "inhibits": "is inhibited by",
    "regulates": "is regulated by",
    "upregulates": "is upregulated by",
    "downregulates": "is downregulated by",
    "increases": "is increased by",
    "decreases": "is decreased by",
    "promotes": "is promoted by",
    "suppresses": "is suppressed by",
    "correlates": "correlates with",
    "interacts with": "interacts with",
    "requires": "is required by",
}

# Предикаты причинной/следственной связи для ChainInference.
_CAUSE_PREDICATES = {"causes", "leads to", "results in", "triggers", "induces", "promotes", "activates"}
_EFFECT_PREDICATES = {"causes", "leads to", "results in", "triggers", "induces", "promotes", "activates"}

# Предикаты, для которых логично строить транзитивную цепочку (A→B, B→C ⇒ A→C).
_TRANSITIVE_PREDICATES = {
    "causes", "leads to", "results in", "triggers", "induces",
    "activates", "increases", "promotes", "affects", "is a cause of",
}


def _t(self_subj: str, pred: str, self_obj: str, **extra: Any) -> Dict[str, Any]:
    base = {"subject_text": str(self_subj), "predicate": pred, "object_text": str(self_obj)}
    base.update(extra)
    return base


def _a(subj: str, pred: str, obj: str) -> Dict[str, Any]:
    return {"subject_text": subj, "predicate": pred, "object_text": obj}


class Transitivity:
    """Гипотетический силлогизм: A→B и B→C ⇒ A→C.

    Применимо к предикатам из _TRANSITIVE_PREDICATES, где предикат цепочки
    совпадает или является причинным.
    """

    name = "transitivity"
    label = "Транзитивность (A→B, B→C ⇒ A→C)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_subj: Dict[str, List[Dict[str, Any]]] = {}
        for st in statements:
            by_subj.setdefault(str(st.get("subject_text") or "").strip().lower(), []).append(st)
        produced = set()
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            if pred not in _TRANSITIVE_PREDICATES:
                continue
            a = str(st.get("subject_text") or "").strip()
            b = str(st.get("object_text") or "").strip()
            b_key = b.lower()
            for nxt in by_subj.get(b_key, []):
                npred = str(nxt.get("predicate") or "").strip().lower()
                if npred not in _TRANSITIVE_PREDICATES:
                    continue
                c = str(nxt.get("object_text") or "").strip()
                if not a or not b or not c or a.lower() == c.lower():
                    continue
                if a.lower() == b.lower() or b.lower() == c.lower():
                    continue
                # вывод по предикату следующего звена (A --next--> C)
                key = (a.lower(), npred, c.lower())
                if key in produced:
                    continue
                produced.add(key)
                new = _a(a, npred, c)
                yield build_knowledge_result(
                    method=LOGICAL,
                    operation=self.name,
                    operation_label=self.label,
                    source_statements=[st, nxt],
                    new_statements=[new],
                    description=(
                        f"Транзитивность: из «{st.get('subject_text')} —[{pred}]→ "
                        f"{b}» и «{b} —[{npred}]→ {c}» следует «{a} —[{npred}]→ {c}»."
                    ),
                )
                if len(produced) >= limit:
                    return


class Contraposition:
    """Контрапозиция: условное 'A→B' даёт 'not B → not A'.

    Применимо к предикатам с известной отрицательной формой.
    """

    name = "contraposition"
    label = "Контрапозиция (A→B ⇒ ¬B→¬A)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            neg = negated_form(pred)
            if not neg:
                continue
            a = str(st.get("subject_text") or "").strip()
            b = str(st.get("object_text") or "").strip()
            if not a or not b or a.lower() == b.lower():
                continue
            new = _a(b, neg, a)
            yield build_knowledge_result(
                method=LOGICAL,
                operation=self.name,
                operation_label=self.label,
                source_statements=[st],
                new_statements=[new],
                description=f"Контрапозиция: из «{a} —[{pred}]→ {b}» следует «{b} —[{neg}]→ {a}».",
            )
            if limit and limit <= 0:
                return


class PredicateInference:
    """Обращение предиката: 'A affects B' ⇒ 'B is affected by A'.

    Для предикатов из _REVERSE_PREDICATES.
    """

    name = "predicate_inference"
    label = "Обращение предиката (A→B ⇒ B→обратнопредикат A)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            rev = _REVERSE_PREDICATES.get(pred)
            if not rev:
                continue
            a = str(st.get("subject_text") or "").strip()
            b = str(st.get("object_text") or "").strip()
            if not a or not b or a.lower() == b.lower():
                continue
            new = _a(b, rev, a)
            yield build_knowledge_result(
                method=LOGICAL,
                operation=self.name,
                operation_label=self.label,
                source_statements=[st],
                new_statements=[new],
                description=f"Обращение: из «{a} —[{pred}]→ {b}» следует «{b} —[{rev}]→ {a}».",
            )
            if limit and limit <= 0:
                return


class ChainInference:
    """Причинная цепочка: A→B и B→C ⇒ причинная связь A→C."""

    name = "chain_inference"
    label = "Причинная цепочка (A→B, B→C ⇒ A причинно связан с C)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_subj: Dict[str, List[Dict[str, Any]]] = {}
        for st in statements:
            by_subj.setdefault(str(st.get("subject_text") or "").strip().lower(), []).append(st)
        produced = set()
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            if pred not in _EFFECT_PREDICATES:
                continue
            a = str(st.get("subject_text") or "").strip()
            b = str(st.get("object_text") or "").strip()
            for nxt in by_subj.get(b.lower(), []):
                npred = str(nxt.get("predicate") or "").strip().lower()
                if npred not in _EFFECT_PREDICATES:
                    continue
                c = str(nxt.get("object_text") or "").strip()
                if not a or not b or not c or a.lower() == c.lower():
                    continue
                if a.lower() == b.lower() or b.lower() == c.lower():
                    continue
                key = (a.lower(), "causes", c.lower())
                if key in produced:
                    continue
                produced.add(key)
                new = _a(a, "causes", c)
                yield build_knowledge_result(
                    method=LOGICAL,
                    operation=self.name,
                    operation_label=self.label,
                    source_statements=[st, nxt],
                    new_statements=[new],
                    description=f"Причинная цепочка: «{a}→{b}» и «{b}→{c}» ⇒ «{a} causes {c}».",
                )
                if limit and limit <= 0:
                    return


class Conjunction:
    """Конъюнкция посылок: из утверждений 'A r B' и 'A s C' — комбинированное.

    Для утверждений с общим субъектом формирует связку 'B and C' как объект.
    """

    name = "conjunction"
    label = "Конъюнкция (объединение посылок по общему субъекту)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_subj: Dict[str, List[Dict[str, Any]]] = {}
        for st in statements:
            by_subj.setdefault(str(st.get("subject_text") or "").strip().lower(), []).append(st)
        produced = set()
        for subj_key, group in by_subj.items():
            if len(group) < 2:
                continue
            subj = str(group[0].get("subject_text") or "").strip()
            combined_objs = [str(st.get("object_text") or "").strip() for st in group[:3]]
            combined_objs = [o for o in combined_objs if o]
            if len(combined_objs) < 2:
                continue
            new_obj = ", ".join(dict.fromkeys(combined_objs))  # уникальные, сохраняем порядок
            key = (subj.lower(), "involves", new_obj.lower())
            if key in produced:
                continue
            produced.add(key)
            new = _a(subj, "involves", new_obj)
            yield build_knowledge_result(
                method=LOGICAL,
                operation=self.name,
                operation_label=self.label,
                source_statements=group,
                new_statements=[new],
                description=f"Конъюнкция: субъект «{subj}» связан с {len(combined_objs)} объектами ⇒ "
                            f"«{subj} involves {new_obj}».",
            )
            if limit and limit <= 0:
                return


class Negation:
    """Отрицание: предикат → отрицательная форма (для проверки/вывода)."""

    name = "negation"
    label = "Отрицание (предикат → отрицательная форма)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            neg = negated_form(pred)
            if not neg:
                continue
            a = str(st.get("subject_text") or "").strip()
            b = str(st.get("object_text") or "").strip()
            if not a or not b:
                continue
            new = _a(a, neg, b)
            yield build_knowledge_result(
                method=LOGICAL,
                operation=self.name,
                operation_label=self.label,
                source_statements=[st],
                new_statements=[new],
                description=f"Отрицание: из «{a} —[{pred}]→ {b}» выводится «{a} —[{neg}]→ {b}» (как проверочное).",
            )
            if limit and limit <= 0:
                return


_OPERATIONS = [
    Transitivity,
    ChainInference,
    Contraposition,
    PredicateInference,
    Conjunction,
    Negation,
]


def logical_operations() -> List[str]:
    """Список идентификаторов доступных логических операций."""
    return [cls.name for cls in _OPERATIONS]


def run_logical_operations(
    statements: Sequence[Dict[str, Any]],
    *,
    operation: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Выполняет логические операции над утверждениями.

    Args:
        statements: исходные утверждения (целевой документ или корпус).
        operation: если задан — только конкретная операция; иначе все.
        limit: суммарный лимит результатов.
    """
    results: List[Dict[str, Any]] = []
    for cls in _OPERATIONS:
        if operation and cls.name != operation:
            continue
        per_remaining = max(1, limit - len(results))
        results.extend(list(cls().run(statements, limit=per_remaining)))
        if len(results) >= limit:
            break
    return results
