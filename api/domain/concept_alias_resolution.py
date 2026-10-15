"""Однозначное сопоставление алиасов понятий между картами схемы 6."""
from __future__ import annotations

from collections import defaultdict

from domain.article_maps import require
from domain.comparison_normalization import canonical

VERSION = "schema6-unambiguous-concept-aliases-1"


def derive_unambiguous_aliases(maps: list[dict]) -> dict:
    """Объединяет подписи только по явным и однозначным алиасам карт.

    Алиас связывается с основной подписью лишь тогда, когда он сам встречается
    как основная подпись понятия в наборе карт и заявлен ровно для одной
    основной подписи. Это не устанавливает идентичность людей, когорт или
    других именованных объектов.
    """
    require(bool(maps), "Явные карты для разрешения алиасов обязательны")
    labels: set[str] = set()
    claims: dict[str, set[str]] = defaultdict(set)
    for snapshot in maps:
        graph = snapshot.get("graph", {})
        require(graph.get("schema_version") == 6, "Разрешение алиасов требует карту схемы 6")
        concepts = {concept["id"]: concept for concept in graph.get("concepts", [])}
        used = {role["concept_id"] for item in graph.get("knowledge", [])
                for statement in item.get("semantic_frame", {}).get("statements", [])
                for role in statement.get("roles", []) if role.get("concept_id") is not None}
        require(used <= set(concepts), "Неизвестная ссылка на понятие при разрешении алиасов")
        for concept_id in sorted(used):
            concept = concepts[concept_id]
            main = canonical(concept["display_text"], "concepts")
            require(bool(main), "Основная подпись понятия не может быть пустой")
            labels.add(main)
            for raw_alias in concept.get("aliases", []):
                alias = canonical(raw_alias, "concepts")
                if alias:
                    claims[alias].add(main)

    parent = {label: label for label in labels}

    def find(label: str) -> str:
        root = label
        while parent[root] != root:
            root = parent[root]
        while parent[label] != label:
            next_label = parent[label]
            parent[label] = root
            label = next_label
        return root

    merged_aliases = []
    ambiguous_aliases = {}
    for alias in sorted(claims):
        targets = claims[alias]
        if alias not in labels:
            continue
        if len(targets) != 1:
            ambiguous_aliases[alias] = sorted(targets)
            continue
        target = next(iter(targets))
        left, right = find(alias), find(target)
        if left != right:
            root, child = sorted((left, right))
            parent[child] = root
            merged_aliases.append({"alias": alias, "target": target})

    resolved = {label: find(label) for label in sorted(labels)}
    for alias, targets in sorted(claims.items()):
        if len(targets) == 1:
            resolved[alias] = find(next(iter(targets)))
    components: dict[str, list[str]] = defaultdict(list)
    for label in sorted(labels):
        components[resolved[label]].append(label)
    return {
        "version": VERSION,
        "canonical_labels": resolved,
        "merged_components": sorted((members for members in components.values() if len(members) > 1),
                                     key=lambda values: tuple(values)),
        "merged_aliases": merged_aliases,
        "ambiguous_aliases": ambiguous_aliases,
        "label_count": len(labels),
        "component_count": len(components),
        "model_calls": 0,
    }


def resolve_concept_label(value: str, alias_index: dict) -> str:
    require(alias_index.get("version") == VERSION, "Совместимая версия индекса алиасов обязательна")
    key = canonical(value, "concepts")
    return alias_index["canonical_labels"].get(key, key)
