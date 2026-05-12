import pytest

from api.runtime import crewai_factory
from api.runtime.crewai_factory import CrewAIFactory
from api.runtime.crewai_payload_adapter import CrewAIRuntimePayloadAdapter
from api.runtime.loaders import CrewGraphLoader
from api.services.llm_catalog import CatalogModel
from crewai import Process
from crewai.tools import BaseTool
from pydantic import BaseModel


def _llm_metadata(*, temperature_supported=True, max_tokens_max=4096):
    return {
        "schema_version": 1,
        "capabilities": {"streaming": True, "tool_calling": True, "json_mode": True},
        "parameters": {
            "temperature": {
                "supported": temperature_supported,
                "default": 0.7 if temperature_supported else None,
                "min": 0,
                "max": 2 if temperature_supported else None,
            },
            "max_tokens": {
                "supported": True,
                "default": 4096,
                "min": 1,
                "max": max_tokens_max,
            },
        },
    }


@pytest.fixture
def llm_catalog():
    return [
        CatalogModel(
            provider_key="openai",
            provider_display_name="OpenAI",
            provider_type="hosted",
            credential_provider="openai",
            model_key="openai/gpt-4o-mini",
            model_display_name="GPT-4o mini",
            llm_metadata_json=_llm_metadata(max_tokens_max=4096),
            provider_metadata_json={"docs_url": "https://platform.openai.com/docs/models"},
        ),
        CatalogModel(
            provider_key="openai",
            provider_display_name="OpenAI",
            provider_type="hosted",
            credential_provider="openai",
            model_key="openai/gpt-5",
            model_display_name="GPT-5",
            llm_metadata_json=_llm_metadata(temperature_supported=False, max_tokens_max=4096),
            provider_metadata_json={"docs_url": "https://platform.openai.com/docs/models"},
        ),
    ]


def test_live_runtime_llm_builds_crewai_llm_with_supported_parameters(monkeypatch, llm_catalog):
    captured = {}

    class CapturingLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(crewai_factory, "LLM", CapturingLLM)

    llm = CrewAIFactory(execution_mode="live", llm_catalog=llm_catalog)._runtime_llm(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "max_tokens": 1024,
        }
    )

    assert isinstance(llm, CapturingLLM)
    assert captured == {
        "model": "openai/gpt-4o-mini",
        "temperature": 0.3,
        "max_tokens": 1024,
    }


def test_live_runtime_llm_drops_unsupported_temperature(monkeypatch, llm_catalog):
    captured = {}

    class CapturingLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(crewai_factory, "LLM", CapturingLLM)

    CrewAIFactory(execution_mode="live", llm_catalog=llm_catalog)._runtime_llm(
        {"model": "openai/gpt-5", "temperature": 0.3, "max_tokens": 2048}
    )

    assert captured == {"model": "openai/gpt-5", "max_tokens": 2048}


def test_live_runtime_llm_rejects_out_of_range_max_tokens(llm_catalog):
    with pytest.raises(ValueError, match="max_tokens must be between 1 and 4096"):
        CrewAIFactory(execution_mode="live", llm_catalog=llm_catalog)._runtime_llm(
            {"model": "openai/gpt-4o-mini", "max_tokens": 4097}
        )


def test_validation_llm_prefers_main_model_over_legacy_model(monkeypatch):
    captured = {}

    class CapturingLLM:
        def __init__(self, model: str = "runtime-validation") -> None:
            captured["model"] = model

    monkeypatch.setattr(crewai_factory, "_ValidationLLM", CapturingLLM)

    CrewAIFactory()._make_validation_llm(
        {
            "llm": {
                "main_model": "gpt-4o-mini",
                "model": "legacy-model",
            }
        }
    )

    assert captured["model"] == "gpt-4o-mini"

    captured.clear()

    CrewAIFactory()._make_validation_llm({"llm": {"model": "legacy-model"}})

    assert captured["model"] == "legacy-model"


def test_manager_validation_llm_accepts_string_payload(monkeypatch):
    captured = {}

    class CapturingLLM:
        def __init__(self, model: str = "runtime-validation") -> None:
            captured["model"] = model

    monkeypatch.setattr(crewai_factory, "_ValidationLLM", CapturingLLM)

    CrewAIFactory()._make_manager_validation_llm("gpt-4o")

    assert captured["model"] == "gpt-4o"


def test_validation_factory_resolves_crew_function_calling_llm():
    kwargs = CrewAIFactory().payload_adapter.crew_kwargs(
        {
            "version_id": "crew-version-1",
            "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini-tools"},
        }
    )

    assert not isinstance(kwargs["function_calling_llm"], str)
    assert kwargs["function_calling_llm"].model == "gpt-4o-mini-tools"


def test_live_factory_resolves_crew_function_calling_llm(monkeypatch):
    class CapturingLLM:
        def __init__(self, **kwargs):
            self.model = kwargs["model"]

    monkeypatch.setattr(crewai_factory, "LLM", CapturingLLM)

    kwargs = CrewAIFactory(execution_mode="live").payload_adapter.crew_kwargs(
        {
            "version_id": "crew-version-1",
            "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini-tools"},
        }
    )

    assert not isinstance(kwargs["function_calling_llm"], str)
    assert kwargs["function_calling_llm"].model == "gpt-4o-mini-tools"


def test_crewai_payload_adapter_converts_crew_saas_payload_to_runtime_kwargs():
    kwargs = CrewAIRuntimePayloadAdapter().crew_kwargs(
        {
            "version_id": "crew-version-1",
            "manager_agent_asset_id": "agent-asset-1",
            "process": "sequential",
            "verbose": False,
            "cache": True,
            "max_rpm": 12,
            "output_log_file": "logs.json",
        }
    )

    assert kwargs == {
        "process": Process.sequential,
        "verbose": False,
        "cache": True,
        "max_rpm": 12,
        "output_log_file": "logs.json",
    }
    assert "manager_agent_asset_id" not in kwargs
    assert "manager_agent" not in kwargs


def test_crewai_payload_adapter_rejects_invalid_crew_payload_type():
    with pytest.raises(ValueError, match="max_rpm"):
        CrewAIRuntimePayloadAdapter().crew_kwargs(
            {
                "version_id": "crew-version-1",
                "process": "sequential",
                "max_rpm": "fast",
            }
        )


def test_crewai_payload_adapter_rejects_unresolved_crew_object_field():
    with pytest.raises(ValueError, match="knowledge_sources"):
        CrewAIRuntimePayloadAdapter().crew_kwargs(
            {
                "version_id": "crew-version-1",
                "process": "sequential",
                "knowledge_sources": [{"name": "docs"}],
            }
        )


def test_crewai_payload_adapter_rejects_unsupported_crewai_field_without_converter():
    with pytest.raises(ValueError, match="unsupported runtime converter.*max_retries"):
        CrewAIRuntimePayloadAdapter().task_kwargs(
            {
                "version_id": "task-version-1",
                "description": "Research the topic.",
                "expected_output": "A report.",
                "max_retries": 5,
            }
        )


