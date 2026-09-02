"""
Генерация знаний: операции мышления (расширенный набор + причинно-следственные).

Операции мышления — способы обработки информации человеком, применяемые здесь к
утверждениям (триплетам) статьи/корпуса для получения нового знания:

  * Analysis      — анализ: разложение утверждения на компоненты (субъект/объект)
  * Synthesis     — синтез: объединение нескольких утверждений в одно
  * Comparison    — сравнение: выделение общего признака у двух субъектов
  * Abstraction   — абстрагирование: выделение обобщающего понятия-категории
  * Generalization— обобщение: из многих частных утверждений — общее
  * Concretization— конкретизация: из общего — частное применение
  * Induction     — индукция: из частных фактов — вероятный общий паттерн
  * Deduction     — дедукция: из общего правила — частный случай
  * Analogy       — аналогия: перенос признака по сходству двух субъектов
  * Causality     — причинность: восстановление причинно-следственной связи
  * Counterfactual— контрфактическая оценка: «что было бы, если бы предикат иной»
  * Classification— классификация: отнесение субъекта к категории

Каждый класс операции имеет интерфейс name/label/run.
"""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional, Sequence

from application.generation.provenance import THINKING
from application.generation.provenance import build_knowledge_result
from application.generation.statements import is_category_edge, negated_form

# Предикаты взаимодействия (для синтеза/аналогии/сравнения)
_INTERACTION = {"affects", "regulates", "interacts with", "activates", "inhibits",
                "increases", "decreases", "promotes", "suppresses", "correlates"}
_CAUSAL = {"causes", "leads to", "results in", "triggers", "induces", "activates",
           "promotes", "increases", "upregulates"}


def _a(subj: str, pred: str, obj: str) -> Dict[str, Any]:
    return {"subject_text": subj, "predicate": pred, "object_text": obj}


class Analysis:
    """Разложение утверждения: выделить субъект и объект анализа."""

    name = "analysis"
    label = "Анализ (разложение утверждения на компоненты)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        produced = set()
        for st in statements:
            subj = str(st.get("subject_text") or "").strip()
            obj = str(st.get("object_text") or "").strip()
            if not subj or not obj:
                continue
            if subj.lower() == obj.lower():
                continue
            key = ("analyzes", subj.lower(), obj.lower())
            if key in produced:
                continue
            produced.add(key)
            new = _a(subj, "relates to", obj)
            yield build_knowledge_result(
                method=THINKING,
                operation=self.name,
                operation_label=self.label,
                source_statements=[st],
                new_statements=[new],
                description=f"Анализ утверждения «{subj} —[{st.get('predicate')}]→ {obj}»: субъект «{subj}» "
                            f"аналитически соотносится с объектом «{obj}».",
            )
            if len(produced) >= limit:
                return


class Synthesis:
    """Синтез: объединить несколько утверждений с общим субъектом в одно знание."""

    name = "synthesis"
    label = "Синтез (объединение утверждений в новое знание)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_subj: Dict[str, List[Dict[str, Any]]] = {}
        for st in statements:
            key = str(st.get("subject_text") or "").strip().lower()
            if key:
                by_subj.setdefault(key, []).append(st)
        produced = set()
        for subj_key, group in by_subj.items():
            if len(group) < 2:
                continue
            subj = str(group[0].get("subject_text") or "").strip()
            objs = [str(st.get("object_text") or "").strip() for st in group[:3] if str(st.get("object_text") or "").strip()]
            if len(set(objs)) < 2:
                continue
            combined = ", ".join(dict.fromkeys(objs))
            key = (subj_key, combined.lower())
            if key in produced:
                continue
            produced.add(key)
            new = _a(subj, "encompasses", combined)
            yield build_knowledge_result(
                method=THINKING,
                operation=self.name,
                operation_label=self.label,
                source_statements=group,
                new_statements=[new],
                description=f"Синтез: субъект «{subj}» имеет {len(objs)} утверждений ⇒ «{subj} encompasses {combined}».",
            )
            if len(produced) >= limit:
                return


