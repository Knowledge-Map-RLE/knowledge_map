"""
Роутер для извлечения и визуализации паттернов как графов Action + LexicalUnit.

Эндпоинты:
  GET   /api/data_extraction/patterns/extract          — извлечь паттерны глобально
  GET   /api/data_extraction/patterns/extract/{doc_id} — извлечь паттерны документа
  POST  /api/data_extraction/patterns/create           — фоновое создание паттернов в БД
  GET   /api/data_extraction/patterns/create-status     — статус создания паттернов
  GET   /api/data_extraction/patterns/{pattern_uid}/text — восстановить текст из паттерна
  GET   /api/data_extraction/patterns/{pattern_uid}/graph — граф паттерна для PixiJS
  POST  /api/data_extraction/patterns/save             — сохранить паттерны в Neo4j
"""
import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patterns", tags=["patterns"])

# In-memory статус фоновой задачи создания паттернов
_pattern_create_status: Dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "progress": 0,      # 0..100
    "message": "",
    "total_patterns": 0,
    "saved_patterns": 0,
    "error": None,
    "started_at": None,
    "finished_at": None,
}

# In-memory статус фоновой задачи извлечения паттернов
_pattern_extract_status: Dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "message": "",
    "total_patterns": 0,
    "patterns": [],
    "error": None,
    "started_at": None,
    "finished_at": None,
}

_status_lock = threading.Lock()


def _update_status(status: str, progress: int = 0, message: str = "", **kwargs):
    """Атомарное обновление статуса."""
    with _status_lock:
        _pattern_create_status["status"] = status
        _pattern_create_status["progress"] = progress
        _pattern_create_status["message"] = message
        _pattern_create_status.update(kwargs)


def _update_extract_status(status: str, progress: int = 0, message: str = "", **kwargs):
    """Атомарное обновление статуса извлечения."""
    with _status_lock:
        _pattern_extract_status["status"] = status
        _pattern_extract_status["progress"] = progress
        _pattern_extract_status["message"] = message
        _pattern_extract_status.update(kwargs)