def test_crewai_payload_adapter_rejects_unknown_payload_typo():
    with pytest.raises(ValueError, match="unsupported CrewAI agent field.*verboze"):
        CrewAIRuntimePayloadAdapter().agent_kwargs(
            {
                "version_id": "agent-version-1",
                "role": "Researcher",
                "goal": "Investigate",
                "backstory": "Handles research.",
                "verboze": True,
            }
        )


def test_crewai_payload_adapter_ignores_agent_ui_metadata():
    kwargs = CrewAIRuntimePayloadAdapter().agent_kwargs(
        {
            "version_id": "agent-version-1",
            "role": "Researcher",
            "goal": "Investigate",
            "backstory": "Handles research.",
            "photo_url": "/data/img/employee1.png",
            "verbose": True,
        }
    )

    assert kwargs == {"verbose": True}


def test_crewai_payload_adapter_rejects_raw_task_response_model():
    with pytest.raises(ValueError, match="response_model"):
        CrewAIRuntimePayloadAdapter().task_kwargs(
            {
                "version_id": "task-version-1",
                "description": "Research the topic.",
                "expected_output": "A report.",
                "response_model": {"type": "object"},
            }
        )


def test_crewai_payload_adapter_converts_task_output_metadata_without_direct_kwargs():
    output_json_kwargs = CrewAIRuntimePayloadAdapter().task_kwargs(
        {
            "version_id": "12345678-1234-1234-1234-123456789abc",
            "task_name": "summary task",
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "summary", "type": "str", "description": "Short summary.", "required": True},
            ],
        }
    )

    assert set(output_json_kwargs) == {"output_json"}
    assert output_json_kwargs["output_json"].__name__ == "summary_task_12345678"

    output_pydantic_kwargs = CrewAIRuntimePayloadAdapter().task_kwargs(
        {
            "version_id": "87654321-1234-1234-1234-123456789abc",
            "task_name": "summary task",
            "output_type": "Output Pydantic",
            "output_schema_fields": [
                {"name": "summary", "type": "str", "required": True},
            ],
        }
    )

    assert set(output_pydantic_kwargs) == {"output_pydantic"}
    assert output_pydantic_kwargs["output_pydantic"].__name__ == "summary_task_87654321"


def test_crewai_payload_adapter_rejects_duplicate_output_schema_field_names():
    with pytest.raises(ValueError, match="duplicate.*summary"):
        CrewAIRuntimePayloadAdapter().task_kwargs(
            {
                "version_id": "task-version-1",
                "task_name": "summary task",
                "output_type": "Output JSON",
                "output_schema_fields": [
                    {"name": "summary", "type": "str", "required": True},
                    {"name": "summary", "type": "str", "required": False},
                ],
            }
        )


def test_crewai_payload_adapter_defaults_omitted_schema_required_to_true():
    kwargs = CrewAIRuntimePayloadAdapter().task_kwargs(
        {
            "version_id": "task-version-1",
            "task_name": "summary task",
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "summary", "type": "str"},
                {"name": "notes", "type": "str", "required": False},
            ],
        }
    )

    output_model = kwargs["output_json"]
    assert output_model.model_fields["summary"].is_required()
    assert not output_model.model_fields["notes"].is_required()


def test_crewai_payload_adapter_allows_explicit_none_for_optional_output_json_fields():
    output_model = CrewAIRuntimePayloadAdapter().task_output_model(
        {
            "version_id": "c2ac8f36-b7fa-475c-acc7-a87f2886dfe1",
            "task_name": "Carousel Slide 1",
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "artifact_id_01", "type": "str", "required": True},
                {"name": "error", "type": "str", "required": False},
            ],
        }
    )["output_json"]

    validated = output_model.model_validate(
        {"artifact_id_01": "dd45ab77-6ed1-40e3-839d-5dff206c2ca0", "error": None}
    )

    assert validated.model_dump() == {
        "artifact_id_01": "dd45ab77-6ed1-40e3-839d-5dff206c2ca0",
        "error": None,
    }


def test_crewai_payload_adapter_keeps_required_output_json_fields_strict():
    output_model = CrewAIRuntimePayloadAdapter().task_output_model(
        {
            "version_id": "required-task-version",
            "task_name": "Required Summary",
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "summary", "type": "str", "required": True},
                {"name": "error", "type": "str", "required": False},
            ],
        }
    )["output_json"]

    with pytest.raises(ValueError, match="summary"):
        output_model.model_validate({"summary": None, "error": None})


def test_crewai_payload_adapter_allows_explicit_none_for_optional_output_pydantic_fields():
    output_model = CrewAIRuntimePayloadAdapter().task_output_model(
        {
            "version_id": "pydantic-task-version",
            "task_name": "Optional Pydantic",
            "output_type": "Output Pydantic",
            "output_schema_fields": [
                {"name": "items", "type": "list", "required": True},
                {"name": "error", "type": "str", "required": False},
            ],
        }
    )["output_pydantic"]

    validated = output_model.model_validate({"items": ["artifact-1"], "error": None})

    assert validated.model_dump() == {"items": ["artifact-1"], "error": None}


def test_crewai_factory_builds_hierarchical_crew_from_runtime_payload():
    runtime_crew = {
        "crew_node_id": "crew-node-1",
        "asset_id": "crew-asset-1",
        "version_id": "crew-version-1",
        "name": "Manager Crew",
        "process": "hierarchical",
        "manager_llm": {"provider": "openai", "model": "gpt-4o"},
        "manager_agent_version_id": None,
        "agent_version_ids": ["agent-version-1", "agent-version-2"],
        "task_version_ids": ["task-version-1"],
    }
    runtime_agents = {
        "agent-version-1": {
            "version_id": "agent-version-1",
            "role": "Researcher",
            "goal": "Investigate",
            "backstory": "Handles research.",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
        },
        "agent-version-2": {
            "version_id": "agent-version-2",
            "role": "Reviewer",
            "goal": "Review",
            "backstory": "Handles review.",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
        },
    }
    runtime_tasks = {
        "task-version-1": {
            "version_id": "task-version-1",
            "task_name": "Investigate Task",
            "description": "Investigate the request.",
            "expected_output": "A summary.",
        }
    }
    task_agent_links = {"task-version-1": "agent-version-1"}

    crew = CrewAIFactory().build_crew(
        runtime_crew=runtime_crew,
        runtime_agents=runtime_agents,
        runtime_tasks=runtime_tasks,
        task_agent_links=task_agent_links,
        task_objects={},
    )

    assert crew.process == Process.hierarchical


def test_crewai_factory_hierarchical_manager_llm_mvp_ignores_manager_agent_asset_reference():
    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "crew_name": "Manager LLM Crew",
            "process": "hierarchical",
            "manager_llm": "gpt-4o-mini",
            "manager_agent_asset_id": "manager-asset-1",
            "manager_agent_version_id": None,
            "agent_version_ids": ["worker-version-1"],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={
            "worker-version-1": {
                "version_id": "worker-version-1",
                "asset_id": "worker-asset-1",
                "role": "Worker",
                "goal": "Do assigned work",
                "backstory": "Handles delegated tasks.",
            },
            "manager-version-1": {
                "version_id": "manager-version-1",
                "asset_id": "manager-asset-1",
                "role": "Manager",
                "goal": "Coordinate work",
                "backstory": "Future manager agent.",
            },
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Work Task",
                "description": "Complete the work.",
                "expected_output": "Finished work.",
            }
        },
        task_agent_links={},
    )

    assert crew.process == Process.hierarchical
    assert crew.manager_agent is None
    assert [agent.role for agent in crew.agents] == ["Worker"]
    assert crew.manager_llm is not None


