from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


INPUT_TOKEN_PATTERN = re.compile(r"(?<!{){([A-Za-z_][A-Za-z0-9_]*)}(?!})")


def input_keys_from_text(value: Any) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    return sorted({match.group(1) for match in INPUT_TOKEN_PATTERN.finditer(value)})


def input_keys_from_presets(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item) and item not in result:
            result.append(item)
    return result


def collect_required_input_keys(
    *,
    runtime_agents: Iterable[Mapping[str, Any]],
    runtime_tasks: Iterable[Mapping[str, Any]],
) -> list[str]:
    keys: set[str] = set()
    for agent in runtime_agents:
        keys.update(input_keys_from_text(agent.get("role")))
        keys.update(input_keys_from_text(agent.get("goal")))
        keys.update(input_keys_from_text(agent.get("backstory")))
    for task in runtime_tasks:
        keys.update(input_keys_from_presets(task.get("input_presets")))
        keys.update(input_keys_from_text(task.get("description")))
        keys.update(input_keys_from_text(task.get("expected_output")))
    return sorted(keys)
