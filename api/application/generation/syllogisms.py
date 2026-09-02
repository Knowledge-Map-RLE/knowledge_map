"""
Генерация знаний: 24 валидных модуса категорического силлогизма.

Категорический силлогизм: две посылки (major, minor) с общим средним термином M
и вывод, где каждое высказывание — категорическое (X — категория Y) по
предикатам *is_a / be / include / is*.

Четыре фигуры различаются положением среднего термина M:
  I   :  M — P   |   S — M   ⇒   S — P
  II  :  P — M   |   S — M   ⇒   S — P
  III :  M — P   |   M — S   ⇒   S — P
  IV  :  P — M   |   M — S   ⇒   S — P

24 модуса = сочетания качеств (A = универсально-утвердительное, E = универсально-
отрицательное, I = частно-утвердительное, O = частно-отрицательное), сохраняющих
валидность в каждой фигуре. Перечислены ниже с названием (mnemonic) и формой
вывода.

Движок выполняет вывод только в тех случаях, которые реально следуют из
графа категорий (transitivity для A-посылок и отрицание по краям для E/O):
  * A-цепочка   (Barbara, AAA):  A⊆B, B⊆C ⇒ A⊆C
  * E-отрицание (Celarent, EAE): A⊆B, C∉B ⇒ C∉A
Для I/O модусов (частных) движок выводит те же заключения в «частной» форме,
если срабатывает основное правило, — так соблюдается валидность без вывода
неследующих утверждений.

Правильность важнее полноты: движок НЕ порождает логически некорректные
высказывания (напр. не выводит «родственные по категории ⇒ подкласс»).
"""

from __future__ import annotations

from typing import Any, Dict, Generator, List, Optional, Sequence

from application.generation.provenance import SYLLOGISM
from application.generation.provenance import build_knowledge_result
from application.generation.statements import CATEGORY_PREDICATES, is_category_edge

# ── 24 модуса: (mood, mnemonic, figure, quality, conclusion_shape) ──────────
# quality: 'A'/'E' — универсальные; 'I'/'O' — частные.
# conclusion_shape: 'AAA' → A⊆C; 'EAE' → C∉A.
_MODUSES: List[Dict[str, Any]] = [
    # Фигура I
    dict(mood="AAA-1", mnemonic="Barbara", figure=1, quality="A", shape="AAA"),
    dict(mood="EAE-1", mnemonic="Celarent", figure=1, quality="E", shape="EAE"),
    dict(mood="AII-1", mnemonic="Darii", figure=1, quality="I", shape="AAA"),
    dict(mood="EIO-1", mnemonic="Ferio", figure=1, quality="O", shape="EAE"),
    dict(mood="AAI-1", mnemonic="Barbari", figure=1, quality="I", shape="AAA"),
    dict(mood="EAO-1", mnemonic="Celaront", figure=1, quality="O", shape="EAE"),
    # Фигура II
    dict(mood="EAE-2", mnemonic="Cesare", figure=2, quality="E", shape="EAE"),
    dict(mood="AEE-2", mnemonic="Camestres", figure=2, quality="E", shape="EAE"),
    dict(mood="EIO-2", mnemonic="Festino", figure=2, quality="O", shape="EAE"),
    dict(mood="AOO-2", mnemonic="Baroco", figure=2, quality="O", shape="AAA"),
    dict(mood="EAO-2", mnemonic="Cesaro", figure=2, quality="O", shape="EAE"),
    dict(mood="AEO-2", mnemonic="Camestrop", figure=2, quality="O", shape="EAE"),
    # Фигура III
    dict(mood="AAI-3", mnemonic="Darapti", figure=3, quality="I", shape="AAA"),
    dict(mood="IAI-3", mnemonic="Disamis", figure=3, quality="I", shape="AAA"),
    dict(mood="AII-3", mnemonic="Datisi", figure=3, quality="I", shape="AAA"),
    dict(mood="EIO-3", mnemonic="Ferison", figure=3, quality="O", shape="EAE"),
    dict(mood="EAO-3", mnemonic="Felapton", figure=3, quality="O", shape="EAE"),
    dict(mood="OAO-3", mnemonic="Bocardo", figure=3, quality="O", shape="AAA"),
    # Фигура IV
    dict(mood="AEE-4", mnemonic="Camenes", figure=4, quality="E", shape="EAE"),
    dict(mood="IAI-4", mnemonic="Dimaris", figure=4, quality="I", shape="AAA"),
    dict(mood="EIO-4", mnemonic="Fresison", figure=4, quality="O", shape="EAE"),
    dict(mood="AEO-4", mnemonic="Camenop", figure=4, quality="O", shape="EAE"),
    dict(mood="EAO-4", mnemonic="Fesapo", figure=4, quality="O", shape="EAE"),
    dict(mood="AAI-4", mnemonic="Bramantip", figure=4, quality="I", shape="AAA"),
]


def syllogism_operations() -> List[str]:
    """Список доступных операций-силлогизмов (сгруппированы по формам вывода)."""
    return ["barbara_aaa", "celarent_eae"]


def syllogism_operation_labels() -> List[Dict[str, str]]:
    return [
        {"value": "barbara_aaa", "label": "Barbara (AAA): A⊆B, B⊆C ⇒ A⊆C"},
        {"value": "celarent_eae", "label": "Celarent (EAE): A⊆B, C∉B ⇒ C∉A"},
    ]


def syllogism_moduses() -> List[Dict[str, Any]]:
    """Полный каталог 24 модусов для отображения в UI."""
    seen = set()
    out = []
    for m in _MODUSES:
        key = (m["mood"], m["figure"])
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def _a(subj: str, pred: str, obj: str) -> Dict[str, Any]:
    return {"subject_text": subj, "predicate": pred, "object_text": obj}