class Comparison:
    """Сравнение: два субъекта с общим предикатом — вывести сравнение."""

    name = "comparison"
    label = "Сравнение (общий признак двух субъектов)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_pred: Dict[str, List[Dict[str, Any]]] = {}
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            if pred:
                by_pred.setdefault(pred, []).append(st)
        produced = set()
        for pred, group in by_pred.items():
            subj_objs = set()
            for st in group:
                subj_objs.add(
                    (str(st.get("subject_text") or "").strip().lower(),
                     str(st.get("object_text") or "").strip().lower())
                )
            if len(subj_objs) < 2:
                continue
            # возьмём первую пару различных субъектов
            pairs = list(subj_objs)
            s1, o1 = pairs[0]
            for s2, o2 in pairs[1:]:
                if s1 == s2:
                    continue
                key = ("compare", s1, s2)
                if key in produced:
                    continue
                produced.add(key)
                new = _a(s1.capitalize() if s1 else s1, "is comparable to (by " + pred + ")", s2.capitalize() if s2 else s2)
                yield build_knowledge_result(
                    method=THINKING,
                    operation=self.name,
                    operation_label=self.label,
                    source_statements=[group[0], next(x for x in group if str(x.get("subject_text") or "").strip().lower() == s2)],
                    new_statements=[new],
                    description=f"Сравнение: «{s1}» и «{s2}» оба участвуют в «{pred}» ⇒ их можно сравнивать по этому признаку.",
                )
                if len(produced) >= limit:
                    return


class Abstraction:
    """Абстрагирование: из конкретных субъектов с общим предикатом — категория."""

    name = "abstraction"
    label = "Абстрагирование (выделение обобщающего признака)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_pred: Dict[str, List[str]] = {}
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            subj = str(st.get("subject_text") or "").strip()
            if pred and subj:
                by_pred.setdefault(pred, []).append(subj)
        produced = set()
        for pred, subs in by_pred.items():
            uniq = list(dict.fromkeys(subs))
            if len(uniq) < 2:
                continue
            key = (pred, tuple(sorted(u.lower() for u in uniq)))
            if key in produced:
                continue
            produced.add(key)
            abstracts = " and ".join(uniq[:3])
            new = _ah("совокупность участников отношения", pred, abstracts)
            yield build_knowledge_result(
                method=THINKING,
                operation=self.name,
                operation_label=self.label,
                source_statements=[{"subject_text": s, "predicate": pred, "object_text": ""} for s in uniq[:3]],
                new_statements=[new],
                description=f"Абстрагирование: субъекты «{', '.join(uniq[:3])}» объединены предикатом «{pred}» ⇒ "
                            f"абстрактная категория «совокупность участников отношения {pred}».",
            )
            if len(produced) >= limit:
                return


def _ah(subj: str, pred: str, obj: str) -> Dict[str, Any]:
    return {"subject_text": subj, "predicate": pred, "object_text": obj}


class Generalization:
    """Обобщение: из многих конкретных утверждений вывести общее правило."""

    name = "generalization"
    label = "Обобщение (из частных утверждений — общее правило)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_pred: Dict[str, List[str]] = {}
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            subj = str(st.get("subject_text") or "").strip()
            if pred and subj:
                by_pred.setdefault(pred, []).append(subj)
        produced = set()
        for pred, subs in by_pred.items():
            uniq = list(dict.fromkeys(subs))
            if len(uniq) < 2:
                continue
            key = (pred, tuple(sorted(u.lower() for u in uniq)))
            if key in produced:
                continue
            produced.add(key)
            new = _a("в общем случае", pred, "влияет на соответствующие объекты")
            yield build_knowledge_result(
                method=THINKING,
                operation=self.name,
                operation_label=self.label,
                source_statements=[{"subject_text": s, "predicate": pred, "object_text": "..."} for s in uniq[:4]],
                new_statements=[new],
                description=f"Обобщение: предикат «{pred}» устойчиво наблюдается у {len(uniq)} субъектов "
                            f"(«{', '.join(uniq[:4])}») ⇒ общее правило о влиянии «{pred}».",
            )
            if len(produced) >= limit:
                return


