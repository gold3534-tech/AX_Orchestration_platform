from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from crewai import Agent, Crew, LLM, Process, Task
from crewai.llms.base_llm import BaseLLM
from pydantic import BaseModel, Field, create_model


_META_PAYLOAD_KEYS = {
    "type",
    "version_id",
    "asset_id",
    "asset_type",
    "version_number",
    "status",
    "metadata_json",
    "agent_name",
    "photo_url",
    "task_name",
    "crew_name",
    "depends_on_task_ids",
    "context_task_ids",
    "agent_version_ids",
    "task_version_ids",
    "manager_agent_version_id",
    "manager_agent_asset_id",
    "input_presets",
    "output_type",
    "output_schema_fields",
}

_RESOLVER_BACKED_FIELDS = {
    "agent": {
        "agent_executor",
        "apps",
        "callbacks",
        "cache_handler",
        "crew",
        "execution_context",
        "guardrail",
        "i18n",
        "knowledge",
        "knowledge_config",
        "knowledge_sources",
        "knowledge_storage",
        "mcps",
        "memory",
        "planning_config",
        "security_config",
        "skills",
        "step_callback",
        "tools",
        "tools_handler",
    },
    "task": {
        "agent",
        "callback",
        "context",
        "converter_cls",
        "guardrail",
        "guardrails",
        "input_files",
        "output_json",
        "output_pydantic",
        "response_model",
        "security_config",
        "tools",
    },
    "crew": {
        "after_kickoff_callbacks",
        "agents",
        "before_kickoff_callbacks",
        "config",
        "execution_context",
        "knowledge",
        "knowledge_sources",
        "manager_agent",
        "security_config",
        "skills",
        "step_callback",
        "task_callback",
        "tasks",
    },
}

_FACTORY_OWNED_FIELDS = {
    "agent": {
        "backstory",
        "goal",
        "name",
        "role",
    },
    "task": {
        "description",
        "expected_output",
        "name",
    },
    "crew": {
        "crew_node_id",
        "description",
        "name",
    },
}

_PRIMITIVE_FIELD_TYPES = {
    "agent": {
        "max_iter": int,
        "max_rpm": int,
        "max_execution_time": int,
        "verbose": bool,
        "allow_delegation": bool,
        "reasoning": bool,
        "max_reasoning_attempts": int,
        "system_template": str,
        "prompt_template": str,
        "response_template": str,
        "cache": bool,
        "max_tokens": int,
        "allow_code_execution": bool,
        "respect_context_window": bool,
        "max_retry_limit": int,
        "multimodal": bool,
        "inject_date": bool,
        "date_format": str,
        "use_system_prompt": bool,
        "code_execution_mode": str,
        "embedder": Mapping,
    },
    "task": {
        "async_execution": bool,
        "human_input": bool,
        "markdown": bool,
        "guardrail_max_retries": int,
        "output_file": str,
        "create_directory": bool,
    },
    "crew": {
        "verbose": bool,
        "max_rpm": int,
        "memory": bool,
        "cache": bool,
        "share_crew": bool,
        "output_log_file": (bool, str),
        "prompt_file": str,
        "planning": bool,
        "stream": bool,
        "tracing": bool,
        "checkpoint": (bool, Mapping),
        "embedder": Mapping,
    },
}

_LLM_SPEC_FIELDS = {
    "agent": {"llm", "function_calling_llm"},
    "task": set(),
    "crew": {"manager_llm", "function_calling_llm", "planning_llm", "chat_llm"},
}

_OUTPUT_FIELD_TYPES: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
    "list": list,
}


class _ResolvedCrewFunctionCallingLLM(LLM):
    def __new__(cls, delegate: BaseLLM):
        return object.__new__(cls)

    def __init__(self, delegate: BaseLLM) -> None:
        object.__setattr__(self, "_delegate", delegate)
        object.__setattr__(self, "model", getattr(delegate, "model", "runtime-validation"))
        object.__setattr__(self, "provider", getattr(delegate, "provider", "openai"))
        object.__setattr__(self, "llm_type", "litellm")
        object.__setattr__(self, "additional_params", {})
        object.__setattr__(self, "stop", [])
        object.__setattr__(self, "stream", False)
        object.__setattr__(self, "callbacks", None)
        object.__setattr__(self, "context_window_size", delegate.get_context_window_size())

    def call(self, *args: Any, **kwargs: Any) -> object:
        return self._delegate.call(*args, **kwargs)

    def supports_function_calling(self) -> bool:
        return self._delegate.supports_function_calling()

    def get_context_window_size(self) -> int:
        return self._delegate.get_context_window_size()


