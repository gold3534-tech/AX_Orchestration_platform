from __future__ import annotations

from collections import deque
from typing import TypeVar


T = TypeVar("T")


def dedupe_preserve_order(values: list[T]) -> list[T]:
    seen: set[T] = set()
    ordered: list[T] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def topological_order(node_ids: list[str], dependency_map: dict[str, list[str]]) -> list[str]:
    inbound = {node_id: 0 for node_id in node_ids}
    dependents = {node_id: [] for node_id in node_ids}
    for node_id, dependency_ids in dependency_map.items():
        if node_id not in inbound:
            raise ValueError(f"Task dependencies reference unknown task: {node_id}")
        for dependency_id in dependency_ids:
            if dependency_id not in inbound:
                raise ValueError(f"Task dependencies reference unknown task: {dependency_id}")
            inbound[node_id] += 1
            dependents.setdefault(dependency_id, []).append(node_id)
    ready = deque([node_id for node_id in node_ids if inbound[node_id] == 0])
    ordered: list[str] = []
    while ready:
        node_id = ready.popleft()
        ordered.append(node_id)
        for dependent in dependents.get(node_id, []):
            inbound[dependent] -= 1
            if inbound[dependent] == 0:
                ready.append(dependent)
    if len(ordered) != len(node_ids):
        raise ValueError("Task dependencies must form an acyclic order.")
    return ordered
