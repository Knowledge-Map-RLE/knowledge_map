"""Pydantic-схемы для декомпозиции цели (goal decomposition, reverse planning).

Слои: Interface Adapters / Domain. Определяют формат запроса пользователя,
дерева плана, возвращаемого LLM, а также ответа эндпоинта /goal/decompose.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GoalPlanItem(BaseModel):
    """Один элемент дерева декомпозиции цели."""

    id: str = Field(..., description="Локальный идентификатор (G1, P1, T1, A1...)")
    level: int = Field(..., description="Уровень иерархии (root = 0)")
    kind: str = Field(..., description="goal | sub_goal | task | action")
    text: str = Field(..., description="Формулировка пункта")
    parent_id: Optional[str] = Field(None, description="id родительского пункта")
    rationale: str = Field("", description="Почему этот пункт нужен для родителя")
    expected_outcome: Optional[str] = Field(None, description="Измеримый результат (для действий)")


class GoalPlanTree(BaseModel):
    """Дерево декомпозиции цели, возвращаемое LLM."""

    goal: str = Field(..., description="Исходный текст цели")
    summary: str = Field("", description="Краткая переформулировка цели")
    items: List[GoalPlanItem] = Field(default_factory=list)


class DecomposeGoalRequest(BaseModel):
    """Запрос на декомпозицию цели."""

    goal_text: str = Field(..., min_length=1, description="Текст цели на естественном языке")
    level: Optional[int] = Field(None, description="Желаемая глубина (если пусто — автоматически)")


class DecomposeGoalResponse(BaseModel):
    """Ответ эндпоинта /goal/decompose.

    Содержит как дерево плана (для отображения в правой панели), так и
    блоки/рёбра графа (для отображения на карте знаний), совместимые с
    KnowledgeGraphBlock / KnowledgeGraphLink из REST /layout/knowledge_triples.
    """

    success: bool = True
    tree: GoalPlanTree
    plan_id: str = Field(..., description="UID документа-плана в Neo4j")
    blocks: List[Dict[str, Any]] = Field(default_factory=list)
    links: List[Dict[str, Any]] = Field(default_factory=list)
    message: str = ""