@pytest.mark.skip(reason="Custom manager agent is reserved for a later phase; Manager LLM is the MVP contract.")
def test_crewai_factory_resolves_manager_agent_from_asset_id():
    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "name": "Manager Crew",
            "process": "hierarchical",
            "manager_agent_asset_id": "manager-asset-1",
            "agent_version_ids": ["worker-version-1"],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={
            "worker-version-1": {
                "version_id": "worker-version-1",
                "asset_id": "worker-asset-1",
                "role": "Worker",
                "goal": "Do the work",
                "backstory": "Handles assigned work.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            },
            "manager-version-1": {
                "version_id": "manager-version-1",
                "asset_id": "manager-asset-1",
                "role": "Manager",
                "goal": "Coordinate the crew",
                "backstory": "Keeps the work organized.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            },
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Work Task",
                "description": "Do the work.",
                "expected_output": "Finished work.",
            }
        },
        task_agent_links={"task-version-1": "worker-version-1"},
    )

    assert crew.process == Process.hierarchical
    assert crew.manager_agent is not None
    assert crew.manager_agent.role == "Manager"
    assert [agent.role for agent in crew.agents] == ["Worker"]


def test_crewai_factory_builds_task_without_agent_when_link_is_absent():
    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "crew_name": "Hierarchical Crew",
            "process": "hierarchical",
            "agent_version_ids": ["agent-version-1"],
            "task_version_ids": ["task-version-1"],
            "manager_llm": "gpt-4o-mini",
        },
        runtime_agents={
            "agent-version-1": {
                "version_id": "agent-version-1",
                "asset_id": "agent-asset-1",
                "role": "Researcher",
                "goal": "Research",
                "backstory": "Finds facts.",
            }
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "description": "Research the topic.",
                "expected_output": "A concise report.",
            }
        },
        task_agent_links={},
    )

    assert len(crew.tasks) == 1
    assert crew.tasks[0].agent is None


def test_crewai_factory_builds_task_with_agent_when_link_exists():
    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "crew_name": "Sequential Crew",
            "process": "sequential",
            "agent_version_ids": ["agent-version-1"],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={
            "agent-version-1": {
                "version_id": "agent-version-1",
                "asset_id": "agent-asset-1",
                "role": "Researcher",
                "goal": "Research",
                "backstory": "Finds facts.",
            }
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "description": "Research the topic.",
                "expected_output": "A concise report.",
            }
        },
        task_agent_links={"task-version-1": "agent-version-1"},
    )

    assert crew.tasks[0].agent is not None
    assert crew.tasks[0].agent.role == "Researcher"


def test_crewai_factory_builds_sequential_crew_from_runtime_snapshot():
    snapshot = CrewGraphLoader().build_runtime_snapshot(
        {
            "schemaVersion": 1,
            "nodes": [
                {
                    "id": "crew:1",
                    "type": "crew",
                    "position": {"x": 0, "y": 0},
                    "data": {
                        "assetId": "c1",
                        "versionId": "cv1",
                        "processType": "sequential",
                    },
                },
                {
                    "id": "agent:1",
                    "type": "agent",
                    "position": {"x": 0, "y": 0},
                    "data": {"assetId": "a1", "versionId": "av1"},
                },
                {
                    "id": "task:1",
                    "type": "task",
                    "position": {"x": 0, "y": 0},
                    "data": {"assetId": "t1", "versionId": "tv1"},
                },
                {
                    "id": "task:2",
                    "type": "task",
                    "position": {"x": 0, "y": 0},
                    "data": {"assetId": "t2", "versionId": "tv2"},
                },
            ],
            "edges": [
                {
                    "id": "assign:1",
                    "source": "agent:1",
                    "target": "task:1",
                    "type": "agent_assignment",
                },
                {
                    "id": "assign:2",
                    "source": "agent:1",
                    "target": "task:2",
                    "type": "agent_assignment",
                },
                {
                    "id": "sequence:1",
                    "source": "task:1",
                    "target": "task:2",
                    "type": "task_sequence",
                },
            ],
            "entities": {
                "agents": {
                    "av1": {
                        "version_id": "av1",
                        "asset_id": "a1",
                        "name": "Researcher",
                        "version_no": 1,
                        "status": "published",
                        "payload": {
                            "role": "Researcher",
                            "goal": "Investigate",
                            "backstory": "Handles research.",
                            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
                            "enabled": True,
                        },
                    }
                },
                "tasks": {
                    "tv1": {
                        "version_id": "tv1",
                        "asset_id": "t1",
                        "name": "Task 1",
                        "version_no": 1,
                        "status": "published",
                        "payload": {
                            "description": "Task 1",
                            "expected_output": "Completed task 1",
                            "output_json_schema": None,
                        },
                    },
                    "tv2": {
                        "version_id": "tv2",
                        "asset_id": "t2",
                        "name": "Task 2",
                        "version_no": 1,
                        "status": "published",
                        "payload": {
                            "description": "Task 2",
                            "expected_output": "Completed task 2",
                            "output_json_schema": None,
                        },
                    },
                },
                "crews": {
                    "cv1": {
                        "version_id": "cv1",
                        "asset_id": "c1",
                        "name": "Workflow Crew",
                        "version_no": 1,
                        "status": "published",
                        "payload": {
                            "description": "Sequential crew",
                            "process": "sequential",
                            "payload_json": {},
                        },
                    }
                },
            },
        }
    )

    crew = CrewAIFactory().build_crew(
        runtime_crew=snapshot["runtime_crew"],
        runtime_agents=snapshot["runtime_agents"],
        runtime_tasks=snapshot["runtime_tasks"],
        task_agent_links=snapshot["task_agent_links"],
    )

    assert [task.description for task in crew.tasks] == ["Task 1", "Task 2"]


