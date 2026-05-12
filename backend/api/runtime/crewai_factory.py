from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable, Mapping
from types import UnionType
from typing import Any, Union, get_args, get_origin

from crewai import Agent, Crew, LLM, Task
from crewai.llms.base_llm import BaseLLM
from sqlalchemy.orm import Session

from api.runtime.crewai_payload_adapter import CrewAIRuntimePayloadAdapter
from api.runtime.llm_config import normalize_llm_config
from api.runtime.tool_metadata import validate_required_env_vars, validate_tool_config
from api.runtime.tool_loader import load_tool
from api.services.llm_catalog import CatalogModel

KnowledgeSearchFn = Callable[[str, list[str], int], list[dict[str, Any]]]


class _ValidationLLM(BaseLLM):
    def __init__(self, model: str = "runtime-validation") -> None:
        super().__init__(model=model, provider="openai")

    def call(self, *args, **kwargs):  # pragma: no cover - runtime validation never executes the LLM
        response_model = kwargs.get("response_model")
        if isinstance(response_model, type) and hasattr(response_model, "model_fields"):
            return json.dumps(
                {
                    field_name: self._sample_value_for_annotation(field.annotation)
                    for field_name, field in response_model.model_fields.items()
                }
            )
        return "runtime-validation"

    def _sample_value_for_annotation(self, annotation: object) -> object:
        origin = get_origin(annotation)
        if origin in {Union, UnionType}:
            non_none_args = [arg for arg in get_args(annotation) if arg is not type(None)]
            if len(non_none_args) == 1:
                return self._sample_value_for_annotation(non_none_args[0])
        if annotation is str:
            return "runtime-validation"
        if annotation is bool:
            return False
        if annotation is int:
            return 1
        if annotation is float:
            return 1.0
        if annotation is dict or origin is dict:
            return {}
        if annotation is list or origin is list:
            return ["runtime-validation"]
        return "runtime-validation"

    def supports_function_calling(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 8192


class CrewAIFactory:
    def __init__(
        self,
        payload_adapter: CrewAIRuntimePayloadAdapter | None = None,
        *,
        execution_mode: str = "validation",
        llm_catalog: Mapping[str, CatalogModel] | None = None,
        knowledge_search_fn: KnowledgeSearchFn | None = None,
        db: Session | None = None,
    ) -> None:
        if execution_mode not in {"validation", "live"}:
            raise ValueError(f"Unsupported CrewAI execution mode: {execution_mode}")
        self.execution_mode = execution_mode
        self.llm_catalog = llm_catalog
        self.knowledge_search_fn = knowledge_search_fn
        self.db = db
        self.payload_adapter = payload_adapter or CrewAIRuntimePayloadAdapter(
            llm_resolver=self._runtime_llm
        )

    def build_crew(
        self,
        *,
        runtime_crew: Mapping[str, object],
        runtime_agents: Mapping[str, Mapping[str, object]],
        runtime_tasks: Mapping[str, Mapping[str, object]],
        task_agent_links: Mapping[str, str],
        agent_tool_links: Mapping[str, list[str]] | None = None,
        task_tool_links: Mapping[str, list[str]] | None = None,
        runtime_tools: Mapping[str, Mapping[str, object]] | None = None,
        agent_knowledge_links: Mapping[str, list[str]] | None = None,
        runtime_knowledge: Mapping[str, Mapping[str, object]] | None = None,
        task_objects: dict[str, Task] | None = None,
        agent_objects: dict[str, Agent] | None = None,
        instrumentation_callbacks: Mapping[str, object] | None = None,
    ) -> Crew:
        agent_tool_links = {} if agent_tool_links is None else agent_tool_links
        task_tool_links = {} if task_tool_links is None else task_tool_links
        runtime_tools = {} if runtime_tools is None else runtime_tools
        agent_knowledge_links = {} if agent_knowledge_links is None else agent_knowledge_links
        runtime_knowledge = {} if runtime_knowledge is None else runtime_knowledge
        task_objects = {} if task_objects is None else task_objects
        agent_objects = {} if agent_objects is None else agent_objects

        crew_agent_ids = [
            agent_version_id
            for agent_version_id in runtime_crew.get("agent_version_ids", [])
            if isinstance(agent_version_id, str) and agent_version_id
        ]
        crew_task_ids = [
            task_version_id
            for task_version_id in runtime_crew.get("task_version_ids", [])
            if isinstance(task_version_id, str) and task_version_id
        ]

        crew_agents = self._dedupe_agents(
            [
                self._resolve_agent_object(
                    agent_version_id=agent_version_id,
                    runtime_agents=runtime_agents,
                    agent_objects=agent_objects,
                    agent_tool_links=agent_tool_links,
                    runtime_tools=runtime_tools,
                    knowledge_item_ids=agent_knowledge_links.get(agent_version_id, []),
                )
                for agent_version_id in crew_agent_ids
            ]
        )

        crew_task_payloads = {
            task_version_id: self._resolve_task_payload(task_version_id, runtime_tasks)
            for task_version_id in crew_task_ids
        }
        ordered_task_ids = self._order_runtime_task_ids(crew_task_payloads, declared_order=crew_task_ids)
        local_task_objects: dict[str, Task] = {}
        for task_version_id in ordered_task_ids:
            payload = crew_task_payloads[task_version_id]
            linked_agent_version_id = task_agent_links.get(task_version_id)
            agent = None
            if linked_agent_version_id is not None:
                agent = self._resolve_agent_object(
                    agent_version_id=linked_agent_version_id,
                    runtime_agents=runtime_agents,
                    agent_objects=agent_objects,
                    agent_tool_links=agent_tool_links,
                    runtime_tools=runtime_tools,
                    knowledge_item_ids=agent_knowledge_links.get(linked_agent_version_id, []),
                )
            context_task_ids = self._task_context_ids(payload)
            available_task_objects = {**task_objects, **local_task_objects}
            missing_context = [
                context_task_id for context_task_id in context_task_ids if context_task_id not in available_task_objects
            ]
            if missing_context:
                raise ValueError(
                    "Flow graph is invalid: task depends on tasks that were not assembled first: "
                    f"{task_version_id} -> {', '.join(missing_context)}"
                )
            tools = self._build_tools_for_version(
                owner_label="TaskVersion",
                version_id=task_version_id,
                tool_keys=task_tool_links.get(task_version_id, []),
                runtime_tools=runtime_tools,
            )
            built_task = self._build_task(
                payload,
                agent,
                context=[available_task_objects[context_task_id] for context_task_id in context_task_ids],
                tools=tools,
            )
            local_task_objects[task_version_id] = built_task
            task_objects.setdefault(task_version_id, built_task)

        crew_kwargs = {
            "name": runtime_crew.get("crew_name") or runtime_crew.get("name") or "Workflow Crew",
            "agents": crew_agents,
            "tasks": [local_task_objects[task_version_id] for task_version_id in ordered_task_ids],
        }
        manager_agent_version_id = None
        if runtime_crew.get("process") != "hierarchical" or not runtime_crew.get("manager_llm"):
            manager_agent_version_id = self._manager_agent_version_id(runtime_crew, runtime_agents)
        if isinstance(manager_agent_version_id, str) and manager_agent_version_id:
            resolved_manager_agent = self._resolve_agent_object(
                agent_version_id=manager_agent_version_id,
                runtime_agents=runtime_agents,
                agent_objects=agent_objects,
                agent_tool_links=agent_tool_links,
                runtime_tools=runtime_tools,
                knowledge_item_ids=agent_knowledge_links.get(manager_agent_version_id, []),
            )
            crew_kwargs["manager_agent"] = resolved_manager_agent
            crew_kwargs["agents"] = [
                agent for agent in crew_agents if str(agent.id) != str(resolved_manager_agent.id)
            ]
        crew_kwargs.update(self.payload_adapter.crew_kwargs(runtime_crew))

        if instrumentation_callbacks:
            step_callback = instrumentation_callbacks.get("step_callback")
            task_callback = instrumentation_callbacks.get("task_callback")
            if callable(step_callback):
                crew_kwargs["step_callback"] = step_callback
            if callable(task_callback):
                crew_kwargs["task_callback"] = task_callback

        try:
            return Crew(**crew_kwargs)
        except Exception as exc:
            raise ValueError(
                f"CrewAI assembly failed for {self._crew_label(runtime_crew)}: {exc}"
            ) from exc

    def _make_validation_llm(self, agent_payload: Mapping[str, object]) -> _ValidationLLM:
        return self._runtime_llm(agent_payload.get("llm") or agent_payload.get("llm_config_json"))

    def _llm_model_name(self, llm_payload: object) -> str | None:
        if isinstance(llm_payload, str) and llm_payload.strip():
            return llm_payload.strip()
        if isinstance(llm_payload, Mapping):
            model = llm_payload.get("main_model") or llm_payload.get("model")
            if isinstance(model, str) and model.strip():
                return model.strip()
        return None

    def _runtime_llm(self, llm_payload: object = None) -> _ValidationLLM | LLM:
        normalized = normalize_llm_config(
            llm_payload,
            llm_catalog=self.llm_catalog,
            strict=self.execution_mode == "live",
        )
        if self.execution_mode == "live":
            return LLM(**normalized.runtime_kwargs)
        return _ValidationLLM(model=normalized.model)

    def _build_agent(
        self,
        payload: Mapping[str, object],
        validation_llm: BaseLLM | None = None,
        *,
        tools: list[object] | None = None,
        knowledge_item_ids: list[str] | None = None,
    ) -> Agent:
        try:
            agent_kwargs = {
                "role": payload["role"],
                "goal": payload["goal"],
                "backstory": payload["backstory"],
            }
            agent_kwargs.update(self.payload_adapter.agent_kwargs(payload))
            combined_tools = list(tools or [])
            knowledge_tool = self._build_knowledge_tool_for_agent(knowledge_item_ids or [])
            if knowledge_tool is not None:
                combined_tools.append(knowledge_tool)
            if combined_tools:
                agent_kwargs["tools"] = combined_tools
            if "llm" not in agent_kwargs:
                agent_kwargs["llm"] = validation_llm or self._runtime_llm(
                    payload.get("llm") or payload.get("llm_config_json")
                )
            return Agent(**agent_kwargs)
        except Exception as exc:
            raise ValueError(
                f"CrewAI assembly failed for AgentVersion {self._require_version_id(payload, 'AgentVersion')}: {exc}"
            ) from exc

    def _build_task(
        self,
        payload: Mapping[str, object],
        agent: Agent | None,
        *,
        context: list[Task],
        tools: list[object] | None = None,
    ) -> Task:
        try:
            task_kwargs = {
                "name": payload.get("task_name"),
                "description": payload["description"],
                "expected_output": payload["expected_output"],
            }
            if agent is not None:
                task_kwargs["agent"] = agent
            task_kwargs.update(self.payload_adapter.task_kwargs(payload))
            if context:
                task_kwargs["context"] = context
            if tools:
                task_kwargs["tools"] = tools
            return Task(**task_kwargs)
        except Exception as exc:
            raise ValueError(
                f"CrewAI assembly failed for TaskVersion {self._require_version_id(payload, 'TaskVersion')}: {exc}"
            ) from exc

    def _build_tools_for_version(
        self,
        *,
        owner_label: str,
        version_id: str,
        tool_keys: list[str],
        runtime_tools: Mapping[str, Mapping[str, object]],
    ) -> list[object]:
        tools: list[object] = []
        seen: set[str] = set()
        for tool_key in tool_keys:
            if not isinstance(tool_key, str) or not tool_key or tool_key in seen:
                continue
            seen.add(tool_key)
            tool_payload = runtime_tools.get(tool_key)
            if tool_payload is None:
                raise ValueError(
                    "Flow graph is invalid: tool edge references a tool that was not hydrated: "
                    f"{owner_label} {version_id} -> {tool_key}"
                )
            module_path = tool_payload.get("module_path")
            class_name = tool_payload.get("class_name")
            if not isinstance(module_path, str) or not module_path.strip():
                raise ValueError(f"Flow graph is invalid: tool {tool_key} is missing module_path.")
            if not isinstance(class_name, str) or not class_name.strip():
                raise ValueError(f"Flow graph is invalid: tool {tool_key} is missing class_name.")
            config = self._tool_config_for_version(tool_payload, version_id)
            validate_tool_config(
                tool_key=tool_key,
                version_id=version_id,
                config=config,
                config_schema_json=tool_payload.get("config_schema_json"),
            )
            validate_required_env_vars(
                tool_key=tool_key,
                version_id=version_id,
                required_env_vars=tool_payload.get("required_env_vars"),
            )
            tools.append(load_tool(module_path.strip(), class_name.strip(), config))
        return tools

    def _build_knowledge_tool_for_agent(self, knowledge_item_ids: list[str]) -> object | None:
        ready_ids = [item_id for item_id in knowledge_item_ids if item_id]
        if not ready_ids:
            return None
        from api.runtime.knowledge_search_tool import AXKnowledgeSearchTool
        from api.services.knowledge import search_bound_knowledge_chunks

        search_fn = self.knowledge_search_fn
        if search_fn is None:
            search_fn = lambda query, item_ids, top_k: search_bound_knowledge_chunks(
                query,
                item_ids,
                top_k=top_k,
                db=self.db,
            )
        return AXKnowledgeSearchTool(
            knowledge_item_ids=ready_ids,
            search_fn=search_fn,
        )

    def _tool_config_for_version(self, tool_payload: Mapping[str, object], version_id: str) -> dict:
        attachments = tool_payload.get("attachments")
        if isinstance(attachments, list):
            for attachment in attachments:
                if not isinstance(attachment, Mapping):
                    continue
                if attachment.get("version_id") != version_id:
                    continue
                tool_config = attachment.get("tool_config_json")
                return dict(tool_config) if isinstance(tool_config, dict) else {}

        default_config = tool_payload.get("default_config_json")
        return dict(default_config) if isinstance(default_config, dict) else {}

    def _make_manager_validation_llm(self, manager_llm_payload: object) -> _ValidationLLM:
        return self._runtime_llm(manager_llm_payload)

    def _manager_agent_version_id(
        self,
        runtime_crew: Mapping[str, object],
        runtime_agents: Mapping[str, Mapping[str, object]],
    ) -> str | None:
        manager_agent_version_id = runtime_crew.get("manager_agent_version_id")
        if isinstance(manager_agent_version_id, str) and manager_agent_version_id:
            return manager_agent_version_id

        manager_agent_asset_id = runtime_crew.get("manager_agent_asset_id")
        if not isinstance(manager_agent_asset_id, str) or not manager_agent_asset_id.strip():
            return None
        target_asset_id = manager_agent_asset_id.strip()
        for agent_version_id, payload in runtime_agents.items():
            if payload.get("asset_id") == target_asset_id:
                return agent_version_id
        raise ValueError(
            "Flow graph is invalid: crew references a manager agent asset that was not assembled: "
            f"{target_asset_id}"
        )

    def _dedupe_agents(self, agents: list[Agent]) -> list[Agent]:
        ordered_agents: list[Agent] = []
        seen_agent_ids: set[str] = set()
        for agent in agents:
            agent_id = str(agent.id)
            if agent_id in seen_agent_ids:
                continue
            seen_agent_ids.add(agent_id)
            ordered_agents.append(agent)
        return ordered_agents

    def _resolve_agent_object(
        self,
        *,
        agent_version_id: str,
        runtime_agents: Mapping[str, Mapping[str, object]],
        agent_objects: dict[str, Agent],
        agent_tool_links: Mapping[str, list[str]] | None = None,
        runtime_tools: Mapping[str, Mapping[str, object]] | None = None,
        knowledge_item_ids: list[str] | None = None,
    ) -> Agent:
        existing_agent = agent_objects.get(agent_version_id)
        if existing_agent is not None:
            return existing_agent
        payload = runtime_agents.get(agent_version_id)
        if payload is None:
            raise ValueError(
                "Flow graph is invalid: TaskVersion references an AgentVersion that was not assembled: "
                f"{agent_version_id}"
            )
        tools = self._build_tools_for_version(
            owner_label="AgentVersion",
            version_id=agent_version_id,
            tool_keys=(agent_tool_links or {}).get(agent_version_id, []),
            runtime_tools=runtime_tools or {},
        )
        built_agent = self._build_agent(
            payload,
            self._make_validation_llm(payload),
            tools=tools,
            knowledge_item_ids=knowledge_item_ids,
        )
        agent_objects[agent_version_id] = built_agent
        return built_agent

    def _resolve_task_payload(
        self,
        task_version_id: str,
        runtime_tasks: Mapping[str, Mapping[str, object]],
    ) -> Mapping[str, object]:
        payload = runtime_tasks.get(task_version_id)
        if payload is None:
            raise ValueError(
                "Flow graph is invalid: crew references a TaskVersion that was not assembled: "
                f"{task_version_id}"
            )
        return payload

    def _order_runtime_task_ids(
        self,
        task_payloads: Mapping[str, Mapping[str, object]],
        *,
        declared_order: list[str],
    ) -> list[str]:
        declared_task_ids = set(declared_order)
        dependency_map = {
            task_version_id: [
                dependency_id
                for dependency_id in self._task_context_ids(task_payloads[task_version_id])
                if dependency_id in declared_task_ids
            ]
            for task_version_id in declared_order
        }
        inbound_counts = {task_version_id: 0 for task_version_id in declared_order}
        dependents: dict[str, list[str]] = {task_version_id: [] for task_version_id in declared_order}
        for task_version_id, dependency_ids in dependency_map.items():
            for dependency_id in dependency_ids:
                inbound_counts[task_version_id] += 1
                dependents.setdefault(dependency_id, []).append(task_version_id)

        ready = deque([task_version_id for task_version_id in declared_order if inbound_counts[task_version_id] == 0])
        ordered_task_ids: list[str] = []
        while ready:
            task_version_id = ready.popleft()
            ordered_task_ids.append(task_version_id)
            for dependent_id in dependents.get(task_version_id, []):
                inbound_counts[dependent_id] -= 1
                if inbound_counts[dependent_id] == 0:
                    ready.append(dependent_id)

        if len(ordered_task_ids) != len(declared_order):
            raise ValueError("Flow graph is invalid: task context edges must form an acyclic task order.")
        return ordered_task_ids

    def _task_context_ids(
        self,
        payload: Mapping[str, object],
    ) -> list[str]:
        ordered_ids: list[str] = []
        seen_ids: set[str] = set()
        for candidate in [*payload.get("depends_on_task_ids", []), *payload.get("context_task_ids", [])]:
            if not isinstance(candidate, str) or not candidate or candidate in seen_ids:
                continue
            seen_ids.add(candidate)
            ordered_ids.append(candidate)
        return ordered_ids

    def _crew_label(self, payload: Mapping[str, object]) -> str:
        version_id = payload.get("version_id")
        if isinstance(version_id, str) and version_id:
            return f"CrewVersion {version_id}"
        crew_name = payload.get("crew_name")
        if isinstance(crew_name, str) and crew_name:
            return f"crew {crew_name}"
        return "workflow crew"

    def _require_version_id(self, payload: Mapping[str, object], label: str) -> str:
        version_id = payload.get("version_id")
        if isinstance(version_id, str) and version_id:
            return version_id
        raise ValueError(f"Flow graph is invalid: missing canonical version_id for {label}.")
