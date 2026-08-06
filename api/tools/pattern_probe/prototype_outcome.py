# -*- coding: utf-8 -*-
"""Prototype: hypothesis-subgraph outcome inference from the statement graph.

Строит доказательственный подграф гипотезы по графу KnowledgeStatement +
ArticleBlock целевой статьи, классифицирует находки в evidence
(SUPPORT / CONTRADICT / NULL / CONTEXT), агрегирует исход по экспериментам
и claims, отдельным флагом помечает метод-неполноту дизайна.

Временный прототип (tools/pattern_probe). Запуск:
  $env:PYTHONIOENCODING="utf-8"; poetry run python prototype_outcome.py
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from neomodel import db
from neomodel import config as neomodel_config

neomodel_config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"
neomodel_config.ENCRYPTED = False

TARGET = "000657ba-aec6-8a11-9c5c-986526539651"
OUT_JSON = "outcome_report.json"

DIRECTION_PREDS = {"понижено в", "повышено в", "без изменений в", "тренд в", "изменено в"}
META_PREDS = {"по сравнению с", "значимость", "p-value", "рисунок", "детали", "уверенность", "назначение", "размер выборки"}

# ── Лексикон полярности параметра ──────────────────────────────────────────
HARM_KEYWORDS = [
    "фиброз", "fibrosis", "fibrot", "сенесцент", "сенесценц", "senescen",
    "sasp", "p16", "p21", "cdkn", "h2ax", "dna damage", "поврежд",
    "воспал", "inflamm", "infiltrat", "липоатроф", "lipoatroph", "тревожн", "anxi",
    "апоптоз", "apoptos", "атроф", "atroph", "стресс", "stress",
    "смертн", "mortal", "летальн", "lethal", "beta-gal", "beta-galactosidase",
    "кахекс", "cachex", "деградац", "degradat", "дисфункц", "dysfunc",
    "инсулинорезистентн", "insulin resist", "ожирен", "obes", "снижение", "decline",
    "потеря", "loss", "impair", "нарушен", "нарушение", "infilt",
    "mcp-1", "mcp1", "c5b", "mac", "abc", "aab", "m1", "провоспалительн",
]
BENEFIT_KEYWORDS = [
    "функц", "function", "активн", "activity", "скорост", "speed",
    "сила", "strength", "grip", "ротарод", "rotarod", "координац", "coordination",
    "баланс", "balance", "закрыт", "заживлен", "healing", "wound", "регенерац",
    "regenerat", "пролиферац", "proliferat", "целостност", "integrity", "сохран",
    "maintenance", "устойчив", "resilien", "резилентн", "mtec", "тимус", "thym",
    "разнообраз", "diversity", "численн", "count", "количеств", "метабол", "metabol",
    "гомеостаз", "homeostas", "выживаем", "survival", "теплопродукц", "термоген",
    "thermogen", "потреблен", "consumption", "расход", "физическ", "долголет",
    "longevity", "продолжительность жизни", "репликативн", "антиоксидантн",
    "antioxidant", "expenditure", "m2", "ил-4", "il4",
]
STRONG_BENEFIT_KEYWORDS = [
    "противовоспалительн", "противовоспал", "анти-воспалительн", "антивоспал",
    "anti-inflamm",
]


def polarity_of(parameter: str) -> Optional[str]:
    t = (parameter or "").lower()
    if any(k in t for k in STRONG_BENEFIT_KEYWORDS):
        return "benefit"
    if any(k in t for k in HARM_KEYWORDS):
        return "harm"
    if any(k in t for k in BENEFIT_KEYWORDS):
        return "benefit"
    return None


STOPWORDS = {
    "в", "и", "на", "с", "по", "для", "при", "у", "к", "от", "о", "из", "за", "во",
    "не", "что", "это", "как", "а", "или", "же", "до", "после", "между", "the", "of",
    "and", "in", "with", "to", "for", "on", "vs", "et", "al", "age", "aged", "y",
}

SPECIES_MARKERS = {
    "russatus": "russatus",
    "acomys russatus": "russatus",
    "spiny": "russatus",
    "dimidiatus": "dimidiatus",
    "musculus": "musculus",
    "mus": "musculus",
    "mouse": "musculus",
    "c57bl": "musculus",
    "мышь": "musculus",
}


def detect_species(text: str) -> Optional[str]:
    t = (text or "").lower()
    for marker, sp in SPECIES_MARKERS.items():
        if marker in t:
            return sp
    return None


def norm_tokens(text: str) -> List[str]:
    toks = re.findall(r"[а-яёa-z0-9]+", (text or "").lower())
    return [t for t in toks if t not in STOPWORDS and len(t) > 1]


_RU_SUFFIXES = ["ами", "ыми", "ие", "ии", "ья", "ью", "ия", "ах", "ам", "ях",
                "ях", "ом", "им", "ов", "ев", "ой", "ый", "ий", "ое", "ого",
                "его", "их", "ых", "ую", "ая", "ем", "ей", "ин", "ну", "но", "на"]
_EN_SUFFIXES = ["ing", "tion", "ed", "es", "ly", "s"]


def stem(word: str) -> str:
    """Лёгкий стеммер (русский/английский) для сопоставления claims ↔ находки."""
    w = word.lower()
    for suf in _RU_SUFFIXES:
        if len(w) - len(suf) >= 3 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    else:
        for suf in _EN_SUFFIXES:
            if len(w) - len(suf) >= 3 and w.endswith(suf):
                w = w[: -len(suf)]
                break
    return w


def stem_tokens(text: str) -> List[str]:
    toks = norm_tokens(text)
    return [stem(t) for t in toks if len(stem(t)) >= 3]


DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "thymus": ["тимус", "mtec", "тимическ", "thym"],
    "liver": ["печен", "hepato", "печеночн"],
    "muscle": ["мышц", "gastrocnemius", "muscle", "скелет"],
    "adipose": ["жиров", "vat", "sat ", "adipocy", "висцеральн"],
    "behavior": ["open field", "rearing", "t-maze", "циркад", "тревожн", "двигательн",
                 "поведенч", "ротарод", "rotarod", "сила захвата", "координац", "баланс",
                 "латентность", "дистанция", "центр"],
    "inflammation": ["воспал", "цитокин", "sasp", "inflamm", "интерлейкин", "il-1", "il-2",
                     "il-4", "il-6", "tnf", "nf-kb", "infiltr", "маркер"],
    "senescence": ["сенесцент", "senescen", "p16", "p21", "cdkn", "h2ax", "клеточное старение"],
    "transcription": ["транскрипт", "rna", "деген", "degen", "deg", "экспресси", "экспрессии",
                      "экспрессия", "ген", "генов"],
    "proteostasis": ["автофаг", "cma", "аугофаг", "протеостаз", "агрег"],
    "regeneration": ["регенерац", "заживл", "закрыт ушн", "репаративн"],
    "serum": ["сыворотк", "serum"],
    "fibrosis": ["фиброз", "fibros"],
    "proliferation": ["пролиферац", "proliferat"],
}


def domain_of(text: str) -> set:
    t = (text or "").lower()
    return {d for d, keys in DOMAIN_KEYWORDS.items() if any(k in t for k in keys)}


def is_significant(sig_text: Optional[str], pvalue: Optional[float]) -> bool:
    if sig_text:
        t = sig_text.lower()
        if any(k in t for k in ["не значим", "незначим", "не достоверн", "недостоверн",
                                " ns", "n.s.", "не показа", "не выявлено", "не отлич"]):
            return False
    if pvalue is not None:
        return pvalue < 0.05
    return True


def parse_pvalue(raw: str) -> Optional[float]:
    s = (raw or "").replace(",", ".").strip()
    m = re.fullmatch(r"<[ ]*([0-9.]+)", s)
    if m:
        return float(m.group(1))
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


# ── Модели ─────────────────────────────────────────────────────────────────
@dataclass
class Finding:
    parameter: str
    direction: str
    group_label: str
    sort_order: int
    significance: Optional[str] = None
    comparison: Optional[str] = None
    pvalue: Optional[float] = None
    pvalue_raw: Optional[str] = None
    role: str = "unknown"
    polarity: Optional[str] = None
    evidence: str = "unknown"
    weight: float = 0.0
    experiment: Optional[str] = None
    flags: List[str] = field(default_factory=list)


@dataclass
class Claim:
    subject: str
    predicate: str
    object: str
    negated: bool
    confidence: float
    notes: Optional[str]
    linked: List[Tuple[str, float]] = field(default_factory=list)  # (finding, score)
    outcome: str = "unverified"
    domain: set = field(default_factory=set)
    generic: bool = False
    experiment_link: Optional[str] = None


@dataclass
class Experiment:
    name: str
    exp_type: Optional[str]
    findings: List[str] = field(default_factory=list)
    control_groups: List[str] = field(default_factory=list)
    exp_groups: List[str] = field(default_factory=list)
    verdict: str = "недостаточно данных"
    counts: Dict[str, int] = field(default_factory=dict)


class OutcomePrototype:
    def __init__(self, doc_id: str):
        self.doc_id = doc_id
        self.statements: List[Dict[str, Any]] = []
        self.blocks: List[Dict[str, Any]] = []
        self.findings: List[Finding] = []
        self.claims: List[Claim] = []
        self.experiments: Dict[str, Experiment] = {}
        self.group_purpose: Dict[str, str] = {}
        self.group_n: Dict[str, str] = {}
        self.finding_uid_to_param: Dict[str, str] = {}
        self.hypothesis: Dict[str, Any] = {}
        self.goals: List[str] = []
        self.method_flags: Dict[str, Any] = {}
        self.block_t57_by_param: Dict[str, List[str]] = {}

    # ── Загрузка ───────────────────────────────────────────────────────────
    def load(self) -> None:
        rows, _ = db.cypher_query(
            "MATCH (d:Document {uid: $u})-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "RETURN s.uid, s.subject_text, s.predicate, s.object_text, s.type, "
            "s.confidence, s.sort_order ORDER BY s.sort_order",
            {"u": self.doc_id},
        )
        self.statements = [
            {
                "uid": r[0], "subject_text": r[1] or "", "predicate": r[2] or "",
                "object_text": r[3] or "", "type": r[4], "confidence": r[5],
                "sort_order": r[6] or 0,
            }
            for r in rows
        ]

        brow, _ = db.cypher_query(
            "MATCH (d:Document {uid: $u})-[:HAS_BLOCK]->(b:ArticleBlock) "
            "RETURN b.uid, b.block_type, b.order, b.data",
            {"u": self.doc_id},
        )
        self.blocks = [
            {"uid": r[0], "block_type": r[1], "order": r[2], "data": self._parse_data(r[3])}
            for r in brow
        ]

    @staticmethod
    def _parse_data(raw: Optional[str]) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            d = json.loads(raw)
            return d if isinstance(d, dict) else {}
        except (ValueError, TypeError):
            return {}

    # ── Реестры ────────────────────────────────────────────────────────────
    def build_registries(self) -> None:
        for b in self.blocks:
            bt = b["block_type"]
            data = b["data"]
            if bt == 55:
                name = (data.get("groupName") or "").strip()
                if name:
                    if data.get("purpose"):
                        self.group_purpose[name] = str(data["purpose"]).strip()
                    if data.get("n"):
                        self.group_n[name] = str(data["n"]).strip()
            elif bt == 57:
                param = (data.get("parameter") or "").strip()
                if param:
                    self.finding_uid_to_param[b["uid"]] = param
                    self.block_t57_by_param.setdefault(param, []).append(b["uid"])
            elif bt == 38:
                subj, pred, obj = (data.get("claimSubject") or "").strip(), \
                    (data.get("claimPredicate") or "").strip(), (data.get("claimObject") or "").strip()
                if subj and pred and obj:
                    neg = data.get("isNegated") in (True, "true", "True", "1", "on")
                    notes = (data.get("confidenceNotes") or "").strip()
                    self.claims.append(Claim(
                        subject=subj, predicate=f"не {pred}" if neg else pred,
                        object=obj, negated=neg, confidence=0.8 if notes else 1.0,
                        notes=notes or None,
                    ))
            elif bt == 14:
                name = (data.get("experimentName") or "").strip()
                if name:
                    exp = Experiment(
                        name=name,
                        exp_type=(data.get("experimentType") or "").strip() or None,
                    )
                    for key in ("findings", "controlPairs", "experimentalPairs"):
                        raw = data.get(key)
                        if not raw:
                            continue
                        try:
                            parsed = json.loads(raw) if isinstance(raw, str) else raw
                        except (ValueError, TypeError):
                            parsed = []
                        if not isinstance(parsed, list):
                            continue
                        if key == "findings":
                            exp.findings = [str(f).strip() for f in parsed if str(f).strip()]
                        elif key == "controlPairs":
                            for p in parsed:
                                g = (p.get("groupRef") or "") if isinstance(p, dict) else ""
                                if g:
                                    exp.control_groups.append(g)
                        elif key == "experimentalPairs":
                            for p in parsed:
                                g = (p.get("groupRef") or "") if isinstance(p, dict) else ""
                                if g:
                                    exp.exp_groups.append(g)
                    self.experiments[name] = exp
            elif bt == 7:
                self.hypothesis = data

        # 'назначение' / 'размер выборки' из стейтментов (если нет в блоках)
        for s in self.statements:
            p = s["predicate"]
            if p == "назначение" and s["subject_text"]:
                self.group_purpose.setdefault(s["subject_text"], s["object_text"])
            elif p == "размер выборки" and s["subject_text"]:
                self.group_n.setdefault(s["subject_text"], s["object_text"])
            elif p == "цель":
                self.goals.append(s["object_text"])

    # ── Находки ────────────────────────────────────────────────────────────
    def collect_findings(self) -> None:
        meta: Dict[str, Dict[str, List[str]]] = {}
        for s in self.statements:
            p = s["predicate"]
            if p in DIRECTION_PREDS:
                self.findings.append(Finding(
                    parameter=s["subject_text"], direction=p,
                    group_label=s["object_text"], sort_order=s["sort_order"] or 0,
                ))
            elif p in ("по сравнению с", "значимость", "p-value"):
                meta.setdefault(s["subject_text"], {}).setdefault(p, []).append(s["object_text"])

        exp_by_name: Dict[str, List[str]] = {}
        for s in self.statements:
            if s["predicate"] == "результат" and s["object_text"]:
                exp_by_name.setdefault(s["subject_text"], []).append(s["object_text"])

        for f in self.findings:
            m = meta.get(f.parameter, {})
            f.comparison = (m.get("по сравнению с") or [None])[0]
            f.significance = (m.get("значимость") or [None])[0]
            for raw in m.get("p-value", []):
                pv = parse_pvalue(raw)
                if pv is not None:
                    f.pvalue = pv
                    f.pvalue_raw = raw
                    break
            # блок-уровень: T57(pValue uuid) → T27(data.pValue)
            if f.pvalue is None:
                for uid in self.block_t57_by_param.get(f.parameter, []):
                    pv_ref = None
                    for b in self.blocks:
                        if b["uid"] == uid:
                            pv_ref = (b["data"].get("pValue") or "").strip()
                            break
                    if not pv_ref:
                        continue
                    for b in self.blocks:
                        if b["uid"] == pv_ref and b["block_type"] == 27:
                            pv = parse_pvalue(str(b["data"].get("pValue", "")))
                            if pv is not None:
                                f.pvalue = pv
                                f.pvalue_raw = f"block:{pv}"
                            break
                    if f.pvalue is not None:
                        break

            # эксперимент, к которому относится находка
            for exp_name, uids in exp_by_name.items():
                for uid in uids:
                    if self.finding_uid_to_param.get(uid) == f.parameter and f.parameter in self.finding_uid_to_param.values():
                        f.experiment = exp_name
                        break
                if f.experiment:
                    break
            if f.experiment is None:
                # прямое сопоставление uid → параметр (находки, привязанные к блокам)
                for exp_name, uids in exp_by_name.items():
                    resolved = [self.finding_uid_to_param.get(u) for u in uids]
                    if f.parameter in resolved:
                        f.experiment = exp_name
                        break

    # ── Роль группы ────────────────────────────────────────────────────────
    @staticmethod
    def group_role(purpose: Optional[str], species: Optional[str], label: str) -> str:
        t = (purpose or "").lower()
        lab = (label or "").lower()
        if any(k in t for k in ("резистентн", "основная группа")):
            return "resilient_aged"
        if any(k in t for k in ("возрастн", "aged control")):
            return "aged_other"
        if any(k in t for k in ("baseline", "молод", "контроль молод")):
            return "young"
        if any(k in t for k in ("контроль", "интервенц", "intervention", "control")):
            return "intervention"
        if "aged" in lab or "возраст" in lab or "старен" in lab:
            return "aged_other" if species in ("dimidiatus", "musculus") else "resilient_aged"
        if "young" in lab or "молод" in lab or "baseline" in lab:
            return "young"
        return "unknown"

    # ── Классификация ──────────────────────────────────────────────────────
    def classify_finding(self, f: Finding) -> None:
        f.polarity = polarity_of(f.parameter)
        species = detect_species(f.group_label)
        purpose = self.group_purpose.get(f.group_label)
        f.role = self.group_role(purpose, species, f.group_label)
        sig = is_significant(f.significance, f.pvalue)
        cmp_species = detect_species(f.comparison)

        favorable = None
        if f.polarity == "harm":
            favorable = {"понижено в"}
        elif f.polarity == "benefit":
            favorable = {"повышено в"}
        # 'без изменений' — нейтрально-благоприятно (стабильность)

        if f.direction == "без изменений в":
            f.evidence = "support"
            f.weight = 0.8 if sig else 0.4
            return

        if f.role == "intervention":
            # исход интервенции напрямую по благоприятности направления
            if favorable is None:
                f.evidence = "unknown"
                return
            if f.direction in favorable:
                f.evidence = "support" if sig else "weak_support"
            else:
                f.evidence = "contradict" if sig else "weak_contradict"
            f.weight = 1.0 if f.evidence == "support" else (0.6 if f.evidence in ("weak_support", "weak_contradict") else 1.0)
            return

        if f.role == "resilient_aged":
            # сравнение с молодыми той же линии — тест сохранности при старении
            if cmp_species == species and (not f.comparison or any(k in (f.comparison or "").lower()
                                                                     for k in ("young", "молод", "baseline"))):
                if favorable is None:
                    f.evidence = "unknown"
                    return
                if f.direction in favorable:
                    f.evidence = "support" if sig else "weak_support"
                else:
                    f.evidence = "contradict" if sig else "weak_contradict"
                f.weight = 1.0 if f.evidence == "support" else (0.6 if "weak" in f.evidence else 1.0)
                return
            # сравнение с другими видами (dimidiatus/musculus) — резилентность
            if cmp_species and cmp_species != species:
                if favorable is None:
                    f.evidence = "unknown"
                    return
                if f.direction in favorable:
                    f.evidence = "support" if sig else "weak_support"
                else:
                    f.evidence = "contradict" if sig else "weak_contradict"
                f.weight = 1.0 if f.evidence == "support" else (0.6 if "weak" in f.evidence else 1.0)
                return
            # без явного сравнения — опираемся на назначение группы
            if favorable is None:
                f.evidence = "unknown"
                return
            if f.direction in favorable:
                f.evidence = "support" if sig else "weak_support"
            else:
                f.evidence = "contradict" if sig else "weak_contradict"
            f.weight = 1.0 if f.evidence == "support" else (0.6 if "weak" in f.evidence else 1.0)
            return

        if f.role == "aged_other":
            # фенотип старения в не-резилентном виде — контекстная поддержка
            if f.polarity == "benefit" and f.direction == "понижено в":
                f.evidence = "context_support"
            elif f.polarity == "harm" and f.direction == "повышено в":
                f.evidence = "context_support"
            elif f.direction == "без изменений в":
                f.evidence = "context"
            else:
                f.evidence = "context"
            f.weight = 0.5 if f.evidence == "context_support" else 0.0
            return

        if f.role == "young":
            f.evidence = "context"
            f.weight = 0.0
            return

        f.evidence = "unknown"

    # ── Связывание claims ↔ находки ───────────────────────────────────────
    def link_claims(self) -> None:
        for c in self.claims:
            c_text = f"{c.subject} {c.object}"
            c.domain = domain_of(c_text)
            c.generic = not c.domain
            c_tokens = set(stem_tokens(c_text))
            for f in self.findings:
                p_toks = set(stem_tokens(f.parameter))
                exp_toks = set(stem_tokens(f.experiment or ""))
                param_overlap = len(c_tokens & p_toks)
                exp_overlap = len(c_tokens & exp_toks)
                if param_overlap >= 1 or exp_overlap >= 2:
                    score = param_overlap + 0.3 * exp_overlap
                    c.linked.append((f, round(score, 2)))
            c.linked.sort(key=lambda x: -x[1])
            # эксперимент-уровень: claim ссылается на эксперимент с большинством
            # связанных находок (прямые домен-согласованные), иначе по токен-пересечению
            from collections import Counter
            exp_counts = Counter(f.experiment for f, _ in c.linked
                                 if f.experiment and f.evidence in
                                 ("support", "weak_support", "context_support", "contradict", "weak_contradict"))
            if exp_counts:
                c.experiment_link = exp_counts.most_common(1)[0][0]
            else:
                best_exp, best_score = None, 0
                for name in self.experiments:
                    exp_toks = set(stem_tokens(name))
                    ov = len(c_tokens & exp_toks)
                    if ov >= 2 and ov > best_score:
                        best_exp, best_score = name, ov
                c.experiment_link = best_exp

    # ── Вердикты ───────────────────────────────────────────────────────────
    def verdict_from_counts(self, counts: Dict[str, int]) -> str:
        sup = counts.get("support", 0) + counts.get("weak_support", 0) * 0.6
        con = counts.get("contradict", 0) + counts.get("weak_contradict", 0) * 0.6
        if con > 0 and con >= sup:
            return "не подтвердилась"
        if sup > 0 and con == 0:
            return "подтвердилась"
        if sup > 0 and con > 0:
            return "частично подтвердилась"
        return "недостаточно данных"

    def claim_verdict(self, c: Claim, study_ok: bool) -> str:
        """Вердикт claim: по домен-согласованным прямым ссылкам, иначе по
        вердикту связанного эксперимента, иначе по агрегации исследования."""
        direct = []
        for f, score in c.linked:
            # прямое совпадение параметра и согласованность домена
            p_overlap = len(set(stem_tokens(c.subject + " " + c.object)) & set(stem_tokens(f.parameter)))
            if p_overlap < 1:
                continue
            if c.generic or (c.domain & domain_of(f.parameter)):
                direct.append(f)
        e_sup = sum(1 for f in direct if f.evidence in ("support", "context_support"))
        e_con = sum(1 for f in direct if f.evidence in ("contradict", "weak_contradict"))
        if direct and (e_sup or e_con):
            if e_con >= e_sup:
                return "contradicted"
            if e_con == 0:
                return "supported"
            return "partially supported"
        if c.experiment_link:
            ev = self.experiments[c.experiment_link].verdict
            if ev == "подтвердилась":
                return "supported (по эксперименту)"
            if ev == "не подтвердилась":
                return "contradicted (по эксперименту)"
            if ev == "частично подтвердилась":
                return "partially supported (по эксперименту)"
        if c.generic and study_ok:
            return "supported (агрегация исследования)"
        return "unverified"

    def aggregate(self) -> None:
        exp_counts: Dict[str, Dict[str, int]] = {}
        for f in self.findings:
            key = f.experiment or "(без эксперимента)"
            d = exp_counts.setdefault(key, {})
            d[f.evidence] = d.get(f.evidence, 0) + 1
        for name, counts in exp_counts.items():
            exp = self.experiments.get(name)
            if exp is None:
                exp = Experiment(name=name)
                self.experiments[name] = exp
            exp.counts = counts
            exp.verdict = self.verdict_from_counts(counts)

        study_ok = self.study_verdict_ok()
        for c in self.claims:
            c.outcome = self.claim_verdict(c, study_ok)

    # ── Метод-флаги ────────────────────────────────────────────────────────
    def assess_method(self) -> None:
        flags: Dict[str, Any] = {}
        has_control_pairs = any(e.control_groups for e in self.experiments.values())
        has_comparison_meta = any(f.comparison for f in self.findings)
        flags["control"] = {
            "ok": has_control_pairs or has_comparison_meta,
            "control_pairs": sum(1 for e in self.experiments.values() if e.control_groups),
            "comparison_meta": sum(1 for f in self.findings if f.comparison),
        }
        stats_blocks = [b for b in self.blocks if b["block_type"] == 37]
        stats_stmts = any(s["predicate"] == "статистическая обработка" for s in self.statements)
        flags["statistics"] = {
            "ok": bool(stats_blocks) or stats_stmts,
            "t37_blocks": len(stats_blocks),
            "stat_processing_stmts": stats_stmts,
        }
        used_groups = {f.group_label for f in self.findings}
        missing_n = [g for g in used_groups if g not in self.group_n]
        flags["sample_size"] = {
            "ok": not missing_n,
            "groups_without_n": missing_n,
        }
        sig_findings = [f for f in self.findings if f.evidence in ("support", "contradict") and is_significant(f.significance, f.pvalue)]
        missing_p = [f.parameter for f in sig_findings if f.pvalue is None]
        flags["p_value"] = {
            "ok": not missing_p,
            "significant_without_p": missing_p,
        }
        flags["hypothesis"] = {"ok": bool(self.hypothesis)}
        flags["design_incomplete"] = any(not v["ok"] for k, v in flags.items() if isinstance(v, dict) and "ok" in v)
        self.method_flags = flags

    # ── Отчёт ──────────────────────────────────────────────────────────────
    def report(self) -> Dict[str, Any]:
        counts = {}
        for f in self.findings:
            counts[f.evidence] = counts.get(f.evidence, 0) + 1
        roles = {}
        for f in self.findings:
            roles[f.role] = roles.get(f.role, 0) + 1
        polarity = {}
        for f in self.findings:
            polarity[str(f.polarity)] = polarity.get(str(f.polarity), 0) + 1

        return {
            "doc_id": self.doc_id,
            "hypothesis": self.hypothesis,
            "goals": self.goals,
            "findings_total": len(self.findings),
            "evidence_counts": counts,
            "role_counts": roles,
            "polarity_counts": polarity,
            "experiments": {
                name: {
                    "type": e.exp_type,
                    "findings": len(e.findings),
                    "control_groups": e.control_groups,
                    "exp_groups": e.exp_groups,
                    "counts": e.counts,
                    "verdict": e.verdict,
                }
                for name, e in sorted(self.experiments.items())
            },
            "claims": [
                {
                    "statement": f"{c.subject} → {c.predicate} → {c.object}",
                    "negated": c.negated,
                    "confidence": c.confidence,
                    "outcome": c.outcome,
                    "domain": sorted(c.domain) or ["generic"],
                    "experiment_link": c.experiment_link,
                    "linked": [{"finding": f.parameter, "group": f.group_label,
                                "evidence": f.evidence, "score": s}
                               for f, s in c.linked[:8]],
                }
                for c in self.claims
            ],
            "findings": [
                {
                    "parameter": f.parameter,
                    "direction": f.direction,
                    "group": f.group_label,
                    "comparison": f.comparison,
                    "significance": f.significance,
                    "pvalue": f.pvalue,
                    "polarity": f.polarity,
                    "role": f.role,
                    "evidence": f.evidence,
                    "experiment": f.experiment,
                }
                for f in self.findings
            ],
            "method_flags": self.method_flags,
            "study_verdict": self.study_verdict(),
        }

    def study_verdict_ok(self) -> bool:
        confirmed = sum(1 for e in self.experiments.values() if e.verdict == "подтвердилась")
        refuted = sum(1 for e in self.experiments.values() if e.verdict == "не подтвердилась")
        return confirmed > refuted

    def study_verdict(self) -> Dict[str, Any]:
        exp_verdicts = [e.verdict for e in self.experiments.values()]
        confirmed = sum(1 for v in exp_verdicts if v == "подтвердилась")
        refuted = sum(1 for v in exp_verdicts if v in ("не подтвердилась",))
        partial = sum(1 for v in exp_verdicts if v == "частично подтвердилась")
        claims_supported = sum(1 for c in self.claims if c.outcome.startswith("supported"))
        claims_contradicted = sum(1 for c in self.claims if c.outcome.startswith("contradicted"))
        if claims_contradicted and claims_contradicted >= claims_supported:
            verdict = "гипотеза не подтвердилась"
        elif claims_supported and not claims_contradicted:
            verdict = "гипотеза подтвердилась"
        elif claims_supported:
            verdict = "гипотеза частично подтвердилась"
        else:
            verdict = "недостаточно данных для вывода"
        return {
            "verdict": verdict,
            "experiments_confirmed": confirmed,
            "experiments_refuted": refuted,
            "experiments_partial": partial,
            "claims_supported": claims_supported,
            "claims_contradicted": claims_contradicted,
        }

    def print_human(self, rep: Dict[str, Any]) -> None:
        print(f"\n═══ ПРОТОТИП: ИСХОД ИССЛЕДОВАНИЯ (документ {rep['doc_id'][:8]}) ═══")
        print(f"Всего находок: {rep['findings_total']}")
        print(f"Evidence: {rep['evidence_counts']}")
        print(f"Роли групп: {rep['role_counts']}")
        print(f"Полярность: {rep['polarity_counts']}")
        print("\n── Гипотеза (T7) ──")
        print(json.dumps(rep["hypothesis"], ensure_ascii=False, indent=2) if rep["hypothesis"] else "(нет блока T7)")
        print("\n── Цели ──")
        for g in rep["goals"]:
            print(f"  • {g}")

        print("\n── Эксперименты ──")
        for name, e in rep["experiments"].items():
            print(f"  [{e['verdict']}] {name} (тип: {e['type'] or '—'}, находок: {e['findings']})")
            print(f"      контроль: {e['control_groups'] or '—'}; эксп.: {e['exp_groups'] or '—'}")
            print(f"      counts: {e['counts']}")

        print("\n── Claims (T38) ──")
        for c in rep["claims"]:
            dom = ", ".join(c["domain"])
            expl = f" | domain={dom}" if dom != "generic" else " | domain=generic"
            if c.get("experiment_link"):
                expl += f" | exp-link={c['experiment_link'][:60]}"
            print(f"  [{c['outcome']}]{expl} {c['statement']} (conf={c['confidence']})")
            shown = 0
            for link in c["linked"]:
                if shown >= 4:
                    print(f"      … ещё {len(c['linked']) - shown}")
                    break
                print(f"      ↳ {link['finding']} | {link['group']} | {link['evidence']} | score={link['score']}")
                shown += 1

        print("\n── Спорные находки (contradict / weak / unknown в интервенции) ──")
        concerned = [f for f in rep["findings"]
                     if f["evidence"] in ("contradict", "weak_contradict")
                     or (f["role"] == "intervention" and f["evidence"] == "unknown")]
        for f in concerned:
            print(f"  [!] {f['parameter']} | {f['direction']} | {f['group']} "
                  f"| cmp={f['comparison']} | p={f['pvalue']} | {f['evidence']}")
        if not concerned:
            print("  (нет)")

        print("\n── Метод-неполнота (независимый флаг) ──")
        for k, v in rep["method_flags"].items():
            if isinstance(v, dict) and "ok" in v:
                print(f"  {'✓' if v['ok'] else '✗'} {k}: {v}")
        sv = rep["study_verdict"]
        print(f"\n═══ ВЕРДИКТ: {sv['verdict']} ═══")
        print(f"  эксперименты: подтверждено={sv['experiments_confirmed']}, "
              f"опровергнуто={sv['experiments_refuted']}, частично={sv['experiments_partial']}; "
              f"claims: поддержано={sv['claims_supported']}, опровергнуто={sv['claims_contradicted']}")

    def run(self) -> Dict[str, Any]:
        self.load()
        self.build_registries()
        self.collect_findings()
        for f in self.findings:
            self.classify_finding(f)
        self.link_claims()
        self.aggregate()
        self.assess_method()
        rep = self.report()
        with open(OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
        self.print_human(rep)
        return rep


def main() -> None:
    OutcomePrototype(TARGET).run()


if __name__ == "__main__":
    main()
