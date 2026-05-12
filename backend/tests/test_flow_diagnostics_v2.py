from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import BaseModel

from api.services.llm_catalog import CatalogModel


class _StructuredOutput(BaseModel):
    summary: str
    confidence: float


def _snapshot_with_one_crew() -> dict:
    return {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {
                    "id": "crew:research",
                    "type": "crew",
                    "data": {"assetId": "crew-asset", "versionId": "crew-version"},
                },
                {"id": "output:main", "type": "output", "data": {}},
            ],
            "edges": [
                {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                {"id": "edge:start:crew", "source": "start:main", "target": "crew:research", "type": "flow"},
                {"id": "edge:crew:output", "source": "crew:research", "target": "output:main", "type": "flow"},
            ],
        },
        "crew_refs": [
            {
                "node_id": "crew:research",
                "asset_id": "crew-asset",
                "version_id": "crew-version",
                "latest_version_id": "crew-version",
                "status": "latest",
            }
        ],
        "crew_input_mappings": {
            "crew:research": {"topic": {"source": "state", "path": "topic"}},
        },
        "crew_snapshots": {
            "crew:research": {
                "schemaVersion": 1,
                "required_inputs": ["topic"],
                "runtime_crew": {
                    "crew_name": "Research Crew",
                    "agent_version_ids": ["agent-1"],
                    "task_version_ids": ["task-1"],
                },
                "runtime_agents": {
                    "agent-1": {
                        "role": "Researcher",
                        "goal": "Research the topic",
                        "backstory": "Careful researcher.",
                        "llm": "gpt-4o-mini",
                    }
                },
                "runtime_tasks": {
                    "task-1": {
                        "task_name": "Research",
                        "description": "Research {topic}.",
                        "expected_output": "Structured result.",
                        "output_type": "Output JSON",
                        "output_schema_fields": [
                            {"name": "summary", "type": "str", "required": True},
                            {"name": "confidence", "type": "float", "required": True},
                        ],
                    }
                },
                "task_agent_links": {"task-1": "agent-1"},
                "agent_tool_links": {},
                "task_tool_links": {},
                "runtime_tools": {},
            }
        },
        "output_fields": [
            {"label": "Raw", "source": "node", "nodeId": "crew:research", "path": "output.raw"}
        ],
    }


