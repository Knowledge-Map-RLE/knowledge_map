"""English prompt for goal decomposition (reverse/backward planning).

Converts a goal written in natural language into a hierarchical plan of
sub-goals, tasks, and actions. The degree of decomposition (number of levels)
is chosen automatically by the model based on the complexity of the goal.

The output is a strict JSON tree used by :class:`GoalDecompositionService`
to drive LLM formalization into Knowledge Map triplets via the existing
DSL prompt (`llm_triplet_extraction_prompt_dsl.py`).

Placeholders: ``__GOAL_TEXT__``.
"""

GOAL_DECOMPOSITION_TEMPLATE_EN = """# ROLE
You are a strategic planning system for the "Knowledge Map" — a tool that stores
all knowledge as a graph of assertions (triplets) and helps move toward concrete goals.
Your task is DECOMPOSITION OF A GOAL using REVERSE (BACKWARD) PLANNING:
start from the desired end state and work backward to concrete, achievable actions.

# INPUT
GOAL:
«__GOAL_TEXT__»

# DEGREE OF DECOMPOSITION (AUTOMATIC)
Automatically decide how many levels are needed to reach a concrete action plan.
Use your judgment; a good rule of thumb:
- Very simple goal (one obvious step)        -> 2 levels (goal -> actions)
- Normal goal                                -> 3 levels (goal -> sub-goals -> actions)
- Complex / long-term / scientific goal      -> 4-5 levels
    (goal -> sub-goals -> tasks -> actions -> concrete steps)

Do NOT over-decompose trivial goals and do NOT under-decompose complex ones.
Each level must be a genuine refinement of its parent, not a copy.

# WHAT TO PRODUCE
A hierarchical plan where every item is ONE atomic action/condition/target stated
as a single, self-contained idea. Each item must be causally relevant: completing
its children should bring the parent measurably closer.

Additionally, for every item you MUST specify:
- a short "rationale" explaining WHY this item is needed to reach its parent;
- for actions: an expected/measurable observable outcome.

# OUTPUT FORMAT (STRICT JSON, NO MARKDOWN, NO PROSE OUTSIDE JSON)
{
  "goal": "<original goal text>",
  "summary": "<one concise sentence restating the goal>",
  "items": [
    {
      "id": "G1",
      "level": 0,
      "kind": "goal",
      "text": "<the goal itself>",
      "parent_id": null,
      "rationale": "<why this is the goal>"
    },
    {
      "id": "P1",
      "level": 1,
      "kind": "sub_goal",
      "text": "<sub-goal text>",
      "parent_id": "G1",
      "rationale": "<why this sub-goal is needed>"
    },
    {
      "id": "T1",
      "level": 2,
      "kind": "task",
      "text": "<task text>",
      "parent_id": "P1",
      "rationale": "<why this task is needed>"
    },
    {
      "id": "A1",
      "level": 3,
      "kind": "action",
      "text": "<action text>",
      "parent_id": "T1",
      "rationale": "<why this action is needed>",
      "expected_outcome": "<measurable observable result>"
    }
  ]
}

# HARD RULES
1. Output ONLY valid JSON. No bullets, no fences, no extra text.
2. Use the SAME LANGUAGE as the input goal.
3. Every item must be atomic: one idea, one statement, one target.
4. Each item except the root (goal) has exactly one "parent_id" pointing to an
   item one level above. Build a proper tree (no cycles, no orphans).
5. Level numbers: root = 0, each child = parent level + 1.
6. kind must be one of: "goal", "sub_goal", "task", "action".
7. Actions (deepest level) MUST carry "expected_outcome".
8. Never fabricate. Only propose realistic, achievable, verifiable items.
9. The decomposition must be causally sound: it must make sense as a path from
   today's state to the desired goal.
"""


def build_goal_decomposition_prompt(goal_text: str) -> str:
    """Builds the decomposition prompt for the given goal text."""
    return GOAL_DECOMPOSITION_TEMPLATE_EN.replace("__GOAL_TEXT__", goal_text)
