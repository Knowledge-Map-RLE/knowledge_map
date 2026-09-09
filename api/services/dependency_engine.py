"""
Layer: Services
Package: services.dependency_engine

Dependency engine for the Knowledge Map.

IMPORTANT SEMANTIC DISTINCTION
------------------------------
The source data contains REFERENCES between resources (including assertion IDs).
Those references are required for recursive resolution, but they are NOT,
by themselves, visual dependency edges.

This engine builds a second graph:

    assertion A  --->  assertion B

only when A is a plausible prerequisite/result/mechanism for B, or when an
explicit goal-decomposition relation says so.

Pipeline:
    1. Resolve references for comparison/display.
    2. Candidate Generator: deterministic, conservative rules.
    3. Semantic Verifier: symbolic acceptance + optional LLM for ambiguous cases.
    4. DAG filter: reject cycles.
    5. Optional Neo4j persistence.

The visual Knowledge Map should consume only DependencyEdge objects produced here.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from neomodel import db

from domain.models.dependency import DependencyEdge, DependencyType, DiscoveryMethod

logger = logging.getLogger(__name__)


# =============================================================================
# Normalisation
# =============================================================================

def _normalize_text(text: str) -> str:
    """Canonical text form used for deterministic matching."""
    t = (text or "").strip().lower()
    t = re.sub(r"[\s_]+", " ", t)
    t = re.sub(r"[^\wа-яё ]", "", t, flags=re.UNICODE)
    return t.strip()


def _normalize_entity(text: str) -> str:
    """Canonical entity/state form."""
    t = _normalize_text(text)
    t = re.sub(r"\b(?:the|a|an)\b", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _predicate_key(predicate: str) -> str:
    """Normalize a predicate without trying to infer its full semantics."""
    return _normalize_text(predicate).replace(" ", "_")


# =============================================================================
# Predicate semantics
# =============================================================================

# Predicates that are clearly unsuitable for the main goal-directed dependency
# graph. They can still exist in the knowledge graph and be used elsewhere.
_NOISE_PREDICATES = {
    "is_a",
    "isa",
    "has",
    "contains",
    "related_to",
    "similar_to",
    "associated_with",
    "same_as",
    "alias",
    "also_known_as",
    "part_of",
    "located_in",
    "in",
    "of",
    "with",
}

# Provenance / epistemic edges are valuable, but they should not automatically
# become mechanism/goal edges in the visual map.
_EVIDENCE_PREDICATES = {
    "supports",
    "supported_by",
    "contradicts",
    "contradicted_by",
    "refutes",
    "refuted_by",
    "cites",
    "cited_by",
    "reported_in",
    "derived_from",
    "replicates",
    "replicated_by",
    "evidence_for",
    "evidence_against",
}

# Explicit planning relations. Their direction is handled separately because
# subject/object semantics are "goal/subgoal" rather than ordinary causality.
_GOAL_PREDICATES = {
    "decomposed_into",
    "decomposes_into",
}

# Explicit dependency predicates. For these, the assertion
#   A --depends_on/requires--> B
# means the visual dependency is B -> A.
_EXPLICIT_DEPENDENCY_PREDICATES = {
    "depends_on",
    "depends_on_assertion",
    "requires",
    "requires_assertion",
    "prerequisite",
    "prerequisite_is",
}

_DIRECTION_UP = {
    "increase", "increases", "increased",
    "upregulate", "upregulates", "upregulated",
    "raise", "raises",
    "promote", "promotes",
    "stimulate", "stimulates",
    "activate", "activates",
    "enhance", "enhances",
    "boost", "boosts",
    "induce", "induces",
    "produce", "produces",
    "cause", "causes",
    "lead_to", "leads_to",
    "result_in", "results_in",
    "повыш", "увеличив", "стимул", "активир",
    "растет", "растёт", "усил", "вызывает", "индуц",
}

_DIRECTION_DOWN = {
    "decrease", "decreases", "decreased",
    "downregulate", "downregulates", "downregulated",
    "reduce", "reduces",
    "suppress", "suppresses",
    "inhibit", "inhibits",
    "block", "blocks",
    "prevent", "prevents",
    "lower", "lowers",
    "пониж", "сниж", "угнет", "подавл", "тормоз",
    "ингиб", "блокир", "предотвращ",
}

# Predicates that describe a change/state transition and are therefore
# candidates for chaining when the result of A is the input of B.
_CAUSAL_PREDICATE_STEMS = (
    _DIRECTION_UP
    | _DIRECTION_DOWN
    | {
        "changes",
        "change",
        "affects",
        "affect",
        "modulates",
        "modulate",
        "regulates",
        "regulate",
        "depends",
        "requires",
    }
)

# Noun/state forms used when A.object = "mTOR" and
# B.subject = "mTOR inhibition".
_NOMINAL_STEMS = {
    "up": {
        "activat", "increas", "upregulat", "stimul", "promot", "enhanc",
        "boost", "induc", "rais", "повыш", "усилен", "активирован",
        "стимулирован", "индуц",
    },
    "down": {
        "inhibit", "downregulat", "suppress", "reduc", "decreas",
        "block", "prevent", "lowe", "торможен", "подавлен", "снижен",
        "ингиб", "блокир", "предотвращ", "пониж",
    },
}


def _predicate_direction(predicate: str) -> str:
    """Classify only the coarse direction needed by chaining heuristics."""
    p = _normalize_text(predicate)
    words = set(p.replace("_", " ").split())

    if any(w in words for w in {"up", "increase", "increases", "activate", "activates"}):
        return "up"
    if any(w in words for w in {"down", "decrease", "decreases", "inhibit", "inhibits"}):
        return "down"

    # Stem matching for inflected English/Russian predicates.
    for token in _DIRECTION_UP:
        token_n = _normalize_text(token)
        if len(token_n) >= 4 and token_n in p:
            return "up"
    for token in _DIRECTION_DOWN:
        token_n = _normalize_text(token)
        if len(token_n) >= 4 and token_n in p:
            return "down"

    return "other"


def _is_noise_predicate(predicate: str) -> bool:
    return _predicate_key(predicate) in _NOISE_PREDICATES


def _is_evidence_predicate(predicate: str) -> bool:
    return _predicate_key(predicate) in _EVIDENCE_PREDICATES


def _is_goal_predicate(predicate: str) -> bool:
    return _predicate_key(predicate) in _GOAL_PREDICATES


def _is_explicit_dependency_predicate(predicate: str) -> bool:
    return _predicate_key(predicate) in _EXPLICIT_DEPENDENCY_PREDICATES


def _is_causal_predicate(predicate: str) -> bool:
    p = _predicate_key(predicate)
    if p in _NOISE_PREDICATES or p in _EVIDENCE_PREDICATES:
        return False
    if p in {"step", "result", "sequence"}:
        return False
    if _predicate_direction(p) != "other":
        return True
    return any(
        _normalize_text(stem) in _normalize_text(p)
        for stem in _CAUSAL_PREDICATE_STEMS
        if len(_normalize_text(stem)) >= 4
    )


def _state_matches(obj_text: str, subject_text: str, direction: str) -> bool:
    """
    Does subject_text look like the state produced by applying predicate
    direction to obj_text?

        mTOR + down -> "mTOR inhibition"
        mTOR + up   -> "mTOR activation"

    This rule deliberately requires obj_text to be a prefix/component of
    subject_text. It does not use generic fuzzy substring matching.
    """
    obj_n = _normalize_entity(obj_text)
    subj_n = _normalize_entity(subject_text)
    if not obj_n or not subj_n:
        return False

    if obj_n == subj_n:
        return True

    if not subj_n.startswith(obj_n + " "):
        return False

    stems = _NOMINAL_STEMS.get(direction, set())
    tail = subj_n[len(obj_n):].strip()

    return any(stem in tail for stem in stems)


# =============================================================================
# Recursive reference resolution
# =============================================================================

@dataclass(frozen=True)
class ResolvedTerm:
    """Human-readable resolved representation plus the reference chain."""

    text: str
    references: Tuple[str, ...] = ()


class AssertionResolver:
    """
    Resolves assertion-ID references recursively for matching and LLM prompts.

    This does NOT create visual edges. Resolution is purely a representation
    operation.
    """

    MAX_DEPTH = 32

    def __init__(self, triples: Dict[str, Dict[str, Any]]):
        self._triples = triples
        self._cache: Dict[str, str] = {}

    def resolve_resource(self, uid: str, depth: int = 0, stack: Optional[Set[str]] = None) -> str:
        if uid in self._cache:
            return self._cache[uid]

        if depth >= self.MAX_DEPTH:
            return f"<{uid}:max-depth>"

        stmt = self._triples.get(uid)
        if not stmt:
            return uid

        stack = set(stack or ())
        if uid in stack:
            return f"<{uid}:cycle>"
        stack.add(uid)

        subject = self.resolve_value(stmt.get("subject_text", ""), depth + 1, stack)
        predicate = str(stmt.get("predicate", "") or "").strip()
        obj = self.resolve_value(stmt.get("object_text", ""), depth + 1, stack)

        text = f"{subject} → {predicate} → {obj}"
        self._cache[uid] = text
        return text

    def resolve_value(self, value: Any, depth: int = 0, stack: Optional[Set[str]] = None) -> str:
        raw = "" if value is None else str(value).strip()
        if not raw:
            return ""

        if raw in self._triples:
            return self.resolve_resource(raw, depth, stack)

        return raw

    def statement_text(self, uid: str) -> str:
        return self.resolve_resource(uid)


# =============================================================================
# Candidate Generator
# =============================================================================

class CandidateGenerator:
    """
    Conservative candidate generator.

    Core rule:
        A.object == B.subject
    is only a CANDIDATE when A and B describe causal/mechanistic state
    transitions. We no longer treat every subject/object reference as a
    visual dependency.

    Removed intentionally:
      * generic "all structural triples -> all statements in blocks"
      * arbitrary direction composition that creates shortcut edges A -> C
      * textual index containing both subjects and objects (which produced
        accidental matches in both directions)
    """

    EXACT_MATCH_CONFIDENCE = 0.78
    NOMINAL_MATCH_CONFIDENCE = 0.70
    EXPLICIT_CONFIDENCE = 1.0

    def __init__(self, triples: Dict[str, Dict[str, Any]]):
        self._triples = triples
        self._resolver = AssertionResolver(triples)
        self._subject_index: Dict[str, List[str]] = {}
        self._build_index()

    def _is_assertion(self, stmt: Dict[str, Any]) -> bool:
        return str(stmt.get("type", "")).upper() != "META"

    def _build_index(self) -> None:
        for uid, stmt in self._triples.items():
            if not self._is_assertion(stmt):
                continue

            subject = _normalize_entity(self._resolved_subject(uid, stmt))
            if subject:
                self._subject_index.setdefault(subject, []).append(uid)

    def _resolved_subject(self, uid: str, stmt: Dict[str, Any]) -> str:
        raw = stmt.get("subject_text", "")
        if str(raw) in self._triples and str(raw) != uid:
            return self._resolver.resolve_resource(str(raw))
        return str(raw or "")

    def _resolved_object(self, uid: str, stmt: Dict[str, Any]) -> str:
        raw = stmt.get("object_text", "")
        if str(raw) in self._triples and str(raw) != uid:
            return self._resolver.resolve_resource(str(raw))
        return str(raw or "")

    def _make_edge(
        self,
        source_uid: str,
        target_uid: str,
        dependency_type: DependencyType,
        confidence: float,
        method: DiscoveryMethod,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DependencyEdge:
        return DependencyEdge(
            source_uid=source_uid,
            target_uid=target_uid,
            dependency_type=dependency_type,
            confidence=confidence,
            discovery_method=method,
            is_verified=False,
            metadata=metadata or {},
        )

    def generate(self) -> List[DependencyEdge]:
        edges: List[DependencyEdge] = []

        edges.extend(self._explicit_dependencies())
        edges.extend(self._goal_decomposition())
        edges.extend(self._exact_state_flow())
        edges.extend(self._nominalized_state_flow())

        deduped = self._deduplicate(edges)

        logger.info(
            "CandidateGenerator: %d raw candidates -> %d after dedup",
            len(edges),
            len(deduped),
        )
        return deduped

    def _explicit_dependencies(self) -> List[DependencyEdge]:
        """
        Explicit assertion:
            A --depends_on--> B
        means the visual edge:
            B -> A

        This is deliberately the only place where an assertion predicate
        directly defines a dependency edge.
        """
        edges: List[DependencyEdge] = []

        for uid, stmt in self._triples.items():
            if self._is_assertion(stmt):
                continue

            predicate = stmt.get("predicate", "")
            if not _is_explicit_dependency_predicate(predicate):
                continue

            subject_uid = str(stmt.get("subject_text", "") or "")
            object_uid = str(stmt.get("object_text", "") or "")
            if subject_uid in self._triples and object_uid in self._triples:
                edges.append(
                    self._make_edge(
                        source_uid=object_uid,
                        target_uid=subject_uid,
                        dependency_type=DependencyType.LOGICAL,
                        confidence=self.EXPLICIT_CONFIDENCE,
                        method=DiscoveryMethod.STRUCTURAL,
                        metadata={"kind": "explicit_dependency"},
                    )
                )

        return edges

    def _goal_decomposition(self) -> List[DependencyEdge]:
        """
        Goal decomposition assertion:
            Step --decomposed_into--> Goal
        gives:
            Step -> Goal

        In the domain data the subject of "X decomposed_into Y" is the concrete
        step (subgoal) and the object is the parent goal it feeds into. The
        visual dependency therefore goes from the prerequisite step to the goal:
            source = subject (step), target = object (goal).
        """
        edges: List[DependencyEdge] = []

        for uid, stmt in self._triples.items():
            if str(stmt.get("type", "")).upper() != "META":
                continue

            if not _is_goal_predicate(stmt.get("predicate", "")):
                continue

            step_uid = str(stmt.get("subject_text", "") or "")
            goal_uid = str(stmt.get("object_text", "") or "")

            if step_uid not in self._triples or goal_uid not in self._triples:
                continue

            edges.append(
                self._make_edge(
                    source_uid=step_uid,
                    target_uid=goal_uid,
                    dependency_type=DependencyType.GOAL_DIRECTED,
                    confidence=1.0,
                    method=DiscoveryMethod.GOAL_DECOMPOSITION,
                    metadata={"kind": "goal_decomposition"},
                )
            )

        return edges

    def _exact_state_flow(self) -> List[DependencyEdge]:
        """
        A.object == B.subject.

        This is accepted only for causal/mechanistic transitions. In particular,
        "Rapamycin inhibits mTOR" -> "mTOR is located in ..." will NOT become a
        map dependency.
        """
        edges: List[DependencyEdge] = []

        for uid_a, stmt_a in self._triples.items():
            if not self._is_assertion(stmt_a):
                continue

            pred_a = str(stmt_a.get("predicate", "") or "")
            if not _is_causal_predicate(pred_a):
                continue

            obj_a = _normalize_entity(self._resolved_object(uid_a, stmt_a))
            if not obj_a:
                continue

            for uid_b in self._subject_index.get(obj_a, []):
                if uid_b == uid_a:
                    continue

                stmt_b = self._triples.get(uid_b)
                if not stmt_b or not self._is_assertion(stmt_b):
                    continue

                pred_b = str(stmt_b.get("predicate", "") or "")
                if not _is_causal_predicate(pred_b):
                    continue

                edges.append(
                    self._make_edge(
                        source_uid=uid_a,
                        target_uid=uid_b,
                        dependency_type=DependencyType.CAUSAL,
                        confidence=self.EXACT_MATCH_CONFIDENCE,
                        method=DiscoveryMethod.EXACT_MATCH,
                        metadata={
                            "kind": "exact_state_flow",
                            "matched": obj_a,
                        },
                    )
                )

        return edges

    def _nominalized_state_flow(self) -> List[DependencyEdge]:
        """
        Example:
            A1: Rapamycin inhibits mTOR
            A2: mTOR inhibition increases autophagy

        => A1 -> A2

        Unlike the old engine, this rule does NOT infer A1 -> A3 through a
        third assertion. It only connects the directly dependent pair.

        Performance note: a naive nested loop over all statement pairs is
        O(N^2) and hangs on corpora with thousands of triples. Because
        ``_state_matches`` only ever matches subjects that *start* with the
        object term, we restrict the scan to subjects sharing the first token
        of the object term, which preserves the exact same semantics.
        """
        edges: List[DependencyEdge] = []

        causal_uids = [
            uid
            for uid, stmt in self._triples.items()
            if self._is_assertion(stmt)
            and _is_causal_predicate(str(stmt.get("predicate", "") or ""))
        ]

        # Нормализованный разрешённый субъект каждого утверждения.
        resolved_subject: Dict[str, str] = {}
        buckets: Dict[str, List[str]] = {}
        for uid in causal_uids:
            subj_n = _normalize_entity(self._resolved_subject(uid, self._triples[uid]))
            resolved_subject[uid] = subj_n
            if subj_n:
                buckets.setdefault(subj_n.split(" ", 1)[0], []).append(uid)

        for uid_a in causal_uids:
            stmt_a = self._triples[uid_a]
            pred_a = str(stmt_a.get("predicate", "") or "")
            direction_a = _predicate_direction(pred_a)
            if direction_a not in {"up", "down"}:
                continue

            obj_a_raw = self._resolved_object(uid_a, stmt_a)
            obj_a_n = _normalize_entity(obj_a_raw)
            if not obj_a_n:
                continue

            first = obj_a_n.split(" ", 1)[0]
            for uid_b in buckets.get(first, ()):
                if uid_b == uid_a:
                    continue

                stmt_b = self._triples[uid_b]
                pred_b = str(stmt_b.get("predicate", "") or "")
                if not _is_causal_predicate(pred_b):
                    continue

                subject_b = self._resolved_subject(uid_b, stmt_b)
                if not _state_matches(obj_a_raw, subject_b, direction_a):
                    continue

                edges.append(
                    self._make_edge(
                        source_uid=uid_a,
                        target_uid=uid_b,
                        dependency_type=DependencyType.CAUSAL,
                        confidence=self.NOMINAL_MATCH_CONFIDENCE,
                        method=DiscoveryMethod.PREDICATE_DIRECTION,
                        metadata={
                            "kind": "nominalized_state_flow",
                            "object": obj_a_raw,
                            "subject": subject_b,
                            "direction": direction_a,
                        },
                    )
                )

        return edges

    def _deduplicate(self, edges: List[DependencyEdge]) -> List[DependencyEdge]:
        best: Dict[Tuple[str, str], DependencyEdge] = {}

        for edge in edges:
            if not edge.source_uid or not edge.target_uid:
                continue
            if edge.source_uid == edge.target_uid:
                continue

            key = (edge.source_uid, edge.target_uid)
            current = best.get(key)
            if current is None or edge.confidence > current.confidence:
                best[key] = edge

        return list(best.values())


# =============================================================================
# Semantic Verifier
# =============================================================================

class SemanticVerifier:
    """
    Verifies candidate edges.

    Policy:
      * Explicit / goal-decomposition edges are accepted symbolically.
      * High-confidence exact matches are accepted symbolically.
      * Ambiguous nominalized matches can be sent to LLM.
      * LLM sees recursively resolved assertion text, never raw UUIDs.
    """

    LLM_THRESHOLD = 0.80

    def __init__(self):
        self._llm_client = None

    def _get_llm_client(self):
        if self._llm_client is None:
            try:
                from services.ai_model_client import get_ai_model_client
                self._llm_client = get_ai_model_client()
            except Exception as exc:
                logger.warning("LLM client unavailable: %s", exc)
        return self._llm_client

    def verify(
        self,
        candidates: List[DependencyEdge],
        triples: Dict[str, Dict[str, Any]],
        use_llm: bool = True,
    ) -> List[DependencyEdge]:
        resolver = AssertionResolver(triples)

        verified: List[DependencyEdge] = []
        llm_candidates: List[DependencyEdge] = []

        for edge in candidates:
            kind = str((edge.metadata or {}).get("kind", ""))

            # These are already explicit semantic instructions.
            if kind in {"explicit_dependency", "goal_decomposition"}:
                edge.is_verified = True
                verified.append(edge)
                continue

            # Exact state flow is a strong symbolic signal, but still below 0.80:
            # it may be a syntactic chain which is not actually a goal dependency.
            if edge.confidence >= self.LLM_THRESHOLD:
                edge.is_verified = True
                verified.append(edge)
            elif use_llm:
                llm_candidates.append(edge)
            else:
                # Without LLM we still keep deterministic candidates, but mark
                # them unverified so callers can decide whether to display them.
                edge.is_verified = False
                verified.append(edge)

        llm_results: List[DependencyEdge] = []
        if use_llm and llm_candidates:
            llm_results = self._llm_verify_batch(llm_candidates, triples, resolver)
            verified.extend(llm_results)

        logger.info(
            "SemanticVerifier: %d candidates -> %d verified (%d LLM)",
            len(candidates),
            len(verified),
            len(llm_results),
        )
        return verified

    def _llm_verify_batch(
        self,
        candidates: List[DependencyEdge],
        triples: Dict[str, Dict[str, Any]],
        resolver: AssertionResolver,
    ) -> List[DependencyEdge]:
        client = self._get_llm_client()
        if not client:
            logger.warning(
                "LLM unavailable; keeping ambiguous candidates unverified"
            )
            return candidates

        verified: List[DependencyEdge] = []
        for edge in candidates:
            result = self._llm_verify_single(edge, triples, resolver, client)
            if result is not None:
                verified.append(result)

        return verified

    def _llm_verify_single(
        self,
        edge: DependencyEdge,
        triples: Dict[str, Dict[str, Any]],
        resolver: AssertionResolver,
        client: Any,
    ) -> Optional[DependencyEdge]:
        if edge.source_uid not in triples or edge.target_uid not in triples:
            return None

        text_a = resolver.statement_text(edge.source_uid)
        text_b = resolver.statement_text(edge.target_uid)

        prompt = f"""
