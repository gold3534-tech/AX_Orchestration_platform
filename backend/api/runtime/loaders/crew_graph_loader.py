from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from crewai import Process

from api.runtime.input_tokens import collect_required_input_keys
from api.runtime.loaders.shared import dedupe_preserve_order
from api.runtime.tool_metadata import validate_tool_config
from api.schemas.crew_graph import (
    CrewGraphDocument,
    CrewGraphEntity,
    CrewGraphKnowledgeEntity,
    CrewGraphNode,
    CrewGraphToolEntity,
)


_INPUT_PRESET_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_OUTPUT_SCHEMA_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RUNTIME_META_KEYS = {
    "version_id",
    "asset_id",
    "asset_type",
    "name",
    "agent_name",
    "task_name",
    "crew_name",
    "version_number",
    "status",
    "metadata_json",
    "enabled",
    "depends_on_task_ids",
    "context_task_ids",
    "input_presets",
    "payload_json",
    "config_json",
    "llm_config_json",
    "manager_llm_config_json",
    "function_calling_llm_config_json",
}
_OUTPUT_SCHEMA_TYPES = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "dict": "object",
    "list": "array",
}


class CrewGraphLoader:
    def validate_draft_graph(self, graph: dict) -> None:
        document = CrewGraphDocument.model_validate(graph)
        self._validate_document(document, enforce_sequential_assignments=False, allow_placeholders=True)

    def validate_publish_graph(self, graph: dict) -> None:
        self._validate_document(CrewGraphDocument.model_validate(graph))

    def build_runtime_snapshot(self, graph: dict) -> dict:
        document = CrewGraphDocument.model_validate(graph)
        normalized = self._validate_document(document)

        crew_node = normalized["crew_node"]
        agent_nodes = normalized["agent_nodes"]
        task_nodes = normalized["task_nodes"]
        context_map = normalized["task_contexts_by_node_id"]
        task_agent_links_by_node_id = normalized["task_agent_links_by_node_id"]
        ordered_task_node_ids = normalized["ordered_task_node_ids"]
        ordered_task_version_ids = [
            self._require_version_id(normalized["node_by_id"][task_node_id], expected_type="task")
            for task_node_id in ordered_task_node_ids
        ]

        runtime_agents = {
            self._require_version_id(agent_node, expected_type="agent"): self._build_runtime_agent(
                agent_node=agent_node,
                entity=self._require_hydrated_entity_for_node(
                    agent_node,
                    entities=document.entities.agents,
                    expected_type="agent",
                ),
            )
            for agent_node in agent_nodes
        }
        runtime_tasks = {
            self._require_version_id(task_node, expected_type="task"): self._build_runtime_task(
                task_node=task_node,
                entity=self._require_hydrated_entity_for_node(
                    task_node,
                    entities=document.entities.tasks,
                    expected_type="task",
                ),
                depends_on_task_ids=[
                    self._require_version_id(normalized["node_by_id"][context_task_id], expected_type="task")
                    for context_task_id in context_map.get(task_node.id, [])
                ],
            )
            for task_node in task_nodes
        }
        task_agent_links = {
            self._require_version_id(normalized["node_by_id"][task_node_id], expected_type="task"): self._require_version_id(
                normalized["node_by_id"][agent_node_id], expected_type="agent"
            )
            for task_node_id, agent_node_id in task_agent_links_by_node_id.items()
        }
        agent_version_ids = {
            self._require_version_id(agent_node, expected_type="agent")
            for agent_node in agent_nodes
        }
        task_version_ids = {
            self._require_version_id(task_node, expected_type="task")
            for task_node in task_nodes
        }
        agent_tool_links = self._build_version_tool_links(document.entities.tools, agent_version_ids)
        agent_knowledge_links = self._build_version_knowledge_links(
            document.entities.knowledge,
            agent_version_ids,
        )
        task_tool_links = self._build_version_tool_links(document.entities.tools, task_version_ids)
        referenced_tool_keys: set[str] = set()
        for tool_keys in agent_tool_links.values():
            referenced_tool_keys.update(tool_keys)
        for tool_keys in task_tool_links.values():
            referenced_tool_keys.update(tool_keys)
        runtime_tools = {
            tool_key: document.entities.tools[tool_key].model_dump()
            for tool_key in referenced_tool_keys
            if tool_key in document.entities.tools
        }
        referenced_knowledge_ids = {
            knowledge_id
            for ids in agent_knowledge_links.values()
            for knowledge_id in ids
        }
        runtime_knowledge = {
            knowledge_id: {
                "id": entity.id,
                "name": entity.name,
                "status": entity.status,
                "embedding_provider": entity.embedding_provider,
                "embedding_model": entity.embedding_model,
            }
            for knowledge_id, entity in document.entities.knowledge.items()
            if knowledge_id in referenced_knowledge_ids
        }
        agent_version_ids = [
            self._require_version_id(agent_node, expected_type="agent")
            for agent_node in agent_nodes
        ]
        runtime_crew = self._build_runtime_crew(
            crew_node=crew_node,
            entity=self._require_hydrated_entity_for_node(
                crew_node,
                entities=document.entities.crews,
                expected_type="crew",
            ),
            runtime_agents=runtime_agents,
            agent_version_ids=agent_version_ids,
            task_version_ids=ordered_task_version_ids,
        )
        required_inputs = collect_required_input_keys(
            runtime_agents=runtime_agents.values(),
            runtime_tasks=runtime_tasks.values(),
        )
        output_schema = self._build_output_schema(
            ordered_task_version_ids=ordered_task_version_ids,
            runtime_tasks=runtime_tasks,
        )

        return {
            "schemaVersion": 1,
            "runtime_crew": runtime_crew,
            "runtime_agents": runtime_agents,
            "runtime_tasks": runtime_tasks,
            "required_inputs": required_inputs,
            "output_schema": output_schema,
            "task_agent_links": task_agent_links,
            "agent_tool_links": agent_tool_links,
            "tool_links": agent_tool_links,
            "agent_knowledge_links": agent_knowledge_links,
            "runtime_knowledge": runtime_knowledge,
            "task_tool_links": task_tool_links,
            "runtime_tools": runtime_tools,
        }

    def _build_output_schema(
        self,
        *,
        ordered_task_version_ids: list[str],
        runtime_tasks: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: set[str] = set()
        for task_version_id in ordered_task_version_ids:
            task_payload = runtime_tasks.get(task_version_id)
            if task_payload is None:
                continue
            schema = self._task_output_schema_from_payload(task_payload)
            if schema is None:
                continue
            schema_properties = schema.get("properties")
            if isinstance(schema_properties, Mapping):
                properties.update(schema_properties)
            schema_required = schema.get("required")
            if isinstance(schema_required, list):
                required.update(item for item in schema_required if isinstance(item, str))
        if properties:
            return {"type": "object", "properties": properties, "required": sorted(required)}
        return {"type": "object", "properties": {"raw": {"type": "string"}}, "required": []}

    def _task_output_schema_from_payload(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        if payload.get("output_type") not in {"Output JSON", "Output Pydantic"}:
            return None

        fields = payload.get("output_schema_fields")
        if not isinstance(fields, list) or not fields:
            return None

        properties: dict[str, dict[str, Any]] = {}
        required: list[str] = []
        for field in fields:
            if not isinstance(field, Mapping):
                continue

            raw_name = field.get("name")
            raw_type = field.get("type")
            if not isinstance(raw_name, str) or not raw_name.strip():
                continue
            if not isinstance(raw_type, str) or not raw_type.strip():
                continue

            name = raw_name.strip()
            if _OUTPUT_SCHEMA_FIELD_NAME_PATTERN.fullmatch(name) is None:
                continue

            json_type = _OUTPUT_SCHEMA_TYPES.get(raw_type.strip().lower())
            if json_type is None:
                continue

            field_schema: dict[str, Any] = {"type": json_type}
            description = field.get("description")
            if isinstance(description, str) and description.strip():
                field_schema["description"] = description.strip()
            properties[name] = field_schema
            if bool(field.get("required", True)):
                required.append(name)

        if not properties:
            return None
        return {"type": "object", "properties": properties, "required": sorted(set(required))}

    def _build_version_tool_links(
        self,
        tools: Mapping[str, CrewGraphToolEntity],
        version_ids: set[str],
    ) -> dict[str, list[str]]:
        result: dict[str, list[tuple[int, str]]] = {}
        for tool_key, tool_entity in tools.items():
            for attachment in tool_entity.attachments:
                if attachment.version_id in version_ids:
                    result.setdefault(attachment.version_id, []).append(
                        (attachment.sort_order, tool_key)
                    )
        return {
            version_id: [
                tool_key
                for _, tool_key in sorted(items, key=lambda item: (item[0], item[1]))
            ]
            for version_id, items in result.items()
        }

    def _build_version_knowledge_links(
        self,
        knowledge: Mapping[str, CrewGraphKnowledgeEntity],
        version_ids: set[str],
    ) -> dict[str, list[str]]:
        result: dict[str, list[tuple[int, str]]] = {}
        for knowledge_item_id, entity in knowledge.items():
            for attachment in entity.attachments:
                if attachment.version_id in version_ids:
                    if entity.status != "ready":
                        raise ValueError(
                            f"Crew graph is invalid: Knowledge item {knowledge_item_id} is not ready."
                        )
                    result.setdefault(attachment.version_id, []).append(
                        (attachment.sort_order, knowledge_item_id)
                    )
        return {
            version_id: [
                knowledge_item_id
                for _, knowledge_item_id in sorted(items, key=lambda item: (item[0], item[1]))
            ]
            for version_id, items in result.items()
        }

    def _validate_document(
        self,
        document: CrewGraphDocument,
        *,
        enforce_sequential_assignments: bool = True,
        allow_placeholders: bool = False,
    ) -> dict[str, Any]:
        node_by_id = {node.id: node for node in document.nodes}
        if len(node_by_id) != len(document.nodes):
            raise ValueError("Crew graph is invalid: node ids must be unique.")

        crew_nodes = [node for node in document.nodes if node.type == "crew"]
        agent_nodes = [node for node in document.nodes if node.type == "agent"]
        task_nodes = [node for node in document.nodes if node.type == "task"]
        placeholder_nodes = [node for node in document.nodes if node.type == "placeholder"]

        if len(crew_nodes) != 1:
            raise ValueError("Crew graph is invalid: exactly one Crew node is required.")
        if not task_nodes and not allow_placeholders:
            raise ValueError("Crew graph is invalid: at least one Task node is required.")
        if placeholder_nodes and not allow_placeholders:
            raise ValueError(
                "Crew graph is invalid: placeholder nodes must be bound before validation or publish. "
                f"Placeholder nodes: {', '.join(node.id for node in placeholder_nodes)}."
            )
        self._validate_unique_node_version_ids(
            nodes=task_nodes,
            expected_type="task",
            label="Task",
        )
        self._validate_unique_node_version_ids(
            nodes=agent_nodes,
            expected_type="agent",
            label="Agent",
        )

        edge_ids = {edge.id for edge in document.edges}
        if len(edge_ids) != len(document.edges):
            raise ValueError("Crew graph is invalid: edge ids must be unique.")

        task_agent_links_by_node_id: dict[str, str] = {}
        task_contexts_by_node_id: dict[str, list[str]] = defaultdict(list)
        sequence_edges: list[tuple[str, str]] = []
        for edge in document.edges:
            source_node = node_by_id.get(edge.source)
            target_node = node_by_id.get(edge.target)
            if source_node is None or target_node is None:
                raise ValueError(f"Crew graph is invalid: edge references missing node: {edge.id}")

            if edge.type == "agent_assignment":
                if source_node.type != "agent" or target_node.type != "task":
                    raise ValueError("Crew graph is invalid: agent_assignment edges must connect Agent -> Task.")
                if target_node.id in task_agent_links_by_node_id:
                    raise ValueError(
                        f"Crew graph is invalid: Task node {target_node.id} cannot be assigned to more than one Agent."
                    )
                task_agent_links_by_node_id[target_node.id] = source_node.id
                continue

            if edge.type == "task_context":
                if source_node.type != "task" or target_node.type != "task":
                    raise ValueError("Crew graph is invalid: task_context edges must connect Task -> Task.")
                if source_node.id == target_node.id:
                    raise ValueError("Crew graph is invalid: task_context edges cannot self-reference.")
                task_contexts_by_node_id[target_node.id].append(source_node.id)
                continue

            if edge.type == "task_sequence":
                if source_node.type != "task" or target_node.type != "task":
                    raise ValueError("Crew graph is invalid: task_sequence edges must connect Task -> Task.")
                if source_node.id == target_node.id:
                    raise ValueError("Crew graph is invalid: task_sequence edges cannot self-reference.")
                sequence_edges.append((source_node.id, target_node.id))
                continue

            raise ValueError(f"Crew graph is invalid: unsupported edge type {edge.type}.")

        crew_entity = self._require_hydrated_entity_for_node(
            crew_nodes[0],
            entities=document.entities.crews,
            expected_type="crew",
        )
        process_type = self._canonical_process_type(
            node_process_type=crew_nodes[0].data.processType,
            payload=crew_entity.payload,
        )
        ordered_task_node_ids = self._ordered_task_node_ids_from_sequence(
            task_nodes=task_nodes,
            sequence_edges=sequence_edges,
        )
        task_order_index = {
            task_node_id: index
            for index, task_node_id in enumerate(ordered_task_node_ids)
        }
        for dependent_task_id, context_task_ids in task_contexts_by_node_id.items():
            for context_task_id in context_task_ids:
                if task_order_index[context_task_id] >= task_order_index[dependent_task_id]:
                    raise ValueError(
                        "Crew graph is invalid: task_context source must run before "
                        f"dependent Task: {context_task_id} -> {dependent_task_id}."
                    )
        if process_type == "sequential" and enforce_sequential_assignments:
            missing_task_ids = [
                task_node.id
                for task_node in task_nodes
                if task_node.id not in task_agent_links_by_node_id
            ]
            if missing_task_ids:
                raise ValueError(
                    "Crew graph is invalid: Sequential Crew must assign every Task to an Agent. "
                    f"Missing Task nodes: {', '.join(missing_task_ids)}."
                )

        self._validate_entity_references(
            crew_nodes=crew_nodes,
            agent_nodes=agent_nodes,
            task_nodes=task_nodes,
            document=document,
        )
        self._validate_tool_attachment_configs(document.entities.tools)
        self._validate_crew_payload_rules(crew_nodes[0], agent_nodes, document)

        return {
            "node_by_id": node_by_id,
            "crew_node": crew_nodes[0],
            "agent_nodes": agent_nodes,
            "task_nodes": task_nodes,
            "ordered_task_node_ids": ordered_task_node_ids,
            "task_contexts_by_node_id": {
                task_node.id: dedupe_preserve_order(task_contexts_by_node_id.get(task_node.id, []))
                for task_node in task_nodes
            },
            "task_agent_links_by_node_id": task_agent_links_by_node_id,
        }

    def _validate_unique_node_version_ids(
        self,
        *,
        nodes: list[CrewGraphNode],
        expected_type: str,
        label: str,
    ) -> None:
        node_ids_by_version_id: dict[str, list[str]] = defaultdict(list)
        for node in nodes:
            version_id = self._require_version_id(node, expected_type=expected_type)
            node_ids_by_version_id[version_id].append(node.id)

        for version_id, node_ids in node_ids_by_version_id.items():
            if len(node_ids) > 1:
                raise ValueError(
                    f"Crew graph is invalid: {label} version {version_id} "
                    f"cannot be reused by multiple {label} nodes: {', '.join(node_ids)}."
                )

    def _ordered_task_node_ids_from_sequence(
        self,
        *,
        task_nodes: list[CrewGraphNode],
        sequence_edges: list[tuple[str, str]],
    ) -> list[str]:
        task_node_ids = [task_node.id for task_node in task_nodes]
        next_by_task_id: dict[str, str] = {}
        previous_by_task_id: dict[str, str] = {}
        for source_task_id, target_task_id in sequence_edges:
            if source_task_id in next_by_task_id:
                raise ValueError(
                    "Crew graph is invalid: task_sequence allows at most one outgoing edge per Task."
                )
            if target_task_id in previous_by_task_id:
                raise ValueError(
                    "Crew graph is invalid: task_sequence allows at most one incoming edge per Task."
                )
            next_by_task_id[source_task_id] = target_task_id
            previous_by_task_id[target_task_id] = source_task_id

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_node_id: str) -> None:
            if task_node_id in visited:
                return
            if task_node_id in visiting:
                raise ValueError("Crew graph is invalid: task_sequence edges must be acyclic.")
            visiting.add(task_node_id)
            next_task_id = next_by_task_id.get(task_node_id)
            if next_task_id is not None:
                visit(next_task_id)
            visiting.remove(task_node_id)
            visited.add(task_node_id)

        for task_node_id in task_node_ids:
            visit(task_node_id)

        sequenced_task_ids = set(next_by_task_id) | set(previous_by_task_id)
        chain_head_ids = [
            task_node_id
            for task_node_id in task_node_ids
            if task_node_id in sequenced_task_ids and task_node_id not in previous_by_task_id
        ]
        ordered_task_node_ids: list[str] = []
        for chain_head_id in chain_head_ids:
            task_node_id: str | None = chain_head_id
            while task_node_id is not None:
                ordered_task_node_ids.append(task_node_id)
                task_node_id = next_by_task_id.get(task_node_id)
        ordered_task_node_ids.extend(
            task_node_id
            for task_node_id in task_node_ids
            if task_node_id not in sequenced_task_ids
        )
        return ordered_task_node_ids

    def _validate_entity_references(
        self,
        *,
        crew_nodes: list[CrewGraphNode],
        agent_nodes: list[CrewGraphNode],
        task_nodes: list[CrewGraphNode],
        document: CrewGraphDocument,
    ) -> None:
        for crew_node in crew_nodes:
            self._require_hydrated_entity_for_node(
                crew_node,
                entities=document.entities.crews,
                expected_type="crew",
            )
        for agent_node in agent_nodes:
            self._require_hydrated_entity_for_node(
                agent_node,
                entities=document.entities.agents,
                expected_type="agent",
            )
        for task_node in task_nodes:
            self._require_hydrated_entity_for_node(
                task_node,
                entities=document.entities.tasks,
                expected_type="task",
            )

    def _validate_tool_attachment_configs(self, tools: Mapping[str, CrewGraphToolEntity]) -> None:
        for tool_key, tool_entity in tools.items():
            for attachment in tool_entity.attachments:
                validate_tool_config(
                    tool_key=tool_key,
                    version_id=attachment.version_id,
                    config=attachment.tool_config_json,
                    config_schema_json=tool_entity.config_schema_json,
                )

    def _validate_crew_payload_rules(
        self,
        crew_node: CrewGraphNode,
        agent_nodes: list[CrewGraphNode],
        document: CrewGraphDocument,
    ) -> None:
        crew_entity = self._require_hydrated_entity_for_node(
            crew_node,
            entities=document.entities.crews,
            expected_type="crew",
        )
        effective_process_type = self._canonical_process_type(
            node_process_type=crew_node.data.processType,
            payload=crew_entity.payload,
        )

        self._validate_process_type(effective_process_type, crew_entity=crew_entity)

        if effective_process_type != "hierarchical":
            return

        if not agent_nodes:
            raise ValueError(
                "Crew graph is invalid: hierarchical Crew must include at least one worker Agent."
            )

        payload = crew_entity.payload
        manager_llm = self._manager_llm_payload(payload.get("manager_llm"))
        if manager_llm:
            return

        raise ValueError(
            "Crew graph is invalid: hierarchical Crew must define manager_llm."
        )

    def _validate_process_type(self, process_type: str, *, crew_entity: CrewGraphEntity) -> None:
        try:
            Process(process_type)
        except ValueError as exc:
            raise ValueError(
                f"Crew graph is invalid: unsupported crew process '{process_type}' for Crew node {crew_entity.version_id}."
            ) from exc

    def _build_runtime_crew(
        self,
        *,
        crew_node: CrewGraphNode,
        entity: CrewGraphEntity,
        runtime_agents: Mapping[str, Mapping[str, Any]],
        agent_version_ids: list[str],
        task_version_ids: list[str],
    ) -> dict[str, Any]:
        runtime_crew = {
            "crew_node_id": crew_node.id,
            "asset_id": crew_node.data.assetId,
            "version_id": crew_node.data.versionId,
            "name": "Workflow Crew",
            "crew_name": "Workflow Crew",
            "description": None,
            "process": crew_node.data.processType or "sequential",
            "manager_agent_version_id": None,
            "agent_version_ids": dedupe_preserve_order(agent_version_ids),
            "task_version_ids": list(task_version_ids),
        }

        self._validate_entity_matches_node(crew_node, entity)
        payload = entity.payload
        process_type = self._canonical_process_type(
            node_process_type=crew_node.data.processType,
            payload=payload,
        )
        manager_agent_version_id = None
        if process_type != "hierarchical":
            manager_agent_version_id = self._manager_agent_version_id_from_entity(
                payload,
                runtime_agents=runtime_agents,
            )
        runtime_crew.update(
            {
                "asset_id": entity.asset_id,
                "version_id": entity.version_id,
                "name": entity.name,
                "crew_name": entity.name,
                "description": entity.description,
                "process": process_type,
                "manager_agent_version_id": manager_agent_version_id,
            }
        )
        runtime_crew.update(
            _copy_sparse_payload(
                payload,
                exclude={
                    "process",
                    "process_type",
                    "manager_agent_version_id",
                    "manager_agent_asset_id",
                },
            )
        )
        return runtime_crew

    def _canonical_process_type(self, *, node_process_type: str | None, payload: Mapping[str, Any]) -> str:
        process_type = payload.get("process") or payload.get("process_type")
        if isinstance(process_type, str) and process_type.strip():
            return process_type.strip()
        if isinstance(node_process_type, str) and node_process_type.strip():
            return node_process_type.strip()
        return "sequential"

    def _build_runtime_agent(self, *, agent_node: CrewGraphNode, entity: CrewGraphEntity) -> dict[str, Any]:
        self._validate_entity_matches_node(agent_node, entity)
        payload = entity.payload
        runtime_agent = {
            "version_id": entity.version_id,
            "asset_id": entity.asset_id,
            "asset_type": "agent",
            "name": entity.name,
            "agent_name": entity.name,
            "version_number": entity.version_no,
            "status": entity.status,
            "role": payload.get("role", ""),
            "goal": payload.get("goal", ""),
            "backstory": payload.get("backstory", ""),
        }
        runtime_agent.update(_copy_sparse_payload(payload, exclude={"role", "goal", "backstory"}))
        return runtime_agent

    def _build_runtime_task(
        self,
        *,
        task_node: CrewGraphNode,
        entity: CrewGraphEntity,
        depends_on_task_ids: list[str],
    ) -> dict[str, Any]:
        self._validate_entity_matches_node(task_node, entity)
        payload = entity.payload
        runtime_task = {
            "version_id": entity.version_id,
            "asset_id": entity.asset_id,
            "asset_type": "task",
            "name": entity.name,
            "task_name": entity.name,
            "version_number": entity.version_no,
            "status": entity.status,
            "description": payload["description"],
            "expected_output": payload["expected_output"],
            "input_presets": list(payload.get("input_presets") or []),
            "depends_on_task_ids": list(depends_on_task_ids),
            "context_task_ids": list(depends_on_task_ids),
        }
        runtime_task.update(
            _copy_sparse_payload(
                payload,
                exclude={
                    "description",
                    "expected_output",
                    "input_presets",
                    "depends_on_task_ids",
                    "context_task_ids",
                },
            )
        )
        return runtime_task

    def _manager_llm_payload(self, value: object) -> dict[str, Any]:
        if isinstance(value, Mapping):
            payload = dict(value)
            candidate = payload.get("main_model") or payload.get("model")
            return payload if isinstance(candidate, str) and bool(candidate.strip()) else {}
        if isinstance(value, str):
            trimmed = value.strip()
            return {"model": trimmed} if trimmed else {}
        return {}

    def _manager_agent_version_id_from_entity(
        self,
        payload: Mapping[str, Any],
        *,
        runtime_agents: Mapping[str, Mapping[str, Any]],
    ) -> str | None:
        manager_agent_version_id = payload.get("manager_agent_version_id")
        if isinstance(manager_agent_version_id, str) and manager_agent_version_id.strip():
            return manager_agent_version_id.strip()
        manager_agent_asset_id = payload.get("manager_agent_asset_id")
        if not isinstance(manager_agent_asset_id, str) or not manager_agent_asset_id.strip():
            return None
        for agent_version_id, runtime_agent in runtime_agents.items():
            if runtime_agent.get("asset_id") == manager_agent_asset_id.strip():
                return agent_version_id
        raise ValueError(
            "Crew graph is invalid: hierarchical Crew manager Agent reference must resolve to a normalized Agent."
        )

    def _validate_task_payload(self, task_node: CrewGraphNode, entity: CrewGraphEntity) -> None:
        payload = entity.payload
        for field_name in ("description", "expected_output"):
            value = payload.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Crew graph is invalid: hydrated task entity for node {task_node.id} must define {field_name}."
                )
        input_presets = payload.get("input_presets")
        if input_presets is None:
            return
        if not isinstance(input_presets, list) or any(
            not isinstance(item, str) or _INPUT_PRESET_PATTERN.fullmatch(item) is None
            for item in input_presets
        ):
            raise ValueError(
                f"Crew graph is invalid: hydrated task entity for node {task_node.id} "
                "input_presets must be a list of valid input keys."
            )

    def _require_hydrated_entity_for_node(
        self,
        node: CrewGraphNode,
        *,
        entities: Mapping[str, CrewGraphEntity],
        expected_type: str,
    ) -> CrewGraphEntity:
        version_id = self._require_version_id(node, expected_type=expected_type)
        entity = entities.get(version_id)
        if entity is None:
            raise ValueError(
                f"Crew graph is invalid: missing hydrated {expected_type} entity for node {node.id}."
            )
        self._validate_entity_matches_node(node, entity)
        if expected_type == "task":
            self._validate_task_payload(node, entity)
        return entity

    def _validate_entity_matches_node(self, node: CrewGraphNode, entity: CrewGraphEntity) -> None:
        if entity.version_id != node.data.versionId or entity.asset_id != node.data.assetId:
            raise ValueError(
                f"Crew graph entity for node {node.id} does not match node reference assetId/versionId."
            )

    def _require_version_id(self, node: CrewGraphNode, *, expected_type: str) -> str:
        if node.type != expected_type:
            raise ValueError(
                f"Crew graph is invalid: expected {expected_type} node but received {node.type}."
            )
        version_id = node.data.versionId
        asset_id = node.data.assetId
        if version_id is None or asset_id is None:
            raise ValueError(
                f"Crew graph is invalid: {expected_type.capitalize()} node {node.id} must define assetId and versionId."
            )
        return version_id

def _copy_sparse_payload(payload: Mapping[str, Any], exclude: set[str] | None = None) -> dict[str, Any]:
    excluded_keys = _RUNTIME_META_KEYS | (exclude or set())
    return {
        key: value
        for key, value in payload.items()
        if key not in excluded_keys and value is not None
    }