def test_crewai_factory_passes_runtime_tools_to_task(monkeypatch):
    loaded_tools = []

    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    def fake_load_tool(module_path: str, class_name: str, config: dict | None = None):
        loaded_tools.append((module_path, class_name, config))
        return FakeTool()

    monkeypatch.setattr(crewai_factory, "load_tool", fake_load_tool)

    runtime_crew = {
        "crew_node_id": "crew-node-1",
        "asset_id": "crew-asset-1",
        "version_id": "crew-version-1",
        "name": "Tool Crew",
        "process": "sequential",
        "manager_agent_version_id": None,
        "agent_version_ids": ["agent-version-1"],
        "task_version_ids": ["task-version-1"],
    }
    runtime_agents = {
        "agent-version-1": {
            "version_id": "agent-version-1",
            "role": "Researcher",
            "goal": "Investigate",
            "backstory": "Handles research.",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
        }
    }
    runtime_tasks = {
        "task-version-1": {
            "version_id": "task-version-1",
            "task_name": "Investigate Task",
            "description": "Investigate the request.",
            "expected_output": "A summary.",
        }
    }

    crew = CrewAIFactory().build_crew(
        runtime_crew=runtime_crew,
        runtime_agents=runtime_agents,
        runtime_tasks=runtime_tasks,
        task_agent_links={"task-version-1": "agent-version-1"},
        task_tool_links={"task-version-1": ["search_docs"]},
        runtime_tools={
            "search_docs": {
                "tool_key": "search_docs",
                "module_path": "api.tools.search_docs",
                "class_name": "SearchDocsTool",
                "default_config_json": {"limit": 3},
            }
        },
    )

    assert loaded_tools == [("api.tools.search_docs", "SearchDocsTool", {"limit": 3})]
    assert len(crew.tasks) == 1
    assert len(crew.tasks[0].tools) == 1
    assert crew.tasks[0].tools[0].name == "fake"


def test_crewai_factory_passes_task_owned_tools_without_red_assignment(monkeypatch):
    loaded_tools = []

    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    def fake_load_tool(module_path: str, class_name: str, config: dict | None = None):
        loaded_tools.append((module_path, class_name, config))
        return FakeTool()

    monkeypatch.setattr(crewai_factory, "load_tool", fake_load_tool)

    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "name": "Hierarchical Tool Crew",
            "process": "hierarchical",
            "manager_llm": "gpt-4o-mini",
            "agent_version_ids": [],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={},
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Unassigned Task",
                "description": "Use a task-owned tool.",
                "expected_output": "A result.",
            }
        },
        task_agent_links={},
        task_tool_links={"task-version-1": ["search_docs"]},
        runtime_tools={
            "search_docs": {
                "tool_key": "search_docs",
                "module_path": "api.tools.search_docs",
                "class_name": "SearchDocsTool",
                "default_config_json": {"limit": 3},
                "attachments": [
                    {"version_id": "task-version-1", "tool_config_json": {"limit": 7}, "sort_order": 0}
                ],
            }
        },
    )

    assert loaded_tools == [("api.tools.search_docs", "SearchDocsTool", {"limit": 7})]
    assert len(crew.tasks) == 1
    assert len(crew.tasks[0].tools) == 1


def test_crewai_factory_keeps_agent_and_task_tools_native_when_keys_overlap(monkeypatch):
    loaded_tools = []

    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    def fake_load_tool(module_path: str, class_name: str, config: dict | None = None):
        loaded_tools.append((module_path, class_name, config))
        return FakeTool()

    monkeypatch.setattr(crewai_factory, "load_tool", fake_load_tool)

    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "name": "Native Tool Crew",
            "process": "sequential",
            "agent_version_ids": ["agent-version-1"],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={
            "agent-version-1": {
                "version_id": "agent-version-1",
                "role": "Web Researcher",
                "goal": "Search the web",
                "backstory": "Uses search tools.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Lookup Task",
                "description": "Search the web and summarize.",
                "expected_output": "A summary.",
            }
        },
        task_agent_links={"task-version-1": "agent-version-1"},
        agent_tool_links={"agent-version-1": ["shared_lookup"]},
        task_tool_links={"task-version-1": ["shared_lookup"]},
        runtime_tools={
            "shared_lookup": {
                "tool_key": "shared_lookup",
                "module_path": "crewai_tools",
                "class_name": "WebsiteSearchTool",
                "default_config_json": {"depth": 1},
                "attachments": [
                    {"version_id": "agent-version-1", "tool_config_json": {"depth": 2}, "sort_order": 0},
                    {"version_id": "task-version-1", "tool_config_json": {"depth": 5}, "sort_order": 0},
                ],
            },
        },
    )

    assert loaded_tools == [
        ("crewai_tools", "WebsiteSearchTool", {"depth": 2}),
        ("crewai_tools", "WebsiteSearchTool", {"depth": 5}),
    ]
    assert len(crew.agents[0].tools) == 1
    assert len(crew.tasks[0].tools) == 1


def test_crewai_factory_does_not_borrow_agent_config_for_task_tool(monkeypatch):
    loaded_tools = []

    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    def fake_load_tool(module_path: str, class_name: str, config: dict | None = None):
        loaded_tools.append((module_path, class_name, config))
        return FakeTool()

    monkeypatch.setattr(crewai_factory, "load_tool", fake_load_tool)

    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "name": "Native Tool Crew",
            "process": "sequential",
            "agent_version_ids": ["agent-version-1"],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={
            "agent-version-1": {
                "version_id": "agent-version-1",
                "role": "Researcher",
                "goal": "Look up data",
                "backstory": "Uses lookup tools.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Lookup Task",
                "description": "Look up supporting data.",
                "expected_output": "A concise summary.",
            }
        },
        task_agent_links={"task-version-1": "agent-version-1"},
        agent_tool_links={"agent-version-1": ["shared_lookup"]},
        task_tool_links={"task-version-1": ["shared_lookup"]},
        runtime_tools={
            "shared_lookup": {
                "tool_key": "shared_lookup",
                "module_path": "crewai_tools",
                "class_name": "WebsiteSearchTool",
                "default_config_json": {"depth": 1},
                "attachments": [
                    {"version_id": "agent-version-1", "tool_config_json": {"depth": 2}, "sort_order": 0}
                ],
            }
        },
    )

    assert loaded_tools == [
        ("crewai_tools", "WebsiteSearchTool", {"depth": 2}),
        ("crewai_tools", "WebsiteSearchTool", {"depth": 1}),
    ]
    assert len(crew.agents[0].tools) == 1
    assert len(crew.tasks[0].tools) == 1


def test_crewai_factory_uses_default_config_when_selected_tool_has_no_matching_attachment(monkeypatch):
    loaded_tools = []

    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    def fake_load_tool(module_path: str, class_name: str, config: dict | None = None):
        loaded_tools.append((module_path, class_name, config))
        return FakeTool()

    monkeypatch.setattr(crewai_factory, "load_tool", fake_load_tool)

    CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "name": "Default Config Crew",
            "process": "sequential",
            "agent_version_ids": ["agent-version-1"],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={
            "agent-version-1": {
                "version_id": "agent-version-1",
                "role": "Researcher",
                "goal": "Look up data",
                "backstory": "Uses lookup tools.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Lookup Task",
                "description": "Look up supporting data.",
                "expected_output": "A concise summary.",
            }
        },
        task_agent_links={"task-version-1": "agent-version-1"},
        task_tool_links={"task-version-1": ["shared_lookup"]},
        runtime_tools={
            "shared_lookup": {
                "tool_key": "shared_lookup",
                "module_path": "crewai_tools",
                "class_name": "WebsiteSearchTool",
                "default_config_json": {"depth": 1},
                "attachments": [
                    {"version_id": "other-version", "tool_config_json": {"depth": 9}, "sort_order": 0}
                ],
            }
        },
    )

    assert loaded_tools == [
        ("crewai_tools", "WebsiteSearchTool", {"depth": 1}),
    ]


