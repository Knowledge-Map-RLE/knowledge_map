from __future__ import annotations

import re

from src.domain.models import Statement, StatementType, StatementID, Concept
from src.domain.interfaces import PipelineStep


# META patterns:
#   (regex, direction, predicate)
#   direction = "ref_in_subj" → referenced fact goes in subject (UUID → pred → concept)
#   direction = "ref_in_obj"  → referenced fact goes in object (concept → pred → UUID)
#   regex group 1 = referrer text (the one that references)
_META_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # referee_in_subject: "as revealed by PD research" → FACT → pred → PD research
    (re.compile(r'as\s+revealed\s+by\s+(.+)', re.I), 'ref_in_subj', 'revealed by'),
    (re.compile(r'as\s+shown\s+by\s+(.+)', re.I), 'ref_in_subj', 'shown by'),
    (re.compile(r'as\s+demonstrated\s+by\s+(.+)', re.I), 'ref_in_subj', 'demonstrated by'),
    (re.compile(r'as\s+proposed\s+by\s+(.+)', re.I), 'ref_in_subj', 'proposed by'),
    (re.compile(r'as\s+discussed\s+in\s+(.+)', re.I), 'ref_in_subj', 'discussed in'),
    (re.compile(r'is\s+supported\s+by\s+(.+)', re.I), 'ref_in_subj', 'supported by'),
    (re.compile(r'was\s+found\s+by\s+(.+)', re.I), 'ref_in_subj', 'found by'),
    (re.compile(r'is\s+described\s+in\s+(.+)', re.I), 'ref_in_subj', 'described in'),
    # referee_in_object: "X suggests that Y" → X → suggest → FACT(Y)
    (re.compile(r'(.+)\s+suggests?\s+that', re.I), 'ref_in_obj', 'suggest'),
    (re.compile(r'(.+)\s+suggested\s+that', re.I), 'ref_in_obj', 'suggest'),
    (re.compile(r'(.+)\s+shows?\s+that', re.I), 'ref_in_obj', 'show'),
    (re.compile(r'(.+)\s+demonstrated\s+that', re.I), 'ref_in_obj', 'demonstrate'),
    (re.compile(r'(.+)\s+demonstrates?\s+that', re.I), 'ref_in_obj', 'demonstrate'),
    (re.compile(r'(.+)\s+indicates?\s+that', re.I), 'ref_in_obj', 'indicate'),
    (re.compile(r'(.+)\s+indicated\s+that', re.I), 'ref_in_obj', 'indicate'),
    (re.compile(r'(.+)\s+proposes?\s+that', re.I), 'ref_in_obj', 'propose'),
    (re.compile(r'(.+)\s+proposed\s+that', re.I), 'ref_in_obj', 'propose'),
    (re.compile(r'(.+)\s+have\s+shown\s+that', re.I), 'ref_in_obj', 'show'),
    (re.compile(r'(.+)\s+has\s+shown\s+that', re.I), 'ref_in_obj', 'show'),
    (re.compile(r'(.+)\s+revealed\s+that', re.I), 'ref_in_obj', 'reveal'),
    (re.compile(r'(.+)\s+reveals?\s+that', re.I), 'ref_in_obj', 'reveal'),
]


_VERB_FORMS: dict[str, set[str]] = {
    "be": {"is", "are", "was", "were", "been", "am", "being", "'s", "'re", "'m"},
    "have": {"has", "had", "having", "'ve", "'s"},
    "do": {"does", "did", "doing", "done"},
    "show": {"shows", "showed", "shown", "showing"},
    "suggest": {"suggests", "suggested", "suggesting"},
    "reveal": {"reveals", "revealed", "revealing"},
    "demonstrate": {"demonstrates", "demonstrated", "demonstrating"},
    "indicate": {"indicates", "indicated", "indicating"},
    "propose": {"proposes", "proposed", "proposing"},
    "discuss": {"discusses", "discussed", "discussing"},
    "describe": {"describes", "described", "describing"},
    "support": {"supports", "supported", "supporting"},
    "find": {"finds", "found", "finding"},
    "contain": {"contains", "contained", "containing"},
    "lead": {"leads", "led", "leading"},
    "cause": {"causes", "caused", "causing"},
    "associate": {"associates", "associated", "associating"},
    "involve": {"involves", "involved", "involving"},
    "depict": {"depicts", "depicted", "depicting"},
}


