from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any


ALLOWED_TOOL_MODULES = ("crewai_tools", "api.tools")
TEST_TOOL_MODULE_PREFIX = "tests."


def is_allowlisted_tool_module(module_path: str) -> bool:
    for allowed_module in ALLOWED_TOOL_MODULES:
        if module_path == allowed_module or module_path.startswith(f"{allowed_module}."):
            return True
    if module_path.startswith(TEST_TOOL_MODULE_PREFIX) and os.getenv("PYTEST_CURRENT_TEST"):
        return True
    return False


def require_allowlisted_tool_module(module_path: str) -> None:
    if not is_allowlisted_tool_module(module_path):
        raise ValueError(f"Tool module is not allowlisted: {module_path}")


def validate_tool_config(
    *,
    tool_key: str,
    version_id: str,
    config: Mapping[str, Any],
    config_schema_json: object,
) -> None:
    if not isinstance(config_schema_json, Mapping) or not config_schema_json:
        return
    additional_properties = config_schema_json.get("additionalProperties", True)
    properties = config_schema_json.get("properties")
    if not isinstance(properties, Mapping):
        if additional_properties is not False:
            return
        properties = {}
    if additional_properties is False:
        for key in config:
            if key not in properties:
                raise ValueError(
                    f"Unsupported config field '{key}' for tool {tool_key} on version {version_id}."
                )
    for key, value in config.items():
        field_schema = properties.get(key)
        if not isinstance(field_schema, Mapping):
            continue
        expected_type = field_schema.get("type")
        if not _matches_json_type(value, expected_type):
            raise ValueError(
                f"Invalid config field '{key}' for tool {tool_key} on version {version_id}: "
                f"expected {expected_type}."
            )
        allowed_values = field_schema.get("enum")
        if isinstance(allowed_values, list) and allowed_values and value not in allowed_values:
            allowed = ", ".join(str(item) for item in allowed_values)
            raise ValueError(
                f"Invalid config field '{key}' for tool {tool_key} on version {version_id}: "
                f"expected one of: {allowed}."
            )
        minimum = field_schema.get("minimum")
        maximum = field_schema.get("maximum")
        if type(minimum) in {int, float} and _is_number(value) and value < minimum:
            raise ValueError(
                f"Invalid config field '{key}' for tool {tool_key} on version {version_id}: "
                f"expected between {minimum} and {maximum}."
            )
        if type(maximum) in {int, float} and _is_number(value) and value > maximum:
            raise ValueError(
                f"Invalid config field '{key}' for tool {tool_key} on version {version_id}: "
                f"expected between {minimum} and {maximum}."
            )


def validate_required_env_vars(
    *,
    tool_key: str,
    version_id: str,
    required_env_vars: object,
) -> None:
    if not isinstance(required_env_vars, list):
        return
    missing: list[str] = []
    for item in required_env_vars:
        if not isinstance(item, Mapping):
            continue
        if item.get("required") is not True:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if not os.getenv(name.strip()):
            missing.append(name.strip())
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise ValueError(
            f"Tool {tool_key} on version {version_id} requires environment variable(s): {names}."
        )


def _matches_json_type(value: object, expected_type: object) -> bool:
    if expected_type is None:
        return True
    if isinstance(expected_type, list):
        return any(_matches_json_type(value, candidate) for candidate in expected_type)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return type(value) is int
    if expected_type == "number":
        return _is_number(value)
    if expected_type == "boolean":
        return type(value) is bool
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return True


def _is_number(value: object) -> bool:
    return type(value) in {int, float}
