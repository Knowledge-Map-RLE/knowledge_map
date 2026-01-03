# Ontology Reversibility Tests

## Overview

This document describes the reversibility test suite for the Ontology system. The goal is to verify that text can be perfectly reconstructed from the ontology graph representation.

**Core Principle**: Text → Ontology → Text should result in identical output.

## Test Sentence

The primary test sentence is:

```
Since the discovery of dopamine as a neurotransmitter in the 1950s, Parkinson's disease (PD) research has generated a rich and complex body of knowledge, revealing PD to be an age-related multifactorial disease, influenced by both genetic and environmental factors.
```

This sentence was chosen because it contains:
- Common English words
- Punctuation (commas, parentheses, period)
- Numbers with special formatting (1950s)
- Acronyms (PD)
- Contractions (Parkinson's)
- Complex sentence structure with multiple clauses
- Both capital and lowercase letters
- Multiple mentions of the same entity (PD appears twice)

## Reconstruction Rules

### Rule 1: Token Order (CRITICAL)

**Description**: Reconstruct tokens in order of `(sent_idx, token_idx)`

**Why**: Ensures original sentence structure is preserved

**Implementation**:
```cypher
MATCH (o:Ontology)
WHERE o.concept_type = 'token'
RETURN o
ORDER BY o.sent_idx ASC, o.token_idx ASC
```

**Example**:
- Tokens in test sentence: [Since, the, discovery, of, dopamine, as, ...]
- Must maintain this exact order

**Test Cases**:
- ✓ Single sentence: all tokens have same `sent_idx`, `token_idx` increases
- ✓ Multiple sentences: `sent_idx` increases, `token_idx` resets
- ✓ No gaps or skipped indices

### Rule 2: Original Text Form (CRITICAL)

**Description**: Use original text from `HAS_TEXT`, NOT lemma

**Why**: Preserves inflections and exact form

**Implementation**:
```cypher
MATCH (o:Ontology)-[:HAS_TEXT]->(text:OntologyProperty {type: 'text'})
RETURN text.value
```

**Example**:
- Token lemma: "generate"
- Morphological features: {Tense: Past, VerbForm: Fin}
- Original text: "generated"
- **Reconstruct with**: "generated" (NOT "generate")

**Test Cases**:
- ✓ Past tense verbs: "generated", "revealed", "influenced" (not "generate", "reveal", "influence")
- ✓ Plural nouns: "factors", "relationships" (not "factor", "relationship")
- ✓ Conjugated verbs: "is", "has" (not "be", "have")

### Rule 3: Whitespace Preservation (CRITICAL)

**Description**: Append whitespace from `HAS_WHITESPACE` after each token

**Why**: Preserves spacing, prevents words from merging

**Implementation**:
```cypher
MATCH (o:Ontology)-[:HAS_WHITESPACE]->(ws:OntologyProperty {type: 'whitespace'})
RETURN text.value + ws.value
```

**Example**:
```
Token: {text: "Since", whitespace: " "}
  → Reconstruct as: "Since" + " " = "Since "

Token: {text: ".", whitespace: ""}
  → Reconstruct as: "." + "" = "."

Token: {text: ",", whitespace: " "}
  → Reconstruct as: "," + " " = ", "
```

**Whitespace Values**:
- `" "` (single space) - most tokens
- `""` (empty) - before punctuation, at end of text
- `"\n"` (newline) - for multi-paragraph text
- Multiple spaces preserved when present

**Test Cases**:
- ✓ No double spaces in output
- ✓ Space after commas: `", "`
- ✓ No space before punctuation: `"word."`
- ✓ Space before opening parenthesis: `" ("`
- ✓ No space after opening parenthesis: `"(PD)"`

### Rule 4: Punctuation Handling (CRITICAL)

**Description**: Punctuation tokens are separate Ontology nodes with POS='PUNCT'

**Why**: Ensures correct punctuation placement and spacing

**Implementation**:
```cypher
MATCH (o:Ontology)
MATCH (o)-[:HAS_POS]->(pos:OntologyProperty {type: 'pos', value: 'PUNCT'})
RETURN o
```

**Punctuation Examples**:

| Token | Whitespace | Position | Notes |
|-------|-----------|----------|-------|
| `,` | ` ` | After noun/verb | Comma followed by space |
| `.` | `` | End of sentence | Period with no following space |
| `(` | `` | Before entity | Opening paren, no internal space |
| `)` | ` ` | After entity | Closing paren followed by space |
| `:` | ` ` | Before list | Colon followed by space |

**Test Cases**:
- ✓ Comma after "1950s,": `"1950s, "`
- ✓ Parentheses "the (PD) research": `"the (PD) research"`
- ✓ Period at end ".": `". "` (no trailing space)
- ✓ Apostrophe "Parkinson's": `"Parkinson's "`

### Rule 5: Capitalization (CRITICAL)

**Description**: Capitalization is preserved in original text property

**Why**: Maintains sentence structure and acronyms

**Implementation**:
- Use original `text` value exactly as stored
- No modification needed (already capitalized correctly)

**Example**:
- Sentence start: "Since" (capital S)
- Acronyms: "PD" (all capitals)
- Lowercase: "the", "of", "and"

**Capitalization Rules**:

| Context | Example | Preserved | Notes |
|---------|---------|-----------|-------|
| Sentence start | Since | ✓ | Must be capital |
| Acronym | PD | ✓ | All capitals |
| Common noun | discovery | ✓ | Lowercase |
| Proper noun | Parkinson | ✓ | Title case |
| Middle of sentence | dopamine | ✓ | Lowercase unless proper |

**Test Cases**:
- ✓ First word capitalized: "Since" not "since"
- ✓ Acronyms uppercase: "PD" not "Pd"
- ✓ Proper nouns: "Parkinson's disease"
- ✓ Common words: "the", "of", "and" in lowercase

## Reconstruction Algorithm

### Phase 1: Simple Reconstruction (Current)

```python
def reconstruct_text_from_ontology(self) -> str:
    """
    1. Query all Ontology nodes ordered by (sent_idx, token_idx)
    2. For each node:
       - Get text from HAS_TEXT
       - Get whitespace from HAS_WHITESPACE
       - Append: text + whitespace
    3. Strip trailing whitespace
    4. Return concatenated string
    """

    query = """
    MATCH (o:Ontology)-[:HAS_TEXT]->(text:OntologyProperty {type: 'text'})
    MATCH (o)-[:HAS_WHITESPACE]->(ws:OntologyProperty {type: 'whitespace'})
    WHERE o.concept_type = 'token'
    RETURN text.value, ws.value
    ORDER BY o.sent_idx ASC, o.token_idx ASC
    """

    result = session.run(query)
    parts = [text + ws for text, ws in result]
    return ''.join(parts).rstrip()
```

**Complexity**: O(n) where n = number of tokens

**Why This Works**:
- Original text forms are stored (not lemmas)
- Whitespace is stored explicitly
- Token order is preserved via indices
- No complex logic needed

### Phase 2: Advanced Reconstruction (Future)

For reconstructing from lemmas + morphology:

```python
def reconstruct_from_lemmas(self) -> str:
    """
    1. Get lemma from HAS_LEMMA
    2. Get morph features from HAS_MORPH
    3. Inflect lemma using features (lemminflect library)
    4. Apply capitalization rules
    5. Add whitespace
    """
    # Uses lemminflect for English word inflection
    # Example: lemma="generate" + {Tense:Past} → "generated"
```

## Quality Metrics

### Character Accuracy

**Definition**: Percentage of characters that match

```
accuracy = (matching_characters / total_characters) * 100
```

**Target**: 100% (or ≥99.5% allowing minor whitespace variations)

**Example**:
```
Original:      "Since the discovery..."
Reconstructed: "Since the discovery..."
Difference:    [exact match]
Accuracy:      100%
```

### Word Accuracy

**Definition**: Percentage of words that match

```
accuracy = (matching_words / total_words) * 100
```

**Target**: 100% (or ≥99%)

**Example**:
```
Original words:      [Since, the, discovery, of, dopamine, ...]
Reconstructed words: [Since, the, discovery, of, dopamine, ...]
Matching words:      All 37 words match
Accuracy:            100%
```

### Edit Distance

**Definition**: Minimum number of character edits (insertions, deletions, substitutions) needed to transform reconstructed into original

**Algorithm**: Levenshtein distance

**Target**: 0 (no edits needed)

**Example**:
- Original: "Since the discovery"
- Reconstructed: "Since the discovery"
- Edit distance: 0

### BLEU Score

**Definition**: Translation quality metric measuring n-gram overlap

**Algorithm**: NLTK's `sentence_bleu` function

**Target**: 1.0 (perfect match)

**Range**: 0.0 to 1.0
- 1.0 = identical
- 0.9-1.0 = excellent
- 0.7-0.9 = good
- <0.7 = needs improvement

## Test Execution

### Running Tests

```bash
cd nlp
pytest tests/integration/test_ontology_reversibility.py -v
```

### Expected Output (100% Pass)

```
test_exact_reconstruction ✓ PASSED
test_reconstruction_preserves_morphology ✓ PASSED
test_reconstruction_preserves_capitalization ✓ PASSED
test_reconstruction_preserves_punctuation ✓ PASSED
test_reconstruction_preserves_whitespace ✓ PASSED
test_token_order_preservation ✓ PASSED
test_reconstruction_quality_metrics ✓ PASSED
test_validate_reconstruction_integrity ✓ PASSED
test_morphology_feature_preservation ✓ PASSED
test_reconstruction_robustness ✓ PASSED

====== 10 passed in 2.34s ======
```

### Debugging Failures

If a test fails, use the reconstruction integrity validator:

```python
from nlp.src.ontology_reconstructor import OntologyReconstructor

reconstructor = OntologyReconstructor()
report = reconstructor.validate_reconstruction_integrity(original_text)

print("Issues found:")
for issue in report['issues']:
    print(f"  - {issue['type']}: {issue['message']}")

print("\nMetrics:")
print(f"  Character accuracy: {report['metrics']['char_accuracy']:.2%}")
print(f"  Word accuracy: {report['metrics']['word_accuracy']:.2%}")
print(f"  Edit distance: {report['metrics']['edit_distance']}")
```

## Genetic Algorithm Optimization

### Training Data

The genetic algorithm is trained on multiple sentences to discover optimal reconstruction rules.

**Training set size**: 20-30 sentences

**Sample training sentences**:
```
1. "The discovery of dopamine revolutionized neuroscience."
2. "Parkinson's disease affects millions worldwide."
3. "Recent research has yielded new insights."
4. "Scientists discovered new mechanisms of action."
5. "The treatment paradigm is shifting rapidly."
... (15-25 more sentences)
```

### Fitness Function

```python
def fitness(rules, training_examples):
    """
    Fitness = sum of Levenshtein distances across all examples
    Lower is better (0 = perfect reconstruction)
    """
    total_distance = 0
    for example in training_examples:
        reconstructed = reconstruct_with_rules(example, rules)
        distance = levenshtein_distance(example.original, reconstructed)
        total_distance += distance
    return total_distance
```

### Genetic Algorithm Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Population size | 50 | Enough diversity without excessive computation |
| Generations | 100 | Sufficient for convergence |
| Mutation rate | 0.1 | 10% probability of random weight change |
| Crossover | Average weights | Simple and effective |
| Selection | Top 50% | Keep best performers |

### Optimized Rules Output

After optimization, rules are saved to:

```json
{
  "rules": [
    {
      "rule_id": "token_order",
      "weight": 1.0,
      "description": "Order tokens by (sent_idx, token_idx)"
    },
    {
      "rule_id": "original_text",
      "weight": 1.0,
      "description": "Use HAS_TEXT property, not lemma"
    },
    {
      "rule_id": "whitespace_preservation",
      "weight": 1.0,
      "description": "Append HAS_WHITESPACE after each token"
    },
    {
      "rule_id": "punctuation_handling",
      "weight": 1.0,
      "description": "Handle PUNCT tokens as separate nodes"
    },
    {
      "rule_id": "capitalization",
      "weight": 1.0,
      "description": "Preserve original capitalization"
    }
  ],
  "optimization_results": {
    "generations_completed": 100,
    "final_fitness": 0,
    "training_accuracy": 1.0,
    "test_accuracy": 0.99,
    "optimization_time_seconds": 156.42
  }
}
```

## Validation Checklist

Before declaring reversibility tests PASSING, verify:

- [ ] Test sentence reconstructs exactly (character for character)
- [ ] Character accuracy ≥ 99%
- [ ] Word accuracy ≥ 99%
- [ ] Edit distance ≤ 5
- [ ] BLEU score ≥ 0.95
- [ ] All morphological features preserved
- [ ] All capitalization patterns preserved
- [ ] All punctuation in correct positions
- [ ] No double spaces in output
- [ ] All token order correct (sent_idx, token_idx)
- [ ] Genetic algorithm converges (fitness → 0)
- [ ] Ontology integrity valid (no missing indices)

## Edge Cases Handled

### 1. Contractions

Example: "Parkinson's"
- Stored as: text="Parkinson's", lemma="Parkinson"
- Morphology: {POS: PROPN}
- Reconstructed as: "Parkinson's" ✓

### 2. Numbers with Formatting

Example: "1950s"
- Stored as: text="1950s", lemma="1950"
- Morphology: {NumType: Card}
- Reconstructed as: "1950s" ✓

### 3. Acronyms

Example: "PD" (Parkinson's Disease)
- Stored as: text="PD", lemma="PD"
- Morphology: {POS: NOUN}
- Capitalization: ALL UPPERCASE
- Reconstructed as: "PD" ✓

### 4. Parentheses and Quotes

Example: "(PD)" or "quoted text"
- Each punctuation is separate token
- Whitespace handled correctly
- Reconstructed as: "(PD) " ✓

### 5. Multi-sentence Paragraphs

Example: Multiple sentences with different sent_idx
- Tokens ordered by (sent_idx, token_idx)
- Each sentence reconstructs correctly
- Reconstructed with proper spacing ✓

## Performance Targets

| Metric | Target | Current | Notes |
|--------|--------|---------|-------|
| Exact reconstruction | 100% | TBD | Character-perfect match |
| Test execution time | <10s | TBD | All tests complete quickly |
| Ontology generation time | <30s | TBD | For test sentence |
| Memory usage | <100MB | TBD | Reasonable for testing |

## Failure Investigation Guide

If tests fail, follow this process:

### Step 1: Check Token Count

```python
reconstructor = OntologyReconstructor()
tokens = reconstructor.get_all_tokens()
print(f"Found {len(tokens)} tokens")
```

Expected: 37 tokens for test sentence

### Step 2: Check Token Order

```python
for i, token in enumerate(tokens):
    if token['sent_idx'] is None or token['token_idx'] is None:
        print(f"Token {i} missing indices: {token}")
```

Expected: All tokens have valid indices

### Step 3: Check Text Form

```python
bad_tokens = [t for t in tokens if t['text'] != t['text'].strip()]
print(f"Tokens with extra whitespace: {bad_tokens}")
```

Expected: No extra whitespace in text property

### Step 4: Check Reconstruction

```python
reconstructed = reconstructor.reconstruct_text_from_ontology()
metrics = reconstructor.compute_reconstruction_metrics(original, reconstructed)

print(f"Character accuracy: {metrics.char_accuracy:.2%}")
print(f"Word accuracy: {metrics.word_accuracy:.2%}")
print(f"Edit distance: {metrics.edit_distance}")
print(f"First diff at char {metrics.edit_distance_details['first_diff_pos']}")
```

### Step 5: Compare Original vs Reconstructed

```python
import difflib
diff = list(difflib.unified_diff(
    original.splitlines(keepends=True),
    reconstructed.splitlines(keepends=True)
))
for line in diff:
    print(line)
```

## Summary

The Ontology Reversibility Test suite ensures that:

1. ✓ Text can be perfectly reconstructed from the ontology graph
2. ✓ All morphological features are preserved
3. ✓ All capitalization patterns are preserved
4. ✓ All punctuation is in correct positions
5. ✓ All whitespace is correctly maintained
6. ✓ Token order is preserved via sent_idx and token_idx

This validates that the Ontology system can faithfully represent any text while maintaining semantic and syntactic structure for downstream analysis.

---

**Last Updated**: 2025-12-25
**Test Sentence Count**: 1 primary + 10 additional
**Expected Success Rate**: 100%