class Concretization:
    """Конкретизация: из категориального утверждения — конкретные вхождения."""

    name = "concretization"
    label = "Конкретизация (из категории — конкретное утверждение)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        produced = set()
        for st in statements:
            if not is_category_edge(st.get("predicate")):
                continue
            subj = str(st.get("subject_text") or "").strip()
            obj = str(st.get("object_text") or "").strip()
            if not subj or not obj or subj.lower() == obj.lower():
                continue
            key = ("concrete", subj.lower(), obj.lower())
            if key in produced:
                continue
            produced.add(key)
            new = _a(subj, "участвует в категории", obj)
            yield build_knowledge_result(
                method=THINKING,
                operation=self.name,
                operation_label=self.label,
                source_statements=[st],
                new_statements=[new],
                description=f"Конкретизация: категориальное «{subj} {st.get('predicate')} {obj}» ⇒ "
                            f"субъект «{subj}» конкретно участвует в категории «{obj}».",
            )
            if len(produced) >= limit:
                return


class Induction:
    """Индукция: из частных фактов вывести вероятный общий паттерн."""

    name = "induction"
    label = "Индукция (частные факты → общий паттерн)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_pred: Dict[str, List[str]] = {}
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            subj = str(st.get("subject_text") or "").strip()
            if pred and subj:
                by_pred.setdefault(pred, []).append(subj)
        produced = set()
        for pred, subs in by_pred.items():
            uniq = list(dict.fromkeys(subs))
            if len(uniq) >= 2:
                key = ("induction", pred)
                if key in produced:
                    continue
                produced.add(key)
                new = _a("множество субъектов с предикатом «" + pred + "»", "индуцирует", "паттерн " + pred)
                yield build_knowledge_result(
                    method=THINKING,
                    operation=self.name,
                    operation_label=self.label,
                    source_statements=[{"subject_text": s, "predicate": pred, "object_text": ""} for s in uniq[:4]],
                    new_statements=[new],
                    description=f"Индукция: предикат «{pred}» встречается у {len(uniq)} субъектов "
                                f"(«{', '.join(uniq[:4])}») ⇒ вероятный общий паттерн.",
                )
                if len(produced) >= limit:
                    return


class Deduction:
    """Дедукция: из категориального общего — конкретный вывод."""

    name = "deduction"
    label = "Дедукция (общее правило → частный случай)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        produced = set()
        cats = [st for st in statements if is_category_edge(st.get("predicate"))]
        for cat in cats:
            subj = str(cat.get("subject_text") or "").strip()
            obj = str(cat.get("object_text") or "").strip()
            if not subj or not obj:
                continue
            # для каждого субъекта, который входит в obj, выводим принадлежность к obj
            for st in statements:
                if st is cat:
                    continue
                other_subj = str(st.get("subject_text") or "").strip()
                other_obj = str(st.get("object_text") or "").strip()
                if other_subj.lower() == subj.lower():
                    key = ("deduct", other_obj.lower(), obj.lower())
                    if key in produced:
                        continue
                    produced.add(key)
                    new = _a(other_obj, "is_a", obj)
                    yield build_knowledge_result(
                        method=THINKING,
                        operation=self.name,
                        operation_label=self.label,
                        source_statements=[cat, st],
                        new_statements=[new],
                        description=f"Дедукция: из категориального «{subj} is_a {obj}» и утверждения про «{subj}» "
                                    f"⇒ «{other_obj} is_a {obj}».",
                    )
                    if len(produced) >= limit:
                        return


class Analogy:
    """Аналогия: перенос признака с одного субъекта на сходный по предикату."""

    name = "analogy"
    label = "Аналогия (перенос признака по сходству)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_pred: Dict[str, List[str]] = {}
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            if pred not in _INTERACTION:
                continue
            subj = str(st.get("subject_text") or "").strip()
            obj = str(st.get("object_text") or "").strip()
            if subj and obj:
                by_pred.setdefault(pred, []).append((subj, obj))
        produced = set()
        for pred, pairs in by_pred.items():
            uniq = list(dict.fromkeys(pairs))
            if len(uniq) < 2:
                continue
            s1, o1 = uniq[0]
            for s2, o2 in uniq[1:]:
                if s1 == s2:
                    continue
                key = ("analogy", s1.lower(), s2.lower(), o1.lower())
                if key in produced:
                    continue
                produced.add(key)
                new = _a(s2, "likely also " + pred, o1)
                yield build_knowledge_result(
                    method=THINKING,
                    operation=self.name,
                    operation_label=self.label,
                    source_statements=[
                        {"subject_text": s1, "predicate": pred, "object_text": o1},
                        {"subject_text": s2, "predicate": pred, "object_text": o2},
                    ],
                    new_statements=[new],
                    description=f"Аналогия: «{s1} {pred} {o1}» и «{s2} {pred} {o2}»; по сходству предиката "
                                f"переносим признак: «{s2} likely also {pred} {o1}».",
                )
                if len(produced) >= limit:
                    return


