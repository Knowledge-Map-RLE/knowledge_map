"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.goal_decomposition
Responsibility: HTTP-эндпоинт декомпозиции цели (обратное планирование)
для страницы /km (правая панель).

Эндпоинт принимает цель на естественном языке, строит план её достижения
через LLM, формализует в Язык Знаний (триплеты через существующий DSL-промпт)
и сохраняет на карте знаний как связную компоненту графа.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from src.schemas.goal_decomposition import DecomposeGoalRequest, DecomposeGoalResponse
from services.goal_decomposition_service import GoalDecompositionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goal", tags=["goal-decomposition"])

_service = GoalDecompositionService()


@router.post("/decompose", response_model=DecomposeGoalResponse)
async def decompose_goal(request: DecomposeGoalRequest) -> Dict[str, Any]:
    """Декомпозирует цель и возвращает план + блоки/рёбра для карты знаний."""
    try:
        result = await _service.decompose(goal_text=request.goal_text)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Неожиданная ошибка декомпозиции цели")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервиса декомпозиции")