def test_crewai_factory_passes_attachment_config_to_tool_constructor(monkeypatch):
    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    load_calls = []

    def fake_load_tool(module_path, class_name, config):
        load_calls.append({"module_path": module_path, "class_name": class_name, "config": config})
        return FakeTool()

    monkeypatch.setattr(crewai_factory, "load_tool", fake_load_tool)

    CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "name": "Creative Crew",
            "process": "sequential",
            "agent_version_ids": ["agent-version-1"],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={
            "agent-version-1": {
                "version_id": "agent-version-1",
                "role": "Image director",
                "goal": "Generate images",
                "backstory": "Uses image tools.",
                "llm": {"model": "gpt-4o-mini"},
            }
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Image Task",
                "description": "Generate an image.",
                "expected_output": "An artifact.",
            }
        },
        task_agent_links={"task-version-1": "agent-version-1"},
        agent_tool_links={"agent-version-1": ["ax.nano_banana_image"]},
        runtime_tools={
            "ax.nano_banana_image": {
                "tool_key": "ax.nano_banana_image",
                "module_path": "api.tools.nano_banana_image_tool",
                "class_name": "AXNanoBananaImageTool",
                "default_config_json": {},
                "config_schema_json": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string"},
                        "aspect_ratio": {"type": "string", "enum": ["1:1", "9:16", "16:9"]},
                        "image_size": {"type": "string", "enum": ["1K", "2K", "4K"]},
                    },
                    "additionalProperties": False,
                },
                "attachments": [
                    {
                        "version_id": "agent-version-1",
                        "tool_config_json": {
                            "model": "gemini-3-pro-image-preview",
                            "aspect_ratio": "16:9",
                            "image_size": "2K",
                        },
                        "sort_order": 0,
                    }
                ],
            }
        },
    )

    assert load_calls == [
        {
            "module_path": "api.tools.nano_banana_image_tool",
            "class_name": "AXNanoBananaImageTool",
            "config": {
                "model": "gemini-3-pro-image-preview",
                "aspect_ratio": "16:9",
                "image_size": "2K",
            },
        }
    ]


def test_crewai_factory_passes_agent_runtime_kwargs():
    agent = CrewAIFactory()._build_agent(
        {
            "version_id": "agent-version-1",
            "role": "Researcher",
            "goal": "Investigate",
            "backstory": "Handles research.",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini-tools"},
            "max_iter": 7,
            "max_rpm": 12,
            "max_execution_time": 90,
            "verbose": True,
            "allow_delegation": True,
            "reasoning": True,
            "max_reasoning_attempts": 3,
            "system_template": "System template",
            "prompt_template": "Prompt template",
            "response_template": "Response template",
            "cache": False,
            "respect_context_window": True,
            "max_retry_limit": 4,
        },
        CrewAIFactory()._make_validation_llm({"llm": {"model": "gpt-4o-mini"}}),
    )

    assert agent.max_iter == 7
    assert agent.max_rpm == 12
    assert agent.max_execution_time == 90
    assert agent.verbose is True
    assert agent.allow_delegation is True
    assert agent.reasoning is True
    assert agent.max_reasoning_attempts == 3
    assert agent.system_template == "System template"
    assert agent.prompt_template == "Prompt template"
    assert agent.response_template == "Response template"
    assert agent.cache is False
    assert agent.respect_context_window is True
    assert agent.max_retry_limit == 4
    assert agent.function_calling_llm is not None
    assert agent.function_calling_llm.model == "gpt-4o-mini-tools"


def test_crewai_factory_rejects_invalid_agent_llm_payload():
    with pytest.raises(ValueError, match="llm"):
        CrewAIFactory()._build_agent(
            {
                "version_id": "agent-version-1",
                "role": "Researcher",
                "goal": "Investigate",
                "backstory": "Handles research.",
                "llm": 123,
            }
        )


def test_crewai_factory_passes_task_runtime_kwargs():
    agent = CrewAIFactory()._build_agent(
        {
            "version_id": "agent-version-1",
            "role": "Researcher",
            "goal": "Investigate",
            "backstory": "Handles research.",
            "llm": {"model": "gpt-4o-mini"},
        },
        CrewAIFactory()._make_validation_llm({"llm": {"model": "gpt-4o-mini"}}),
    )

    task = CrewAIFactory()._build_task(
        {
            "version_id": "task-version-1",
            "task_name": "Research Task",
            "description": "Research the topic.",
            "expected_output": "A report.",
            "async_execution": False,
            "human_input": True,
            "markdown": True,
            "guardrail_max_retries": 2,
            "output_file": "reports/research.md",
            "create_directory": False,
        },
        agent,
        context=[],
        tools=[],
    )

    assert task.human_input is True
    assert task.markdown is True
    assert task.guardrail_max_retries == 2
    assert task.output_file == "reports/research.md"
    assert task.create_directory is False


def test_crewai_factory_rejects_unresolved_object_backed_agent_field():
    with pytest.raises(ValueError, match="callbacks"):
        CrewAIFactory()._build_agent(
            {
                "version_id": "agent-version-1",
                "role": "Researcher",
                "goal": "Investigate",
                "backstory": "Handles research.",
                "llm": {"model": "gpt-4o-mini"},
                "callbacks": ["unresolved"],
            },
            CrewAIFactory()._make_validation_llm({"llm": {"model": "gpt-4o-mini"}}),
        )


def test_crewai_factory_builds_task_output_json_model():
    agent = CrewAIFactory()._build_agent(
        {
            "version_id": "agent-version-1",
            "role": "Researcher",
            "goal": "Investigate",
            "backstory": "Handles research.",
            "llm": {"model": "gpt-4o-mini"},
        },
        CrewAIFactory()._make_validation_llm({"llm": {"model": "gpt-4o-mini"}}),
    )

    task = CrewAIFactory()._build_task(
        {
            "version_id": "12345678-1234-1234-1234-123456789abc",
            "task_name": "123 summary task",
            "description": "Research the topic.",
            "expected_output": "A report.",
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "summary", "type": "str", "description": "Short summary.", "required": True},
                {"name": "confidence", "type": "float", "description": "Score.", "required": False},
            ],
        },
        agent,
        context=[],
        tools=[],
    )

    assert task.output_json.__name__ == "TaskOutput_123_summary_task_12345678"
    assert issubclass(task.output_json, BaseModel)
    assert task.output_json.model_fields["summary"].is_required()
    assert task.output_json.model_fields["summary"].description == "Short summary."
    assert not task.output_json.model_fields["confidence"].is_required()
    assert task.output_json.model_fields["confidence"].default is None
    assert task.output_json.model_fields["confidence"].description == "Score."


def test_validation_llm_returns_schema_compatible_json_for_structured_tasks():
    output_model = CrewAIRuntimePayloadAdapter().task_output_model(
        {
            "version_id": "structured-task-version",
            "task_name": "structured task",
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "title", "type": "str", "required": True},
                {"name": "descriptions", "type": "list", "required": True},
            ],
        }
    )["output_json"]

    response = crewai_factory._ValidationLLM().call(response_model=output_model)

    assert output_model.model_validate_json(response).model_dump() == {
        "title": "runtime-validation",
        "descriptions": ["runtime-validation"],
    }


