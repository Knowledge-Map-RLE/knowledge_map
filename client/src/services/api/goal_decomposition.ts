import { fetchJson } from './http';
import type { KnowledgeGraphBlock, KnowledgeGraphLink } from './layout';

/** Один элемент дерева декомпозиции цели. */
export interface GoalPlanItem {
  id: string;
  level: number;
  kind: 'goal' | 'sub_goal' | 'task' | 'action';
  text: string;
  parent_id: string | null;
  rationale: string;
  expected_outcome?: string | null;
}

/** Дерево декомпозиции цели (ответ LLM). */
export interface GoalPlanTree {
  goal: string;
  summary: string;
  items: GoalPlanItem[];
}

/** Ответ эндпоинта /goal/decompose. */
export interface DecomposeGoalResponse {
  success: boolean;
  tree: GoalPlanTree;
  plan_id: string;
  blocks: KnowledgeGraphBlock[];
  links: KnowledgeGraphLink[];
  message?: string;
}

/** Декомпозиция цели (обратное планирование). */
export async function decomposeGoal(goalText: string): Promise<DecomposeGoalResponse> {
  return fetchJson<DecomposeGoalResponse>('/goal/decompose', {
    method: 'POST',
    body: JSON.stringify({ goal_text: goalText }),
  });
}