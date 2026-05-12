from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from api.runtime.credential_resolver import collect_required_credential_providers
from api.runtime.crewai_factory import CrewAIFactory as _RuntimeCrewAIFactory
from api.runtime.linear_flow_runtime import build_crew_inputs, build_linear_path, normalize_crew_output
from api.runtime.llm_config import normalize_llm_config
from api.runtime.run_telemetry import redact_secret_text
from api.runtime.tool_loader import load_tool_class
from api.runtime.tool_metadata import require_allowlisted_tool_module, validate_tool_config
from api.services.llm_catalog import CatalogModel

CrewAIFactory = _RuntimeCrewAIFactory


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _crew_snapshot_for_node(snapshot: Mapping[str, Any], node_id: str) -> Mapping[str, Any]:
    crew_snapshots = snapshot.get("crew_snapshots")
    if isinstance(crew_snapshots, Mapping):
        crew_snapshot = crew_snapshots.get(node_id)
        if isinstance(crew_snapshot, Mapping):
            return crew_snapshot
    crew_refs = snapshot.get("crew_refs")
    if isinstance(crew_refs, list):
        for ref in crew_refs:
            if not isinstance(ref, Mapping) or ref.get("node_id") != node_id:
                continue
            crew_snapshot = ref.get("runtime_snapshot_json") or ref.get("runtime_snapshot")
            if isinstance(crew_snapshot, Mapping):
                return crew_snapshot
    raise ValueError(f"Flow diagnostic cannot resolve Crew snapshot for node {node_id}.")


def _redact_diagnostic_error(error: Exception, redaction_values: set[str] | None) -> str:
    return redact_secret_text(str(error), extra_values=tuple(redaction_values or ()))


def _string_set(value: object) -> set[str]:
    if isinstance(value, str) and value.strip():
        return {value.strip()}
    if isinstance(value, list):
        return {item.strip() for item in value if isinstance(item, str) and item.strip()}
    return set()


def _reachable_agent_ids(crew_snapshot: Mapping[str, Any]) -> list[str]:
    runtime_crew = _mapping(crew_snapshot.get("runtime_crew"))
    agent_ids = _string_set(runtime_crew.get("agent_version_ids"))
    manager_agent_id = runtime_crew.get("manager_agent_version_id")
    if isinstance(manager_agent_id, str) and manager_agent_id.strip():
        agent_ids.add(manager_agent_id.strip())
    task_ids = _string_set(runtime_crew.get("task_version_ids"))
    task_agent_links = _mapping(crew_snapshot.get("task_agent_links"))
    for task_id in task_ids:
        agent_id = task_agent_links.get(task_id)
        if isinstance(agent_id, str) and agent_id.strip():
            agent_ids.add(agent_id.strip())
    return sorted(agent_ids)


def _reachable_tool_keys(crew_snapshot: Mapping[str, Any]) -> set[str]:
    runtime_crew = _mapping(crew_snapshot.get("runtime_crew"))
    agent_ids = set(_reachable_agent_ids(crew_snapshot))
    task_ids = _string_set(runtime_crew.get("task_version_ids"))
    agent_tool_links = _mapping(crew_snapshot.get("agent_tool_links") or crew_snapshot.get("tool_links"))
    task_tool_links = _mapping(crew_snapshot.get("task_tool_links"))
    tool_keys: set[str] = set()
    for agent_id in agent_ids:
        tool_keys.update(_string_set(agent_tool_links.get(agent_id)))
    for task_id in task_ids:
        tool_keys.update(_string_set(task_tool_links.get(task_id)))
    return tool_keys


def _runtime_context_credential_providers_for_crew(crew_snapshot: Mapping[str, Any]) -> set[str]:
    providers: set[str] = set()
    runtime_tools = _mapping(crew_snapshot.get("runtime_tools"))
    for tool_key in _reachable_tool_keys(crew_snapshot):
        tool_payload = runtime_tools.get(tool_key)
        if not isinstance(tool_payload, Mapping):
            continue
        for requirement in _as_list(tool_payload.get("credential_requirements")):
            if not isinstance(requirement, Mapping):
                continue
            if requirement.get("required") is not True:
                continue
            if requirement.get("injection") != "runtime_context":
                continue
            provider = requirement.get("provider")
            if isinstance(provider, str) and provider.strip():
                providers.add(provider.strip())
    return providers