def _run_pattern_creation_in_background(
    max_nodes: int,
    max_depth: int,
    limit_per_n: int,
    min_frequency: int,
    mode: str,
    save_to_db: bool,
):
    """Фоновая задача: извлечение + сохранение паттернов в Neo4j."""
    from application.patterns.pattern_extractor import PatternExtractor
    from domain.models.pattern import Pattern

    driver = None
    try:
        _update_status(
            "running", progress=5,
            message="Подключение к Neo4j...",
            started_at=datetime.now().isoformat(),
        )

        driver = _get_driver()
        extractor = PatternExtractor(driver)

        _update_status(
            "running", progress=10,
            message="Извлечение dependency n-gram паттернов...",
        )

        # Извлекаем паттерны по шагам для прогресса
        dep_result = extractor.extract_dependency_ngrams(
            max_depth=max_depth,
            limit_per_n=limit_per_n,
        )

        total_dep = dep_result.total_patterns
        _update_status(
            "running", progress=30,
            message=f"Извлечено {total_dep} dependency паттернов. Извлечение Action паттернов...",
        )

        action_result = extractor.extract_action_patterns(
            max_nodes=max_nodes,
            min_frequency=min_frequency,
        )

        _update_status(
            "running", progress=50,
            message=f"Извлечено {action_result.total_patterns} Action паттернов. Извлечение смешанных...",
        )

        mixed_result = extractor.extract_mixed_patterns(
            max_nodes=max_nodes,
            min_frequency=min_frequency,
        )

        all_patterns = dep_result.patterns + action_result.patterns + mixed_result.patterns

        # Дедупликация
        seen: set = set()
        unique: List = []
        for p in all_patterns:
            if p.pattern_hash not in seen:
                seen.add(p.pattern_hash)
                unique.append(p)

        _update_status(
            "running", progress=60,
            message=f"Найдено {len(unique)} уникальных паттернов. Сохранение в БД...",
            total_patterns=len(unique),
        )

        if not save_to_db:
            _update_status(
                "done", progress=100,
                message="Извлечение завершено (без сохранения)",
                total_patterns=len(unique),
                saved_patterns=0,
                finished_at=datetime.now().isoformat(),
            )
            return

        # Сохраняем в БД batch-ами
        saved_count = 0
        total = len(unique)
        batch_size = 20

        for i in range(0, total, batch_size):
            batch = unique[i:i + batch_size]
            with driver.session() as session:
                for p in batch:
                    edges_json = json.dumps(
                        [
                            {
                                "source_id": e.source_id,
                                "target_id": e.target_id,
                                "edge_type": e.edge_type.value,
                                "relation_subtype": e.relation_subtype,
                            }
                            for e in p.canon_edges
                        ],
                        ensure_ascii=False,
                    )

                    session.run(
                        """
                        CREATE (p:Pattern {
                            uid: $uid,
                            name: $name,
                            description: $description,
                            pattern_hash: $pattern_hash,
                            frequency: $frequency,
                            stability: $stability,
                            doc_count: $doc_count,
                            node_count: $node_count,
                            edge_count: $edge_count,
                            size_category: $size_category,
                            edges_json: $edges_json
                        })
                        """,
                        {
                            "uid": p.uid,
                            "name": p.name,
                            "description": p.description,
                            "pattern_hash": p.pattern_hash,
                            "frequency": p.frequency,
                            "stability": p.stability,
                            "doc_count": p.doc_count,
                            "node_count": p.node_count,
                            "edge_count": p.edge_count,
                            "size_category": p.size_category,
                            "edges_json": edges_json,
                        },
                    )
                    saved_count += 1

            progress_pct = 60 + int((saved_count / total) * 35)
            _update_status(
                "running", progress=progress_pct,
                message=f"Сохранено {saved_count}/{total} паттернов...",
                saved_patterns=saved_count,
            )

        _update_status(
            "done", progress=100,
            message=f"Создано {saved_count} паттернов в Neo4j",
            saved_patterns=saved_count,
            finished_at=datetime.now().isoformat(),
        )
        logger.info(f"Pattern creation complete: {saved_count} patterns saved")

    except Exception as e:
        logger.error(f"Pattern creation error: {e}", exc_info=True)
        _update_status(
            "error", progress=0,
            message=f"Ошибка: {str(e)}",
            error=str(e),
            finished_at=datetime.now().isoformat(),
        )
    finally:
        if driver:
            driver.close()


@router.post("/create")
async def create_patterns_in_db(
    background_tasks: BackgroundTasks,
    max_nodes: int = Query(100, ge=1, le=200, description="Макс. узлов в паттерне"),
    max_depth: int = Query(5, ge=1, le=10, description="Макс. глубина dependency n-grams"),
    limit_per_n: int = Query(50, ge=10, le=200, description="Лимит паттернов на длину"),
    min_frequency: int = Query(1, ge=1, description="Мин. частота паттерна"),
    mode: str = Query("all", description="Режим: all, dependency, action, mixed"),
    save_to_db: bool = Query(True, description="Сохранять ли в Neo4j"),
):
    """
    Фоновое создание паттернов в Neo4j с отслеживанием прогресса.

    Запускает извлечение паттернов и сохраняет их как отдельные Pattern-узлы.
    Прогресс доступен через GET /patterns/create-status.
    """
    with _status_lock:
        if _pattern_create_status["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Создание паттернов уже выполняется. Дождитесь завершения.",
            )

    _update_status(
        "running", progress=0, message="Запуск...",
        total_patterns=0, saved_patterns=0, error=None,
        started_at=datetime.now().isoformat(), finished_at=None,
    )

    background_tasks.add_task(
        _run_pattern_creation_in_background,
        max_nodes=max_nodes,
        max_depth=max_depth,
        limit_per_n=limit_per_n,
        min_frequency=min_frequency,
        mode=mode,
        save_to_db=save_to_db,
    )

    return {
        "success": True,
        "message": "Создание паттернов запущено в фоне",
        "status_url": "/api/data_extraction/patterns/create-status",
    }


@router.get("/create-status")
async def get_pattern_create_status():
    """
    Получить статус фоновой задачи создания паттернов.

    Returns:
        {
            "status": "idle" | "running" | "done" | "error",
            "progress": 0..100,
            "message": "...",
            "total_patterns": N,
            "saved_patterns": M,
            "error": null | "error text",
            "started_at": "...",
            "finished_at": "..."
        }
    """
    with _status_lock:
        return dict(_pattern_create_status)