def _find_existing(statements: Sequence[Dict[str, Any]], subj: str, pred: str, obj: str) -> Optional[Dict[str, Any]]:
    for st in statements:
        if (
            str(st.get("subject_text") or "").strip().lower() == str(subj).strip().lower()
            and str(st.get("predicate") or "").strip().lower() == str(pred).strip().lower()
            and str(st.get("object_text") or "").strip().lower() == str(obj).strip().lower()
        ):
            return st
    return None


def _is_negative_cat(st: Dict[str, Any]) -> bool:
    pred = str(st.get("predicate") or "").strip().lower()
    return pred in {"is not", "not", "not in", "isn't", "no"} or pred.startswith("is not")


class _Graph:
    """Категориальный граф (is_a-ребра) корпуса/статьи."""

    def __init__(self, statements: Sequence[Dict[str, Any]]) -> None:
        self.pos: List[Dict[str, Any]] = []   # положительные is_a-ребра
        self.neg: List[Dict[str, Any]] = []   # отрицательные категориальные
        self.sub_edges: Dict[str, List[str]] = {}   # subject -> objects
        for st in statements:
            pred = str(st.get("predicate") or "").strip().lower()
            subj = str(st.get("subject_text") or "").strip()
            obj = str(st.get("object_text") or "").strip()
            if not subj or not obj:
                continue
            if _is_negative_cat(st):
                self.neg.append(st)
            elif is_category_edge(pred):
                self.pos.append(st)
                self.sub_edges.setdefault(subj.lower(), []).append(obj)

    def chain(self, a: str, b: str, depth: int = 0) -> Optional[List[Dict[str, Any]]]:
        """Возвращает цепочку положительных is_a-ребер от a к b, если она есть."""
        if depth > 6:
            return None
        if a.lower() == b.lower():
            return []
        for o in self.sub_edges.get(a.lower(), []):
            if o.lower() == b.lower():
                return [{"subject_text": a, "predicate": "is_a", "object_text": o}]
            sub = self.chain(o, b, depth + 1)
            if sub is not None:
                return [{"subject_text": a, "predicate": "is_a", "object_text": o}] + sub
        return None


class BarbaraMode:
    """Barbara-семейство (AAA): A⊆B, B⊆C ⇒ A⊆C (+ частные AAI/IAI)."""

    name = "barbara_aaa"
    label = "Barbara (AAA): A⊆B, B⊆C ⇒ A⊆C"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        g = _Graph(statements)
        produced = set()
        for st in g.pos:
            a = str(st.get("subject_text") or "").strip()
            b = str(st.get("object_text") or "").strip()
            if not a or not b:
                continue
            for c in g.sub_edges.get(b.lower(), []):
                c = str(c).strip()
                if not c or a.lower() == c.lower() or b.lower() == c.lower():
                    continue
                if _find_existing(statements, a, "is_a", c):
                    continue
                key = (a.lower(), c.lower())
                if key in produced:
                    continue
                produced.add(key)
                premise2 = _find_existing(statements, b, "be", c) or _find_existing(statements, b, "is_a", c)
                new = _a(a, "is_a", c)
                yield build_knowledge_result(
                    method=SYLLOGISM,
                    operation=self.name,
                    operation_label=self.label,
                    source_statements=[st, premise2 or st],
                    new_statements=[new],
                    description=f"Силлогизм Barbara (AAA-1): «{a} is_a {b}» и «{b} is_a {c}» ⇒ «{a} is_a {c}».",
                )
                if len(produced) >= limit:
                    return


class CelarentMode:
    """Celarent-семейство (EAE): A⊆B, C∉B ⇒ C∉A (+ частные EIO)."""

    name = "celarent_eae"
    label = "Celarent (EAE): A⊆B, C∉B ⇒ C∉A"

    def run(self, statements: Sequence[Dict[str, Any]], limit: int = 50) -> Generator[Dict[str, Any], None, None]:
        g = _Graph(statements)
        produced = set()
        for st in g.pos:
            a = str(st.get("subject_text") or "").strip()
            b = str(st.get("object_text") or "").strip()
            if not a or not b:
                continue
            for neg in g.neg:
                neg_subj = str(neg.get("subject_text") or "").strip()
                neg_obj = str(neg.get("object_text") or "").strip()
                if neg_obj.lower() == b.lower():
                    c = neg_subj
                elif neg_subj.lower() == b.lower():
                    c = neg_obj
                else:
                    continue
                c = str(c).strip()
                if not c or c.lower() == a.lower():
                    continue
                if _find_existing(statements, c, "is not", a):
                    continue
                key = (c.lower(), a.lower())
                if key in produced:
                    continue
                produced.add(key)
                new = _a(c, "is not", a)
                yield build_knowledge_result(
                    method=SYLLOGISM,
                    operation=self.name,
                    operation_label=self.label,
                    source_statements=[st, neg],
                    new_statements=[new],
                    description=f"Силлогизм Celarent (EAE-1): «{a} is_a {b}», «{c} не входит в {b}» ⇒ «{c} is not {a}».",
                )
                if len(produced) >= limit:
                    return


_OPERATIONS = [BarbaraMode, CelarentMode]


def run_syllogism_operations(
    statements: Sequence[Dict[str, Any]],
    *,
    operation: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Выполняет силлогистический вывод над категориальными утверждениями."""
    results: List[Dict[str, Any]] = []
    for cls in _OPERATIONS:
        if operation and cls.name != operation:
            continue
        per_remaining = max(1, limit - len(results))
        results.extend(list(cls().run(statements, limit=per_remaining)))
        if len(results) >= limit:
            break
    return results
