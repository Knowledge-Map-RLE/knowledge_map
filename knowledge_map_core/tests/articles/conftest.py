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


def extract_triplets(resp) -> list[dict]:
    """Convert a pipeline response (dict or proto) to a list of {subject, predicate, object} dicts."""
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
        cid = c.id if hasattr(c, 'id') else c.get('id')
        ctext = c.normalized_text or c.text if hasattr(c, 'normalized_text') else (c.get('normalized_text') or c.get('text'))
        concept_map[cid] = ctext

    result = []
    for stmt in stmts:
        sid = stmt.subject_id if hasattr(stmt, 'subject_id') else stmt.get('subject_id')
        oid = stmt.object_id if hasattr(stmt, 'object_id') else stmt.get('object_id')
        pred = stmt.predicate if hasattr(stmt, 'predicate') else stmt.get('predicate')
        lit = stmt.literal_value if hasattr(stmt, 'literal_value') else stmt.get('literal_value', '')
        subj_text = concept_map.get(sid, "")
        obj_text = lit or concept_map.get(oid, "")
        result.append({"subject": subj_text, "predicate": pred, "object": obj_text})
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


def _contained_in(needle: str, haystack: str) -> bool:
    """Check if needle words appear in order within haystack (word-subsequence match).

    Allows additional words between GT words, e.g. GT "age-related disease" matches
    pipeline "age-related multifactorial disease" because "age-related" → "disease"
    appear as a subsequence. Also handles singular/plural mismatch via _words_match.
    """
    n_words = needle.lower().split()
    h_words = haystack.lower().split()
    i = 0
    for word in h_words:
        if i < len(n_words) and _words_match(word, n_words[i]):
            i += 1
    return i == len(n_words)


def find_matching_statement(
    triplet: Triplet,
    responses: list,
) -> bool:
    """Check if any pipeline statement matches the triplet by content."""
    t_subj = triplet.subject.lower().strip()
    t_pred = triplet.predicate.lower().strip()
    t_obj = triplet.object.lower().strip()
    for resp in responses:
        for item in extract_triplets(resp):
            p_subj = item["subject"].lower().strip()
            p_pred = item["predicate"].lower().strip()
            p_obj = item["object"].lower().strip()
            if p_subj == t_subj and p_pred == t_pred and p_obj == t_obj:
                return True
            # Fallback: allow text to contain extra words in either direction
            if p_pred == t_pred and _contained_in(t_subj, p_subj) and _contained_in(t_obj, p_obj):
                return True
            # Reverse direction: pipeline words are subsequence of GT words
            if p_pred == t_pred and _contained_in(p_subj, t_subj) and _contained_in(p_obj, t_obj):
                return True
            # Independent direction: subj and obj can use different directions
            if p_pred == t_pred:
                subj_match = t_subj == p_subj or _contained_in(t_subj, p_subj) or _contained_in(p_subj, t_subj)
                obj_match = t_obj == p_obj or _contained_in(t_obj, p_obj) or _contained_in(p_obj, t_obj)
                if subj_match and obj_match:
                    return True
    return False