def test_validation_llm_returns_schema_compatible_json_for_optional_structured_types():
    output_model = CrewAIRuntimePayloadAdapter().task_output_model(
        {
            "version_id": "optional-structured-task-version",
            "task_name": "optional structured task",
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "title", "type": "str", "required": True},
                {"name": "items", "type": "list", "required": False},
                {"name": "count", "type": "int", "required": False},
                {"name": "score", "type": "float", "required": False},
                {"name": "ok", "type": "bool", "required": False},
                {"name": "metadata", "type": "dict", "required": False},
            ],
        }
    )["output_json"]

    response = crewai_factory._ValidationLLM().call(response_model=output_model)

    assert output_model.model_validate_json(response).model_dump() == {
        "title": "runtime-validation",
        "items": ["runtime-validation"],
        "count": 1,
        "score": 1.0,
        "ok": False,
        "metadata": {},
    }


def test_crewai_factory_builds_task_output_pydantic_model_with_empty_name_fallback():
    agent = CrewAIFactory()._build_agent(
        {
            "version_id": "agent-version-1",
            "role": "Researcher",
            "goal": "Investigate",
            "backstory": "Handles research.",
            "llm": {"model": "gpt-4o-mini"},
        },
        CrewAIFactory()._make_validation_llm({"llm": {"model": "gpt-4o-mini"}}),
    )

    task = CrewAIFactory()._build_task(
        {
            "version_id": "",
            "task_name": "",
            "description": "Research the topic.",
            "expected_output": "A report.",
            "output_type": "Output Pydantic",
            "output_schema_fields": [
                {"name": "items", "type": "list", "required": True},
            ],
        },
        agent,
        context=[],
        tools=[],
    )

    assert task.output_pydantic.__name__ == "TaskOutput_00000000"
    assert issubclass(task.output_pydantic, BaseModel)
    assert task.output_pydantic.model_fields["items"].is_required()


def test_crewai_factory_rejects_deprecated_crewai_trigger_context_field():
    agent = CrewAIFactory()._build_agent(
        {
            "version_id": "agent-version-1",
            "role": "Researcher",
            "goal": "Investigate",
            "backstory": "Handles research.",
            "llm": {"model": "gpt-4o-mini"},
        },
        CrewAIFactory()._make_validation_llm({"llm": {"model": "gpt-4o-mini"}}),
    )

    with pytest.raises(ValueError, match="allow_crewai_trigger_context"):
        CrewAIFactory()._build_task(
            {
                "version_id": "task-version-1",
                "task_name": "Research Task",
                "description": "Research the topic.",
                "expected_output": "A report.",
                "allow_crewai_trigger_context": True,
            },
            agent,
            context=[],
            tools=[],
        )


def test_crewai_factory_passes_crew_runtime_kwargs():
    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "name": "Runtime Crew",
            "process": "sequential",
            "agent_version_ids": ["agent-version-1"],
            "task_version_ids": ["task-version-1"],
            "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini-tools"},
            "verbose": True,
            "planning": True,
            "memory": True,
            "cache": False,
            "max_rpm": 20,
            "tracing": True,
        },
        runtime_agents={
            "agent-version-1": {
                "version_id": "agent-version-1",
                "role": "Researcher",
                "goal": "Investigate",
                "backstory": "Handles research.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Research Task",
                "description": "Research the topic.",
                "expected_output": "A report.",
            }
        },
        task_agent_links={"task-version-1": "agent-version-1"},
    )

    assert crew.verbose is True
    assert crew.planning is True
    assert crew.memory is True
    assert crew.cache is False
    assert crew.max_rpm == 20
    assert crew.tracing is True
    assert crew.function_calling_llm is not None
    assert crew.function_calling_llm.model == "gpt-4o-mini-tools"


def test_crewai_factory_rejects_invalid_crew_llm_payloads():
    base_kwargs = {
        "runtime_agents": {
            "agent-version-1": {
                "version_id": "agent-version-1",
                "role": "Researcher",
                "goal": "Investigate",
                "backstory": "Handles research.",
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        },
        "runtime_tasks": {
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Research Task",
                "description": "Research the topic.",
                "expected_output": "A report.",
            }
        },
        "task_agent_links": {"task-version-1": "agent-version-1"},
    }
    runtime_crew = {
        "version_id": "crew-version-1",
        "name": "Runtime Crew",
        "process": "sequential",
        "agent_version_ids": ["agent-version-1"],
        "task_version_ids": ["task-version-1"],
    }

    for llm_field, value in [
        ("manager_llm", {}),
        ("function_calling_llm", {"provider": "openai"}),
        ("planning_llm", 123),
    ]:
        with pytest.raises(ValueError, match=llm_field):
            CrewAIFactory().build_crew(
                runtime_crew={**runtime_crew, llm_field: value},
                **base_kwargs,
            )


def test_crewai_factory_rejects_unresolved_full_shape_crew_config_graph():
    with pytest.raises(ValueError, match="agents"):
        CrewAIFactory().build_crew(
            runtime_crew={
                "version_id": "crew-version-1",
                "name": "Runtime Crew",
                "process": "sequential",
                "agent_version_ids": ["agent-version-1"],
                "task_version_ids": ["task-version-1"],
                "cache": False,
                "agents": [
                    {
                        "role": "Configured Agent",
                        "goal": "Configured goal",
                        "backstory": "Configured backstory.",
                    }
                ],
            },
            runtime_agents={
                "agent-version-1": {
                    "version_id": "agent-version-1",
                    "role": "Runtime Agent",
                    "goal": "Investigate",
                    "backstory": "Handles research.",
                    "llm": {"provider": "openai", "model": "gpt-4o-mini"},
                }
            },
            runtime_tasks={
                "task-version-1": {
                    "version_id": "task-version-1",
                    "task_name": "Runtime Task",
                    "description": "Runtime task.",
                    "expected_output": "Runtime output.",
                }
            },
            task_agent_links={"task-version-1": "agent-version-1"},
        )


def test_crewai_factory_accepts_platform_instrumentation_callbacks():
    step_calls = []
    task_calls = []

    def step_callback(payload):
        step_calls.append(payload)

    def task_callback(payload):
        task_calls.append(payload)

    crew = CrewAIFactory().build_crew(
        runtime_crew={
            "version_id": "crew-version-1",
            "name": "Instrumented Crew",
            "process": "sequential",
            "agent_version_ids": ["agent-version-1"],
            "task_version_ids": ["task-version-1"],
        },
        runtime_agents={
            "agent-version-1": {
                "version_id": "agent-version-1",
                "role": "Researcher",
                "goal": "Investigate",
                "backstory": "Handles research.",
                "llm": {"model": "gpt-4o-mini"},
            }
        },
        runtime_tasks={
            "task-version-1": {
                "version_id": "task-version-1",
                "task_name": "Research Task",
                "description": "Research the topic.",
                "expected_output": "A report.",
            }
        },
        task_agent_links={"task-version-1": "agent-version-1"},
        instrumentation_callbacks={
            "step_callback": step_callback,
            "task_callback": task_callback,
        },
    )

    assert crew.step_callback is step_callback
    assert crew.task_callback is task_callback