class Causality:
    """Причинность: восстановление причинно-следственной связи цепочки."""

    name = "causality"
    label = "Причинность (восстановление причинной связи A→C)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        by_subj: Dict[str, List[Dict[str, Any]]] = {}
        for st in statements:
            by_subj.setdefault(str(st.get("subject_text") or "").strip().lower(), []).append(st)
        produced = set()
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            if pred not in _CAUSAL:
                continue
            a = str(st.get("subject_text") or "").strip()
            b = str(st.get("object_text") or "").strip()
            for nxt in by_subj.get(b.lower(), []):
                npred = str(nxt.get("predicate") or "").strip().lower()
                if npred not in _CAUSAL:
                    continue
                c = str(nxt.get("object_text") or "").strip()
                if not a or not b or not c or a.lower() == c.lower():
                    continue
                key = ("causal", a.lower(), c.lower())
                if key in produced:
                    continue
                produced.add(key)
                new = _a(a, "causes", c)
                yield build_knowledge_result(
                    method=THINKING,
                    operation=self.name,
                    operation_label=self.label,
                    source_statements=[st, nxt],
                    new_statements=[new],
                    description=f"Причинность: «{a}→{b}» и «{b}→{c}» ⇒ причинная связь «{a} causes {c}».",
                )
                if len(produced) >= limit:
                    return


class Counterfactual:
    """Контрфактическая оценка: что было бы, если бы предикат был иным."""

    name = "counterfactual"
    label = "Контрфактическая оценка (инверсия предиката)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        produced = set()
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            neg = negated_form(pred)
            if not neg:
                continue
            subj = str(st.get("subject_text") or "").strip()
            obj = str(st.get("object_text") or "").strip()
            if not subj or not obj:
                continue
            key = ("cf", subj.lower(), obj.lower())
            if key in produced:
                continue
            produced.add(key)
            new = _a(subj, "if not " + pred, obj)
            yield build_knowledge_result(
                method=THINKING,
                operation=self.name,
                operation_label=self.label,
                source_statements=[st],
                new_statements=[new],
                description=f"Контрфактическая оценка: если бы «{subj} {pred} {obj}» было ложным, "
                            f"записали бы «{subj} if not {pred} {obj}» (гипотеза для проверки).",
            )
            if len(produced) >= limit:
                return


class Classification:
    """Классификация: отнесение субъекта/объекта к категории по include/is_a."""

    name = "classification"
    label = "Классификация (отнесение к категории)"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        produced = set()
        for st in statements:
            if not is_category_edge(st.get("predicate")):
                continue
            subj = str(st.get("subject_text") or "").strip()
            obj = str(st.get("object_text") or "").strip()
            if not subj or not obj:
                continue
            # классифицируем объект как принадлежащий субъекту (если объект — элементы категории)
            key = ("classify", subj.lower(), obj.lower())
            if key in produced:
                continue
            produced.add(key)
            new = _a(obj, "is a member of category", subj)
            yield build_knowledge_result(
                method=THINKING,
                operation=self.name,
                operation_label=self.label,
                source_statements=[st],
                new_statements=[new],
                description=f"Классификация: «{subj} {st.get('predicate')} {obj}» ⇒ «{obj} is a member of category {subj}».",
            )
            if len(produced) >= limit:
                return


_OPERATIONS = [
    Analysis,
    Synthesis,
    Comparison,
    Abstraction,
    Generalization,
    Concretization,
    Induction,
    Deduction,
    Analogy,
    Causality,
    Counterfactual,
    Classification,
]


def thinking_operations() -> List[str]:
    """Идентификаторы доступных операций мышления."""
    return [cls.name for cls in _OPERATIONS]


def run_thinking_operations(
    statements: Sequence[Dict[str, Any]],
    *,
    operation: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Выполняет операции мышления над утверждениями."""
    results: List[Dict[str, Any]] = []
    for cls in _OPERATIONS:
        if operation and cls.name != operation:
            continue
        per_remaining = max(1, limit - len(results))
        results.extend(list(cls().run(statements, limit=per_remaining)))
        if len(results) >= limit:
            break
    return results
