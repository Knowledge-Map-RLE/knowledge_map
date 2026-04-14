"""
Layer: Domain (Entities)
Package: domain.models.pattern
Responsibility: Чистое представление Паттерна как графа Action + LexicalUnit.

Паттерн — это подграф произвольной топологии (от 1 до ~100 вершин),
состоящий из узлов Action и LexicalUnit, связанных рёбрами
LEADS_TO, DEPENDS_ON, PART_OF.

Восстанавливает исходный текст из структуры графа по правилам английского языка.

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi, grpc, aioboto3, spacy
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# =============================================================================
# Перечисления
# =============================================================================

class PatternNodeType(str, Enum):
    """Тип узла внутри паттерна."""
    ACTION = "Action"
    LEXICAL_UNIT = "LexicalUnit"


class PatternEdgeType(str, Enum):
    """Тип ребра внутри паттерна."""
    LEADS_TO = "LEADS_TO"
    DEPENDS_ON = "DEPENDS_ON"
    PART_OF = "PART_OF"


class NodeRole(str, Enum):
    """Семантическая роль узла внутри паттерна."""
    VERB = "verb"
    SUBJECT = "subject"
    OBJECT = "object"
    MODIFIER = "modifier"
    COMPOUND = "compound"
    CONNECTOR = "connector"  # Action-узел, связывающий другие Actions


# =============================================================================
# Domain-модели
# =============================================================================

@dataclass
class PatternNode:
    """
    Узел паттерна — обёртка над Action или LexicalUnit.

    Хранит ссылку на оригинальный uid в Neo4j и семантическую роль
    внутри паттерна.
    """
    node_id: str                     # uid узла в Neo4j (Action.uid или LexicalUnit.uid)
    node_type: PatternNodeType       # Action | LexicalUnit
    role: NodeRole                   # verb, subject, object, modifier, ...
    text: str = ""                   # текст узла (verb для Action, text для LexicalUnit)
    lemma: str = ""                  # лемма
    pos: str = ""                    # POS-тег (для LexicalUnit)
    action_class: str = ""           # action_class (для Action)
    doc_id: str = ""                 # документ, из которого узел
    metadata: Dict[str, Any] = field(default_factory=dict)

    def canonical_key(self) -> str:
        """Канонический ключ для структурного хеширования."""
        # Для Action: (action_class, verb_lemma)
        # Для LexicalUnit: (pos, lemma)
        if self.node_type == PatternNodeType.ACTION:
            return f"ACT:{self.action_class}:{self.lemma}"
        return f"LU:{self.pos}:{self.lemma}"


@dataclass
class PatternEdge:
    """
    Ребро паттерна — связь между двумя PatternNode.

    Типы: LEADS_TO (Action→Action), DEPENDS_ON (LU→LU), PART_OF (LU→Action).
    """
    source_id: str                   # uid исходного узла
    target_id: str                   # uid целевого узла
    edge_type: PatternEdgeType       # LEADS_TO | DEPENDS_ON | PART_OF
    relation_subtype: str = ""       # enables, causes, nsubj, dobj, amod, compound, ...
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def canonical_key(self) -> str:
        """Канонический ключ ребра для дедупликации."""
        return f"{self.edge_type.value}:{self.relation_subtype}"


@dataclass
class PatternInstance:
    """
    Одно конкретное вхождение паттерна в графе.

    Хранит mapping канонических позиций паттерна → реальные uid узлов.
    """
    node_mapping: Dict[str, str]     # canonical_pattern_node_id → real_uid
    doc_id: str                      # документ, в котором найдено вхождение
    confidence: float = 1.0


@dataclass
class Pattern:
    """
    Паттерн — абстрактный граф, извлечённый из корпуса.

    Хранит:
      - canon_nodes: канонические узлы (абстрактная структура)
      - canon_edges: канонические рёбра
      - instances: конкретные вхождения паттерна в графе
      - frequency: общее число вхождений
      - stability: docs_with_pattern / total_occurrences
      - pattern_hash: канонический хеш для дедупликации
      - uid: уникальный идентификатор паттерна (для хранения в БД)
    """
    uid: str = ""
    name: str = ""
    description: str = ""
    created_at: str = ""
    pattern_hash: str = ""

    # Каноническая структура (абстрактный граф)
    canon_nodes: List[PatternNode] = field(default_factory=list)
    canon_edges: List[PatternEdge] = field(default_factory=list)

    # Конкретные вхождения
    instances: List[PatternInstance] = field(default_factory=list)

    # Статистика
    frequency: int = 0
    stability: float = 0.0
    doc_count: int = 0  # число уникальных документов с этим паттерном

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.pattern_hash:
            self.pattern_hash = self.compute_hash()
        if self.instances and not self.doc_count:
            self.doc_count = len(set(i.doc_id for i in self.instances))

    # ------------------------------------------------------------------
    # Свойства
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        """Число узлов в каноническом графе паттерна."""
        return len(self.canon_nodes)

    @property
    def edge_count(self) -> int:
        """Число рёбер в каноническом графе паттерна."""
        return len(self.canon_edges)

    @property
    def action_nodes(self) -> List[PatternNode]:
        """Узлы типа Action."""
        return [n for n in self.canon_nodes if n.node_type == PatternNodeType.ACTION]

    @property
    def lexical_nodes(self) -> List[PatternNode]:
        """Узлы типа LexicalUnit."""
        return [n for n in self.canon_nodes if n.node_type == PatternNodeType.LEXICAL_UNIT]

    @property
    def leads_to_edges(self) -> List[PatternEdge]:
        """Рёбра LEADS_TO."""
        return [e for e in self.canon_edges if e.edge_type == PatternEdgeType.LEADS_TO]

    @property
    def depends_on_edges(self) -> List[PatternEdge]:
        """Рёбра DEPENDS_ON."""
        return [e for e in self.canon_edges if e.edge_type == PatternEdgeType.DEPENDS_ON]

    @property
    def part_of_edges(self) -> List[PatternEdge]:
        """Рёбра PART_OF."""
        return [e for e in self.canon_edges if e.edge_type == PatternEdgeType.PART_OF]

    @property
    def size_category(self) -> str:
        """Категория размера паттерна."""
        n = self.node_count
        if n == 1:
            return "unigram"
        elif n <= 3:
            return "small"
        elif n <= 10:
            return "medium"
        elif n <= 30:
            return "large"
        else:
            return "xlarge"

    # ------------------------------------------------------------------
    # Хеширование (дедупликация)
    # ------------------------------------------------------------------

    def compute_hash(self) -> str:
        """
        Вычисляет канонический хеш паттерна для дедупликации.

        Хеш зависит только от структуры графа (типы узлов, типы рёбер),
        а не от конкретных uid или текстов.
        """
        # Сортируем узлы по canonical_key
        node_keys = sorted(n.canonical_key() for n in self.canon_nodes)
        # Сортируем рёбра по canonical_key + source/target
        edge_keys = sorted(
            (e.canonical_key(), e.source_id, e.target_id)
            for e in self.canon_edges
        )
        raw = f"nodes:{node_keys}|edges:{edge_keys}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def matches_structure(self, other: "Pattern") -> bool:
        """Проверяет, совпадает ли структура с другим паттерном."""
        return self.pattern_hash == other.pattern_hash

    # ------------------------------------------------------------------
    # Восстановление текста из паттерна
    # ------------------------------------------------------------------

    def render_text(self) -> str:
        """
        Восстанавливает читаемый английский текст из структуры паттерна.

        Алгоритм:
          1. Группирует LexicalUnit по родительскому Action (через PART_OF)
          2. Для каждого Action восстанавливает фразу в SVO-порядке
          3. Связывает Actions через LEADS_TO с因果-коннекторами
          4. DEPENDS_ON между LexicalUnit: compound-слияния, amod перед noun
        """
        if not self.canon_nodes:
            return ""

        # Шаг 1: Группируем LexicalUnit по Action
        action_phrases = self._build_action_phrases()

        # Шаг 2: Связываем Actions через LEADS_TO
        if self.leads_to_edges:
            return self._connect_action_phrases(action_phrases)

        # Один Action или только LexicalUnit
        if action_phrases:
            return " ".join(action_phrases.values())

        # Только LexicalUnit (DEPENDS_ON цепочка)
        return self._render_dependency_chain()

    def _build_action_phrases(self) -> Dict[str, str]:
        """
        Для каждого Action-узла строит фразу в SVO-порядке.

        Returns: {action_node_id: "subject verb object modifiers"}
        """
        phrases: Dict[str, str] = {}

        for action in self.action_nodes:
            # Находим LexicalUnit, которые PART_OF этого Action
            part_of = [
                e for e in self.part_of_edges
                if e.target_id == action.node_id
            ]
            child_lu_ids = {e.source_id for e in part_of}

            # Классифицируем LexicalUnit по ролям
            subjects: List[PatternNode] = []
            verbs: List[PatternNode] = []
            objects: List[PatternNode] = []
            modifiers: List[PatternNode] = []
            compounds: Dict[str, PatternNode] = {}  # compound_target -> compound_source

            for node in self.lexical_nodes:
                if node.node_id not in child_lu_ids:
                    continue
                if node.role == NodeRole.SUBJECT:
                    subjects.append(node)
                elif node.role == NodeRole.VERB:
                    verbs.append(node)
                elif node.role == NodeRole.OBJECT:
                    objects.append(node)
                elif node.role == NodeRole.MODIFIER:
                    modifiers.append(node)
                elif node.role == NodeRole.COMPOUND:
                    # Найдём цель compound-связи
                    for edge in self.depends_on_edges:
                        if edge.source_id == node.node_id and edge.relation_subtype == "compound":
                            compounds[edge.target_id] = node

            # Строим фразу: [subject] verb [modifiers] [object]
            parts: List[str] = []

            # Subject
            if subjects:
                subj_text = self._resolve_compound(subjects[0], compounds)
                parts.append(subj_text)

            # Verb
            if verbs:
                parts.append(verbs[0].text or verbs[0].lemma)
            elif action.text:
                parts.append(action.text)

            # Modifiers (наречия перед глаголом или в конце)
            adv_mods = [m for m in modifiers if m.pos == "ADV"]
            adj_mods = [m for m in modifiers if m.pos in ("ADJ",)]

            # Прилагательные — к ближайшему существительному
            for am in adj_mods:
                for edge in self.depends_on_edges:
                    if edge.source_id == am.node_id and edge.relation_subtype == "amod":
                        # Прилагательное перед существительным
                        for i, obj in enumerate(objects):
                            if obj.node_id == edge.target_id:
                                objects[i] = self._prepend_modifier(obj, am)
                        for i, subj in enumerate(subjects):
                            if subj.node_id == edge.target_id:
                                subjects[i] = self._prepend_modifier(subj, am)

            # Наречия
            if adv_mods:
                parts.extend(m.text or m.lemma for m in adv_mods)

            # Object
            for obj in objects:
                obj_text = self._resolve_compound(obj, compounds)
                parts.append(obj_text)

            if parts:
                phrases[action.node_id] = " ".join(parts)
            elif action.text:
                phrases[action.node_id] = action.text

        return phrases

    def _resolve_compound(
        self, node: PatternNode, compounds: Dict[str, PatternNode]
    ) -> str:
        """Добавляет compound-модификаторы перед основным словом."""
        text = node.text or node.lemma
        if node.node_id in compounds:
            compound_node = compounds[node.node_id]
            text = f"{compound_node.text or compound_node.lemma} {text}"
        return text

    def _prepend_modifier(self, target: PatternNode, modifier: PatternNode) -> PatternNode:
        """Добавляет прилагательное-модификатор перед существительным."""
        mod_text = modifier.text or modifier.lemma
        base_text = target.text or target.lemma
        import copy
        result = copy.copy(target)
        result.text = f"{mod_text} {base_text}"
        return result

    def _connect_action_phrases(self, phrases: Dict[str, str]) -> str:
        """
        Связывает фразы Actions через LEADS_TO с因果-коннекторами.
        """
        # Строим цепочку из LEADS_TO
        connectors = {
            "enables": "This enables",
            "causes": "This leads to",
            "prevents": "This prevents",
            "via_mechanism": "through the mechanism of",
            "sequential": "Then",
        }

        visited: Set[str] = set()
        sentences: List[str] = []

        # Находим стартовые узлы (без входящих LEADS_TO)
        targets = {e.target_id for e in self.leads_to_edges}
        sources = {e.source_id for e in self.leads_to_edges}
        roots = sources - targets

        # Если нет явных корней, берём первый source
        if not roots and self.leads_to_edges:
            roots = {self.leads_to_edges[0].source_id}

        for root_id in sorted(roots):
            if root_id in visited:
                continue
            self._traverse_leads_chain(root_id, phrases, visited, sentences, connectors)

        return ". ".join(sentences)

    def _traverse_leads_chain(
        self,
        node_id: str,
        phrases: Dict[str, str],
        visited: Set[str],
        sentences: List[str],
        connectors: Dict[str, str],
    ):
        """DFS по цепочке LEADS_TO."""
        if node_id in visited:
            return
        visited.add(node_id)

        phrase = phrases.get(node_id, "")
        if phrase:
            sentences.append(phrase)

        # Находим исходящие LEADS_TO
        outgoing = [e for e in self.leads_to_edges if e.source_id == node_id]
        for edge in outgoing:
            connector = connectors.get(edge.relation_subtype, "This leads to")
            target_phrase = phrases.get(edge.target_id, "")
            if target_phrase:
                sentences.append(f"{connector} {target_phrase[0].lower()}{target_phrase[1:]}")
            self._traverse_leads_chain(edge.target_id, phrases, visited, sentences, connectors)

    def _render_dependency_chain(self) -> str:
        """
        Восстанавливает текст из цепочки DEPENDS_ON (без Actions).
        """
        if not self.lexical_nodes:
            return ""

        # Находим корневые узлы (без входящих DEPENDS_ON)
        targets = {e.target_id for e in self.depends_on_edges}
        roots = [n for n in self.lexical_nodes if n.node_id not in targets]
        if not roots:
            roots = self.lexical_nodes[:1]

        parts: List[str] = []
        visited: Set[str] = set()

        for root in roots:
            self._traverse_dep_chain(root.node_id, parts, visited)

        return " ".join(parts) if parts else " ".join(
            n.text or n.lemma for n in self.lexical_nodes
        )

    def _traverse_dep_chain(
        self, node_id: str, parts: List[str], visited: Set[str]
    ):
        """DFS по цепочке DEPENDS_ON."""
        if node_id in visited:
            return
        visited.add(node_id)

        node = next((n for n in self.lexical_nodes if n.node_id == node_id), None)
        if node:
            parts.append(node.text or node.lemma)

        # Находим исходящие DEPENDS_ON
        outgoing = [e for e in self.depends_on_edges if e.source_id == node_id]
        for edge in outgoing:
            self._traverse_dep_chain(edge.target_id, parts, visited)

    # ------------------------------------------------------------------
    # Сериализация / десериализация
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "name": self.name,
            "description": self.description,
            "pattern_hash": self.pattern_hash,
            "created_at": self.created_at,
            "frequency": self.frequency,
            "stability": round(self.stability, 4),
            "doc_count": self.doc_count,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "size_category": self.size_category,
            "canon_nodes": [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type.value,
                    "role": n.role.value,
                    "text": n.text,
                    "lemma": n.lemma,
                    "pos": n.pos,
                    "action_class": n.action_class,
                    "doc_id": n.doc_id,
                }
                for n in self.canon_nodes
            ],
            "canon_edges": [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "edge_type": e.edge_type.value,
                    "relation_subtype": e.relation_subtype,
                    "confidence": e.confidence,
                }
                for e in self.canon_edges
            ],
            "instances": [
                {
                    "node_mapping": inst.node_mapping,
                    "doc_id": inst.doc_id,
                    "confidence": inst.confidence,
                }
                for inst in self.instances
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pattern":
        pattern = cls(
            uid=data.get("uid", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            pattern_hash=data.get("pattern_hash", ""),
            created_at=data.get("created_at", ""),
            frequency=data.get("frequency", 0),
            stability=data.get("stability", 0.0),
            doc_count=data.get("doc_count", 0),
        )
        for nd in data.get("canon_nodes", []):
            pattern.canon_nodes.append(PatternNode(
                node_id=nd["node_id"],
                node_type=PatternNodeType(nd["node_type"]),
                role=NodeRole(nd["role"]),
                text=nd.get("text", ""),
                lemma=nd.get("lemma", ""),
                pos=nd.get("pos", ""),
                action_class=nd.get("action_class", ""),
                doc_id=nd.get("doc_id", ""),
            ))
        for ed in data.get("canon_edges", []):
            pattern.canon_edges.append(PatternEdge(
                source_id=ed["source_id"],
                target_id=ed["target_id"],
                edge_type=PatternEdgeType(ed["edge_type"]),
                relation_subtype=ed.get("relation_subtype", ""),
                confidence=ed.get("confidence", 1.0),
            ))
        for inst_d in data.get("instances", []):
            pattern.instances.append(PatternInstance(
                node_mapping=inst_d["node_mapping"],
                doc_id=inst_d["doc_id"],
                confidence=inst_d.get("confidence", 1.0),
            ))
        return pattern