def test_run_compatibility_diagnostics_calls_build_kickoff_and_validation_llm(monkeypatch):
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_compatibility_diagnostics

    calls: list[str] = []

    class FakeCrew:
        def kickoff(self, *, inputs):
            calls.append(f"kickoff:{inputs['topic']}")
            return {"raw": "diagnostic-output"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            calls.append(f"factory:{execution_mode}")

        def build_crew(self, **kwargs):
            calls.append("build_crew")
            agent = next(iter(kwargs["runtime_agents"].values()))
            llm = flow_diagnostics.CrewAIFactory(execution_mode="validation")._runtime_llm(agent.get("llm"))
            llm.call(response_model=_StructuredOutput)
            calls.append("llm_call")
            return FakeCrew()

    monkeypatch.setattr(flow_diagnostics, "CrewAIFactory", FakeFactory)

    result = run_compatibility_diagnostics(
        snapshot=_snapshot_with_one_crew(),
        inputs={"topic": "MVP"},
    )

    assert result["mode"] == "compatibility"
    assert result["provider_calls"] == "blocked"
    assert result["status"] == "passed"
    assert result["required_credentials"] == ["openai"]
    assert result["crews"][0]["node_id"] == "crew:research"
    assert result["crews"][0]["build_crew"] == "passed"
    assert result["crews"][0]["kickoff"] == "passed"
    assert result["crews"][0]["llm_call"] == "passed"
    assert calls == ["factory:validation", "build_crew", "llm_call", "kickoff:MVP"]


def test_run_compatibility_diagnostics_lists_runtime_context_credentials(monkeypatch):
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_compatibility_diagnostics

    class FakeCrew:
        def kickoff(self, *, inputs):
            return {"raw": "diagnostic-output"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            assert execution_mode == "validation"

        def build_crew(self, **kwargs):
            return FakeCrew()

    snapshot = deepcopy(_snapshot_with_one_crew())
    crew_snapshot = snapshot["crew_snapshots"]["crew:research"]
    crew_snapshot["agent_tool_links"] = {"agent-1": ["ax.google_sheets"]}
    crew_snapshot["runtime_tools"] = {
        "ax.google_sheets": {
            "module_path": "api.tools.google_sheets_tool",
            "class_name": "AXGoogleSheetsTool",
            "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": True},
            "default_config_json": {},
            "credential_requirements": [
                {
                    "provider": "google_workspace",
                    "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
                    "required": True,
                    "injection": "runtime_context",
                }
            ],
        }
    }
    monkeypatch.setattr(flow_diagnostics, "CrewAIFactory", FakeFactory)

    result = run_compatibility_diagnostics(snapshot=snapshot, inputs={"topic": "MVP"})

    assert "google_workspace" in result["required_credentials"]


def test_run_compatibility_diagnostics_reports_failed_crew(monkeypatch):
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_compatibility_diagnostics

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            assert execution_mode == "validation"

        def build_crew(self, **kwargs):
            raise ValueError("CrewAI assembly failed for Research Crew")

    monkeypatch.setattr(flow_diagnostics, "CrewAIFactory", FakeFactory)

    result = run_compatibility_diagnostics(
        snapshot=_snapshot_with_one_crew(),
        inputs={"topic": "MVP"},
    )

    assert result["status"] == "failed"
    assert result["crews"][0]["build_crew"] == "failed"
    assert result["crews"][0]["llm_call"] == "failed"
    assert "CrewAI assembly failed" in result["crews"][0]["error"]


def test_run_compatibility_diagnostics_reports_failed_kickoff_before_llm_proven(monkeypatch):
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_compatibility_diagnostics

    class FakeCrew:
        def kickoff(self, *, inputs):
            raise RuntimeError("kickoff failed before validation output")

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            assert execution_mode == "validation"

        def build_crew(self, **kwargs):
            return FakeCrew()

    monkeypatch.setattr(flow_diagnostics, "CrewAIFactory", FakeFactory)

    result = run_compatibility_diagnostics(
        snapshot=_snapshot_with_one_crew(),
        inputs={"topic": "MVP"},
    )

    assert result["status"] == "failed"
    assert result["crews"][0]["build_crew"] == "passed"
    assert result["crews"][0]["kickoff"] == "failed"
    assert result["crews"][0]["llm_call"] == "failed"
    assert "kickoff failed" in result["crews"][0]["error"]


def test_run_compatibility_diagnostics_redacts_error_values(monkeypatch):
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_compatibility_diagnostics

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            assert execution_mode == "validation"

        def build_crew(self, **kwargs):
            raise ValueError("CrewAI assembly failed with serper-secret")

    monkeypatch.setattr(flow_diagnostics, "CrewAIFactory", FakeFactory)

    result = run_compatibility_diagnostics(
        snapshot=_snapshot_with_one_crew(),
        inputs={"topic": "MVP"},
        redaction_values={"serper-secret"},
    )

    assert result["status"] == "failed"
    assert "serper-secret" not in result["crews"][0]["error"]
    assert "[redacted]" in result["crews"][0]["error"]


def test_run_compatibility_diagnostics_reports_effective_default_llm(monkeypatch):
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_compatibility_diagnostics

    class FakeCrew:
        def kickoff(self, *, inputs):
            return {"raw": "ok"}

    class FakeFactory:
        def __init__(self, *, execution_mode="validation", llm_catalog=None):
            assert execution_mode == "validation"
            assert llm_catalog["openai/gpt-4o-mini"].credential_provider == "openai"

        def build_crew(self, **kwargs):
            return FakeCrew()

    catalog = {
        "openai/gpt-4o-mini": CatalogModel(
            provider_key="openai",
            provider_display_name="OpenAI",
            provider_type="hosted",
            credential_provider="openai",
            model_key="openai/gpt-4o-mini",
            model_display_name="GPT-4o mini",
            llm_metadata_json={
                "pricing": {
                    "input_per_1m_tokens": 0.15,
                    "output_per_1m_tokens": 0.6,
                    "currency": "USD",
                }
            },
            provider_metadata_json={},
        )
    }
    snapshot = _snapshot_with_one_crew()
    snapshot["crew_snapshots"]["crew:research"]["runtime_agents"]["agent-1"].pop("llm")
    monkeypatch.setattr(flow_diagnostics, "CrewAIFactory", FakeFactory)

    result = run_compatibility_diagnostics(snapshot=snapshot, inputs={"topic": "MVP"}, llm_catalog=catalog)

    assert result["required_credentials"] == ["openai"]
    assert result["llm_diagnostics"][0]["effective_llm"] == {
        "source": "default",
        "provider": "openai",
        "model": "openai/gpt-4o-mini",
    }
    assert result["llm_diagnostics"][0]["pricing_available"] is True


def test_run_tool_mock_call_check_validates_args_schema_without_calling_run(monkeypatch):
    from crewai.tools import BaseTool
    from pydantic import BaseModel
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_tool_mock_call_check

    calls: list[str] = []

    class SearchArgs(BaseModel):
        search_query: str
        limit: int

    class FakeSearchTool(BaseTool):
        name: str = "Fake Search"
        description: str = "Search without calling an API."
        args_schema: type[BaseModel] = SearchArgs

        def _run(self, **kwargs):
            calls.append("_run")
            return "external result"

    monkeypatch.setattr(flow_diagnostics, "load_tool_class", lambda module_path, class_name: FakeSearchTool)

    result = run_tool_mock_call_check(
        snapshot={
            "schemaVersion": 1,
            "crew_snapshots": {
                "crew:research": {
                    "runtime_crew": {
                        "agent_version_ids": ["agent-1"],
                        "task_version_ids": ["task-1"],
                    },
                    "runtime_agents": {},
                    "runtime_tasks": {},
                    "task_agent_links": {"task-1": "agent-1"},
                    "agent_tool_links": {"agent-1": ["search_docs"]},
                    "task_tool_links": {},
                    "runtime_tools": {
                        "search_docs": {
                            "module_path": "api.tools.search_docs",
                            "class_name": "SearchDocsTool",
                            "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": False},
                            "default_config_json": {},
                            "attachments": [{"version_id": "agent-1", "tool_config_json": {}}],
                            "credential_requirements": [
                                {"provider": "serper", "env_var": "SERPER_API_KEY", "required": True, "injection": "env"}
                            ],
                        }
                    },
                }
            },
        },
        live_credential_providers=[],
    )

    assert result["status"] == "passed"
    assert calls == []
    tool = result["tools"][0]
    assert tool["tool_key"] == "search_docs"
    assert tool["checks"]["args_schema"] == "passed"
    assert tool["sample_input"] == {"limit": 1, "search_query": "runtime-validation"}
    assert tool["external_call"] == "not_called"
    assert tool["credential_requirements"][0]["available_for_live_run"] is False