def _ensure_crewai_field(kind: str, field_name: str) -> None:
    crewai_type = {"agent": Agent, "task": Task, "crew": Crew}[kind]
    if field_name not in crewai_type.model_fields:
        raise ValueError(f"unsupported CrewAI {kind} field '{field_name}'")


def _expect_type(kind: str, field_name: str, value: object, expected_type: object) -> object:
    if expected_type is bool:
        if type(value) is not bool:
            raise ValueError(f"Invalid {kind} payload field '{field_name}': expected bool.")
        return value
    if expected_type is int:
        if type(value) is not int:
            raise ValueError(f"Invalid {kind} payload field '{field_name}': expected int.")
        return value
    if expected_type is float:
        if type(value) not in {int, float}:
            raise ValueError(f"Invalid {kind} payload field '{field_name}': expected float.")
        return value
    if isinstance(expected_type, tuple):
        if not any(_matches_type(value, candidate) for candidate in expected_type):
            names = "|".join(_type_name(candidate) for candidate in expected_type)
            raise ValueError(f"Invalid {kind} payload field '{field_name}': expected {names}.")
        return value
    if not _matches_type(value, expected_type):
        raise ValueError(
            f"Invalid {kind} payload field '{field_name}': expected {_type_name(expected_type)}."
        )
    return value


def _matches_type(value: object, expected_type: object) -> bool:
    if expected_type is Mapping:
        return isinstance(value, Mapping)
    if expected_type is bool:
        return type(value) is bool
    if expected_type is int:
        return type(value) is int
    if expected_type is float:
        return type(value) in {int, float}
    if isinstance(expected_type, type):
        return isinstance(value, expected_type)
    return False


def _type_name(expected_type: object) -> str:
    if expected_type is Mapping:
        return "dict"
    if isinstance(expected_type, type):
        return expected_type.__name__
    return str(expected_type)


def _process(value: object) -> Process:
    if isinstance(value, Process):
        return value
    if isinstance(value, str):
        try:
            return Process(value)
        except ValueError as exc:
            raise ValueError(f"Invalid crew payload field 'process': unsupported value '{value}'.") from exc
    raise ValueError("Invalid crew payload field 'process': expected str.")


def _llm_spec(
    kind: str,
    field_name: str,
    value: object,
    llm_resolver: Callable[[object], object] | None,
) -> object | None:
    if value is None:
        return None
    model_name = _llm_model_name(value)
    if model_name is None:
        raise ValueError(
            f"Invalid {kind} payload field '{field_name}': expected non-empty LLM model spec."
        )
    if llm_resolver is not None:
        resolved = llm_resolver(value)
        if (
            kind == "crew"
            and field_name == "function_calling_llm"
            and isinstance(resolved, BaseLLM)
            and not isinstance(resolved, LLM)
        ):
            return _ResolvedCrewFunctionCallingLLM(resolved)
        return resolved
    return model_name


