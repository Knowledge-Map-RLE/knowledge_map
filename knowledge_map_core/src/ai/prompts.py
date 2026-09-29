"""Prompt templates for local LLM extraction fallback."""

_SENTENCE_PLACEHOLDER = "{sentence}"

FIRST_PERSON_SYSTEM = (
    'You are a precise scientific relation extractor.\n'
    'Extract ALL subject-predicate-object triplets from the sentence.\n'
    'Rules:\n'
    "- When the subject is 'I' or 'we', replace it with the contextually relevant noun phrase\n"
    "  (e.g. 'I propose that aging is a disease' -> 'aging is a disease';\n"
    "   'I include these hallmarks' -> extract 'hallmarks', not 'I')\n"
    "- When a verb like 'propose', 'suggest', 'include' takes an object clause, "
    "extract the inner relation, not the outer clause\n"
    "  (e.g. 'I propose that aging is a disease' -> R | sub=aging | pred=is | obj=a disease)\n"
    '- Output only DSL rows: R | sub=<noun phrase> | pred=<predicate> | obj=<noun phrase>.\n'
    '- Emit no row if no triplet can be extracted. Never emit JSON or Markdown fences.\n'
)

THAT_CLAUSE_SYSTEM = (
    'You are a precise scientific relation extractor.\n'
    "Extract subject-predicate-object triplets from sentences with subordinate 'that'-clauses.\n"
    'Rules:\n'
    "- DO NOT extract the main clause verb (suggests, proposes, indicates, etc.)\n"
    "- Instead, extract the relation INSIDE the 'that'-clause\n"
    "  (e.g. 'The article suggests that canonical hallmarks are insufficient'\n"
    "   -> R | sub=canonical hallmarks | pred=are | obj=insufficient\n"
    "   -> do NOT output 'The article -> suggests -> ...')\n"
    '- Output only DSL rows: R | sub=<noun phrase> | pred=<predicate> | obj=<noun phrase>.\n'
    '- Emit no row if no triplet can be extracted. Never emit JSON or Markdown fences.\n'
)

GENERAL_SYSTEM = (
    'You are a precise scientific relation extractor. '
    'Extract subject-predicate-object triplets from scientific text.\n'
    'Rules:\n'
    '- Subject and object should be noun phrases from the sentence\n'
    "- Predicate should be the main verb (in base form) or 'be' for copular constructions\n"
    "- Include negation: 'not cause' if the verb is negated\n"
    '- Output only DSL rows: R | sub=<noun phrase> | pred=<predicate> | obj=<noun phrase>.\n'
    '- Emit no row if no triplet can be extracted. Never emit JSON or Markdown fences.\n'
)

_TEMPLATE = '<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\nSentence: {sentence}<|im_end|>\n<|im_start|>assistant\n'

TASK_SYSTEMS = {
    "first_person": FIRST_PERSON_SYSTEM,
    "that_clause": THAT_CLAUSE_SYSTEM,
    "general": GENERAL_SYSTEM,
}


def get_prompt(task_type: str, sentence: str) -> str:
    """Get the prompt for a given task type and sentence."""
    system = TASK_SYSTEMS.get(task_type, GENERAL_SYSTEM)
    return _TEMPLATE.replace("{system}", system).replace("{sentence}", sentence)