def _run_pattern_extraction_in_background(
    max_nodes: int,
    max_depth: int,
    limit_per_n: int,
    min_frequency: int,
    mode: str,
):
    """Фоновая задача: извлечение паттернов с прогрессом."""
    from application.patterns.pattern_extractor import PatternExtractor

    driver = None
    try:
        _update_extract_status(
            "running", progress=5,
            message="Подключение к Neo4j...",
            started_at=datetime.now().isoformat(),
        )

        driver = _get_driver()
        extractor = PatternExtractor(driver)

        _update_extract_status(
            "running", progress=10,
            message="Извлечение dependency n-gram паттернов...",
        )

        dep_result = extractor.extract_dependency_ngrams(
            max_depth=max_depth,
            limit_per_n=limit_per_n,
        )

        total_dep = dep_result.total_patterns
        _update_extract_status(
            "running", progress=35,
            message=f"Извлечено {total_dep} dependency паттернов. Извлечение Action паттернов...",
        )

        action_result = extractor.extract_action_patterns(
            max_nodes=max_nodes,
            min_frequency=min_frequency,
        )

        _update_extract_status(
            "running", progress=55,
            message=f"Извлечено {action_result.total_patterns} Action паттернов. Извлечение смешанных...",
        )

        mixed_result = extractor.extract_mixed_patterns(
            max_nodes=max_nodes,
            min_frequency=min_frequency,
        )

        _update_extract_status(
            "running", progress=75,
            message="Объединение и дедупликация...",
        )

        all_patterns = dep_result.patterns + action_result.patterns + mixed_result.patterns

        # Дедупликация
        seen: set = set()
        unique: List = []
        for p in all_patterns:
            if p.pattern_hash not in seen:
                seen.add(p.pattern_hash)
                unique.append(p)

        _update_extract_status(
            "running", progress=95,
            message=f"Найдено {len(unique)} уникальных паттернов",
        )

        # Convert to dicts for response (limit to avoid huge payload)
        patterns_dicts = [p.to_dict() for p in unique[:200]]  # first 200 for display

        _update_extract_status(
            "done", progress=100,
            message=f"Извлечено {len(unique)} паттернов",
            total_patterns=len(unique),
            patterns=patterns_dicts,
            finished_at=datetime.now().isoformat(),
        )
        logger.info(f"Pattern extraction complete: {len(unique)} patterns")

    except Exception as e:
        logger.error(f"Pattern extraction error: {e}", exc_info=True)
        _update_extract_status(
            "error", progress=0,
            message=f"Ошибка: {str(e)}",
            error=str(e),
            finished_at=datetime.now().isoformat(),
        )
    finally:
        if driver:
            driver.close()


@router.post("/extract")
async def extract_patterns_start(
    background_tasks: BackgroundTasks,
    max_nodes: int = Query(100, ge=1, le=200, description="Макс. узлов в паттерне"),
    max_depth: int = Query(5, ge=1, le=10, description="Макс. глубина dependency n-grams"),
    limit_per_n: int = Query(50, ge=10, le=200, description="Лимит паттернов на длину"),
    min_frequency: int = Query(1, ge=1, description="Мин. частота паттерна"),
    mode: str = Query("all", description="Режим: all, dependency, action, mixed"),
):
    """
    Запуск фонового извлечения паттернов с отслеживанием прогресса.

    Результат доступен через GET /patterns/extract-status.
    """
    with _status_lock:
        if _pattern_extract_status["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Извлечение паттернов уже выполняется. Дождитесь завершения.",
            )

    _update_extract_status(
        "running", progress=0, message="Запуск...",
        total_patterns=0, patterns=[], error=None,
        started_at=datetime.now().isoformat(), finished_at=None,
    )

    background_tasks.add_task(
        _run_pattern_extraction_in_background,
        max_nodes=max_nodes,
        max_depth=max_depth,
        limit_per_n=limit_per_n,
        min_frequency=min_frequency,
        mode=mode,
    )

    return {
        "success": True,
        "message": "Извлечение паттернов запущено в фоне",
        "status_url": "/api/data_extraction/patterns/extract-status",
    }