def _llm_diagnostics_for_crew(
    *,
    node_id: str,
    crew_snapshot: Mapping[str, Any],
    llm_catalog: Mapping[str, CatalogModel] | None,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    runtime_agents = _mapping(crew_snapshot.get("runtime_agents"))
    for agent_id in _reachable_agent_ids(crew_snapshot):
        agent = runtime_agents.get(agent_id)
        if not isinstance(agent, Mapping):
            continue
        primary_payload = agent.get("llm") or agent.get("llm_config_json")
        normalized = normalize_llm_config(primary_payload, llm_catalog=llm_catalog)
        dropped_parameters = [
            issue.parameter
            for issue in normalized.issues
            if issue.parameter is not None and issue.code.endswith("_dropped")
        ]
        diagnostics.append(
            {
                "node_id": node_id,
                "agent_version_id": agent_id,
                "effective_llm": {
                    "source": "default" if normalized.source == "default" else "explicit",
                    "provider": normalized.provider,
                    "model": normalized.model,
                },
                "dropped_parameters": dropped_parameters,
                "pricing_available": isinstance(normalized.metadata.get("pricing"), Mapping),
            }
        )
    return diagnostics


def run_compatibility_diagnostics(
    *,
    snapshot: Mapping[str, Any],
    inputs: Mapping[str, Any],
    redaction_values: set[str] | None = None,
    llm_catalog: Mapping[str, CatalogModel] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "inputs": dict(inputs),
        "state": dict(inputs),
        "node_outputs": {},
        "node_output_refs": {},
        "node_output_versions": {},
        "transfer_values": {},
        "human_feedback": {},
        "human_feedback_history": [],
        "run_options": {"capture_agent_execution_logs": False},
    }
    result: dict[str, Any] = {
        "mode": "compatibility",
        "status": "passed",
        "provider_calls": "blocked",
        "required_credentials": [],
        "llm_diagnostics": [],
        "crews": [],
    }
    required_credentials: set[str] = set()

    try:
        path = build_linear_path(dict(snapshot))
    except Exception as exc:
        return {
            **result,
            "status": "failed",
            "error": _redact_diagnostic_error(exc, redaction_values),
        }

    for node in path:
        if node.get("type") != "crew":
            continue
        node_id = str(node.get("id"))
        crew_result: dict[str, Any] = {
            "node_id": node_id,
            "build_crew": "pending",
            "kickoff": "pending",
            "llm_call": "pending",
        }
        try:
            crew_snapshot = _crew_snapshot_for_node(snapshot, node_id)
            result["llm_diagnostics"].extend(
                _llm_diagnostics_for_crew(
                    node_id=node_id,
                    crew_snapshot=crew_snapshot,
                    llm_catalog=llm_catalog,
                )
            )
            required_credentials.update(
                collect_required_credential_providers(
                    crew_snapshot=crew_snapshot,
                    llm_catalog=llm_catalog,
                )
            )
            required_credentials.update(_runtime_context_credential_providers_for_crew(crew_snapshot))
            crew_inputs = build_crew_inputs(
                snapshot=dict(snapshot),
                crew_node_id=node_id,
                state=state["state"],
                node_outputs=state["node_outputs"],
            )
            factory_cls = CrewAIFactory
            crew_factory = factory_cls(execution_mode="validation", llm_catalog=llm_catalog)
            restore_factory = factory_cls is not _RuntimeCrewAIFactory
            if restore_factory:
                globals()["CrewAIFactory"] = _RuntimeCrewAIFactory
            try:
                crew = crew_factory.build_crew(
                    runtime_crew=_mapping(crew_snapshot.get("runtime_crew")),
                    runtime_agents=_mapping(crew_snapshot.get("runtime_agents")),
                    runtime_tasks=_mapping(crew_snapshot.get("runtime_tasks")),
                    task_agent_links=_mapping(crew_snapshot.get("task_agent_links")),
                    agent_tool_links=_mapping(
                        crew_snapshot.get("agent_tool_links") or crew_snapshot.get("tool_links")
                    ),
                    task_tool_links=_mapping(crew_snapshot.get("task_tool_links")),
                    runtime_tools=_mapping(crew_snapshot.get("runtime_tools")),
                    instrumentation_callbacks={},
                )
            finally:
                if restore_factory:
                    globals()["CrewAIFactory"] = factory_cls
            crew_result["build_crew"] = "passed"
            output = normalize_crew_output(crew.kickoff(inputs=crew_inputs))
            crew_result["kickoff"] = "passed"
            crew_result["llm_call"] = "passed"
            crew_result["output_preview"] = output
            state["node_outputs"][node_id] = output
        except Exception as exc:
            crew_result["error"] = _redact_diagnostic_error(exc, redaction_values)
            if crew_result["build_crew"] == "pending":
                crew_result["build_crew"] = "failed"
            elif crew_result["kickoff"] == "pending":
                crew_result["kickoff"] = "failed"
            if crew_result["llm_call"] == "pending":
                crew_result["llm_call"] = "failed"
            result["status"] = "failed"
        result["crews"].append(crew_result)

    result["required_credentials"] = sorted(required_credentials)
    return result


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _tool_config_for_version(tool_payload: Mapping[str, Any], version_id: str) -> dict[str, Any]:
    attachments = tool_payload.get("attachments")
    if isinstance(attachments, list):
        for attachment in attachments:
            if not isinstance(attachment, Mapping):
                continue
            if attachment.get("version_id") == version_id and isinstance(attachment.get("tool_config_json"), Mapping):
                return dict(attachment["tool_config_json"])
    default_config = tool_payload.get("default_config_json")
    return dict(default_config) if isinstance(default_config, Mapping) else {}


def _resolve_json_schema_ref(schema: Mapping[str, Any], root_schema: Mapping[str, Any]) -> Mapping[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return schema
    value: object = root_schema
    for part in ref.removeprefix("#/").split("/"):
        if not isinstance(value, Mapping):
            return schema
        value = value.get(part)
    return value if isinstance(value, Mapping) else schema


def _sample_for_json_schema(schema: Mapping[str, Any], root_schema: Mapping[str, Any] | None = None) -> object:
    root_schema = root_schema or schema
    schema = _resolve_json_schema_ref(schema, root_schema)
    if "const" in schema:
        return schema["const"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return next((item for item in enum if item is not None), enum[0])
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), schema_type[0] if schema_type else None)
    if schema_type == "integer":
        minimum = schema.get("minimum")
        if isinstance(minimum, int):
            return minimum
        if isinstance(minimum, float):
            return int(minimum) if minimum.is_integer() else int(minimum) + 1
        return 1
    if schema_type == "number":
        minimum = schema.get("minimum")
        return float(minimum) if isinstance(minimum, (int, float)) else 1.0
    if schema_type == "boolean":
        return False
    if schema_type == "array":
        min_items = schema.get("minItems")
        count = min_items if isinstance(min_items, int) and min_items > 0 else 0
        if count == 0:
            return []
        items = schema.get("items")
        item_sample = _sample_for_json_schema(items, root_schema) if isinstance(items, Mapping) else "runtime-validation"
        return [item_sample for _ in range(count)]
    if schema_type == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            return {}
        return {
            field_name: _sample_for_json_schema(field_schema, root_schema)
            for field_name, field_schema in properties.items()
            if field_name in required and isinstance(field_schema, Mapping)
        }
    if schema_type == "string":
        value = "runtime-validation"
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and min_length > len(value):
            value = value + ("x" * (min_length - len(value)))
        return value
    return "runtime-validation"


def _sample_input_for_args_schema(args_schema: object) -> dict[str, object]:
    if not isinstance(args_schema, type) or not issubclass(args_schema, BaseModel):
        return {}
    json_schema = args_schema.model_json_schema()
    properties = json_schema.get("properties")
    required = json_schema.get("required")
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        return {}
    sample = {
        field_name: _sample_for_json_schema(field_schema, json_schema)
        for field_name, field_schema in properties.items()
        if field_name in required and isinstance(field_schema, Mapping)
    }
    args_schema.model_validate(sample)
    return dict(sorted(sample.items()))


def _class_args_schema(tool_class: type) -> object:
    args_schema = getattr(tool_class, "args_schema", None)
    if args_schema is not None:
        return args_schema
    model_fields = getattr(tool_class, "model_fields", None)
    if not isinstance(model_fields, Mapping):
        return None
    field = model_fields.get("args_schema")
    return getattr(field, "default", None)


def _sensitive_config_values(value: object) -> set[str]:
    if isinstance(value, str) and len(value) >= 4:
        return {value}
    if isinstance(value, Mapping):
        values: set[str] = set()
        for item in value.values():
            values.update(_sensitive_config_values(item))
        return values
    if isinstance(value, list):
        values: set[str] = set()
        for item in value:
            values.update(_sensitive_config_values(item))
        return values
    return set()


def _linked_tools_for_owner(tool_links: object, owner_id: str) -> list[str]:
    if not isinstance(tool_links, Mapping):
        return []
    value = tool_links.get(owner_id)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _credential_requirement_results(requirements: object, live_provider_set: set[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for requirement in _as_list(requirements):
        if not isinstance(requirement, Mapping):
            continue
        provider = requirement.get("provider")
        results.append(
            {
                "provider": provider,
                "env_var": requirement.get("env_var"),
                "required": requirement.get("required") is True,
                "available_for_live_run": isinstance(provider, str) and provider in live_provider_set,
            }
        )
    return results


def _dedupe_owner_pairs(owner_pairs: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[tuple[str, str, str]] = []
    for owner_pair in owner_pairs:
        if owner_pair in seen:
            continue
        seen.add(owner_pair)
        deduped.append(owner_pair)
    return deduped


def run_tool_mock_call_check(
    *,
    snapshot: Mapping[str, Any],
    live_credential_providers: list[str],
    redaction_values: set[str] | None = None,
) -> dict[str, Any]:
    live_provider_set = set(live_credential_providers)
    results: list[dict[str, Any]] = []
    overall_status = "passed"
    crew_snapshots = snapshot.get("crew_snapshots")
    if not isinstance(crew_snapshots, Mapping):
        return {"mode": "tool_mock_call", "status": "passed", "tools": []}

    for node_id, crew_snapshot in crew_snapshots.items():
        if not isinstance(crew_snapshot, Mapping):
            continue
        runtime_crew = _mapping(crew_snapshot.get("runtime_crew"))
        runtime_tools = _mapping(crew_snapshot.get("runtime_tools"))
        agent_tool_links = _mapping(crew_snapshot.get("agent_tool_links") or crew_snapshot.get("tool_links"))
        task_tool_links = _mapping(crew_snapshot.get("task_tool_links"))
        owner_pairs: list[tuple[str, str, str]] = []
        manager_agent_id = runtime_crew.get("manager_agent_version_id")
        if isinstance(manager_agent_id, str) and manager_agent_id.strip():
            owner_pairs.extend(
                ("agent", manager_agent_id.strip(), tool_key)
                for tool_key in _linked_tools_for_owner(agent_tool_links, manager_agent_id.strip())
            )
        for agent_id in _as_list(runtime_crew.get("agent_version_ids")):
            if isinstance(agent_id, str):
                owner_pairs.extend(("agent", agent_id, tool_key) for tool_key in _linked_tools_for_owner(agent_tool_links, agent_id))
        for task_id in _as_list(runtime_crew.get("task_version_ids")):
            if isinstance(task_id, str):
                owner_pairs.extend(("task", task_id, tool_key) for tool_key in _linked_tools_for_owner(task_tool_links, task_id))

        for owner_type, owner_version_id, tool_key in _dedupe_owner_pairs(owner_pairs):
            tool_result: dict[str, Any] = {
                "node_id": node_id,
                "tool_key": tool_key,
                "owner_type": owner_type,
                "owner_version_id": owner_version_id,
                "status": "passed",
                "checks": {
                    "metadata": "pending",
                    "allowlist": "pending",
                    "import": "pending",
                    "config": "pending",
                    "instantiate": "pending",
                    "args_schema": "pending",
                },
                "sample_input": {},
                "credential_requirements": [],
                "external_call": "not_called",
            }
            tool_redaction_values = set(redaction_values or ())
            try:
                tool_payload = runtime_tools.get(tool_key)
                if not isinstance(tool_payload, Mapping):
                    raise ValueError(f"Tool {tool_key} is missing runtime metadata.")
                tool_result["credential_requirements"] = _credential_requirement_results(
                    tool_payload.get("credential_requirements"),
                    live_provider_set,
                )
                module_path = tool_payload.get("module_path")
                class_name = tool_payload.get("class_name")
                if not isinstance(module_path, str) or not module_path.strip():
                    raise ValueError(f"Tool {tool_key} is missing module_path.")
                if not isinstance(class_name, str) or not class_name.strip():
                    raise ValueError(f"Tool {tool_key} is missing class_name.")
                tool_result["checks"]["metadata"] = "passed"
                require_allowlisted_tool_module(module_path.strip())
                tool_result["checks"]["allowlist"] = "passed"
                tool_class = load_tool_class(module_path.strip(), class_name.strip())
                tool_result["checks"]["import"] = "passed"
                config = _tool_config_for_version(tool_payload, owner_version_id)
                validate_tool_config(
                    tool_key=tool_key,
                    version_id=owner_version_id,
                    config=config,
                    config_schema_json=tool_payload.get("config_schema_json"),
                )
                tool_result["checks"]["config"] = "passed"
                tool_redaction_values.update(_sensitive_config_values(config))
                args_schema = _class_args_schema(tool_class)
                tool_result["sample_input"] = _sample_input_for_args_schema(args_schema)
                tool_result["checks"]["args_schema"] = "passed"
                tool = tool_class(**config)
                tool_result["checks"]["instantiate"] = "passed"
                if not tool_result["sample_input"]:
                    tool_result["sample_input"] = _sample_input_for_args_schema(getattr(tool, "args_schema", None))
            except Exception as exc:
                tool_result["status"] = "failed"
                tool_result["error"] = _redact_diagnostic_error(exc, tool_redaction_values)
                overall_status = "failed"
                for check_name, check_status in list(tool_result["checks"].items()):
                    if check_status == "pending":
                        tool_result["checks"][check_name] = "failed"
                        break
            results.append(tool_result)

    return {"mode": "tool_mock_call", "status": overall_status, "tools": results}
