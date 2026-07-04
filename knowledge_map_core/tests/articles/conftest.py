from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

DATA_ARTICLES = Path(__file__).resolve().parent.parent.parent.parent / "data" / "articles"
GROUND_TRUTH = Path(__file__).resolve().parent / "ground_truth"


class Triplet(NamedTuple):
    subject: str
    predicate: str
    object: str


class GroundTruthEntry(NamedTuple):
    uuid: str
    subject: str
    predicate: str
    object: str
    is_fact: bool

    def resolved_triplet(self, lookup: dict[str, "GroundTruthEntry"]) -> Triplet:
        """Resolve UUID references to get the full text triplet."""
        def resolve(val: str) -> str:
            if re.match(r'^[0-9a-f-]+$', val) and val in lookup:
                inner = lookup[val].resolved_triplet(lookup)
                return inner.subject  # use the subject text as the resolved value
            return val
        return Triplet(resolve(self.subject), self.predicate, resolve(self.object))


_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


def is_uuid(s: str) -> bool:
    return bool(_UUID_RE.match(s))


def load_article_text(article_id: str) -> str:
    """Load article .md text, strip YAML frontmatter and references section."""
    for d in DATA_ARTICLES.iterdir():
        if not d.is_dir():
            continue
        norm = d.name.lower().replace("'", "").replace("’", "").replace("  ", " ")
        if article_id.lower().replace("_", " ").replace("'", "").replace("’", "") in norm:
            md = sorted(d.glob("*.md"))
            for f in md:
                if "rus" in f.name:
                    continue
                text = f.read_text(encoding="utf-8")
                text = _strip_frontmatter(text)
                # Remove references section (everything after ## References)
                ref_idx = text.find("## References")
                if ref_idx != -1:
                    text = text[:ref_idx]
                return text.strip()
    raise FileNotFoundError(f"Article {article_id} not found")


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:]
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Split text into sentences using a robust regex."""
    # Strip HTML and citations (same as pipeline._preprocess_text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\[\d+\](?:\s*\[\d+\])*', '', text)
    # Insert sentence boundary before markdown headers and normalize whitespace
    text = re.sub(r'\n\s*#{1,3}\s+.*?\n', '. ', text)
    text = re.sub(r'\n+', ' ', text)
    sent = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'(])', text)
    return [s.strip() for s in sent if len(s.strip()) > 15]


def parse_truth_file(path: Path) -> dict[str, list[GroundTruthEntry]]:
    """Parse a .truth file into {sentence_text: [GroundTruthEntry]}."""
    entries_by_sentence: dict[str, list[GroundTruthEntry]] = {}
    current_sentence: str | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("# sentence:"):
            current_sentence = line[len("# sentence:"):].strip()
            entries_by_sentence.setdefault(current_sentence, [])
            continue
        if line.startswith("#") or "|" not in line or "→" not in line:
            continue

        # Format: <uuid> | <arg1> → <arg2> → <arg3>
        uuid_part, rest = line.split("|", 1)
        uuid_val = uuid_part.strip()

        parts = [p.strip() for p in rest.split("→")]
        if len(parts) != 3:
            continue

        subj, pred, obj = parts
        is_fact = not is_uuid(subj) and not is_uuid(obj)

        entry = GroundTruthEntry(uuid=uuid_val, subject=subj, predicate=pred, object=obj, is_fact=is_fact)
        if current_sentence:
            entries_by_sentence[current_sentence].append(entry)

    return entries_by_sentence


PROTO_STATEMENT_META = 2
PROTO_SUBJECT_CONCEPT = 1
PROTO_SUBJECT_STATEMENT = 2
PROTO_OBJECT_CONCEPT = 1
PROTO_OBJECT_STATEMENT = 2
PROTO_OBJECT_LITERAL = 3


def _get_attr(obj, name: str, default=None):
    """Get attribute or dict key from a proto-or-dict response object."""
    return obj if isinstance(obj, dict) else (
        obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)
    )


def extract_triplets(resp) -> list[dict]:
    """Convert a pipeline response (dict or proto) to a list of triplet dicts.

    Each result dict has: subject, predicate, object (text),
    plus type (FACT/META), subject_type, object_type (proto ints).
    """
    if resp is None:
        return []
    if isinstance(resp, dict):
        stmts = resp.get("statements", [])
        concepts_list = resp.get("concepts", [])
    else:
        stmts = resp.statements
        concepts_list = resp.concepts
    concept_map = {}
    for c in concepts_list:
        cid = _get_attr(c, 'id')
        ctext = _get_attr(c, 'normalized_text') or _get_attr(c, 'text')
        concept_map[cid] = ctext

    result = []
    for stmt in stmts:
        sid = _get_attr(stmt, 'subject_id', '')
        oid = _get_attr(stmt, 'object_id', '')
        pred = _get_attr(stmt, 'predicate', '')
        lit = _get_attr(stmt, 'literal_value', '')
        stmt_type = _get_attr(stmt, 'type', 1)
        subj_type = _get_attr(stmt, 'subject_type', 1)
        obj_type = _get_attr(stmt, 'object_type', 1)

        if subj_type == PROTO_SUBJECT_STATEMENT:
            subj_text = sid
        else:
            subj_text = concept_map.get(sid, "")

        if obj_type == PROTO_OBJECT_STATEMENT:
            obj_text = oid
        elif obj_type == PROTO_OBJECT_LITERAL:
            obj_text = lit or concept_map.get(oid, "")
        else:
            obj_text = concept_map.get(oid, "")

        result.append({
            "subject": subj_text,
            "predicate": pred,
            "object": obj_text,
            "type": stmt_type,
            "subject_type": subj_type,
            "object_type": obj_type,
        })
    return result


def _words_match(a: str, b: str) -> bool:
    """Match two lowercased words, handling common singular/plural forms."""
    if a == b:
        return True
    # a == b + "s"  (regular plural: factor → factors)
    if len(a) > 2 and a == b + "s":
        return True
    if len(b) > 2 and a + "s" == b:
        return True
    # studies ↔ study  (-ies → -y)
    if len(a) > 3 and a.endswith("ies") and a[:-3] + "y" == b:
        return True
    if len(b) > 3 and b.endswith("ies") and b[:-3] + "y" == a:
        return True
    # processes ↔ process  (-es → ∅)
    if len(a) > 2 and a.endswith("es") and a[:-2] == b:
        return True
    if len(b) > 2 and b.endswith("es") and b[:-2] == a:
        return True
    return False


def _strip_punct(word: str) -> str:
    """Strip trailing punctuation from a word for matching."""
    return word.rstrip('.,;:!?\'\")]}>')


def _contained_in(needle: str, haystack: str) -> bool:
    """Check if needle words appear in order within haystack (word-subsequence match).

    Allows additional words between GT words, e.g. GT "age-related disease" matches
    pipeline "age-related multifactorial disease" because "age-related" → "disease"
    appear as a subsequence. Also handles singular/plural mismatch via _words_match.
    Trailing punctuation is stripped before comparison.
    """
    n_words = [_strip_punct(w) for w in needle.lower().split()]
    h_words = [_strip_punct(w) for w in haystack.lower().split()]
    i = 0
    for word in h_words:
        if i < len(n_words) and _words_match(word, n_words[i]):
            i += 1
    return i == len(n_words)


def _text_match(gt_text: str, pipe_text: str) -> bool:
    """Check if two texts match (exact or contained)."""
    return (gt_text == pipe_text
            or _contained_in(gt_text, pipe_text)
            or _contained_in(pipe_text, gt_text))


def find_matching_statement(
    triplet: Triplet,
    responses: list,
    *,
    is_meta: bool = False,
    gt_entry: GroundTruthEntry | None = None,
    lookup: dict[str, GroundTruthEntry] | None = None,
) -> bool:
    """Check if any pipeline statement matches the triplet.

    For META (is_meta=True): also verifies the pipeline created a META-type
    statement with the correct Statement→Statement link side.
    """
    t_subj = triplet.subject.lower().strip()
    t_pred = triplet.predicate.lower().strip()
    t_obj = triplet.object.lower().strip()

    gt_subj_is_uuid = gt_entry is not None and is_uuid(gt_entry.subject)
    gt_obj_is_uuid = gt_entry is not None and is_uuid(gt_entry.object)

    for resp in responses:
        for item in extract_triplets(resp):
            p_type = item.get("type", 1)
            p_subj_type = item.get("subject_type", 1)
            p_obj_type = item.get("object_type", 1)
            p_subj = item["subject"].lower().strip()
            p_pred = item["predicate"].lower().strip()
            p_obj = item["object"].lower().strip()

            if p_pred != t_pred:
                continue

            if is_meta:
                if p_type != PROTO_STATEMENT_META:
                    continue
                if gt_subj_is_uuid and p_subj_type != PROTO_SUBJECT_STATEMENT:
                    continue
                if gt_obj_is_uuid and p_obj_type != PROTO_OBJECT_STATEMENT:
                    continue
                if not gt_subj_is_uuid and p_subj_type != PROTO_SUBJECT_CONCEPT:
                    continue
                if not gt_obj_is_uuid and p_obj_type != PROTO_OBJECT_LITERAL:
                    if p_obj_type != PROTO_OBJECT_CONCEPT:
                        continue
                # For META: match only the TEXT side (non-UUID);
                # UUID side is validated by type check above.
                # We use raw gt_entry text, not resolved triplet text.
                if p_pred != t_pred:
                    continue
                if not gt_subj_is_uuid and _text_match(gt_entry.subject, p_subj):
                    return True
                if not gt_obj_is_uuid and _text_match(gt_entry.object, p_obj):
                    return True
                continue

            # Text matching (FACT only)
            if p_subj == t_subj and p_obj == t_obj:
                return True
            if _contained_in(t_subj, p_subj) and _contained_in(t_obj, p_obj):
                return True
            if _contained_in(p_subj, t_subj) and _contained_in(p_obj, t_obj):
                return True
            subj_match = _text_match(t_subj, p_subj)
            obj_match = _text_match(t_obj, p_obj)
            if subj_match and obj_match:
                return True
    return False
