"""EvidenceMap service: LLM-нормализация доказательственных карт статей.

Сервис отвечает за три вещи:

1. **Генерация карты** — по тексту статьи (уже без References) через AI Agent
   микросервис (`ai_model_client.generate_text`) строится нормализованная
   доказательственная карта по единой схеме (гипотеза, цели, claims,
   эксперименты, находки, метод-флаги, вердикт). LLM канонизирует параметры и
   использует **фиксированные перечисления** (domain/polarity/direction/...),
   чтобы типизированные подграфы разных статей были сопоставимы.

2. **Хранение** — карта целиком (JSON, включая типизированный граф)
   сохраняется в Neo4j как узел `EvidenceMap` со связью
   `(:Document)-[:HAS_EVIDENCE_MAP]->(:EvidenceMap)`. Графы карт — это корпус
   для майнинга паттернов.

3. **Майнинг и матчинг** — майнинг частотных подграфов выполняется только
   алгоритмически (`services/gspan.py`, никакого LLM/NLP на этом шаге),
   матчинг новой статьи к паттернам тоже чисто алгоритмический.

Единая схема карты:

    {
      "hypothesis": str,
      "goals": [str],
      "claims": [{subject, predicate, object, negated: bool, domain, confidence}],
      "experiments": [{name, type, verdict, control_groups: [str], exp_groups: [str],
                        findings: [str]}],
      "findings": [{parameter, domain, polarity, direction, significance, p: float|null,
                     group_role, experiment: int|null, claim_ref: int|null}],
      "method_flags": {control: bool, statistics: bool, sample_size: bool,
                        p_value: bool, hypothesis: bool},
      "verdict": "supported" | "contradicted" | "partially_supported" | "inconclusive"
    }
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from neomodel import db

from src.uuid8 import uuid8_str
from .ai_model_client import get_ai_model_client
from .article_editor_service import ArticleEditorService
from .gspan import mine_frequent_subgraphs, match_graph

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen/qwen3-4b"
MAX_PROMPT_TEXT_CHARS = 25000

# ── Перечисления (фиксированные значения, требуемые от модели) ────────────
DOMAINS = {
    "behavior", "thymus", "liver", "adipose", "muscle", "inflammation",
    "senescence", "transcription", "proteostasis", "regeneration", "serum",
    "fibrosis", "proliferation", "metabolism", "other",
}
POLARITIES = {"benefit", "harm", "neutral"}
DIRECTIONS = {"up", "down", "unchanged"}
SIGNIFICANCES = {"sig", "ns", "unknown"}
EXPERIMENT_TYPES = {
    "in_vivo", "ex_vivo", "in_vitro", "omics", "behavioral", "clinical", "other",
}
VERDICTS = {"supported", "contradicted", "partially_supported", "inconclusive"}
GROUP_ROLES = {"resilient_aged", "aged_other", "young", "intervention", "unknown"}

_DOMAIN_ALIASES = {
    "поведен": "behavior", "behavio": "behavior", "циркад": "behavior",
    "timus": "thymus", "тимус": "thymus", "thym": "thymus", "mtec": "thymus",
    "печён": "liver", "печен": "liver", "печеночн": "liver",
    "hepato": "liver", "liver": "liver",
    "жиров": "adipose", "adipose": "adipose", "vat": "adipose", "sat": "adipose",
    "мышц": "muscle", "muscle": "muscle", "gastrocnemius": "muscle",
    "воспал": "inflammation", "inflamm": "inflammation", "sasp": "inflammation",
    "цитокин": "inflammation", "senescen": "senescence", "сенесцент": "senescence",
    "p16": "senescence", "p21": "senescence", "cdkn": "senescence", "h2ax": "senescence",
    "транскрипт": "transcription", "rna": "transcription", "ген": "transcription",
    "deg": "transcription", "протеостаз": "proteostasis", "autophag": "proteostasis",
    "cma": "proteostasis", "регенерац": "regeneration", "regenerat": "regeneration",
    "заживл": "regeneration", "сыворотк": "serum", "serum": "serum",
    "фиброз": "fibrosis", "fibros": "fibrosis", "пролиферац": "proliferation",
    "proliferat": "proliferation", "метабол": "metabolism", "metabol": "metabolism",
}
_POLARITY_ALIASES = {
    "benefit": "benefit", "beneficial": "benefit", "positive": "benefit",
    "противовоспал": "benefit", "полезн": "benefit", "благоприят": "benefit",
    "harm": "harm", "harmful": "harm", "negative": "harm", "вредн": "harm",
    "sasp": "harm", "p16": "harm", "фиброз": "harm", "senescen": "harm",
    "воспал": "harm", "neutral": "neutral", "нейтрал": "neutral", "none": "neutral",
}
_DIRECTION_ALIASES = {
    "up": "up", "increase": "up", "повыш": "up", "повышено": "up",
    "upregulated": "up", "выше": "up", "down": "down", "decrease": "down",
    "пониж": "down", "понижено": "down", "downregulated": "down", "ниже": "down",
    "unchanged": "unchanged", "no change": "unchanged", "без изменений": "unchanged",
}
_SIGNIFICANCE_ALIASES = {
    "sig": "sig", "significant": "sig", "значим": "sig", "достоверн": "sig",
    "ns": "ns", "not significant": "ns", "не значим": "ns", "незначим": "ns",
    "недостоверн": "ns", "trend": "ns", "unknown": "unknown",
}


def _norm(value: Any, aliases: Dict[str, str], default: str) -> str:
    t = str(value or "").strip().lower()
    for alias, canon in aliases.items():
        if alias in t:
            return canon
    return default


def norm_domain(value: Any) -> str:
    return _norm(value, _DOMAIN_ALIASES, "other")


def norm_polarity(value: Any) -> str:
    return _norm(value, _POLARITY_ALIASES, "neutral")


def norm_direction(value: Any) -> str:
    return _norm(value, _DIRECTION_ALIASES, "unknown")


def norm_significance(value: Any, p: Optional[float] = None) -> str:
    if p is not None:
        try:
            return "sig" if float(p) < 0.05 else "ns"
        except (TypeError, ValueError):
            pass
    return _norm(value, _SIGNIFICANCE_ALIASES, "unknown")


def norm_experiment_type(value: Any) -> str:
    return _norm(value, {
        "in vivo": "in_vivo", "in_vivo": "in_vivo", "животн": "in_vivo", "mouse": "in_vivo",
        "in vitro": "in_vitro", "in_vitro": "in_vitro", "cell": "in_vitro",
        "ex vivo": "ex_vivo", "ex_vivo": "ex_vivo",
        "rna": "omics", "seq": "omics", "omics": "omics", "transcript": "omics",
        "behavior": "behavioral", "behavioral": "behavioral", "циркад": "behavioral",
        "clinical": "clinical", "клинич": "clinical", "histolog": "ex_vivo",
    }, "other")


def norm_verdict(value: Any) -> str:
    return _norm(value, {
        "supported": "supported", "подтвердил": "supported", "confirm": "supported",
        "contradicted": "contradicted", "не подтвердил": "contradicted",
        "refut": "contradicted", "reject": "contradicted",
        "partial": "partially_supported", "частично": "partially_supported",
        "inconclusive": "inconclusive", "недостаточн": "inconclusive", "unknown": "inconclusive",
    }, "inconclusive")


# ── Типизированный граф карты ──────────────────────────────────────────────
def map_to_graph(m: Dict[str, Any]) -> Dict[str, Any]:
    """Преобразует нормализованную карту в типизированный граф {nodes, edges}.

    Метки узлов стабильны между статьями (перечисления domain/polarity/...),
    поэтому подграфы разных статей сопоставимы для майнинга паттернов:

      * H                       — гипотеза
      * G                       — цель исследования
      * C:{domain}:{neg}        — claim (neg: 1 если negated)
      * E:{type}                — эксперимент
      * F:{domain}:{pol}:{dir}:{sig} — находка
      * M:{flag}:{ok}           — метод-флаг (ok/missing)
    """
    nodes: List[Dict[str, str]] = [{"id": "h", "label": "H"}]
    edges: List[Dict[str, str]] = []

    for i, goal in enumerate(m.get("goals") or []):
        if goal:
            nodes.append({"id": f"g{i}", "label": "G"})
            edges.append({"from": "h", "to": f"g{i}", "label": "goal"})

    claims = m.get("claims") or []
    for i, c in enumerate(claims):
        dom = norm_domain(c.get("domain"))
        neg = "1" if c.get("negated") else "0"
        nodes.append({"id": f"c{i}", "label": f"C:{dom}:{neg}"})
        edges.append({"from": "h", "to": f"c{i}", "label": "tested_by"})

    experiments = m.get("experiments") or []
    for i, e in enumerate(experiments):
        etype = norm_experiment_type(e.get("type"))
        nodes.append({"id": f"e{i}", "label": f"E:{etype}"})

    findings = m.get("findings") or []
    for i, f in enumerate(findings):
        if not (f.get("parameter") or "").strip():
            continue
        dom = norm_domain(f.get("domain"))
        pol = norm_polarity(f.get("polarity"))
        direction = norm_direction(f.get("direction"))
        sig = norm_significance(f.get("significance"), f.get("p"))
        nodes.append({"id": f"f{i}", "label": f"F:{dom}:{pol}:{direction}:{sig}"})
        claim_ref = f.get("claim_ref")
        if isinstance(claim_ref, int) and 0 <= claim_ref < len(claims):
            edges.append({"from": f"c{claim_ref}", "to": f"f{i}", "label": "evidence"})
        exp_ref = f.get("experiment")
        if isinstance(exp_ref, int) and 0 <= exp_ref < len(experiments):
            edges.append({"from": f"e{exp_ref}", "to": f"f{i}", "label": "measures"})

    for flag, ok in (m.get("method_flags") or {}).items():
        if not isinstance(ok, bool):
            continue
        nodes.append({"id": f"m:{flag}", "label": f"M:{flag}:{'ok' if ok else 'missing'}"})
        edges.append({"from": "h", "to": f"m:{flag}", "label": "requires"})

    return {"nodes": nodes, "edges": edges}


# ── Промпт для LLM ─────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """You are a biomedical evidence-structuring engine. Convert the article
into a single JSON evidence map. Output ONLY valid JSON (no markdown, no comments).

