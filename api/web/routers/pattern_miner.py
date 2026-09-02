"""
REST endpoints: выявление паттернов по графу утверждений (PatternMiner).

Endpoints:
  GET  /api/pattern-miner/documents — список документов с числом утверждений
  GET  /api/pattern-miner/methods   — способы и операции генерации знаний
  POST /api/pattern-miner/mine      — майнинг частотных паттернов по корпусу
  POST /api/pattern-miner/generate  — автономная генерация знания 4 способами
  POST /api/pattern-miner/apply     — наложение паттерна на целевой граф
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.pattern_miner_service import PatternMinerService, get_pattern_miner_service

router = APIRouter(prefix="/api/pattern-miner", tags=["pattern_miner"])


class MineRequest(BaseModel):
    doc_ids: Optional[List[str]] = Field(None, description="Ограничение корпуса по документам")
    min_support: float = Field(0.3, ge=0.05, le=1.0, description="Доля корпуса (>0, <=1)")
    min_size: int = Field(2, ge=1, le=8, description="Минимальное число узлов паттерна")
    max_size: int = Field(6, ge=2, le=8, description="Максимальное число узлов паттерна")
    limit: int = Field(200, ge=1, le=1000, description="Лимит паттернов")
    predicate_mode: str = Field("raw", description="raw | direction | bucket")
    useful_only: bool = Field(True, description="Отсекать тривиальные паттерны")
    statements_per_doc_cap: Optional[int] = Field(None, ge=10, le=2000,
                                                  description="Макс. утверждений на статью (сэмплинг)")
    max_nodes: Optional[int] = Field(None, ge=10, le=5000,
                                     description="Макс. узлов графа статьи")


class ApplyRequest(BaseModel):
    doc_id: str = Field(..., description="Целевой документ (результат поиска)")
    pattern: Dict[str, Any] = Field(default_factory=dict,
                                     description="Паттерн {nodes, edges, size, support, id} (для method=pattern)")
    predicate_mode: str = Field("raw", description="raw | direction | bucket")
    max_nodes: Optional[int] = Field(None, ge=10, le=5000,
                                     description="Макс. узлов целевого графа")
    knowledge_method: str = Field("pattern",
                                  description="pattern | logical | syllogism | thinking")
    operation: Optional[str] = Field(None,
                                     description="Конкретная операция способа (если не задана — все)")
    check_existing: bool = Field(True,
                                 description="Сверять сгенерированное знание с БД (new/exists/conflicts)")
    limit: int = Field(200, ge=1, le=2000, description="Лимит результатов генерации")
    statements_per_doc_cap: Optional[int] = Field(None, ge=10, le=2000,
                                                  description="Макс. утверждений на статью (сэмплинг)")
    corpus_doc_ids: Optional[List[str]] = Field(
        None,
        description="Ограничение корпуса генерации набором документов "
                    "(по умолчанию — весь корпус)",
    )


@router.get("/documents")
async def list_documents(
    service: PatternMinerService = Depends(get_pattern_miner_service),
) -> Dict[str, Any]:
    try:
        return await service.list_documents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки документов: {e}")


@router.get("/methods")
async def methods(
    service: PatternMinerService = Depends(get_pattern_miner_service),
) -> Dict[str, Any]:
    try:
        return await service.metadata()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки способов генерации: {e}")


@router.post("/mine")
async def mine_patterns(
    req: MineRequest,
    service: PatternMinerService = Depends(get_pattern_miner_service),
) -> Dict[str, Any]:
    try:
        return await service.mine(
            doc_ids=req.doc_ids,
            min_support=req.min_support,
            min_size=req.min_size,
            max_size=req.max_size,
            limit=req.limit,
            predicate_mode=req.predicate_mode,
            useful_only=req.useful_only,
            statements_per_doc_cap=req.statements_per_doc_cap,
            max_nodes=req.max_nodes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка майнинга паттернов: {e}")


class GenerateAllRequest(BaseModel):
    corpus_doc_ids: Optional[List[str]] = Field(
        None,
        description="Ограничение корпуса генерации набором документов "
                    "(по умолчанию — весь корпус)",
    )
    predicate_mode: str = Field("raw", description="raw | direction | bucket")
    check_existing: bool = Field(True,
                                 description="Сверять сгенерированное знание с БД (new/exists/conflicts)")
    limit_per_method: int = Field(30, ge=1, le=2000, description="Лимит результатов на способ")
    max_nodes: Optional[int] = Field(None, ge=10, le=5000,
                                     description="Макс. узлов графа статьи (паттерн-способ)")
    min_support: float = Field(0.3, ge=0.05, le=1.0,
                               description="Порог поддержки для майнинга паттернов")
    min_size: int = Field(2, ge=1, le=8, description="Мин. число узлов паттерна")
    max_size: int = Field(6, ge=2, le=8, description="Макс. число узлов паттерна")
    statements_per_doc_cap: Optional[int] = Field(None, ge=10, le=2000,
                                                  description="Макс. утверждений на статью (сэмплинг)")
    max_pool_size: int = Field(3000, ge=100, le=60000,
                               description="Макс. размер пула утверждений для генерации")


@router.post("/generate")
async def generate_all(
    req: GenerateAllRequest,
    service: PatternMinerService = Depends(get_pattern_miner_service),
) -> Dict[str, Any]:
    try:
        return await service.generate_all(
            predicate_mode=req.predicate_mode,
            check_existing=req.check_existing,
            limit_per_method=req.limit_per_method,
            max_nodes=req.max_nodes,
            min_support=req.min_support,
            min_size=req.min_size,
            max_size=req.max_size,
            statements_per_doc_cap=req.statements_per_doc_cap,
            max_pool_size=req.max_pool_size,
            corpus_doc_ids=req.corpus_doc_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации знания: {e}")


@router.post("/apply")
async def apply_pattern(
    req: ApplyRequest,
    service: PatternMinerService = Depends(get_pattern_miner_service),
) -> Dict[str, Any]:
    try:
        return await service.apply(
            doc_id=req.doc_id,
            pattern=req.pattern,
            predicate_mode=req.predicate_mode,
            max_nodes=req.max_nodes,
            knowledge_method=req.knowledge_method,
            operation=req.operation,
            check_existing=req.check_existing,
            limit=req.limit,
            statements_per_doc_cap=req.statements_per_doc_cap,
            corpus_doc_ids=req.corpus_doc_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка наложения паттерна: {e}")