def test_crewai_factory_rejects_unknown_tool_config_field(monkeypatch):
    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    monkeypatch.setattr(crewai_factory, "load_tool", lambda *args, **kwargs: FakeTool())

    with pytest.raises(
        ValueError,
        match="Unsupported config field 'unexpected'.*crewai.serper_dev.*agent-version-1",
    ):
        CrewAIFactory().build_crew(
            runtime_crew={
                "version_id": "crew-version-1",
                "name": "Guard Crew",
                "process": "sequential",
                "agent_version_ids": ["agent-version-1"],
                "task_version_ids": ["task-version-1"],
            },
            runtime_agents={
                "agent-version-1": {
                    "version_id": "agent-version-1",
                    "role": "Researcher",
                    "goal": "Search",
                    "backstory": "Uses tools.",
                    "llm": {"model": "gpt-4o-mini"},
                }
            },
            runtime_tasks={
                "task-version-1": {
                    "version_id": "task-version-1",
                    "task_name": "Search Task",
                    "description": "Search.",
                    "expected_output": "Summary.",
                }
            },
            task_agent_links={"task-version-1": "agent-version-1"},
            agent_tool_links={"agent-version-1": ["crewai.serper_dev"]},
            runtime_tools={
                "crewai.serper_dev": {
                    "tool_key": "crewai.serper_dev",
                    "module_path": "crewai_tools",
                    "class_name": "SerperDevTool",
                    "default_config_json": {},
                    "config_schema_json": {
                        "type": "object",
                        "properties": {"n_results": {"type": "integer"}},
                        "additionalProperties": False,
                    },
                    "attachments": [
                        {
                            "version_id": "agent-version-1",
                            "tool_config_json": {"unexpected": True},
                            "sort_order": 0,
                        }
                    ],
                }
            },
        )


def test_crewai_factory_rejects_invalid_tool_config_type(monkeypatch):
    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    monkeypatch.setattr(crewai_factory, "load_tool", lambda *args, **kwargs: FakeTool())

    with pytest.raises(
        ValueError,
        match="Invalid config field 'n_results'.*crewai.serper_dev.*agent-version-1.*integer",
    ):
        CrewAIFactory().build_crew(
            runtime_crew={
                "version_id": "crew-version-1",
                "name": "Guard Crew",
                "process": "sequential",
                "agent_version_ids": ["agent-version-1"],
                "task_version_ids": ["task-version-1"],
            },
            runtime_agents={
                "agent-version-1": {
                    "version_id": "agent-version-1",
                    "role": "Researcher",
                    "goal": "Search",
                    "backstory": "Uses tools.",
                    "llm": {"model": "gpt-4o-mini"},
                }
            },
            runtime_tasks={
                "task-version-1": {
                    "version_id": "task-version-1",
                    "task_name": "Search Task",
                    "description": "Search.",
                    "expected_output": "Summary.",
                }
            },
            task_agent_links={"task-version-1": "agent-version-1"},
            agent_tool_links={"agent-version-1": ["crewai.serper_dev"]},
            runtime_tools={
                "crewai.serper_dev": {
                    "tool_key": "crewai.serper_dev",
                    "module_path": "crewai_tools",
                    "class_name": "SerperDevTool",
                    "default_config_json": {},
                    "config_schema_json": {
                        "type": "object",
                        "properties": {"n_results": {"type": "integer"}},
                        "additionalProperties": False,
                    },
                    "attachments": [
                        {
                            "version_id": "agent-version-1",
                            "tool_config_json": {"n_results": "5"},
                            "sort_order": 0,
                        }
                    ],
                }
            },
        )


def test_crewai_factory_rejects_tool_config_outside_numeric_bounds(monkeypatch):
    from api.runtime.crewai_factory import CrewAIFactory

    with pytest.raises(
        ValueError,
        match="Invalid config field 'poll_timeout_seconds'.*ax.instagram_publish_tool.*between 1 and 300",
    ):
        CrewAIFactory().build_crew(
            runtime_crew={
                "crew_name": "Instagram Crew",
                "agent_version_ids": ["agent-version-1"],
                "task_version_ids": ["task-version-1"],
                "process": "sequential",
            },
            runtime_agents={
                "agent-version-1": {
                    "version_id": "agent-version-1",
                    "role": "Publisher",
                    "goal": "Publish media",
                    "backstory": "Uses Instagram tools.",
                }
            },
            runtime_tasks={
                "task-version-1": {
                    "version_id": "task-version-1",
                    "task_name": "Publish Task",
                    "description": "Publish an artifact.",
                    "expected_output": "Published media.",
                }
            },
            task_agent_links={"task-version-1": "agent-version-1"},
            agent_tool_links={"agent-version-1": ["ax.instagram_publish_tool"]},
            runtime_tools={
                "ax.instagram_publish_tool": {
                    "tool_key": "ax.instagram_publish_tool",
                    "module_path": "api.tools.instagram_publish_tool",
                    "class_name": "AXInstagramPublishTool",
                    "default_config_json": {},
                    "config_schema_json": {
                        "type": "object",
                        "properties": {
                            "poll_timeout_seconds": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 300,
                            }
                        },
                        "additionalProperties": False,
                    },
                    "attachments": [
                        {
                            "version_id": "agent-version-1",
                            "tool_config_json": {"poll_timeout_seconds": 301},
                            "sort_order": 0,
                        }
                    ],
                }
            },
        )


def test_crewai_factory_rejects_closed_schema_without_declared_properties(monkeypatch):
    class FakeTool(BaseTool):
        name: str = "fake"
        description: str = "Fake test tool."

        def _run(self) -> str:
            return "fake"

    monkeypatch.setattr(crewai_factory, "load_tool", lambda *args, **kwargs: FakeTool())

    with pytest.raises(
        ValueError,
        match="Unsupported config field 'unexpected'.*crewai.serper_dev.*agent-version-1",
    ):
        CrewAIFactory().build_crew(
            runtime_crew={
                "version_id": "crew-version-1",
                "name": "Guard Crew",
                "process": "sequential",
                "agent_version_ids": ["agent-version-1"],
                "task_version_ids": ["task-version-1"],
            },
            runtime_agents={
                "agent-version-1": {
                    "version_id": "agent-version-1",
                    "role": "Researcher",
                    "goal": "Search",
                    "backstory": "Uses tools.",
                    "llm": {"model": "gpt-4o-mini"},
                }
            },
            runtime_tasks={
                "task-version-1": {
                    "version_id": "task-version-1",
                    "task_name": "Search Task",
                    "description": "Search.",
                    "expected_output": "Summary.",
                }
            },
            task_agent_links={"task-version-1": "agent-version-1"},
            agent_tool_links={"agent-version-1": ["crewai.serper_dev"]},
            runtime_tools={
                "crewai.serper_dev": {
                    "tool_key": "crewai.serper_dev",
                    "module_path": "crewai_tools",
                    "class_name": "SerperDevTool",
                    "default_config_json": {},
                    "config_schema_json": {
                        "type": "object",
                        "additionalProperties": False,
                    },
                    "attachments": [
                        {
                            "version_id": "agent-version-1",
                            "tool_config_json": {"unexpected": True},
                            "sort_order": 0,
                        }
                    ],
                }
            },
        )


