from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from copy import deepcopy
from typing import Any, Literal, TypedDict

from api.runtime.hitl_policy import RESERVED_CREW_INPUTS, normalize_hitl_contract
from api.schemas.flow_graph import FlowGraphDocument, FlowGraphNode, FlowInputMapping


CrewReferenceStatus = Literal["latest", "new_version_available"]


class PublishedCrewLookupResult(TypedDict):
    asset_id: str
    version_id: str
    latest_version_id: str
    runtime_snapshot_json: dict[str, Any]


PublishedCrewLookup = Callable[..., PublishedCrewLookupResult | None]


IMPLICIT_TOPIC_FIELD = {
    "type": "string",
    "description": "Runtime keyword supplied from the Run page.",
}
SYSTEM_RESERVED_INPUTS = {"topic"}
PROMPT_INPUT_TYPES = {"text", "structured", "raw"}
FILE_INPUT_TYPES = {"image", "pdf", "text_file", "csv", "json_file", "docx", "audio", "video"}
SUPPORTED_TRANSFORMS = {"identity_v1", "join_text_v1", "join_card_news_slides_v1", "json_stringify_v1"}
SUPPORTED_OVERFLOW_POLICIES = {"fail", "truncate"}


class FlowGraphLoader:
    @staticmethod
    def crew_reference_status(current_version_id: str, latest_version_id: str) -> CrewReferenceStatus:
        return "latest" if str(current_version_id) == str(latest_version_id) else "new_version_available"

    def validate(self, graph: dict[str, Any], *, published_crew_lookup: PublishedCrewLookup) -> dict[str, Any]:
        if not self._is_canvas_first_graph(graph):
            return self._validate_legacy_graph(graph, published_crew_lookup=published_crew_lookup)

        graph = self._normalize_hitl_node_data_for_validation(graph)
        document = FlowGraphDocument.model_validate(graph)
        node_by_id = {node.id: node for node in document.nodes}
        if len(node_by_id) != len(document.nodes):
            raise ValueError("Flow graph is invalid: node ids must be unique.")

        input_nodes = [node for node in document.nodes if node.type == "input"]
        start_nodes = [node for node in document.nodes if node.type == "start"]
        output_nodes = [node for node in document.nodes if node.type == "output"]
        crew_nodes = [node for node in document.nodes if node.type == "crew"]
        execution_action_nodes = [node for node in document.nodes if node.type == "execution_action"]
        router_nodes = [node for node in document.nodes if node.type == "router"]
        hitl_nodes = [node for node in document.nodes if node.type == "hitl"]

        if len(start_nodes) != 1:
            raise ValueError("Flow graph is invalid: exactly one Start node is required.")
        if not crew_nodes and not execution_action_nodes:
            raise ValueError("Flow graph is invalid: at least one Crew or Execution Action node is required.")
        if not output_nodes:
            raise ValueError("Flow graph is invalid: at least one Output node is required.")

        edge_ids = {edge.id for edge in document.edges}
        if len(edge_ids) != len(document.edges):
            raise ValueError("Flow graph is invalid: edge ids must be unique.")
        for edge in document.edges:
            if edge.source not in node_by_id or edge.target not in node_by_id:
                raise ValueError(f"Flow graph is invalid: edge references missing node: {edge.id}")
            if edge.type == "tool_reference":
                if node_by_id[edge.source].type != "crew" or node_by_id[edge.target].type != "tool":
                    raise ValueError("Flow graph is invalid: tool_reference edges must connect Crew -> Tool.")
                continue
            if edge.type == "route" and node_by_id[edge.source].type != "router":
                raise ValueError("Flow graph is invalid: route edges must start from Router nodes.")
            if (
                edge.type != "tool_reference"
                and (node_by_id[edge.source].type == "tool" or node_by_id[edge.target].type == "tool")
            ):
                raise ValueError(
                    "Flow graph is invalid: Tool nodes are visual-only and cannot be on the execution path."
                )

        reachable_node_ids = self._reachable_from_start(start_nodes[0].id, document.edges)
        active_crew_nodes = [node for node in crew_nodes if node.id in reachable_node_ids]
        active_execution_action_nodes = [node for node in execution_action_nodes if node.id in reachable_node_ids]
        active_router_nodes = [node for node in router_nodes if node.id in reachable_node_ids]
        active_hitl_nodes = [node for node in hitl_nodes if node.id in reachable_node_ids]
        active_output_nodes = [node for node in output_nodes if node.id in reachable_node_ids]

        if not active_crew_nodes and not active_execution_action_nodes:
            raise ValueError(
                "Flow graph is invalid: at least one Crew or Execution Action node must be reachable from Start."
            )
        if not active_output_nodes:
            raise ValueError("Flow graph is invalid: at least one Output node must be reachable from Start.")

        self._validate_active_hitl_path(graph=document, reachable_node_ids=reachable_node_ids)
        state_schema = self._build_state_schema(input_nodes)
        state_field_names = set(state_schema.get("properties", {}))
        crew_refs, crew_snapshots = self._resolve_crew_refs(active_crew_nodes, published_crew_lookup)
        hitl_contracts = self._validate_hitl_nodes(active_hitl_nodes)
        crew_input_mappings = self._validate_crew_input_mappings(
            active_crew_nodes,
            crew_snapshots,
            state_field_names,
            document.edges,
        )
        self._validate_execution_action_nodes(
            active_execution_action_nodes,
            crew_snapshots,
            {node.id for node in active_execution_action_nodes},
            state_field_names,
            document.edges,
        )
        router_conditions = self._validate_router_conditions(active_router_nodes, crew_snapshots)
        output_fields = self._validate_output_nodes(
            active_output_nodes,
            crew_snapshots,
            {node.id for node in active_execution_action_nodes},
        )
        runtime_graph = document.model_dump(mode="json")
        self._apply_normalized_hitl_node_data(runtime_graph, hitl_contracts)

        return {
            "schemaVersion": 1,
            "graph": runtime_graph,
            "state_schema": state_schema,
            "crew_refs": crew_refs,
            "crew_input_mappings": crew_input_mappings,
            "router_conditions": router_conditions,
            "hitl_contracts": hitl_contracts,
            "output_fields": output_fields,
        }

    def _is_canvas_first_graph(self, graph: dict[str, Any]) -> bool:
        if graph.get("schemaVersion") != 1:
            return False

        nodes = graph.get("nodes")
        if not isinstance(nodes, list):
            return False
        if not nodes:
            return True

        return not all(isinstance(node, dict) and "node_type" in node for node in nodes)

    def _normalize_hitl_node_data_for_validation(self, graph: dict[str, Any]) -> dict[str, Any]:
        normalized_graph = deepcopy(graph)
        nodes = normalized_graph.get("nodes")
        if not isinstance(nodes, list):
            return normalized_graph

        for node in nodes:
            if not isinstance(node, dict) or node.get("type") != "hitl":
                continue
            data = node.get("data")
            node["data"] = normalize_hitl_contract(str(node.get("id") or ""), data if isinstance(data, dict) else {})
        return normalized_graph

    def _apply_normalized_hitl_node_data(
        self,
        graph: dict[str, Any],
        hitl_contracts: dict[str, dict[str, Any]],
    ) -> None:
        nodes = graph.get("nodes")
        if not isinstance(nodes, list):
            return

        for node in nodes:
            if not isinstance(node, dict) or node.get("type") != "hitl":
                continue
            contract = hitl_contracts.get(str(node.get("id") or ""))
            if contract is not None:
                node["data"] = contract

    def _validate_legacy_graph(
        self,
        graph: dict[str, Any],
        *,
        published_crew_lookup: PublishedCrewLookup,
    ) -> dict[str, Any]:
        nodes = graph.get("nodes")
        if not isinstance(nodes, list):
            raise ValueError("Flow graph is invalid: nodes must be a list.")

        crew_refs: list[dict[str, Any]] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("node_type") != "crew":
                continue

            node_id = node.get("id")
            ref = node.get("ref")
            if ref is None:
                ref = {}
            if not isinstance(ref, dict):
                raise ValueError(
                    "Flow graph is invalid: crew node ref must be an object: "
                    f"{node_id}"
                )
            asset_id = ref.get("asset_id")
            version_id = ref.get("version_id")

            if not isinstance(asset_id, str) or not asset_id.strip() or not isinstance(version_id, str) or not version_id.strip():
                raise ValueError(
                    "Flow graph is invalid: crew node is missing a pinned asset_id and version_id: "
                    f"{node_id}"
                )

            lookup = published_crew_lookup(asset_id=asset_id, version_id=version_id)
            if lookup is None:
                raise ValueError(
                    "Flow graph is invalid: crew node references an unpublished crew version: "
                    f"{asset_id}:{version_id}"
                )

            runtime_snapshot_json = lookup.get("runtime_snapshot_json")
            if not isinstance(runtime_snapshot_json, dict) or not runtime_snapshot_json:
                raise ValueError(
                    "Flow graph is invalid: referenced crew version is missing runtime_snapshot_json: "
                    f"{asset_id}:{version_id}"
                )

            latest_version_id = lookup.get("latest_version_id") or version_id
            crew_refs.append(
                {
                    "node_id": node_id,
                    "asset_id": asset_id,
                    "version_id": version_id,
                    "latest_version_id": latest_version_id,
                    "status": self.crew_reference_status(version_id, latest_version_id),
                }
            )

        return {"graph": graph, "crew_refs": crew_refs}

    def _reachable_from_start(
        self,
        start_node_id: str,
        edges: list[Any],
    ) -> set[str]:
        outgoing: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.type not in {"flow", "route"}:
                continue
            outgoing[edge.source].append(edge.target)

        visited = {start_node_id}
        queue = deque([start_node_id])
        while queue:
            current = queue.popleft()
            for target in outgoing.get(current, []):
                if target in visited:
                    continue
                visited.add(target)
                queue.append(target)
        return visited

    def _build_state_schema(self, input_nodes: list[FlowGraphNode]) -> dict[str, Any]:
        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []
        for input_node in input_nodes:
            for field in input_node.data.fields or []:
                properties[field.name] = {"type": field.type}
                if field.description:
                    properties[field.name]["description"] = field.description
                if field.default is not None:
                    properties[field.name]["default"] = field.default
                if field.required:
                    required.append(field.name)
        if input_nodes and "topic" not in properties:
            properties["topic"] = dict(IMPLICIT_TOPIC_FIELD)
        return {"type": "object", "properties": properties, "required": sorted(set(required))}

    def _resolve_crew_refs(
        self,
        crew_nodes: list[FlowGraphNode],
        published_crew_lookup: PublishedCrewLookup,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        crew_refs: list[dict[str, Any]] = []
        crew_snapshots: dict[str, dict[str, Any]] = {}
        for node in crew_nodes:
            asset_id = node.data.assetId
            version_id = node.data.versionId
            if not asset_id or not version_id:
                raise ValueError(
                    "Flow graph is invalid: crew node is missing a pinned asset_id and version_id: "
                    f"{node.id}"
                )

            lookup = published_crew_lookup(asset_id=asset_id, version_id=version_id)
            if lookup is None:
                raise ValueError(
                    "Flow graph is invalid: crew node references an unpublished crew version: "
                    f"{asset_id}:{version_id}"
                )

            runtime_snapshot_json = lookup.get("runtime_snapshot_json")
            if not isinstance(runtime_snapshot_json, dict) or not runtime_snapshot_json:
                raise ValueError(
                    "Flow graph is invalid: referenced crew version is missing runtime_snapshot_json: "
                    f"{asset_id}:{version_id}"
                )

            latest_version_id = lookup.get("latest_version_id") or version_id
            crew_refs.append(
                {
                    "node_id": node.id,
                    "asset_id": asset_id,
                    "version_id": version_id,
                    "latest_version_id": latest_version_id,
                    "status": self.crew_reference_status(version_id, latest_version_id),
                }
            )
            crew_snapshots[node.id] = runtime_snapshot_json
        return crew_refs, crew_snapshots

    def _validate_crew_input_mappings(
        self,
        crew_nodes: list[FlowGraphNode],
        crew_snapshots: dict[str, dict[str, Any]],
        state_field_names: set[str],
        edges: list[Any],
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for node in crew_nodes:
            required_inputs = crew_snapshots.get(node.id, {}).get("required_inputs", [])
            if not isinstance(required_inputs, list):
                required_inputs = []

            mappings = dict(node.data.inputMappings)
            for input_name in mappings:
                if input_name in RESERVED_CREW_INPUTS:
                    raise ValueError(
                        f"Flow graph is invalid: Crew node {node.id} input mapping {input_name} is reserved."
                    )
            for input_name in required_inputs:
                normalized_name = str(input_name).strip()
                if not normalized_name:
                    continue
                if (
                    normalized_name not in mappings
                    and normalized_name in SYSTEM_RESERVED_INPUTS
                    and normalized_name in state_field_names
                ):
                    mappings[normalized_name] = FlowInputMapping(
                        source="state",
                        path=normalized_name,
                    )
                if normalized_name not in mappings and normalized_name in RESERVED_CREW_INPUTS:
                    continue
                if normalized_name not in mappings:
                    raise ValueError(
                        f"Flow graph is invalid: Crew node {node.id} is missing required input mapping: "
                        f"{normalized_name}"
                    )
            for input_name, mapping in mappings.items():
                self._validate_crew_input_mapping_source(
                    node.id,
                    input_name,
                    mapping,
                    crew_snapshots,
                    state_field_names,
                    edges,
                )
            result[node.id] = {
                key: value.model_dump(mode="json", exclude_none=True)
                for key, value in mappings.items()
            }
        return result

    def _validate_crew_input_mapping_source(
        self,
        node_id: str,
        input_name: str,
        mapping: Any,
        crew_snapshots: dict[str, dict[str, Any]],
        state_field_names: set[str],
        edges: list[Any],
    ) -> None:
        if mapping.source == "literal":
            return

        if mapping.source == "state":
            path = (mapping.path or "").strip()
            first_segment = self._first_path_segment(path)
            if not first_segment or first_segment not in state_field_names:
                raise ValueError(
                    f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                    f"references unknown state input field: {mapping.path}"
                )
            return

        if mapping.source == "transform":
            self._validate_transform_input_mapping(
                node_id,
                input_name,
                mapping,
                crew_snapshots,
                edges,
            )
            return

        source_node_id = mapping.nodeId
        if not source_node_id or source_node_id not in crew_snapshots:
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                f"references unknown node output source: {source_node_id}"
            )
        if not self._output_path_resolves(source_node_id, mapping.path, crew_snapshots):
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                f"references unknown node output field: {mapping.path}"
            )

    def _validate_execution_action_nodes(
        self,
        execution_action_nodes: list[FlowGraphNode],
        crew_snapshots: dict[str, dict[str, Any]],
        execution_action_node_ids: set[str],
        state_field_names: set[str],
        edges: list[Any],
    ) -> None:
        for node in execution_action_nodes:
            node_data = node.data.model_dump(mode="python")
            action_key = str(node_data.get("action_key") or node_data.get("actionKey") or "").strip()
            if not action_key:
                raise ValueError(f"Flow graph is invalid: Execution Action node {node.id} is missing action_key.")
            approval_mode = str(node_data.get("approval_mode") or node_data.get("approvalMode") or "never")
            if approval_mode not in {"never", "every_run"}:
                raise ValueError(
                    f"Flow graph is invalid: Execution Action node {node.id} has unsupported approval_mode."
                )
            input_bindings = node_data.get("input_bindings") or node_data.get("inputBindings") or {}
            if not isinstance(input_bindings, dict):
                raise ValueError(
                    f"Flow graph is invalid: Execution Action node {node.id} input_bindings must be an object."
                )
            for input_name, mapping in input_bindings.items():
                binding = mapping if isinstance(mapping, FlowInputMapping) else FlowInputMapping.model_validate(mapping)
                self._validate_execution_action_input_mapping_source(
                    node.id,
                    input_name,
                    binding,
                    crew_snapshots,
                    execution_action_node_ids,
                    state_field_names,
                    edges,
                )

    def _validate_execution_action_input_mapping_source(
        self,
        node_id: str,
        input_name: str,
        mapping: FlowInputMapping,
        crew_snapshots: dict[str, dict[str, Any]],
        execution_action_node_ids: set[str],
        state_field_names: set[str],
        edges: list[Any],
    ) -> None:
        if mapping.source == "literal":
            return

        if mapping.source == "state":
            path = (mapping.path or "").strip()
            first_segment = self._first_path_segment(path)
            if not first_segment or first_segment not in state_field_names:
                raise ValueError(
                    f"Flow graph is invalid: Execution Action node {node_id} input binding {input_name} "
                    f"references unknown state input field: {mapping.path}"
                )
            return

        if mapping.source == "transform":
            raise ValueError(
                f"Flow graph is invalid: Execution Action node {node_id} input binding {input_name} "
                "uses unsupported transform mapping."
            )

        source_node_id = mapping.nodeId
        if not source_node_id or (
            source_node_id not in crew_snapshots and source_node_id not in execution_action_node_ids
        ):
            raise ValueError(
                f"Flow graph is invalid: Execution Action node {node_id} input binding {input_name} "
                f"references unknown node output source: {source_node_id}"
            )
        if not self._node_reaches_target(source_node_id, node_id, edges):
            raise ValueError(
                f"Flow graph is invalid: Execution Action node {node_id} input binding {input_name} "
                f"references non-upstream node output source: {source_node_id}"
            )
        if source_node_id in crew_snapshots and not self._output_path_resolves(
            source_node_id,
            mapping.path,
            crew_snapshots,
        ):
            raise ValueError(
                f"Flow graph is invalid: Execution Action node {node_id} input binding {input_name} "
                f"references unknown node output field: {mapping.path}"
            )

    def _validate_transform_input_mapping(
        self,
        node_id: str,
        input_name: str,
        mapping: FlowInputMapping,
        crew_snapshots: dict[str, dict[str, Any]],
        edges: list[Any],
    ) -> None:
        input_type = mapping.inputType or "text"
        if input_type in FILE_INPUT_TYPES:
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                "file/media transfer requires AX artifact adapter support."
            )
        if input_type not in PROMPT_INPUT_TYPES:
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                f"uses unsupported transform input type: {input_type}"
            )
        mapping.inputType = input_type

        transform = mapping.transform or "identity_v1"
        if transform not in SUPPORTED_TRANSFORMS:
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                f"uses unsupported transform: {transform}"
            )
        mapping.transform = transform

        source_node_id = mapping.nodeId
        if not source_node_id or source_node_id not in crew_snapshots:
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                f"references unknown node output source: {source_node_id}"
            )
        if not self._node_reaches_target(source_node_id, node_id, edges):
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                f"references non-upstream node output source: {source_node_id}"
            )

        source_paths = mapping.paths if mapping.paths is not None else ([mapping.path] if mapping.path else [])
        normalized_paths = [path.strip() for path in source_paths if isinstance(path, str) and path.strip()]
        if not normalized_paths:
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                "must define at least one source path."
            )

        if mapping.paths is not None:
            mapping.paths = normalized_paths
        for path in normalized_paths:
            if not self._output_path_resolves(source_node_id, path, crew_snapshots):
                raise ValueError(
                    f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                    f"references unknown node output field: {path}"
                )

        if mapping.maxChars is not None and mapping.maxChars <= 0:
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                "maxChars must be greater than zero."
            )

        overflow = mapping.overflow or "fail"
        if overflow not in SUPPORTED_OVERFLOW_POLICIES:
            raise ValueError(
                f"Flow graph is invalid: Crew node {node_id} input mapping {input_name} "
                f"uses unsupported overflow policy: {overflow}"
            )
        mapping.overflow = overflow

    def _node_reaches_target(self, source_node_id: str, target_node_id: str, edges: list[Any]) -> bool:
        if source_node_id == target_node_id:
            return False

        outgoing: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.type not in {"flow", "route"}:
                continue
            outgoing[edge.source].append(edge.target)

        visited = {source_node_id}
        queue = deque([source_node_id])
        while queue:
            current = queue.popleft()
            for target in outgoing.get(current, []):
                if target == target_node_id:
                    return True
                if target in visited:
                    continue
                visited.add(target)
                queue.append(target)
        return False

    def _validate_router_conditions(
        self,
        router_nodes: list[FlowGraphNode],
        crew_snapshots: dict[str, dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for node in router_nodes:
            conditions = node.data.conditions
            if not conditions:
                raise ValueError(f"Flow graph is invalid: Router node {node.id} must define at least one condition.")

            dumped: list[dict[str, Any]] = []
            for condition in conditions:
                source_node_id = condition.source.nodeId
                field_path = condition.source.path.removeprefix("output.")
                output_schema = crew_snapshots.get(source_node_id, {}).get("output_schema")
                properties = output_schema.get("properties", {}) if isinstance(output_schema, dict) else {}
                if field_path not in properties:
                    raise ValueError(
                        f"Flow graph is invalid: Router node {node.id} references unknown structured output field: "
                        f"{condition.source.path}"
                    )
                dumped.append(condition.model_dump(mode="json", exclude_none=True))
            result[node.id] = dumped
        return result

    def _validate_hitl_nodes(self, hitl_nodes: list[FlowGraphNode]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for node in hitl_nodes:
            result[node.id] = normalize_hitl_contract(node.id, node.data.model_dump(exclude_none=True))
        return result

    def _validate_active_hitl_path(self, *, graph: FlowGraphDocument, reachable_node_ids: set[str]) -> None:
        flow_edges = [edge for edge in graph.edges if edge.type == "flow"]
        incoming: dict[str, list[str]] = {}
        outgoing: dict[str, list[str]] = {}
        nodes_by_id = {node.id: node for node in graph.nodes}
        for edge in flow_edges:
            incoming.setdefault(edge.target, []).append(edge.source)
            outgoing.setdefault(edge.source, []).append(edge.target)

        for node in graph.nodes:
            if node.type != "hitl" or node.id not in reachable_node_ids:
                continue
            previous_ids = incoming.get(node.id, [])
            previous_crews = [
                node_id
                for node_id in previous_ids
                if nodes_by_id.get(node_id) and nodes_by_id[node_id].type == "crew"
            ]
            if not previous_crews:
                raise ValueError(f"Flow graph is invalid: HITL node {node.id} must follow a Crew node.")
            next_ids = outgoing.get(node.id, [])
            if len(next_ids) != 1:
                raise ValueError(f"Flow graph is invalid: HITL node {node.id} must connect to exactly one next runtime node.")
            next_node = nodes_by_id.get(next_ids[0])
            if next_node is None or next_node.type not in {"crew", "execution_action", "output"}:
                raise ValueError(f"Flow graph is invalid: HITL node {node.id} must connect to a Crew or Output node.")

    def _validate_output_nodes(
        self,
        output_nodes: list[FlowGraphNode],
        crew_snapshots: dict[str, dict[str, Any]],
        execution_action_node_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        execution_action_node_ids = execution_action_node_ids or set()
        fields: list[dict[str, Any]] = []
        labels: set[str] = set()
        for output_node in output_nodes:
            for field in output_node.data.fields or []:
                label = field.label.strip()
                if not label:
                    raise ValueError(
                        f"Flow graph is invalid: Output node {output_node.id} field label must not be blank."
                    )
                if label in labels:
                    raise ValueError(
                        f"Flow graph is invalid: Output node {output_node.id} "
                        f"has duplicate output field label '{label}'."
                    )
                labels.add(label)
                if field.source == "node":
                    if not field.nodeId or (
                        field.nodeId not in crew_snapshots and field.nodeId not in execution_action_node_ids
                    ):
                        raise ValueError(
                            f"Flow graph is invalid: Output node {output_node.id} "
                            f"references unknown node output source: {field.nodeId}"
                        )
                    if field.nodeId in crew_snapshots and not self._output_path_resolves(
                        field.nodeId,
                        field.path,
                        crew_snapshots,
                    ):
                        raise ValueError(
                            f"Flow graph is invalid: Output node {output_node.id} references nonexistent output field: "
                            f"{field.path}"
                        )
                dumped = field.model_dump(mode="json", exclude_none=True)
                dumped["label"] = label
                fields.append(dumped)
        return fields

    def _output_path_resolves(
        self,
        node_id: str,
        path: str | None,
        crew_snapshots: dict[str, dict[str, Any]],
    ) -> bool:
        normalized_path = (path or "").strip().removeprefix("output.")
        if normalized_path == "raw":
            return True

        path_segments = [segment.strip() for segment in normalized_path.split(".") if segment.strip()]
        if not path_segments:
            return False

        output_schema = crew_snapshots[node_id].get("output_schema")
        current_schema: Any = output_schema

        for segment in path_segments:
            properties = self._schema_properties_for_path_traversal(current_schema)
            if segment not in properties:
                return False
            current_schema = properties[segment]

        return True

    def _schema_properties_for_path_traversal(self, schema: Any) -> dict[str, Any]:
        if not isinstance(schema, dict):
            return {}

        properties = schema.get("properties")
        if isinstance(properties, dict):
            return properties

        items = schema.get("items")
        item_properties = items.get("properties") if isinstance(items, dict) else None
        if schema.get("type") == "array" and isinstance(item_properties, dict):
            return item_properties

        return {}

    def _first_path_segment(self, path: str) -> str:
        return path.split(".", 1)[0].strip()