def test_run_tool_mock_call_check_validates_class_args_schema_when_constructor_fails(monkeypatch):
    from crewai.tools import BaseTool
    from pydantic import BaseModel
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_tool_mock_call_check

    class SearchArgs(BaseModel):
        query: str

    class FailingInitTool(BaseTool):
        name: str = "Failing Init"
        description: str = "Fails after class metadata is inspected."
        args_schema: type[BaseModel] = SearchArgs

        def __init__(self, **kwargs):
            raise RuntimeError("constructor side effect failed")

        def _run(self, **kwargs):
            raise AssertionError("_run must not be called")

    monkeypatch.setattr(flow_diagnostics, "load_tool_class", lambda module_path, class_name: FailingInitTool)

    result = run_tool_mock_call_check(
        snapshot={
            "schemaVersion": 1,
            "crew_snapshots": {
                "crew:research": {
                    "runtime_crew": {"agent_version_ids": ["agent-1"]},
                    "agent_tool_links": {"agent-1": ["fragile_tool"]},
                    "runtime_tools": {
                        "fragile_tool": {
                            "module_path": "api.tools.fragile",
                            "class_name": "FragileTool",
                            "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": False},
                            "default_config_json": {},
                            "credential_requirements": [
                                {"provider": "serper", "env_var": "SERPER_API_KEY", "required": False, "injection": "env"}
                            ],
                        }
                    },
                }
            },
        },
        live_credential_providers=["serper"],
    )

    tool = result["tools"][0]
    assert result["status"] == "failed"
    assert tool["credential_requirements"] == [
        {
            "provider": "serper",
            "env_var": "SERPER_API_KEY",
            "required": False,
            "available_for_live_run": True,
        }
    ]
    assert tool["checks"]["args_schema"] == "passed"
    assert tool["sample_input"] == {"query": "runtime-validation"}
    assert tool["checks"]["instantiate"] == "failed"
    assert "constructor side effect failed" in tool["error"]


def test_run_tool_mock_call_check_marks_google_sheets_runtime_context_available():
    from api.runtime.flow_diagnostics import run_tool_mock_call_check

    result = run_tool_mock_call_check(
        snapshot={
            "schemaVersion": 1,
            "crew_snapshots": {
                "crew:research": {
                    "runtime_crew": {"agent_version_ids": ["agent-1"]},
                    "agent_tool_links": {"agent-1": ["custom.sheets_alias"]},
                    "runtime_tools": {
                        "custom.sheets_alias": {
                            "module_path": "api.tools.google_sheets_tool",
                            "class_name": "AXGoogleSheetsTool",
                            "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": True},
                            "default_config_json": {},
                            "credential_requirements": [
                                {
                                    "provider": "google_workspace",
                                    "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
                                    "required": True,
                                    "injection": "runtime_context",
                                }
                            ],
                        }
                    },
                }
            },
        },
        live_credential_providers=["google_workspace"],
    )

    tool = result["tools"][0]
    assert result["status"] == "passed"
    assert tool["tool_key"] == "custom.sheets_alias"
    assert tool["credential_requirements"] == [
        {
            "provider": "google_workspace",
            "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
            "required": True,
            "available_for_live_run": True,
        }
    ]