You are verifying a dependency edge in a scientific goal-directed knowledge map.

Statement A:
{text_a}

Statement B:
{text_b}

Question:
Does B genuinely depend on A as a prerequisite, intermediate mechanism,
state transition, or necessary logical step for a goal-directed chain?

IMPORTANT:
- Mere topical similarity is NOT a dependency.
- Citation/provenance relation is NOT a mechanism dependency.
- Shared entities alone are NOT sufficient.
- Do not infer a dependency just because A and B mention the same concept.
- Prefer "false" when evidence is insufficient.
- The visual map must remain sparse.

Return JSON only:
{{
  "dependency": true,
  "type": "causal|mechanistic|logical|evidential",
  "confidence": 0.0,
  "reason": "brief reason"
}}
""".strip()

        try:
            result = client.generate_text(
                model_id="qwen/qwen3-4b",
                prompt=prompt,
                max_tokens=250,
                temperature=0.0,
                timeout=30,
                extra_body={"thinking": False},
            )
        except Exception as exc:
            logger.warning(
                "LLM verification failed for %s->%s: %s",
                edge.source_uid,
                edge.target_uid,
                exc,
            )
            return edge

        if not result or not result.get("success"):
            return edge

        parsed = self._parse_llm_response(str(result.get("generated_text", "")))
        if not parsed:
            return edge

        dependency = bool(parsed.get("dependency", False))
        confidence = float(parsed.get("confidence", 0.0) or 0.0)

        if not dependency or confidence < 0.5:
            return None

        edge.confidence = min(edge.confidence, confidence)
        edge.is_verified = True

        parsed_type = str(parsed.get("type", "") or "")
        if parsed_type:
            try:
                edge.dependency_type = DependencyType(parsed_type)
            except ValueError:
                # Keep the symbolic type if the model used a value not present
                # in the current enum.
                pass

        metadata = dict(edge.metadata or {})
        metadata["llm_reason"] = str(parsed.get("reason", "") or "")
        metadata["llm_confidence"] = confidence
        edge.metadata = metadata

        return edge

    @staticmethod
    def _parse_llm_response(content: str) -> Optional[Dict[str, Any]]:
        content = re.sub(
            r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE
        )
        content = re.sub(r"\s*```$", "", content)

        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end < start:
            return None

        try:
            return json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            return None


# =============================================================================
# DAG filtering
# =============================================================================

class DAGFilter:
    """
    Turns a set of candidate edges into an acyclic directed graph.

    Strategy:
      * Keep explicit/goal edges first.
      * Then keep edges in descending confidence order.
      * Reject an edge if it would create a cycle.

    This is intentionally deterministic and does not require Neo4j.
    """

    _KIND_PRIORITY = {
        "explicit_dependency": 0,
        "goal_decomposition": 0,
        "exact_state_flow": 1,
        "nominalized_state_flow": 2,
    }

    @classmethod
    def filter(cls, edges: Iterable[DependencyEdge]) -> List[DependencyEdge]:
        edges = list(edges)

        def sort_key(edge: DependencyEdge):
            kind = str((edge.metadata or {}).get("kind", ""))
            return (
                cls._KIND_PRIORITY.get(kind, 10),
                -float(edge.confidence),
                edge.source_uid,
                edge.target_uid,
            )

        ordered = sorted(edges, key=sort_key)

        adjacency: Dict[str, Set[str]] = {}
        accepted: List[DependencyEdge] = []

        for edge in ordered:
            source = edge.source_uid
            target = edge.target_uid

            if not source or not target or source == target:
                continue

            # Would target reach source already? Then adding source -> target
            # closes a cycle.
            if cls._reachable(adjacency, target, source):
                logger.warning(
                    "Rejecting cyclic dependency %s -> %s",
                    source,
                    target,
                )
                continue

            adjacency.setdefault(source, set()).add(target)
            accepted.append(edge)

        return accepted

    @staticmethod
    def _reachable(
        adjacency: Dict[str, Set[str]],
        start: str,
        target: str,
    ) -> bool:
        if start == target:
            return True

        stack = [start]
        visited: Set[str] = set()

        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)

            for nxt in adjacency.get(node, ()):
                if nxt == target:
                    return True
                if nxt not in visited:
                    stack.append(nxt)

        return False


# =============================================================================
# Neo4j Persistence
# =============================================================================

class DependencyPersistence:
    """
    Persists only visual dependency edges.

    IMPORTANT:
    These DEPENDS_ON relationships are a derived graph. They are not the
    semantic references used inside assertions.
    """

    @staticmethod
    def save_edges(edges: List[DependencyEdge]) -> int:
        if not edges:
            return 0

        # Always enforce DAG property at the persistence boundary too.
        edges = DAGFilter.filter(edges)

        db.cypher_query("MATCH ()-[r:DEPENDS_ON]->() DELETE r")
        logger.info("Deleted old DEPENDS_ON edges")

        try:
            db.cypher_query(
                "CREATE INDEX IF NOT EXISTS FOR (s:KnowledgeStatement) ON (s.uid)"
            )
        except Exception:
            logger.warning(
                "Could not ensure KnowledgeStatement(uid) index",
                exc_info=True,
            )

        batch_size = 500
        created = 0

        for i in range(0, len(edges), batch_size):
            batch = edges[i:i + batch_size]
            params = {
                "edges": [
                    {
                        "source_uid": e.source_uid,
                        "target_uid": e.target_uid,
                        "dependency_type": e.dependency_type.value,
                        "confidence": e.confidence,
                        "discovery_method": e.discovery_method.value,
                        "is_verified": e.is_verified,
                    }
                    for e in batch
                ]
            }

            query = """
            UNWIND $edges AS edge
            MATCH (a:KnowledgeStatement {uid: edge.source_uid})
            MATCH (b:KnowledgeStatement {uid: edge.target_uid})
            MERGE (a)-[r:DEPENDS_ON]->(b)
            SET r.dependency_type = edge.dependency_type,
                r.confidence = edge.confidence,
                r.discovery_method = edge.discovery_method,
                r.is_verified = edge.is_verified
            """
            db.cypher_query(query, params)
            created += len(batch)

        logger.info("Created %d DEPENDS_ON edges", created)
        return created

    @staticmethod
    def load_edges() -> List[DependencyEdge]:
        query = """
        MATCH (a:KnowledgeStatement)-[r:DEPENDS_ON]->(b:KnowledgeStatement)
        RETURN a.uid AS source_uid,
               b.uid AS target_uid,
               r.dependency_type AS dependency_type,
               r.confidence AS confidence,
               r.discovery_method AS discovery_method,
               r.is_verified AS is_verified
        """
        result, _ = db.cypher_query(query)

        edges: List[DependencyEdge] = []
        for row in result:
            try:
                edges.append(
                    DependencyEdge(
                        source_uid=str(row[0]),
                        target_uid=str(row[1]),
                        dependency_type=DependencyType(str(row[2] or "causal")),
                        confidence=float(row[3] or 1.0),
                        discovery_method=DiscoveryMethod(
                            str(row[4] or "exact_match")
                        ),
                        is_verified=bool(row[5]),
                    )
                )
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Failed to parse DEPENDS_ON edge: %s", exc
                )

        return edges

    @staticmethod
    def delete_edges() -> None:
        db.cypher_query("MATCH ()-[r:DEPENDS_ON]->() DELETE r")
        logger.info("Deleted all DEPENDS_ON edges")


# =============================================================================
# Main Engine
# =============================================================================

class DependencyEngine:
    """
    Main dependency graph engine.

    The returned graph is the graph for the visual Knowledge Map, NOT the full
    semantic reference graph.
    """

    def __init__(self):
        self._verifier = SemanticVerifier()

    async def build_dependency_graph(
        self,
        triples: Dict[str, Dict[str, Any]],
        use_llm: bool = True,
    ) -> List[DependencyEdge]:
        generator = CandidateGenerator(triples)
        candidates = generator.generate()

        if not candidates:
            logger.info("No dependency candidates found")
            return []

        verified = self._verifier.verify(
            candidates,
            triples,
            use_llm=use_llm,
        )

        dag = DAGFilter.filter(verified)

        logger.info(
            "DependencyEngine: %d triples -> %d candidates -> %d verified -> %d DAG edges",
            len(triples),
            len(candidates),
            len(verified),
            len(dag),
        )

        return dag

    def save(self, edges: List[DependencyEdge]) -> int:
        return DependencyPersistence.save_edges(edges)

    def load(self) -> List[DependencyEdge]:
        return DependencyPersistence.load_edges()

    def clear(self) -> None:
        DependencyPersistence.delete_edges()