{article}

RULES (must be followed strictly):
1. The evidence map represents the article's own evidence structure. Do not invent
   findings that are not reported.
2. Canonicalize parameter names: use stable concise English terms (e.g. "serum
   clusterin", "thymus mass", "VAT Treg"). Treat abbreviations consistently
   (expand them once, then reuse).
3. Ignore figure/table artifacts, references, author contributions, and first-person
   narration. If a statement is only implied but clearly reported, include it.
4. Handle negation exactly (claim.negated). Do not drop "no effect"/"no change"
   findings — record direction "unchanged".
5. p-values: numeric (e.g. 0.01) or null if absent. significance from text
   (p<0.05 -> "sig") OR from p-value.
6. Use ONLY these enum values:
   - claim.domain: behavior|thymus|liver|adipose|muscle|inflammation|senescence|
     transcription|proteostasis|regeneration|serum|fibrosis|proliferation|
     metabolism|other
   - finding.domain: (same list)
   - finding.polarity: benefit|harm|neutral  (is the parameter beneficial or harmful
     in aging/this condition)
   - finding.direction: up|down|unchanged  (how the parameter changes in the
     experimental/resilient group)
   - finding.significance: sig|ns|unknown
   - experiment.type: in_vivo|ex_vivo|in_vitro|omics|behavioral|clinical|other
   - finding.group_role: resilient_aged|aged_other|young|intervention|unknown
   - verdict: supported|contradicted|partially_supported|inconclusive
7. Link findings: finding.claim_ref = index into the claims array (or null) that
   the finding bears on; finding.experiment = index into the experiments array
   (or null). Indexes are 0-based.
8. method_flags are independent evidence-quality flags (true/false):
   control (controlled comparisons exist), statistics (statistical tests reported),
   sample_size (group sizes reported), p_value (significant findings have numeric p),
   hypothesis (an explicit hypothesis is stated).
9. verdict summarizes whether the article's evidence supports the central hypothesis.

Respond with a single JSON object:
{{
  "hypothesis": string,
  "goals": [string],
  "claims": [{{"subject": string, "predicate": string, "object": string,
               "negated": bool, "domain": string, "confidence": number}}],
  "experiments": [{{"name": string, "type": string, "verdict": string,
                    "control_groups": [string], "exp_groups": [string],
                    "findings": [string]}}],
  "findings": [{{"parameter": string, "domain": string, "polarity": string,
                  "direction": string, "significance": string, "p": number|null,
                  "group_role": string, "claim_ref": int|null, "experiment": int|null}}],
  "method_flags": {{"control": bool, "statistics": bool, "sample_size": bool,
                    "p_value": bool, "hypothesis": bool}},
  "verdict": string
}}
"""

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    m = _JSON_FENCE_RE.search(text)
    candidate = m.group(1) if m else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(candidate[start : end + 1])
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def normalize_map(raw: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
    """Приводит ответ LLM к единой схеме (со значениями по умолчанию)."""
    claims_raw = raw.get("claims") or []
    claims: List[Dict[str, Any]] = []
    for c in claims_raw:
        if not isinstance(c, dict):
            continue
        claims.append({
            "subject": str(c.get("subject") or "").strip(),
            "predicate": str(c.get("predicate") or "").strip(),
            "object": str(c.get("object") or "").strip(),
            "negated": bool(c.get("negated")),
            "domain": norm_domain(c.get("domain")),
            "confidence": float(c.get("confidence") or 1.0),
        })
    claims = [c for c in claims if c["subject"] and c["predicate"] and c["object"]]

    experiments_raw = raw.get("experiments") or []
    experiments: List[Dict[str, Any]] = []
    for e in experiments_raw:
        if not isinstance(e, dict):
            continue
        experiments.append({
            "name": str(e.get("name") or "").strip(),
            "type": norm_experiment_type(e.get("type")),
            "verdict": norm_verdict(e.get("verdict")),
            "control_groups": [str(g) for g in (e.get("control_groups") or []) if g],
            "exp_groups": [str(g) for g in (e.get("exp_groups") or []) if g],
            "findings": [str(f) for f in (e.get("findings") or []) if f],
        })
    experiments = [e for e in experiments if e["name"]]

    findings: List[Dict[str, Any]] = []
    for f in raw.get("findings") or []:
        if not isinstance(f, dict) or not str(f.get("parameter") or "").strip():
            continue
        p_raw = f.get("p")
        try:
            p = float(p_raw) if p_raw not in (None, "", "null") else None
        except (TypeError, ValueError):
            p = None
        findings.append({
            "parameter": str(f.get("parameter") or "").strip(),
            "domain": norm_domain(f.get("domain")),
            "polarity": norm_polarity(f.get("polarity")),
            "direction": norm_direction(f.get("direction")),
            "significance": norm_significance(f.get("significance"), p),
            "p": p,
            "group_role": _norm(f.get("group_role"), {
                "resilient": "resilient_aged", "resilient_aged": "resilient_aged",
                "aged_other": "aged_other", "aged": "aged_other",
                "young": "young", "молод": "young", "intervention": "intervention",
                "control": "intervention", "unknown": "unknown",
            }, "unknown"),
            "claim_ref": f.get("claim_ref") if isinstance(f.get("claim_ref"), int) else None,
            "experiment": f.get("experiment") if isinstance(f.get("experiment"), int) else None,
        })

    mf = raw.get("method_flags") or {}
    method_flags = {
        "control": bool(mf.get("control")),
        "statistics": bool(mf.get("statistics")),
        "sample_size": bool(mf.get("sample_size")),
        "p_value": bool(mf.get("p_value")),
        "hypothesis": bool(mf.get("hypothesis")),
    }

    return {
        "doc_id": doc_id,
        "hypothesis": str(raw.get("hypothesis") or "").strip(),
        "goals": [str(g) for g in (raw.get("goals") or []) if str(g).strip()],
        "claims": claims,
        "experiments": experiments,
        "findings": findings,
        "method_flags": method_flags,
        "verdict": norm_verdict(raw.get("verdict")),
        "graph": map_to_graph({
            "goals": [str(g) for g in (raw.get("goals") or []) if str(g).strip()],
            "claims": claims,
            "experiments": experiments,
            "findings": findings,
            "method_flags": method_flags,
        }),
    }


# ── Сервис ─────────────────────────────────────────────────────────────────
class EvidenceMapService:
    def __init__(self) -> None:
        self.article_service = ArticleEditorService()

    # Генерация
    async def generate_map(
        self,
        doc_id: str,
        model_id: str = DEFAULT_MODEL,
        temperature: float = 0.2,
        max_tokens: int = 12000,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        text_result = await self.article_service.get_agent_article_text(doc_id)
        if not text_result.get("success") or not text_result.get("text"):
            return {"success": False, "message": "Текст статьи недоступен",
                    "source": text_result.get("source", "none")}
        text = text_result["text"]
        if len(text) > MAX_PROMPT_TEXT_CHARS:
            text = text[:MAX_PROMPT_TEXT_CHARS]
            logger.info("Article text truncated to %d chars for %s", MAX_PROMPT_TEXT_CHARS, doc_id)
        prompt = _PROMPT_TEMPLATE.replace("{article}", text)

        client = get_ai_model_client()
        result = client.generate_text(
            model_id=model_id,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            enable_chunking=True,
            timeout=timeout,
        )
        if not result.get("success"):
            return {"success": False, "message": result.get("message", "Ошибка LLM")}
        raw = _extract_json(result.get("generated_text", ""))
        if raw is None:
            return {"success": False,
                    "message": "Модель вернула невалидный JSON",
                    "generated_text": (result.get("generated_text") or "")[:2000]}
        map_data = normalize_map(raw, doc_id)
        return {
            "success": True,
            "map": map_data,
            "model_used": result.get("model_used", model_id),
            "tokens": {
                "input": result.get("input_tokens", 0),
                "output": result.get("output_tokens", 0),
            },
        }

    # Хранение в Neo4j
    async def save_map(self, doc_id: str, map_data: Dict[str, Any], model_id: str = DEFAULT_MODEL) -> Dict[str, Any]:
        normalized = normalize_map(map_data, doc_id)
        uid = uuid8_str()
        now = datetime.now(timezone.utc).isoformat()
        db.cypher_query(
            "MATCH (d:Document {uid: $doc_id}) "
            "CREATE (m:EvidenceMap {uid: $uid, doc_id: $doc_id, model_id: $model_id, "
            "created_at: datetime($now), verdict: $verdict, data: $data}) "
            "CREATE (d)-[:HAS_EVIDENCE_MAP]->(m)",
            {
                "uid": uid, "doc_id": doc_id, "model_id": model_id, "now": now,
                "verdict": normalized["verdict"],
                "data": json.dumps(normalized, ensure_ascii=False),
            },
        )
        return {"success": True, "uid": uid, "verdict": normalized["verdict"]}

    async def get_map(self, doc_id: str) -> Optional[Dict[str, Any]]:
        rows, _ = db.cypher_query(
            "MATCH (d:Document {uid: $doc_id})-[:HAS_EVIDENCE_MAP]->(m:EvidenceMap) "
            "RETURN m.uid, m.data, m.created_at, m.model_id "
            "ORDER BY m.created_at DESC LIMIT 1",
            {"doc_id": doc_id},
        )
        if not rows:
            return None
        data = rows[0][1] or "{}"
        try:
            m = json.loads(data)
        except (ValueError, TypeError):
            m = {}
        m["uid"] = rows[0][0]
        created = rows[0][2]
        m["created_at"] = created.isoformat() if hasattr(created, "isoformat") else str(created or "")
        m["model_id"] = rows[0][3] or ""
        return m

    async def delete_map(self, doc_id: str) -> bool:
        db.cypher_query(
            "MATCH (d:Document {uid: $doc_id})-[r:HAS_EVIDENCE_MAP]->(m:EvidenceMap) "
            "DELETE r, m",
            {"doc_id": doc_id},
        )
        return True

    async def list_maps(self) -> List[Dict[str, Any]]:
        rows, _ = db.cypher_query(
            "MATCH (m:EvidenceMap) RETURN m.doc_id, m.verdict, m.created_at, m.model_id "
            "ORDER BY m.created_at DESC",
        )
        out = []
        for r in rows:
            created = r[2]
            out.append({
                "doc_id": r[0], "verdict": r[1],
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created or ""),
                "model_id": r[3] or "",
            })
        return out

    # Корпус для майнинга
    def _corpus_graphs(self, doc_ids: Optional[Sequence[str]]) -> List[Dict[str, Any]]:
        if doc_ids:
            graphs = []
            for d in doc_ids:
                m = self._load_latest(d)
                if m and m.get("graph"):
                    graphs.append({"id": d, "verdict": m.get("verdict"), **m["graph"]})
            return graphs
        rows, _ = db.cypher_query(
            "MATCH (m:EvidenceMap) RETURN m.doc_id, m.data "
            "ORDER BY m.created_at DESC",
        )
        seen: Dict[str, str] = {}
        graphs = []
        for r in rows:
            doc_id = r[0]
            if doc_id in seen:
                continue
            seen[doc_id] = doc_id
            try:
                data = json.loads(r[1] or "{}")
            except (ValueError, TypeError):
                continue
            if data.get("graph"):
                graphs.append({"id": doc_id, "verdict": data.get("verdict"), **data["graph"]})
        return graphs

    def _load_latest(self, doc_id: str) -> Optional[Dict[str, Any]]:
        rows, _ = db.cypher_query(
            "MATCH (d:Document {uid: $doc_id})-[:HAS_EVIDENCE_MAP]->(m:EvidenceMap) "
            "RETURN m.data ORDER BY m.created_at DESC LIMIT 1",
            {"doc_id": doc_id},
        )
        if not rows:
            return None
        try:
            return json.loads(rows[0][0] or "{}")
        except (ValueError, TypeError):
            return None

    # Майнинг
    async def mine(
        self,
        doc_ids: Optional[Sequence[str]] = None,
        min_support: float = 0.6,
        min_size: int = 2,
        max_size: int = 6,
        limit: int = 2000,
    ) -> Dict[str, Any]:
        graphs = self._corpus_graphs(doc_ids)
        if not graphs:
            return {"success": True, "patterns": [], "corpus_size": 0,
                    "message": "Нет карт в корпусе"}
        patterns = self._mine_with_hist(
            graphs, min_support=min_support, min_size=min_size,
            max_size=max_size, limit=limit,
        )
        return {"success": True, "patterns": patterns, "corpus_size": len(graphs)}

    def _mine_with_hist(
        self,
        graphs: Sequence[Dict[str, Any]],
        min_support: float = 0.6,
        min_size: int = 2,
        max_size: int = 6,
        limit: int = 2000,
    ) -> List[Dict[str, Any]]:
        patterns = mine_frequent_subgraphs(
            graphs, min_support=min_support, min_size=min_size,
            max_size=max_size, limit=limit,
        )
        verdicts = {g["id"]: g.get("verdict", "inconclusive") for g in graphs}
        for p in patterns:
            hist: Dict[str, int] = {}
            for gid in p.get("graphs", []):
                v = verdicts.get(gid, "inconclusive")
                hist[v] = hist.get(v, 0) + 1
            p["verdict_histogram"] = hist
        return patterns

    # Матчинг
    async def match(
        self,
        doc_id: str,
        patterns: Optional[List[Dict[str, Any]]] = None,
        min_support: float = 1.0,
        min_size: int = 2,
        max_size: int = 6,
        limit: int = 2000,
    ) -> Dict[str, Any]:
        target = self._load_latest(doc_id)
        if not target or not target.get("graph"):
            return {"success": False, "message": "У статьи нет сохранённой EvidenceMap",
                    "matched": [], "prediction": None}
        if patterns is None:
            graphs = self._corpus_graphs(None)
            if len(graphs) <= 1:
                # один граф в корпусе — мин. поддержка 1 (самопаттерны)
                pass
            patterns = self._mine_with_hist(
                graphs, min_support=min_support, min_size=min_size,
                max_size=max_size, limit=limit,
            )
        matched = match_graph(target["graph"], patterns)
        if not patterns:
            return {"success": True, "matched": [], "prediction": None,
                    "message": "Нет паттернов для матчинга"}

        # агрегация: взвешенный вердикт по совпавшим паттернам
        from collections import Counter
        weights: Counter = Counter()
        per_pattern: List[Dict[str, Any]] = []
        for m in matched:
            pat = next((p for p in patterns if p.get("id") == m["pattern"]), None)
            hist = (pat or {}).get("verdict_histogram") or {}
            m["verdict_histogram"] = hist
            m["support"] = pat.get("support", 0) if pat else 0
            per_pattern.append(m)
            total = sum(hist.values()) or 1
            for v, cnt in hist.items():
                weights[v] += (cnt / total) * (1 + m["size"] / max(1, max_size))
        total_w = sum(weights.values())
        if not total_w:
            return {"success": True, "matched": per_pattern, "prediction": None,
                    "message": "Паттерны не имеют вердиктных гистограмм"}
        verdict, top_w = weights.most_common(1)[0]
        confidence = round(top_w / total_w, 3)
        prediction = {
            "verdict": verdict,
            "confidence": confidence,
            "weighted_histogram": dict(weights),
            "matched_count": len(per_pattern),
            "method_flags": target.get("method_flags", {}),
        }
        return {"success": True, "matched": per_pattern, "prediction": prediction}


_evidence_map_service: Optional[EvidenceMapService] = None


def get_evidence_map_service() -> EvidenceMapService:
    global _evidence_map_service
    if _evidence_map_service is None:
        _evidence_map_service = EvidenceMapService()
    return _evidence_map_service