def test_run_tool_mock_call_check_deduplicates_manager_agent_tool_when_also_runtime_agent(monkeypatch):
    from crewai.tools import BaseTool
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_tool_mock_call_check

    class ManagerTool(BaseTool):
        name: str = "Manager Tool"
        description: str = "Manager tool."

        def _run(self, **kwargs):
            raise AssertionError("_run must not be called")

    monkeypatch.setattr(flow_diagnostics, "load_tool_class", lambda module_path, class_name: ManagerTool)

    result = run_tool_mock_call_check(
        snapshot={
            "schemaVersion": 1,
            "crew_snapshots": {
                "crew:research": {
                    "runtime_crew": {
                        "manager_agent_version_id": "manager-agent-1",
                        "agent_version_ids": ["manager-agent-1"],
                    },
                    "agent_tool_links": {"manager-agent-1": ["manager_tool"]},
                    "runtime_tools": {
                        "manager_tool": {
                            "module_path": "api.tools.manager",
                            "class_name": "ManagerTool",
                            "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": False},
                            "default_config_json": {},
                        }
                    },
                }
            },
        },
        live_credential_providers=[],
    )

    assert result["status"] == "passed"
    assert [tool["tool_key"] for tool in result["tools"]] == ["manager_tool"]
    assert result["tools"][0]["owner_type"] == "agent"
    assert result["tools"][0]["owner_version_id"] == "manager-agent-1"


def test_run_tool_mock_call_check_generates_representative_samples_for_json_schema(monkeypatch):
    from typing import Literal

    from crewai.tools import BaseTool
    from pydantic import BaseModel, Field
    from api.runtime import flow_diagnostics
    from api.runtime.flow_diagnostics import run_tool_mock_call_check

    class NestedArgs(BaseModel):
        category: str = Field(min_length=3)

    class SearchArgs(BaseModel):
        mode: Literal["recent", "popular"]
        page: int = Field(ge=5)
        filters: NestedArgs
        tags: list[str] = Field(min_length=1)

    class FakeSearchTool(BaseTool):
        name: str = "Fake Search"
        description: str = "Search without calling an API."
        args_schema: type[BaseModel] = SearchArgs

        def _run(self, **kwargs):
            raise AssertionError("_run must not be called")

    monkeypatch.setattr(flow_diagnostics, "load_tool_class", lambda module_path, class_name: FakeSearchTool)

    result = run_tool_mock_call_check(
        snapshot={
            "schemaVersion": 1,
            "crew_snapshots": {
                "crew:research": {
                    "runtime_crew": {"agent_version_ids": ["agent-1"]},
                    "agent_tool_links": {"agent-1": ["search_docs"]},
                    "runtime_tools": {
                        "search_docs": {
                            "module_path": "api.tools.search_docs",
                            "class_name": "SearchDocsTool",
                            "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": False},
                            "default_config_json": {},
                        }
                    },
                }
            },
        },
        live_credential_providers=[],
    )

    assert result["status"] == "passed"
    assert result["tools"][0]["sample_input"] == {
        "filters": {"category": "runtime-validation"},
        "mode": "recent",
        "page": 5,
        "tags": ["runtime-validation"],
    }


def test_run_tool_mock_call_check_reports_import_failure_after_allowlist_passes():
    from api.runtime.flow_diagnostics import run_tool_mock_call_check

    result = run_tool_mock_call_check(
        snapshot={
            "schemaVersion": 1,
            "crew_snapshots": {
                "crew:research": {
                    "runtime_crew": {"agent_version_ids": ["agent-1"]},
                    "agent_tool_links": {"agent-1": ["missing_tool"]},
                    "runtime_tools": {
                        "missing_tool": {
                            "module_path": "api.tools.no_such_module",
                            "class_name": "MissingTool",
                            "config_schema_json": {"type": "object", "properties": {}, "additionalProperties": False},
                            "default_config_json": {},
                        }
                    },
                }
            },
        },
        live_credential_providers=[],
    )

    tool = result["tools"][0]
    assert result["status"] == "failed"
    assert tool["checks"]["allowlist"] == "passed"
    assert tool["checks"]["import"] == "failed"