def _llm_model_name(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        model = value.get("main_model") or value.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
    return None


class CrewAIRuntimePayloadAdapter:
    def __init__(self, llm_resolver: Callable[[object], object] | None = None) -> None:
        self._llm_resolver = llm_resolver

    def agent_kwargs(self, payload: Mapping[str, object]) -> dict[str, object]:
        return self._convert_kwargs("agent", payload)

    def task_kwargs(self, payload: Mapping[str, object]) -> dict[str, object]:
        kwargs = self._convert_kwargs("task", payload)
        kwargs.update(self.task_output_model(payload))
        return kwargs

    def crew_kwargs(self, payload: Mapping[str, object]) -> dict[str, object]:
        return self._convert_kwargs("crew", payload)

    def _convert_kwargs(self, kind: str, payload: Mapping[str, object]) -> dict[str, object]:
        kwargs: dict[str, object] = {}
        primitive_types = _PRIMITIVE_FIELD_TYPES[kind]
        resolver_backed_fields = _RESOLVER_BACKED_FIELDS[kind]
        llm_fields = _LLM_SPEC_FIELDS[kind]

        for field_name, value in payload.items():
            if (
                value is None
                or field_name in _META_PAYLOAD_KEYS
                or field_name in _FACTORY_OWNED_FIELDS[kind]
            ):
                continue
            if field_name == "process" and kind == "crew":
                _ensure_crewai_field(kind, field_name)
                kwargs[field_name] = _process(value)
                continue
            if field_name in resolver_backed_fields:
                raise ValueError(
                    f"Invalid {kind} runtime payload: field '{field_name}' is resolved by the flow graph."
                )
            if field_name in primitive_types:
                _ensure_crewai_field(kind, field_name)
                kwargs[field_name] = _expect_type(kind, field_name, value, primitive_types[field_name])
                continue
            if field_name in llm_fields:
                _ensure_crewai_field(kind, field_name)
                llm = _llm_spec(kind, field_name, value, self._llm_resolver)
                if llm is not None:
                    kwargs[field_name] = llm
                continue
            _ensure_crewai_field(kind, field_name)
            raise ValueError(f"unsupported runtime converter for {kind} field '{field_name}'")
        return kwargs

    def task_output_model(self, payload: Mapping[str, object]) -> dict[str, type[BaseModel]]:
        output_type = payload.get("output_type")
        if output_type is None:
            return {}
        if output_type not in {"Output JSON", "Output Pydantic"}:
            raise ValueError(f"Invalid task payload field 'output_type': unsupported value '{output_type}'.")

        model = self._build_output_model(payload)
        if output_type == "Output JSON":
            return {"output_json": model}
        return {"output_pydantic": model}

    def _build_output_model(self, payload: Mapping[str, object]) -> type[BaseModel]:
        schema_fields = payload.get("output_schema_fields")
        if not isinstance(schema_fields, list) or not schema_fields:
            raise ValueError("Structured task output requires non-empty output_schema_fields.")

        pydantic_fields: dict[str, tuple[Any, Any]] = {}
        seen_field_names: set[str] = set()
        for field in schema_fields:
            if not isinstance(field, Mapping):
                raise ValueError("Structured task output fields must be objects.")

            name = field.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Structured task output fields require a non-empty name.")
            field_name = name.strip()
            if field_name in seen_field_names:
                raise ValueError(f"Structured task output contains duplicate field '{field_name}'.")
            seen_field_names.add(field_name)

            type_name = field.get("type")
            if not isinstance(type_name, str):
                raise ValueError(f"Structured task output field '{field_name}' requires a type.")
            python_type = _OUTPUT_FIELD_TYPES.get(type_name.strip().lower())
            if python_type is None:
                raise ValueError(
                    f"Structured task output field '{field_name}' has unsupported type '{type_name}'."
                )

            required = True if "required" not in field else bool(field.get("required"))
            field_type = python_type if required else python_type | None
            default = ... if required else None
            description = field.get("description")
            if isinstance(description, str) and description.strip():
                default = Field(default, description=description.strip())
            pydantic_fields[field_name] = (field_type, default)

        return create_model(self._output_model_name(payload), __base__=BaseModel, **pydantic_fields)

    def _output_model_name(self, payload: Mapping[str, object]) -> str:
        task_name = payload.get("task_name")
        name_part = ""
        if isinstance(task_name, str):
            name_part = re.sub(r"_+", "_", re.sub(r"[^0-9A-Za-z]+", "_", task_name)).strip("_")
        if not name_part:
            name_part = "TaskOutput"
        if name_part[0].isdigit():
            name_part = f"TaskOutput_{name_part}"

        version_id = payload.get("version_id")
        version_part = "00000000"
        if isinstance(version_id, str) and version_id:
            version_part = re.sub(r"[^0-9A-Za-z]+", "", version_id[:8]) or "00000000"
        return f"{name_part}_{version_part}"