@router.get("/extract-status")
async def get_pattern_extract_status():
    """
    Получить статус фоновой задачи извлечения паттернов.

    Returns:
        {
            "status": "idle" | "running" | "done" | "error",
            "progress": 0..100,
            "message": "...",
            "total_patterns": N,
            "patterns": [...],  // доступы при status=done
            "error": null | "error text",
            "started_at": "...",
            "finished_at": "..."
        }
    """
    with _status_lock:
        return dict(_pattern_extract_status)


@router.get("/extract")
async def extract_patterns_global(
    max_nodes: int = Query(100, ge=1, le=200, description="Макс. узлов в паттерне"),
    max_depth: int = Query(5, ge=1, le=10, description="Макс. глубина dependency n-grams"),
    limit_per_n: int = Query(50, ge=10, le=200, description="Лимит паттернов на длину"),
    min_frequency: int = Query(1, ge=1, description="Мин. частота паттерна"),
    mode: str = Query("all", description="Режим: all, dependency, action, mixed"),
):
    """
    Глобальное извлечение паттернов из всех документов.

    Включает:
      - Dependency n-grams (как Pattern-объекты, аналог analyze_dependency_ngrams)
      - Action patterns (LEADS_TO цепочки)
      - Mixed patterns (Action + LexicalUnit)

    :param max_nodes: макс. узлов в одном паттерне (до 200)
    :param max_depth: глубина dependency n-grams (1-10)
    :param limit_per_n: лимит паттернов для каждой длины
    :param min_frequency: мин. частота для включения
    :param mode: "all", "dependency", "action", "mixed"
    """
    try:
        from application.patterns.pattern_extractor import PatternExtractor

        driver = _get_driver()
        extractor = PatternExtractor(driver)

        if mode == "dependency":
            result = extractor.extract_dependency_ngrams(
                max_depth=max_depth,
                limit_per_n=limit_per_n,
            )
        elif mode == "action":
            result = extractor.extract_action_patterns(
                max_nodes=max_nodes,
                min_frequency=min_frequency,
            )
        elif mode == "mixed":
            result = extractor.extract_mixed_patterns(
                max_nodes=max_nodes,
                min_frequency=min_frequency,
            )
        else:  # all
            result = extractor.extract_all(
                max_nodes=max_nodes,
                max_depth=max_depth,
                limit_per_n=limit_per_n,
                min_frequency=min_frequency,
            )

        driver.close()

        return {
            "success": True,
            "total_patterns": result.total_patterns,
            "max_nodes_seen": result.max_nodes_seen,
            "extraction_mode": result.extraction_mode,
            "doc_ids": result.doc_ids,
            "patterns": result.to_dict()["patterns"],
        }

    except ImportError:
        raise HTTPException(status_code=500, detail="PatternExtractor не найден")
    except Exception as e:
        logger.error(f"Ошибка извлечения паттернов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.get("/extract/{doc_id}")
async def extract_patterns_document(
    doc_id: str,
    max_nodes: int = Query(100, ge=1, le=200, description="Макс. узлов в паттерне"),
    max_depth: int = Query(5, ge=1, le=10, description="Макс. глубина dependency n-grams"),
    limit_per_n: int = Query(50, ge=10, le=200, description="Лимит паттернов на длину"),
    mode: str = Query("all", description="Режим: all, dependency, action, mixed"),
):
    """
    Извлечение паттернов одного документа.

    :param doc_id: ID документа
    :param max_nodes: макс. узлов в одном паттерне
    :param max_depth: глубина dependency n-grams (1-10)
    :param limit_per_n: лимит паттернов для каждой длины
    :param mode: "all", "dependency", "action", "mixed"
    """
    try:
        from application.patterns.pattern_extractor import PatternExtractor

        driver = _get_driver()
        extractor = PatternExtractor(driver)

        if mode == "dependency":
            result = extractor.extract_dependency_ngrams(
                max_depth=max_depth,
                limit_per_n=limit_per_n,
                doc_id=doc_id,
            )
        elif mode == "action":
            result = extractor.extract_action_patterns(
                max_nodes=max_nodes,
                doc_id=doc_id,
            )
        elif mode == "mixed":
            result = extractor.extract_mixed_patterns(
                max_nodes=max_nodes,
                doc_id=doc_id,
            )
        else:  # all
            result = extractor.extract_all(
                max_nodes=max_nodes,
                max_depth=max_depth,
                limit_per_n=limit_per_n,
                doc_id=doc_id,
            )

        driver.close()

        return {
            "success": True,
            "doc_id": doc_id,
            "total_patterns": result.total_patterns,
            "max_nodes_seen": result.max_nodes_seen,
            "patterns": result.to_dict()["patterns"],
        }

    except ImportError:
        raise HTTPException(status_code=500, detail="PatternExtractor не найден")
    except Exception as e:
        logger.error(f"Ошибка извлечения паттернов для {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.get("/{pattern_uid}/text")
async def reconstruct_pattern_text(pattern_uid: str):
    """
    Восстановить читаемый английский текст из структуры паттерна.

    Использует domain-метод Pattern.render_text() для реконструкции
    текста из графовой структуры по правилам английского языка.
    """
    try:
        # Сначала пытаемся найти сохранённый паттерн в БД
        pattern_data = _load_pattern_from_db(pattern_uid)
        if pattern_data:
            from domain.models.pattern import Pattern
            pattern = Pattern.from_dict(pattern_data)
            return {
                "success": True,
                "pattern_uid": pattern_uid,
                "rendered_text": pattern.render_text(),
                "node_count": pattern.node_count,
                "edge_count": pattern.edge_count,
            }

        raise HTTPException(status_code=404, detail=f"Паттерн {pattern_uid} не найден")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка реконструкции текста: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.get("/{pattern_uid}/graph")
async def get_pattern_graph(pattern_uid: str):
    """
    Получить граф паттерна для визуализации в PixiJS.

    Возвращает nodes + edges в формате, готовом для LinguisticGraphRenderer.
    """
    try:
        pattern_data = _load_pattern_from_db(pattern_uid)
        if pattern_data:
            from domain.models.pattern import Pattern

            pattern = Pattern.from_dict(pattern_data)
            nodes: List[Dict[str, Any]] = []
            edges: List[Dict[str, Any]] = []

            for pn in pattern.canon_nodes:
                node: Dict[str, Any] = {
                    "uid": pn.node_id,
                    "_type": pn.node_type.value,
                    "role": pn.role.value,
                    "text": pn.text,
                    "lemma": pn.lemma,
                    "pos": pn.pos,
                    "doc_id": pn.doc_id,
                }
                if pn.node_type.value == "Action":
                    node["verb"] = pn.text
                    node["action_class"] = pn.action_class
                nodes.append(node)

            for pe in pattern.canon_edges:
                edges.append({
                    "src_uid": pe.source_id,
                    "tgt_uid": pe.target_id,
                    "edge_type": pe.edge_type.value,
                    "relation_subtype": pe.relation_subtype,
                    "confidence": pe.confidence,
                })

            return {
                "success": True,
                "pattern_uid": pattern_uid,
                "name": pattern.name,
                "frequency": pattern.frequency,
                "stability": pattern.stability,
                "doc_count": pattern.doc_count,
                "size_category": pattern.size_category,
                "rendered_text": pattern.render_text(),
                "nodes": nodes,
                "edges": edges,
            }

        raise HTTPException(status_code=404, detail=f"Паттерн {pattern_uid} не найден")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения графа паттерна: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@router.post("/save")
async def save_patterns_to_db(
    patterns: List[Dict[str, Any]],
    replace_existing: bool = Query(False, description="Заменить существующие"),
):
    """
    Сохранить извлечённые паттерны в Neo4j.

    Каждый паттерн создаёт узел Pattern с связями CONTAINS_NODE к
    Action и LexicalUnit.

    :param patterns: массив паттернов (результат extract)
    :param replace_existing: заменить существующие с тем же pattern_hash
    """
    if not patterns:
        return {"success": False, "message": "Нет паттернов для сохранения"}

    try:
        driver = _get_driver()
        saved_count = 0

        with driver.session() as session:
            for pd in patterns:
                if replace_existing and pd.get("pattern_hash"):
                    # Удаляем существующий с таким же hash
                    session.run(
                        "MATCH (p:Pattern {pattern_hash: $hash}) DETACH DELETE p",
                        {"hash": pd["pattern_hash"]},
                    )

                # Создаём узел Pattern
                edges_json = __import__("json").dumps(
                    [{"source_id": e["source_id"], "target_id": e["target_id"],
                      "edge_type": e["edge_type"], "relation_subtype": e.get("relation_subtype", "")}
                     for e in pd.get("canon_edges", [])],
                    ensure_ascii=False,
                )

                session.run(
                    """
                    CREATE (p:Pattern {
                        uid: $uid,
                        name: $name,
                        description: $description,
                        pattern_hash: $pattern_hash,
                        frequency: $frequency,
                        stability: $stability,
                        doc_count: $doc_count,
                        node_count: $node_count,
                        edge_count: $edge_count,
                        size_category: $size_category,
                        edges_json: $edges_json
                    })
                    """,
                    {
                        "uid": pd.get("uid", ""),
                        "name": pd.get("name", ""),
                        "description": pd.get("description", ""),
                        "pattern_hash": pd.get("pattern_hash", ""),
                        "frequency": pd.get("frequency", 0),
                        "stability": pd.get("stability", 0.0),
                        "doc_count": pd.get("doc_count", 0),
                        "node_count": pd.get("node_count", 0),
                        "edge_count": pd.get("edge_count", 0),
                        "size_category": pd.get("size_category", ""),
                        "edges_json": edges_json,
                    },
                )
                saved_count += 1

        driver.close()

        return {
            "success": True,
            "saved_count": saved_count,
            "message": f"Сохранено {saved_count} паттернов",
        }

    except Exception as e:
        logger.error(f"Ошибка сохранения паттернов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


# =============================================================================
# Helpers
# =============================================================================

def _get_driver():
    """Создаёт Neo4j driver из переменных окружения."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, password))


def _load_pattern_from_db(pattern_uid: str) -> Optional[Dict[str, Any]]:
    """Загружает паттерн из Neo4j по UID."""
    driver = _get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (p:Pattern {uid: $uid}) RETURN p {.uid, .name, .description, "
                ".pattern_hash, .frequency, .stability, .doc_count, .node_count, "
                ".edge_count, .size_category, .edges_json} AS data",
                {"uid": pattern_uid},
            )
            record = result.single()
            if record:
                data = record["data"]
                import json
                canon_nodes = []
                # Загружаем узлы через CONTAINS_NODE связи
                nodes_result = session.run(
                    "MATCH (p:Pattern {uid: $uid})-[r:CONTAINS_NODE]->(n) "
                    "RETURN n.uid AS uid, type(n) AS _type, r.role AS role, "
                    "       r.node_type AS node_type, r.original_index AS original_index, "
                    "       n.text AS text, n.lemma AS lemma, n.pos AS pos, "
                    "       n.verb AS verb, n.action_class AS action_class, n.doc_id AS doc_id",
                    {"uid": pattern_uid},
                )
                for nr in nodes_result:
                    node_type = nr["node_type"] or nr["_type"]
                    canon_nodes.append({
                        "node_id": nr["uid"],
                        "node_type": node_type,
                        "role": nr["role"] or "modifier",
                        "text": nr.get("verb") or nr.get("text") or "",
                        "lemma": nr.get("lemma") or "",
                        "pos": nr.get("pos") or "",
                        "action_class": nr.get("action_class") or "",
                        "doc_id": nr.get("doc_id") or "",
                    })

                # Рёбра из edges_json
                canon_edges = []
                if data.get("edges_json"):
                    canon_edges = json.loads(data["edges_json"])

                return {
                    "uid": data.get("uid", pattern_uid),
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "pattern_hash": data.get("pattern_hash", ""),
                    "frequency": data.get("frequency", 0),
                    "stability": data.get("stability", 0.0),
                    "doc_count": data.get("doc_count", 0),
                    "canon_nodes": canon_nodes,
                    "canon_edges": canon_edges,
                }
            return None
    finally:
        driver.close()
