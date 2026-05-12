from __future__ import annotations

from typing import Any

from api.runtime.transfer_transforms import TransferTransformError, resolve_transform_mapping


class UnsupportedGraphError(ValueError):
    pass


VALID_HITL_OUTCOMES = {"approved", "needs_revision", "rejected"}
SUPPORTED_LINEAR_NODE_TYPES = {"crew", "hitl", "execution_action", "output"}


def _graph(snapshot: dict[str, Any]) -> dict[str, Any]:
    graph = snapshot.get("graph")
    if not isinstance(graph, dict):
        raise UnsupportedGraphError("Flow runtime snapshot is missing graph.")
    return graph


def _nodes_by_id(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = _graph(snapshot).get("nodes")
    if not isinstance(nodes, list):
        raise UnsupportedGraphError("Flow runtime graph nodes must be a list.")
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise UnsupportedGraphError("Flow runtime graph contains a non-object node.")
        node_id = str(node.get("id") or "")
        if not node_id:
            raise UnsupportedGraphError("Flow runtime graph contains a node without id.")
        if node_id in result:
            raise UnsupportedGraphError(f"Flow runtime graph contains duplicate node id: {node_id}")
        result[node_id] = node
    return result


def _flow_edges(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    edges = _graph(snapshot).get("edges")
    if not isinstance(edges, list):
        raise UnsupportedGraphError("Flow runtime graph edges must be a list.")
    return [edge for edge in edges if isinstance(edge, dict) and edge.get("type") == "flow"]


def build_linear_path(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    nodes_by_id = _nodes_by_id(snapshot)
    start_nodes = [node for node in nodes_by_id.values() if node.get("type") == "start"]
    if len(start_nodes) != 1:
        raise UnsupportedGraphError("Flow runtime graph must contain exactly one start node.")

    outgoing: dict[str, list[str]] = {}
    incoming: dict[str, list[str]] = {}
    for edge in _flow_edges(snapshot):
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in nodes_by_id or target not in nodes_by_id:
            raise UnsupportedGraphError(f"Flow runtime graph edge references missing node: {edge.get('id')}")
        outgoing.setdefault(source, []).append(target)
        incoming.setdefault(target, []).append(source)

    current_id = str(start_nodes[0]["id"])
    path: list[dict[str, Any]] = []
    visited = {current_id}
    while True:
        next_ids = outgoing.get(current_id, [])
        if len(next_ids) > 1:
            raise UnsupportedGraphError(f"Flow runtime graph has multiple outgoing edges from {current_id}.")
        if not next_ids:
            break
        next_id = next_ids[0]
        if next_id in visited:
            raise UnsupportedGraphError(f"Flow runtime graph contains an unsupported cycle at {next_id}.")
        visited.add(next_id)
        node = nodes_by_id[next_id]
        node_type = node.get("type")
        current_node = nodes_by_id[current_id]
        if current_node.get("type") == "hitl" and node_type not in {"crew", "execution_action", "output"}:
            raise UnsupportedGraphError(f"HITL node {current_node.get('id')} must be followed by Crew or Output.")
        if node_type == "router":
            raise UnsupportedGraphError("Flow runtime graph contains router nodes, which are not supported in P0.")
        if node_type == "input":
            raise UnsupportedGraphError("Input nodes are not executable after start.")
        if node_type not in SUPPORTED_LINEAR_NODE_TYPES:
            kind = node_type if node_type else "<missing>"
            raise UnsupportedGraphError(
                f"Unsupported flow runtime node type: {kind} at node {node.get('id')}."
            )
        path.append(node)
        current_id = next_id

    output_nodes = [node for node in path if node.get("type") == "output"]
    if len(output_nodes) != 1:
        raise UnsupportedGraphError("Flow runtime graph must contain exactly one output node on the linear path.")
    output_index = path.index(output_nodes[0])
    if output_index != len(path) - 1:
        raise UnsupportedGraphError("Flow runtime output node must terminate the linear path.")
    for index, node in enumerate(path):
        if node.get("type") != "hitl":
            continue
        previous_node = path[index - 1] if index > 0 else None
        if previous_node is None or previous_node.get("type") != "crew":
            raise UnsupportedGraphError(f"HITL node {node.get('id')} must follow a Crew node.")
        next_node = path[index + 1] if index + 1 < len(path) else None
        if next_node is None or next_node.get("type") not in {"crew", "execution_action", "output"}:
            raise UnsupportedGraphError(f"HITL node {node.get('id')} must be followed by Crew or Output.")
    for node_id, sources in incoming.items():
        if node_id in nodes_by_id and nodes_by_id[node_id].get("type") != "input" and len(sources) > 1:
            raise UnsupportedGraphError(f"Flow runtime graph has multiple incoming edges to {node_id}.")
    return path


def read_path(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    current = payload
    for segment in [part for part in path.split(".") if part]:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        return None
    return current


def build_crew_inputs(
    *,
    snapshot: dict[str, Any],
    crew_node_id: str,
    state: dict[str, Any],
    node_outputs: dict[str, Any],
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mappings = snapshot.get("crew_input_mappings", {}).get(crew_node_id, {})
    if not isinstance(mappings, dict):
        return dict(runtime_context or {})

    inputs: dict[str, Any] = {}
    for input_name, mapping in mappings.items():
        if not isinstance(mapping, dict):
            continue
        source = mapping.get("source")
        if source == "literal":
            inputs[str(input_name)] = mapping.get("value")
        elif source == "state":
            inputs[str(input_name)] = read_path(state, mapping.get("path"))
        elif source == "node":
            node_id = str(mapping.get("nodeId") or "")
            inputs[str(input_name)] = read_path({"output": node_outputs.get(node_id)}, mapping.get("path"))
        elif source == "transform":
            try:
                inputs[str(input_name)] = resolve_transform_mapping(
                    target_node_id=crew_node_id,
                    target_input=str(input_name),
                    mapping=mapping,
                    node_outputs=node_outputs,
                )
            except TransferTransformError as exc:
                raise ValueError(str(exc)) from exc
    if runtime_context:
        inputs.update(runtime_context)
    return inputs


def crew_runtime_snapshot_for_node(snapshot: dict[str, Any], crew_node: dict[str, Any]) -> dict[str, Any]:
    node_data = crew_node.get("data")
    if not isinstance(node_data, dict):
        raise UnsupportedGraphError(f"Crew node {crew_node.get('id')} is missing versionId.")
    version_id = str(node_data.get("versionId") or "")
    if not version_id:
        raise UnsupportedGraphError(f"Crew node {crew_node.get('id')} is missing versionId.")
    graph = snapshot.get("graph")
    if not isinstance(graph, dict):
        raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
    entities = graph.get("entities")
    if not isinstance(entities, dict):
        raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
    crews = entities.get("crews")
    if not isinstance(crews, dict):
        raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
    entity = crews.get(version_id)
    if not isinstance(entity, dict):
        raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
    runtime_snapshot = entity.get("runtime_snapshot_json")
    if not isinstance(runtime_snapshot, dict) or not runtime_snapshot:
        raise UnsupportedGraphError(f"Crew runtime snapshot missing for version {version_id}.")
    return runtime_snapshot


def normalize_crew_output(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    normalized: dict[str, Any] = {}
    tasks_output = getattr(result, "tasks_output", None)
    if isinstance(tasks_output, list):
        for task_output in tasks_output:
            normalized.update(_structured_output_dict(task_output))
    raw = getattr(result, "raw", None)
    normalized.update(_structured_output_dict(result))
    if normalized:
        if raw is not None and "raw" not in normalized:
            normalized["raw"] = raw
        return normalized
    if raw is not None:
        return {"raw": raw}
    return {"raw": str(result)}


def _structured_output_dict(result: Any) -> dict[str, Any]:
    json_dict = getattr(result, "json_dict", None)
    if isinstance(json_dict, dict):
        return dict(json_dict)
    pydantic_output = getattr(result, "pydantic", None)
    if pydantic_output is not None and hasattr(pydantic_output, "model_dump"):
        dumped = pydantic_output.model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {}


def build_output_payload(
    *,
    snapshot: dict[str, Any],
    state: dict[str, Any],
    node_outputs: dict[str, Any],
) -> dict[str, Any]:
    fields = snapshot.get("output_fields")
    if not isinstance(fields, list):
        return {}

    output: dict[str, Any] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        label = str(field.get("label") or field.get("path") or "output")
        source = field.get("source")
        if source == "literal":
            output[label] = field.get("value")
        elif source == "state":
            output[label] = read_path(state, field.get("path"))
        elif source == "node":
            node_id = str(field.get("nodeId") or "")
            output[label] = read_path({"output": node_outputs.get(node_id)}, field.get("path"))
    return output