def test_crewai_factory_reports_missing_required_tool_env(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="crewai.serper_dev.*agent-version-1.*SERPER_API_KEY"):
        CrewAIFactory().build_crew(
            runtime_crew={
                "version_id": "crew-version-1",
                "name": "Guard Crew",
                "process": "sequential",
                "agent_version_ids": ["agent-version-1"],
                "task_version_ids": ["task-version-1"],
            },
            runtime_agents={
                "agent-version-1": {
                    "version_id": "agent-version-1",
                    "role": "Researcher",
                    "goal": "Search",
                    "backstory": "Uses tools.",
                    "llm": {"model": "gpt-4o-mini"},
                }
            },
            runtime_tasks={
                "task-version-1": {
                    "version_id": "task-version-1",
                    "task_name": "Search Task",
                    "description": "Search.",
                    "expected_output": "Summary.",
                }
            },
            task_agent_links={"task-version-1": "agent-version-1"},
            agent_tool_links={"agent-version-1": ["crewai.serper_dev"]},
            runtime_tools={
                "crewai.serper_dev": {
                    "tool_key": "crewai.serper_dev",
                    "module_path": "crewai_tools",
                    "class_name": "SerperDevTool",
                    "default_config_json": {},
                    "required_env_vars": [
                        {
                            "name": "SERPER_API_KEY",
                            "description": "API key for Serper",
                            "required": True,
                        }
                    ],
                    "attachments": [
                        {"version_id": "agent-version-1", "tool_config_json": {}, "sort_order": 0}
                    ],
                }
            },
        )


def test_factory_injects_knowledge_tool_only_for_bound_agent():
    from api.runtime.crewai_factory import CrewAIFactory

    factory = CrewAIFactory()
    crew = factory.build_crew(
        runtime_crew={
            "crew_name": "Knowledge Crew",
            "agent_version_ids": ["av1", "av2"],
            "task_version_ids": ["tv1"],
            "process": "sequential",
        },
        runtime_agents={
            "av1": {"version_id": "av1", "role": "Researcher", "goal": "Answer", "backstory": "Helpful."},
            "av2": {"version_id": "av2", "role": "Reviewer", "goal": "Check", "backstory": "Careful."},
        },
        runtime_tasks={
            "tv1": {"version_id": "tv1", "description": "Answer from docs", "expected_output": "Answer"}
        },
        task_agent_links={"tv1": "av1"},
        agent_knowledge_links={"av1": ["k1"]},
        runtime_knowledge={"k1": {"id": "k1", "name": "FAQ", "status": "ready"}},
    )

    agents_by_role = {agent.role: agent for agent in crew.agents}
    assert any(
        getattr(tool, "name", "") == "AX Knowledge Search" for tool in agents_by_role["Researcher"].tools
    )
    assert not any(
        getattr(tool, "name", "") == "AX Knowledge Search" for tool in agents_by_role["Reviewer"].tools
    )


def test_factory_uses_injected_knowledge_search_fn_for_bound_agent_tool():
    from api.runtime.crewai_factory import CrewAIFactory

    calls = []

    def fake_search(query, knowledge_item_ids, top_k):
        calls.append({"query": query, "knowledge_item_ids": knowledge_item_ids, "top_k": top_k})
        return [
            {
                "knowledge_item_id": "k1",
                "knowledge_name": "FAQ",
                "content": "Refund policy is 30 days.",
                "score": 1.0,
                "metadata": {},
            }
        ]

    crew = CrewAIFactory(knowledge_search_fn=fake_search).build_crew(
        runtime_crew={
            "crew_name": "Knowledge Crew",
            "agent_version_ids": ["av1"],
            "task_version_ids": ["tv1"],
            "process": "sequential",
        },
        runtime_agents={
            "av1": {"version_id": "av1", "role": "Researcher", "goal": "Answer", "backstory": "Helpful."},
        },
        runtime_tasks={
            "tv1": {"version_id": "tv1", "description": "Answer from docs", "expected_output": "Answer"}
        },
        task_agent_links={"tv1": "av1"},
        agent_knowledge_links={"av1": ["k1"]},
        runtime_knowledge={"k1": {"id": "k1", "name": "FAQ", "status": "ready"}},
    )

    knowledge_tool = next(tool for tool in crew.agents[0].tools if tool.name == "AX Knowledge Search")
    result = knowledge_tool._run(query="refund policy")

    assert calls == [{"query": "refund policy", "knowledge_item_ids": ["k1"], "top_k": 5}]
    assert result["matches"][0]["content"] == "Refund policy is 30 days."


def test_factory_default_knowledge_search_fn_is_bound_to_db(db, monkeypatch):
    from api.db import models
    from api.runtime.crewai_factory import CrewAIFactory
    from api.services.knowledge_embeddings import DeterministicEmbeddingProvider

    provider = DeterministicEmbeddingProvider(dimension=2)
    monkeypatch.setattr(
        "api.services.knowledge.get_default_embedding_provider",
        lambda: provider,
    )
    item = models.KnowledgeItem(
        workspace_id="00000000-0000-0000-0000-000000000000",
        owner_user_id="00000000-0000-0000-0000-000000000000",
        name="제안요청서",
        status="ready",
        source_file_name="rfp.pdf",
        source_file_size=1,
        storage_bucket="knowledge",
        storage_path="rfp.pdf",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        chunk_count=1,
    )
    db.add(item)
    db.flush()
    db.add(
        models.KnowledgeChunk(
            knowledge_item_id=item.id,
            workspace_id=item.workspace_id,
            chunk_index=0,
            content="제안요청서는 AI 사업계획서 자동화 플랫폼을 요구한다.",
            content_hash="rfp-1",
            metadata_json={"page_start": 1},
            embedding_json=provider.embed_texts(["AI 사업계획서 자동화 플랫폼"])[0],
        )
    )
    db.commit()

    crew = CrewAIFactory(db=db).build_crew(
        runtime_crew={
            "crew_name": "Knowledge Crew",
            "agent_version_ids": ["av1"],
            "task_version_ids": ["tv1"],
            "process": "sequential",
        },
        runtime_agents={
            "av1": {"version_id": "av1", "role": "RFP Analyst", "goal": "Analyze", "backstory": "Careful."},
        },
        runtime_tasks={
            "tv1": {"version_id": "tv1", "description": "Analyze the RFP", "expected_output": "Analysis"}
        },
        task_agent_links={"tv1": "av1"},
        agent_knowledge_links={"av1": [str(item.id)]},
        runtime_knowledge={str(item.id): {"id": str(item.id), "name": "제안요청서", "status": "ready"}},
    )

    knowledge_tool = next(tool for tool in crew.agents[0].tools if tool.name == "AX Knowledge Search")
    result = knowledge_tool._run(query="AI 사업계획서")

    assert result["matches"][0]["knowledge_item_id"] == str(item.id)
    assert "AI 사업계획서 자동화 플랫폼" in result["matches"][0]["content"]