def _words_match(w1: str, w2: str) -> bool:
    if w1 == w2:
        return True
    for base, forms in _VERB_FORMS.items():
        if w1 == base and w2 in forms:
            return True
        if w2 == base and w1 in forms:
            return True
        if w1 in forms and w2 in forms:
            return True
    return False


def _contained_in(needle: str, haystack: str) -> bool:
    """Check if all words of needle appear in order inside haystack (verb-form aware)."""
    n_words = needle.lower().split()
    h_words = haystack.lower().split()
    i = 0
    for word in h_words:
        if i < len(n_words) and _words_match(n_words[i], word):
            i += 1
    return i == len(n_words)


def _fact_matches_text(fact: Statement, text_fragment: str) -> bool:
    """Check if a fact's subject and predicate appear within a text fragment."""
    subj = fact.subject.text if isinstance(fact.subject, Concept) else ""
    if not subj:
        return False
    pred = fact.predicate
    return _contained_in(subj, text_fragment) and _contained_in(pred, text_fragment)


class MetaBuilder(PipelineStep):
    """Builds meta-statements (M-type) linking facts discovered from context."""

    def process(
        self,
        statements: list[Statement],
        concepts: dict[str, Concept],
        context: dict,
    ) -> tuple[list[Statement], dict[str, Concept]]:
        facts = [s for s in statements if s.type == StatementType.FACT]
        meta_statements: list[Statement] = []

        # Step 1: Pattern-based META
        if len(facts) >= 1:
            meta_statements.extend(self._build_from_patterns(facts, context.get("doc_id", "")))

        # Step 2: Shared-concept META (existing fallback), skip if already covered
        if len(facts) >= 2:
            existing_pairs = self._existing_meta_pairs(meta_statements)
            meta_statements.extend(self._build_shared_concept(facts, context, existing_pairs))

        statements.extend(meta_statements)
        return statements, concepts

    @staticmethod
    def _existing_meta_pairs(meta_list: list[Statement]) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for m in meta_list:
            s_id = str(m.subject.id) if isinstance(m.subject, Statement) else ""
            o_id = str(m.object.id) if isinstance(m.object, Statement) else ""
            if s_id and o_id:
                pairs.add((s_id, o_id))
        return pairs

    def _build_from_patterns(
        self, facts: list[Statement], doc_id: str,
    ) -> list[Statement]:
        """Scan sentences for META patterns and create corresponding META statements."""
        meta_statements: list[Statement] = []

        # Group facts by sentence text
        sent_to_facts: dict[str, list[Statement]] = {}
        for f in facts:
            key = f.sentence_text or ""
            sent_to_facts.setdefault(key, []).append(f)

        for sentence_text, sent_facts in sent_to_facts.items():
            if not sentence_text:
                continue
            meta_statements.extend(
                self._pattern_search(sentence_text, sent_facts, facts, doc_id)
            )

        return meta_statements

    def _pattern_search(
        self, sentence_text: str,
        sent_facts: list[Statement],
        all_facts: list[Statement],
        doc_id: str,
    ) -> list[Statement]:
        """Search one sentence for all META pattern matches."""
        result: list[Statement] = []
        used_refs: set[str] = set()

        for pattern, direction, predicate in _META_PATTERNS:
            match = pattern.search(sentence_text)
            if not match:
                continue

            if direction == 'ref_in_subj':
                referrer_text = match.group(1).strip()
                referee_part = sentence_text[:match.start()].strip()
            else:
                referrer_text = match.group(1).strip()
                referee_part = sentence_text[match.end():].strip()

            if not referee_part or not referrer_text:
                continue

            # Filter dummy subjects (e.g. "it has been" = dummy "it")
            if referrer_text.lower().startswith('it has ') or referrer_text.lower() == 'it has':
                continue

            # Clean referrer text: strip citation brackets [N] and trailing punctuation
            referrer_text = re.sub(r'\s*\[\d+(?:[,\s]+\d+)*\]\.?\s*$', '', referrer_text)
            referrer_text = referrer_text.rstrip('.,;:')

            if not referrer_text:
                continue

            # Find a fact matching the referee_part
            matched_fact = self._find_referee_fact(referee_part, sent_facts)
            if matched_fact is None:
                continue
            ref_id = str(matched_fact.id)
            if ref_id in used_refs:
                continue
            used_refs.add(ref_id)

            referrer = Concept(
                id=f"meta_ref_{doc_id}_{len(result)}",
                text=referrer_text,
                normalized_text=referrer_text.lower(),
            )

            if direction == 'ref_in_subj':
                meta = Statement(
                    id=StatementID.new(),
                    type=StatementType.META,
                    subject=matched_fact,
                    predicate=predicate,
                    object=referrer,
                    sentence_text=sentence_text,
                    metadata={"pattern": pattern.pattern},
                )
            else:
                meta = Statement(
                    id=StatementID.new(),
                    type=StatementType.META,
                    subject=referrer,
                    predicate=predicate,
                    object=matched_fact,
                    sentence_text=sentence_text,
                    metadata={"pattern": pattern.pattern},
                )
            result.append(meta)

        return result

    @staticmethod
    def _find_referee_fact(
        referee_part: str, sent_facts: list[Statement],
    ) -> Statement | None:
        """Find the fact whose content matches the referee text portion."""
        best: Statement | None = None
        best_score = 0
        for fact in sent_facts:
            subj = fact.subject.text if isinstance(fact.subject, Concept) else ""
            obj = fact.object.text if isinstance(fact.object, Concept) else ""
            score = 0
            if subj and _contained_in(subj, referee_part):
                score += 2
            if fact.predicate and _contained_in(fact.predicate, referee_part):
                score += 1
            if obj and _contained_in(obj, referee_part):
                score += 1
            if score > best_score:
                best_score = score
                best = fact
        if best_score >= 2:
            return best
        return None

    @staticmethod
    def _build_shared_concept(
        facts: list[Statement],
        context: dict,
        existing_pairs: set[tuple[str, str]],
    ) -> list[Statement]:
        """Build META statements between facts sharing a concept (fallback)."""
        meta_statements: list[Statement] = []

        concept_to_facts: dict[str, list[int]] = {}
        for i, fact in enumerate(facts):
            if isinstance(fact.subject, Concept):
                concept_to_facts.setdefault(fact.subject_id, []).append(i)
            if isinstance(fact.object, Concept):
                concept_to_facts.setdefault(fact.object_id, []).append(i)

        seen_pairs: set[tuple[int, int]] = set()
        for cid, fact_idxs in concept_to_facts.items():
            if len(fact_idxs) < 2:
                continue
            for i in range(len(fact_idxs)):
                for j in range(i + 1, len(fact_idxs)):
                    a_idx, b_idx = fact_idxs[i], fact_idxs[j]
                    pair = (a_idx, b_idx) if a_idx < b_idx else (b_idx, a_idx)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    fact_a = facts[a_idx]
                    fact_b = facts[b_idx]
                    key = (str(fact_a.id), str(fact_b.id))
                    if key in existing_pairs:
                        continue
                    meta = Statement(
                        id=StatementID.new(),
                        type=StatementType.META,
                        subject=fact_a,
                        predicate="related_to",
                        object=fact_b,
                        sentence_text=context.get("sentence", ""),
                        metadata={"via_concept": cid},
                    )
                    meta_statements.append(meta)

        return meta_statements
