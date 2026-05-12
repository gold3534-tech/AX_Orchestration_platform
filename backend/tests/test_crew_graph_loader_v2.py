import pytest
from pydantic import ValidationError

from api.schemas.crew_graph import CrewGraphDocument
from api.runtime.loaders import CrewGraphLoader


def _node(node_id: str, node_type: str, data: dict) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "data": data,
    }


def _edge(edge_id: str, source: str, target: str, edge_type: str) -> dict:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": edge_type,
    }


def make_valid_crew_graph_with_chain(task_node_ids: list[str]) -> dict:
    asset_version_ids = [f"tv{index}" for index in range(1, len(task_node_ids) + 1)]
    nodes = [
        _node(
            "crew:1",
            "crew",
            {
                "assetId": "c1",
                "versionId": "cv1",
                "processType": "sequential",
            },
        ),
        _node("agent:1", "agent", {"assetId": "a1", "versionId": "av1"}),
    ]
    edges = []
    for index, task_node_id in enumerate(task_node_ids, start=1):
        nodes.append(
            _node(
                task_node_id,
                "task",
                {
                    "assetId": f"t{index}",
                    "versionId": asset_version_ids[index - 1],
                },
            )
        )
        edges.append(
            _edge(
                f"assign:{index}",
                "agent:1",
                task_node_id,
                "agent_assignment",
            )
        )
        if index > 1:
            edges.append(
                _edge(
                    f"sequence:{index - 1}",
                    task_node_ids[index - 2],
                    task_node_id,
                    "task_sequence",
                )
            )
    return {
        "schemaVersion": 1,
        "nodes": nodes,
        "edges": edges,
    }


def make_valid_publish_graph() -> dict:
    return make_valid_crew_graph_with_chain(["task:1", "task:2"])


def make_valid_hydrated_publish_graph(*, include_tool: bool = False, hierarchical: bool = False) -> dict:
    graph = make_valid_publish_graph()
    graph["entities"] = {
        "agents": {
            "av1": {
                "version_id": "av1",
                "asset_id": "a1",
                "version_no": 1,
                "name": "Researcher",
                "status": "published",
                "payload": {
                    "role": "Researcher",
                    "goal": "Investigate",
                    "backstory": "Handles research.",
                    "llm": {"provider": "openai", "model": "gpt-4o-mini"},
                },
            }
        },
        "tasks": {
            "tv1": {
                "version_id": "tv1",
                "asset_id": "t1",
                "version_no": 1,
                "name": "Task 1",
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
                "version_no": 1,
                "name": "Task 2",
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
                "version_no": 1,
                "name": "Workflow Crew",
                "status": "published",
                "payload": {
                    "process": "hierarchical" if hierarchical else "sequential",
                    "manager_agent_asset_id": None,
                    "manager_llm": "gpt-4o-mini" if hierarchical else {},
                    "payload_json": {},
                },
            }
        },
        "tools": {},
    }
    if include_tool:
        graph["entities"]["tools"]["search_docs"] = {
            "tool_key": "search_docs",
            "name": "Search Docs",
            "description": "Search documentation.",
            "tool_type": "local",
            "module_path": "api.tools.search_docs",
            "class_name": "SearchDocsTool",
            "default_config_json": {"limit": 3},
            "attachments": [
                {
                    "version_id": "av1",
                    "tool_config_json": {"timeout_seconds": 30},
                    "sort_order": 0,
                }
            ],
        }
    return graph


def _knowledge_entity(
    knowledge_id: str,
    *,
    status: str = "ready",
    attachments: list[dict] | None = None,
    embedding_provider: str = "openai",
    embedding_model: str = "text-embedding-3-small",
) -> dict:
    return {
        "id": knowledge_id,
        "name": f"Knowledge {knowledge_id}",
        "status": status,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "attachments": attachments if attachments is not None else [],
    }


def make_direct_tool_metadata_graph() -> dict:
    return {
        "schemaVersion": 1,
        "nodes": [
            _node("crew:1", "crew", {"assetId": "c1", "versionId": "cv1", "processType": "sequential"}),
            _node("agent:1", "agent", {"assetId": "a1", "versionId": "av1"}),
            _node("task:1", "task", {"assetId": "t1", "versionId": "tv1"}),
        ],
        "edges": [
            _edge("assign:1", "agent:1", "task:1", "agent_assignment"),
        ],
        "entities": {
            "tools": {
                "search_docs": {
                    "tool_key": "search_docs",
                    "name": "Search Docs",
                    "description": "Search documentation.",
                    "tool_type": "local",
                    "module_path": "api.tools.search_docs",
                    "class_name": "SearchDocsTool",
                    "default_config_json": {"limit": 3},
                    "attachments": [
                        {
                            "version_id": "tv1",
                            "tool_config_json": {},
                            "sort_order": 0,
                        }
                    ],
                }
            },
        },
    }


def make_direct_graph(*, process: str = "sequential", edges: list[dict] | None = None, include_placeholder: bool = False) -> dict:
    nodes = [
        _node("crew:1", "crew", {"assetId": "c1", "versionId": "cv1", "processType": process}),
        _node("agent:1", "agent", {"assetId": "a1", "versionId": "av1"}),
        _node("agent:2", "agent", {"assetId": "a2", "versionId": "av2"}),
        _node("task:1", "task", {"assetId": "t1", "versionId": "tv1"}),
        _node("task:2", "task", {"assetId": "t2", "versionId": "tv2"}),
        _node("task:3", "task", {"assetId": "t3", "versionId": "tv3"}),
    ]
    if include_placeholder:
        nodes.append(_node("placeholder:1", "placeholder", {"kind": "placeholder"}))

    return {
        "schemaVersion": 1,
        "nodes": nodes,
        "edges": edges if edges is not None else [
            _edge("assign:1", "agent:1", "task:1", "agent_assignment"),
            _edge("assign:2", "agent:2", "task:2", "agent_assignment"),
            _edge("assign:3", "agent:1", "task:3", "agent_assignment"),
            _edge("sequence:3:1", "task:3", "task:1", "task_sequence"),
            _edge("context:3:1", "task:3", "task:1", "task_context"),
        ],
        "entities": {
            "agents": {
                "av1": {
                    "version_id": "av1",
                    "asset_id": "a1",
                    "version_no": 1,
                    "name": "Researcher",
                    "status": "published",
                    "payload": {"role": "Researcher", "goal": "Research", "backstory": "Finds facts."},
                },
                "av2": {
                    "version_id": "av2",
                    "asset_id": "a2",
                    "version_no": 1,
                    "name": "Writer",
                    "status": "published",
                    "payload": {"role": "Writer", "goal": "Write", "backstory": "Writes reports."},
                },
            },
            "tasks": {
                "tv1": {
                    "version_id": "tv1",
                    "asset_id": "t1",
                    "version_no": 1,
                    "name": "Task 1",
                    "status": "published",
                    "payload": {"description": "Task 1", "expected_output": "Task 1 output"},
                },
                "tv2": {
                    "version_id": "tv2",
                    "asset_id": "t2",
                    "version_no": 1,
                    "name": "Task 2",
                    "status": "published",
                    "payload": {"description": "Task 2", "expected_output": "Task 2 output"},
                },
                "tv3": {
                    "version_id": "tv3",
                    "asset_id": "t3",
                    "version_no": 1,
                    "name": "Task 3",
                    "status": "published",
                    "payload": {"description": "Task 3", "expected_output": "Task 3 output"},
                },
            },
            "crews": {
                "cv1": {
                    "version_id": "cv1",
                    "asset_id": "c1",
                    "version_no": 1,
                    "name": "Direct Crew",
                    "status": "published",
                    "payload": {"process": process},
                }
            },
            "tools": {},
        },
    }


def test_crew_graph_schema_accepts_direct_canvas_nodes_and_edges():
    document = CrewGraphDocument.model_validate(
        {
            "schemaVersion": 1,
            "nodes": [
                _node("crew:1", "crew", {"assetId": "c1", "versionId": "cv1", "processType": "sequential"}),
                _node("placeholder:1", "placeholder", {"kind": "placeholder"}),
                _node("agent:1", "agent", {"assetId": "a1", "versionId": "av1"}),
                _node("task:1", "task", {"assetId": "t1", "versionId": "tv1"}),
                _node("task:2", "task", {"assetId": "t2", "versionId": "tv2"}),
            ],
            "edges": [
                _edge("assign:1", "agent:1", "task:1", "agent_assignment"),
                _edge("context:1", "task:2", "task:1", "task_context"),
                _edge("sequence:1", "task:1", "task:2", "task_sequence"),
            ],
            "entities": {},
        }
    )

    assert [node.type for node in document.nodes] == ["crew", "placeholder", "agent", "task", "task"]
    assert [edge.type for edge in document.edges] == [
        "agent_assignment",
        "task_context",
        "task_sequence",
    ]


@pytest.mark.parametrize(
    ("node_type", "edge_type"),
    [
        ("workflow", "agent_assignment"),
        ("tool", "agent_assignment"),
        ("task", "unsupported_edge"),
        ("task", "agent_uses_tool"),
        ("task", "task_uses_tool"),
    ],
)
def test_crew_graph_schema_rejects_unsupported_graph_contract(node_type, edge_type):
    graph = {
        "schemaVersion": 1,
        "nodes": [
            _node("crew:1", "crew", {"assetId": "c1", "versionId": "cv1", "processType": "sequential"}),
            _node("agent:1", "agent", {"assetId": "a1", "versionId": "av1"}),
            _node("task:1", node_type, {"assetId": "t1", "versionId": "tv1"}),
            _node("task:2", "task", {"assetId": "t2", "versionId": "tv2"}),
        ],
        "edges": [_edge("edge:1", "agent:1", "task:1", edge_type)],
    }

    with pytest.raises(ValidationError):
        CrewGraphDocument.model_validate(graph)


def test_crew_graph_tool_metadata_defaults_config_json():
    graph = make_direct_tool_metadata_graph()
    del graph["entities"]["tools"]["search_docs"]["default_config_json"]

    validated = CrewGraphDocument.model_validate(graph)

    assert validated.entities.tools["search_docs"].default_config_json == {}


@pytest.mark.parametrize("metadata_field", ["name", "description", "tool_type", "module_path", "class_name"])
def test_crew_graph_tool_metadata_rejects_blank_strings(metadata_field: str):
    graph = make_direct_tool_metadata_graph()
    graph["entities"]["tools"]["search_docs"][metadata_field] = "   "

    with pytest.raises(ValueError, match="field must not be empty"):
        CrewGraphDocument.model_validate(graph)


def test_crew_graph_loader_builds_direct_node_runtime_snapshot():
    snapshot = CrewGraphLoader().build_runtime_snapshot(make_direct_graph())

    assert snapshot["runtime_crew"]["agent_version_ids"] == ["av1", "av2"]
    assert snapshot["runtime_crew"]["task_version_ids"] == ["tv3", "tv1", "tv2"]
    assert snapshot["task_agent_links"] == {"tv1": "av1", "tv2": "av2", "tv3": "av1"}
    assert snapshot["runtime_tasks"]["tv1"]["context_task_ids"] == ["tv3"]
    assert snapshot["runtime_tasks"]["tv2"].get("context_task_ids", []) == []


def test_crew_graph_loader_allows_placeholder_during_draft_save_only():
    graph = make_direct_graph(include_placeholder=True)

    CrewGraphLoader().validate_draft_graph(graph)

    with pytest.raises(ValueError, match=r"placeholder nodes must be bound.*placeholder:1"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_crew_graph_loader_allows_placeholder_only_draft_save():
    graph = make_direct_graph(include_placeholder=True)
    graph["nodes"] = [
        _node("crew:1", "crew", {"assetId": "c1", "versionId": "cv1", "processType": "sequential"}),
        _node("placeholder:1", "placeholder", {"kind": "placeholder"}),
    ]
    graph["edges"] = []

    CrewGraphLoader().validate_draft_graph(graph)

    with pytest.raises(ValueError, match="at least one Task node is required"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_crew_graph_loader_rejects_orange_context_from_future_source_task():
    graph = make_direct_graph(
        edges=[
            _edge("assign:1", "agent:1", "task:1", "agent_assignment"),
            _edge("assign:2", "agent:2", "task:2", "agent_assignment"),
            _edge("context:2:1", "task:2", "task:1", "task_context"),
        ]
    )

    with pytest.raises(ValueError, match=r"context.*must run before.*task:2 -> task:1"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_crew_graph_loader_rejects_multiple_red_assignments_to_one_task():
    graph = make_direct_graph(
        edges=[
            _edge("assign:1", "agent:1", "task:1", "agent_assignment"),
            _edge("assign:2", "agent:2", "task:1", "agent_assignment"),
        ]
    )

    with pytest.raises(ValueError, match="more than one Agent"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_crew_graph_loader_blocks_sequential_validate_publish_without_all_red_assignments():
    graph = make_direct_graph(edges=[_edge("assign:1", "agent:1", "task:1", "agent_assignment")])

    with pytest.raises(ValueError, match=r"Sequential Crew.*must assign every Task.*task:2"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_crew_graph_loader_rejects_duplicate_task_version_nodes():
    graph = make_direct_graph()
    for node in graph["nodes"]:
        if node["id"] == "task:2":
            node["data"]["versionId"] = "tv1"
            break

    with pytest.raises(ValueError, match=r"Task version.*cannot be reused.*task:1.*task:2"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_crew_graph_loader_rejects_duplicate_agent_version_nodes():
    graph = make_direct_graph()
    for node in graph["nodes"]:
        if node["id"] == "agent:2":
            node["data"]["versionId"] = "av1"
            break

    with pytest.raises(ValueError, match=r"Agent version.*cannot be reused.*agent:1.*agent:2"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_crew_graph_loader_allows_hierarchical_tasks_without_red_assignments():
    graph = make_direct_graph(process="hierarchical", edges=[])
    graph["entities"]["crews"]["cv1"]["payload"] = {
        "process": "hierarchical",
        "manager_llm": "gpt-4o-mini",
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_crew"]["process"] == "hierarchical"
    assert snapshot["runtime_crew"]["task_version_ids"] == ["tv1", "tv2", "tv3"]
    assert snapshot["task_agent_links"] == {}


def test_crew_graph_loader_task_sequence_orders_tasks_and_explicit_context_controls_context():
    graph = make_valid_hydrated_publish_graph()
    graph["edges"].append(_edge("context:1:2", "task:1", "task:2", "task_context"))

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_crew"]["task_version_ids"] == ["tv1", "tv2"]
    assert snapshot["runtime_crew"]["agent_version_ids"] == ["av1"]
    assert snapshot["task_agent_links"] == {"tv1": "av1", "tv2": "av1"}
    assert snapshot["runtime_tasks"]["tv1"]["context_task_ids"] == []
    assert snapshot["runtime_tasks"]["tv2"]["context_task_ids"] == ["tv1"]


def test_crew_graph_loader_uses_direct_assignments_for_task_agent_links():
    graph = make_valid_hydrated_publish_graph()
    graph["nodes"].extend(
        [
            _node("agent:2", "agent", {"assetId": "a2", "versionId": "av2"}),
            _node("task:3", "task", {"assetId": "t3", "versionId": "tv3"}),
        ]
    )
    graph["edges"].extend(
        [
            _edge("assign:3", "agent:2", "task:3", "agent_assignment"),
            _edge("sequence:2", "task:2", "task:3", "task_sequence"),
        ]
    )
    graph["entities"]["agents"]["av2"] = {
        "version_id": "av2",
        "asset_id": "a2",
        "version_no": 1,
        "name": "Writer",
        "status": "published",
        "payload": {
            "role": "Writer",
            "goal": "Write",
            "backstory": "Handles writing.",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
        },
    }
    graph["entities"]["tasks"]["tv3"] = {
        "version_id": "tv3",
        "asset_id": "t3",
        "version_no": 1,
        "name": "Task 3",
        "status": "published",
        "payload": {
            "description": "Task 3",
            "expected_output": "Completed task 3",
            "output_json_schema": None,
        },
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_crew"]["task_version_ids"] == ["tv1", "tv2", "tv3"]
    assert snapshot["task_agent_links"] == {"tv1": "av1", "tv2": "av1", "tv3": "av2"}
    assert snapshot["runtime_crew"]["agent_version_ids"] == ["av1", "av2"]


def test_crew_graph_loader_includes_unassigned_agent_nodes_as_delegation_pool_members():
    graph = make_valid_hydrated_publish_graph()
    graph["nodes"].append(_node("agent:pool", "agent", {"assetId": "a3", "versionId": "av3"}))
    graph["entities"]["agents"]["av3"] = {
        "version_id": "av3",
        "asset_id": "a3",
        "version_no": 1,
        "name": "Specialist",
        "status": "published",
        "payload": {
            "role": "Specialist",
            "goal": "Help delegated work",
            "backstory": "Available for delegation.",
            "llm": {"provider": "openai", "model": "gpt-4o-mini"},
            "allow_delegation": False,
        },
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_crew"]["agent_version_ids"] == ["av1", "av3"]
    assert sorted(snapshot["runtime_agents"].keys()) == ["av1", "av3"]
    assert snapshot["task_agent_links"] == {"tv1": "av1", "tv2": "av1"}


def test_crew_graph_loader_projects_task_tools_from_version_attachments():
    graph = make_valid_hydrated_publish_graph(include_tool=True)
    graph["entities"]["tools"]["search_docs"]["attachments"] = [
        {
            "version_id": "tv1",
            "tool_config_json": {},
            "sort_order": 0,
        }
    ]

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["task_tool_links"] == {"tv1": ["search_docs"]}
    assert sorted(snapshot["runtime_tools"].keys()) == ["search_docs"]
    assert snapshot["runtime_tools"]["search_docs"]["module_path"] == "api.tools.search_docs"


def test_crew_graph_loader_projects_agent_tools_from_version_attachments():
    snapshot = CrewGraphLoader().build_runtime_snapshot(make_valid_hydrated_publish_graph(include_tool=True))

    assert snapshot["agent_tool_links"] == {"av1": ["search_docs"]}
    assert snapshot["tool_links"] == {"av1": ["search_docs"]}
    assert sorted(snapshot["runtime_tools"].keys()) == ["search_docs"]


def test_crew_graph_loader_preserves_tool_metadata_in_runtime_tools():
    from api.runtime.loaders import CrewGraphLoader

    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tools"]["crewai.serper_dev"] = {
        "tool_key": "crewai.serper_dev",
        "name": "Serper Dev Search",
        "description": "Search the web with Serper Dev.",
        "tool_type": "crewai_tool",
        "module_path": "crewai_tools",
        "class_name": "SerperDevTool",
        "default_config_json": {},
        "config_schema_json": {
            "type": "object",
            "properties": {"n_results": {"type": "integer"}},
            "additionalProperties": False,
        },
        "input_schema_json": {
            "type": "object",
            "properties": {"search_query": {"type": "string"}},
            "required": ["search_query"],
        },
        "ui_schema_json": {"fields": {"n_results": {"widget": "number"}}},
        "required_env_vars": [
            {"name": "SERPER_API_KEY", "description": "API key for Serper", "required": True}
        ],
        "attachments": [{"version_id": "av1", "tool_config_json": {"n_results": 2}, "sort_order": 0}],
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)
    tool = snapshot["runtime_tools"]["crewai.serper_dev"]

    assert tool["config_schema_json"]["properties"]["n_results"]["type"] == "integer"
    assert tool["input_schema_json"]["required"] == ["search_query"]
    assert tool["ui_schema_json"]["fields"]["n_results"]["widget"] == "number"
    assert tool["required_env_vars"][0]["name"] == "SERPER_API_KEY"


def test_crew_graph_loader_preserves_tool_config_in_runtime_snapshot():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tools"] = {
        "ax.nano_banana_image": {
            "tool_key": "ax.nano_banana_image",
            "name": "AX Nano Banana Image",
            "description": "Generate image artifacts.",
            "tool_type": "python_class",
            "module_path": "api.tools.nano_banana_image_tool",
            "class_name": "AXNanoBananaImageTool",
            "default_config_json": {"model": "gemini-3.1-flash-image-preview", "aspect_ratio": "1:1", "image_size": "1K"},
            "config_schema_json": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "aspect_ratio": {"type": "string", "enum": ["1:1", "9:16", "16:9"]},
                    "image_size": {"type": "string", "enum": ["1K", "2K", "4K"]},
                },
                "additionalProperties": False,
            },
            "ui_schema_json": {"fields": {"aspect_ratio": {"label": "Output ratio"}}},
            "attachments": [
                {
                    "version_id": "av1",
                    "tool_config_json": {"model": "gemini-3-pro-image-preview", "aspect_ratio": "16:9", "image_size": "2K"},
                    "sort_order": 0,
                }
            ],
        }
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    tool = snapshot["runtime_tools"]["ax.nano_banana_image"]
    assert snapshot["agent_tool_links"] == {"av1": ["ax.nano_banana_image"]}
    assert tool["config_schema_json"]["properties"]["aspect_ratio"]["enum"] == ["1:1", "9:16", "16:9"]
    assert tool["ui_schema_json"]["fields"]["aspect_ratio"]["label"] == "Output ratio"
    assert tool["attachments"][0]["tool_config_json"] == {
        "model": "gemini-3-pro-image-preview",
        "aspect_ratio": "16:9",
        "image_size": "2K",
    }


def test_crew_graph_loader_rejects_invalid_tool_config_in_runtime_snapshot():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tools"] = {
        "ax.nano_banana_image": {
            "tool_key": "ax.nano_banana_image",
            "name": "AX Nano Banana Image",
            "description": "Generate image artifacts.",
            "tool_type": "python_class",
            "module_path": "api.tools.nano_banana_image_tool",
            "class_name": "AXNanoBananaImageTool",
            "default_config_json": {},
            "config_schema_json": {
                "type": "object",
                "properties": {"aspect_ratio": {"type": "string", "enum": ["1:1", "9:16", "16:9"]}},
                "additionalProperties": False,
            },
            "attachments": [
                {"version_id": "av1", "tool_config_json": {"aspect_ratio": "4:5"}, "sort_order": 0}
            ],
        }
    }

    with pytest.raises(ValueError, match="Invalid config field 'aspect_ratio'.*ax.nano_banana_image.*av1"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_crew_graph_loader_preserves_tool_credential_requirements():
    from api.runtime.loaders import CrewGraphLoader

    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tools"]["crewai.serper_dev"] = {
        "tool_key": "crewai.serper_dev",
        "name": "Serper Dev Search",
        "description": "Search the web with Serper Dev.",
        "tool_type": "crewai_tool",
        "module_path": "crewai_tools",
        "class_name": "SerperDevTool",
        "default_config_json": {},
        "credential_requirements": [
            {"provider": "serper", "env_var": "SERPER_API_KEY", "required": True, "injection": "env"}
        ],
        "attachments": [{"version_id": "av1", "tool_config_json": {}, "sort_order": 0}],
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_tools"]["crewai.serper_dev"]["credential_requirements"] == [
        {"provider": "serper", "env_var": "SERPER_API_KEY", "required": True, "injection": "env"}
    ]


def test_crew_graph_loader_exposes_required_inputs_from_task_input_presets():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tasks"]["tv1"]["payload"]["input_presets"] = ["topic"]

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_tasks"]["tv1"]["input_presets"] == ["topic"]
    assert snapshot["required_inputs"] == ["topic"]


def test_crew_graph_loader_exposes_required_inputs_from_agent_and_task_text_tokens():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["agents"]["av1"]["payload"]["goal"] = "Research {topic} for {audience}"
    graph["entities"]["tasks"]["tv1"]["payload"]["description"] = "Create a brief about {topic}"
    graph["entities"]["tasks"]["tv2"]["payload"]["expected_output"] = "A report for {audience}"

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["required_inputs"] == ["audience", "topic"]


def test_crew_graph_loader_publishes_output_schema_from_last_structured_task():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tasks"]["tv2"]["payload"].update(
        {
            "description": "Create card news for {topic}",
            "expected_output": "Structured card news",
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "title_slide", "type": "str", "required": True, "description": "Cover title"},
                {"name": "body_slides", "type": "list", "required": True, "description": "Body slides"},
                {"name": "outro_slide", "type": "str", "required": True, "description": "Outro"},
            ],
        }
    )

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["required_inputs"] == ["topic"]
    assert snapshot["output_schema"] == {
        "type": "object",
        "properties": {
            "title_slide": {"type": "string", "description": "Cover title"},
            "body_slides": {"type": "array", "description": "Body slides"},
            "outro_slide": {"type": "string", "description": "Outro"},
        },
        "required": ["body_slides", "outro_slide", "title_slide"],
    }


def test_crew_graph_loader_accumulates_structured_task_output_schema_for_flow_bindings():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tasks"]["tv1"]["payload"].update(
        {
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "row_number", "type": "int", "required": True},
                {"name": "partner_link", "type": "str", "required": True},
            ],
        }
    )
    graph["entities"]["tasks"]["tv2"]["payload"].update(
        {
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": "og_title", "type": "str", "required": True},
            ],
        }
    )

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["output_schema"] == {
        "type": "object",
        "properties": {
            "row_number": {"type": "integer"},
            "partner_link": {"type": "string"},
            "og_title": {"type": "string"},
        },
        "required": ["og_title", "partner_link", "row_number"],
    }


def test_crew_graph_loader_skips_invalid_output_schema_fields():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tasks"]["tv2"]["payload"].update(
        {
            "output_type": "Output JSON",
            "output_schema_fields": [
                {"name": " valid_default_required ", "type": "str"},
                {"name": "_", "type": "bool"},
                {"name": "bad-name", "type": "str", "required": True},
                {"name": "café", "type": "str", "required": True},
                {"name": "1starts_with_digit", "type": "str", "required": True},
                {"name": "unsupported_type", "type": "tuple", "required": True},
            ],
        }
    )

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["output_schema"] == {
        "type": "object",
        "properties": {
            "valid_default_required": {"type": "string"},
            "_": {"type": "boolean"},
        },
        "required": ["_", "valid_default_required"],
    }


def test_crew_graph_loader_ignores_invalid_or_escaped_input_tokens():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["agents"]["av1"]["payload"]["goal"] = "Ignore {bad-token} and {{escaped}}"
    graph["entities"]["tasks"]["tv1"]["payload"]["description"] = "Use {topic}"

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["required_inputs"] == ["topic"]


def test_crew_graph_loader_accepts_agent_and_task_tool_attachments_without_tool_nodes():
    graph = make_valid_hydrated_publish_graph(include_tool=True)
    graph["entities"]["tools"]["search_docs"]["attachments"].append(
        {
            "version_id": "tv1",
            "tool_config_json": {},
            "sort_order": 0,
        }
    )

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["agent_tool_links"] == {"av1": ["search_docs"]}
    assert snapshot["task_tool_links"] == {"tv1": ["search_docs"]}
    assert sorted(snapshot["runtime_tools"].keys()) == ["search_docs"]


def test_crew_graph_loader_runtime_tools_excludes_unreferenced_tools():
    graph = make_valid_hydrated_publish_graph(include_tool=True)
    graph["entities"]["tools"]["unused_tool"] = {
        "tool_key": "unused_tool",
        "name": "Unused",
        "description": "Should not appear.",
        "tool_type": "local",
        "module_path": "api.tools.unused",
        "class_name": "UnusedTool",
        "default_config_json": {},
        "attachments": [],
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert sorted(snapshot["runtime_tools"].keys()) == ["search_docs"]


def test_crew_graph_loader_rejects_task_without_agent_assignment():
    graph = make_valid_hydrated_publish_graph()
    graph["edges"] = [
        edge for edge in graph["edges"] if edge["type"] != "agent_assignment"
    ]

    with pytest.raises(ValueError, match="assign every Task"):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_orders_tasks_from_task_sequence_edges():
    graph = make_valid_crew_graph_with_chain(["task:1", "task:2", "task:3"])
    graph["entities"] = {
        "agents": {
            "av1": {
                "version_id": "av1",
                "asset_id": "a1",
                "version_no": 1,
                "name": "Researcher",
                "status": "published",
                "payload": {
                    "role": "Researcher",
                    "goal": "Investigate",
                    "backstory": "Handles research.",
                    "llm": {"provider": "openai", "model": "gpt-4o-mini"},
                },
            }
        },
        "tasks": {
            "tv1": {
                "version_id": "tv1",
                "asset_id": "t1",
                "version_no": 1,
                "name": "Task 1",
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
                "version_no": 1,
                "name": "Task 2",
                "status": "published",
                "payload": {
                    "description": "Task 2",
                    "expected_output": "Completed task 2",
                    "output_json_schema": None,
                },
            },
            "tv3": {
                "version_id": "tv3",
                "asset_id": "t3",
                "version_no": 1,
                "name": "Task 3",
                "status": "published",
                "payload": {
                    "description": "Task 3",
                    "expected_output": "Completed task 3",
                    "output_json_schema": None,
                },
            },
        },
        "crews": {
            "cv1": {
                "version_id": "cv1",
                "asset_id": "c1",
                "version_no": 1,
                "name": "Workflow Crew",
                "status": "published",
                "payload": {
                    "process": "sequential",
                    "manager_llm": {},
                    "payload_json": {},
                },
            }
        },
        "tools": {},
    }

    runtime_graph = CrewGraphLoader().build_runtime_snapshot(graph)

    assert runtime_graph["runtime_crew"]["task_version_ids"] == ["tv1", "tv2", "tv3"]


def test_crew_graph_loader_sets_hierarchical_manager_agent_version_to_null_for_manager_llm_mvp():
    graph = make_valid_hydrated_publish_graph(hierarchical=True)
    graph["entities"]["crews"]["cv1"]["payload"]["manager_agent_asset_id"] = "a2"
    graph["entities"]["crews"]["cv1"]["payload"]["manager_llm"] = "gpt-4o-mini"

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_crew"]["process"] == "hierarchical"
    assert snapshot["runtime_crew"]["manager_llm"] == "gpt-4o-mini"
    assert snapshot["runtime_crew"]["manager_agent_version_id"] is None


def test_crew_graph_loader_rejects_effective_hierarchical_crew_without_manager_config():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["crews"]["cv1"]["payload"] = {
        "process": "hierarchical",
        "payload_json": {},
    }

    with pytest.raises(ValueError, match="hierarchical Crew must define"):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_rejects_legacy_only_hierarchical_manager_llm_config():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["crews"]["cv1"]["payload"] = {
        "process": "hierarchical",
        "manager_llm_config_json": {"provider": "openai", "model": "legacy-manager"},
    }

    with pytest.raises(ValueError, match="hierarchical Crew must define"):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_rejects_entity_identifier_mismatch_during_snapshot_build():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["agents"]["av1"]["version_id"] = "av-mismatch"

    with pytest.raises(ValueError, match="does not match node reference"):
        CrewGraphLoader().build_runtime_snapshot(graph)


@pytest.mark.parametrize(
    ("entity_kind", "entity_key"),
    [
        ("agents", "av1"),
        ("tasks", "tv1"),
        ("crews", "cv1"),
    ],
)
def test_crew_graph_loader_rejects_unresolved_publish_entities(
    entity_kind: str,
    entity_key: str,
):
    graph = make_valid_hydrated_publish_graph()
    del graph["entities"][entity_kind][entity_key]

    with pytest.raises(ValueError, match="missing hydrated"):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_snapshot_rejects_unresolved_agent_entity_instead_of_placeholder():
    graph = make_valid_hydrated_publish_graph()
    del graph["entities"]["agents"]["av1"]

    with pytest.raises(ValueError, match="missing hydrated"):
        CrewGraphLoader().build_runtime_snapshot(graph)


@pytest.mark.parametrize("missing_field", ["description", "expected_output"])
def test_crew_graph_loader_rejects_task_entity_missing_required_runtime_fields(
    missing_field: str,
):
    graph = make_valid_hydrated_publish_graph()
    del graph["entities"]["tasks"]["tv1"]["payload"][missing_field]

    with pytest.raises(ValueError, match=missing_field):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_rejects_task_input_presets_that_are_not_lists():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tasks"]["tv1"]["payload"]["input_presets"] = "topic"

    with pytest.raises(ValueError, match="input_presets must be a list of valid input keys"):
        CrewGraphLoader().validate_publish_graph(graph)


@pytest.mark.parametrize("input_preset", ["bad-token", "1topic", "", 123, None])
def test_crew_graph_loader_rejects_invalid_task_input_preset_keys(input_preset):
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["tasks"]["tv1"]["payload"]["input_presets"] = ["topic", input_preset]

    with pytest.raises(ValueError, match="input_presets must be a list of valid input keys"):
        CrewGraphLoader().validate_publish_graph(graph)


@pytest.mark.parametrize(
    ("entity_kind", "entity_version_id", "entity_asset_id"),
    [
        ("agents", "av-mismatch", "a1"),
        ("tasks", "tv-mismatch", "t1"),
        ("crews", "cv-mismatch", "c1"),
    ],
)
def test_crew_graph_loader_rejects_entity_identifier_mismatch_during_publish_validation(
    entity_kind: str,
    entity_version_id: str,
    entity_asset_id: str,
):
    graph = make_valid_hydrated_publish_graph()
    if entity_kind == "agents":
        graph["entities"]["agents"]["av1"]["version_id"] = entity_version_id
        graph["entities"]["agents"]["av1"]["asset_id"] = entity_asset_id
    elif entity_kind == "tasks":
        graph["entities"]["tasks"]["tv1"]["version_id"] = entity_version_id
        graph["entities"]["tasks"]["tv1"]["asset_id"] = entity_asset_id
    else:
        graph["entities"]["crews"]["cv1"]["version_id"] = entity_version_id
        graph["entities"]["crews"]["cv1"]["asset_id"] = entity_asset_id

    with pytest.raises(ValueError, match="does not match node reference"):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_rejects_hierarchical_crew_with_only_manager_agent_reference():
    graph = make_valid_hydrated_publish_graph(hierarchical=True)
    graph["entities"]["crews"]["cv1"]["payload"].pop("manager_llm", None)
    graph["entities"]["crews"]["cv1"]["payload"]["manager_agent_asset_id"] = "a1"

    with pytest.raises(ValueError, match="hierarchical Crew must define manager_llm"):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_rejects_hierarchical_crew_without_worker_agents():
    graph = make_valid_hydrated_publish_graph(hierarchical=True)
    graph["nodes"] = [node for node in graph["nodes"] if node["type"] != "agent"]
    graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "agent_assignment"]
    graph["entities"]["agents"] = {}

    with pytest.raises(ValueError, match="hierarchical Crew must include at least one worker Agent"):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_rejects_invalid_crew_process():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["crews"]["cv1"]["payload"]["process"] = "parallel_universe"

    with pytest.raises(ValueError, match="unsupported crew process"):
        CrewGraphLoader().validate_publish_graph(graph)


def test_crew_graph_loader_canonicalizes_trimmed_crew_process():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["crews"]["cv1"]["payload"]["process"] = " sequential "

    CrewGraphLoader().validate_publish_graph(graph)
    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_crew"]["process"] == "sequential"


def test_crew_graph_loader_preserves_crewai_runtime_attributes_in_snapshot():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["agents"]["av1"]["payload"].update(
        {
            "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini-tools"},
            "max_iter": 5,
            "max_rpm": 10,
            "max_execution_time": 120,
            "verbose": True,
            "allow_delegation": True,
            "reasoning": True,
            "max_reasoning_attempts": 2,
            "system_template": "System template",
            "prompt_template": "Prompt template",
            "response_template": "Response template",
            "cache": False,
            "respect_context_window": True,
        }
    )
    graph["entities"]["tasks"]["tv1"]["payload"].update(
        {
            "async_execution": False,
            "human_input": True,
            "markdown": True,
            "output_type": "Output JSON",
            "output_schema_fields": [{"name": "caption", "type": "str", "required": True}],
            "guardrail_max_retries": 2,
            "output_file": "reports/research.md",
            "create_directory": False,
        }
    )
    graph["entities"]["crews"]["cv1"]["payload"].update(
        {
            "function_calling_llm": {"provider": "openai", "model": "gpt-4o-mini-tools"},
            "verbose": True,
            "planning": True,
            "memory": True,
            "cache": False,
            "max_rpm": 20,
            "tracing": True,
        }
    )

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    agent = snapshot["runtime_agents"]["av1"]
    assert agent["function_calling_llm"] == {"provider": "openai", "model": "gpt-4o-mini-tools"}
    assert agent["max_iter"] == 5
    assert agent["max_rpm"] == 10
    assert agent["max_execution_time"] == 120
    assert agent["verbose"] is True
    assert agent["allow_delegation"] is True
    assert agent["reasoning"] is True
    assert agent["max_reasoning_attempts"] == 2
    assert agent["system_template"] == "System template"
    assert agent["prompt_template"] == "Prompt template"
    assert agent["response_template"] == "Response template"
    assert agent["cache"] is False
    assert agent["respect_context_window"] is True
    assert "payload_json" not in agent
    assert "config_json" not in agent

    task = snapshot["runtime_tasks"]["tv1"]
    assert task["async_execution"] is False
    assert task["human_input"] is True
    assert task["markdown"] is True
    assert task["output_type"] == "Output JSON"
    assert task["output_schema_fields"] == [{"name": "caption", "type": "str", "required": True}]
    assert task["guardrail_max_retries"] == 2
    assert task["output_file"] == "reports/research.md"
    assert task["create_directory"] is False
    assert "payload_json" not in task
    assert "config_json" not in task

    crew = snapshot["runtime_crew"]
    assert crew["function_calling_llm"] == {"provider": "openai", "model": "gpt-4o-mini-tools"}
    assert crew["verbose"] is True
    assert crew["planning"] is True
    assert crew["memory"] is True
    assert crew["cache"] is False
    assert crew["max_rpm"] == 20
    assert crew["tracing"] is True
    assert "payload_json" not in crew
    assert "config_json" not in crew


def test_crew_graph_loader_carries_sparse_top_level_attributes_without_defaults():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["agents"]["av1"]["payload"].update(
        {
            "role": "Sparse Researcher",
            "goal": "Investigate sparse runtime attributes",
            "backstory": "Carries only explicitly stored fields.",
            "cache": False,
            "max_retry_limit": 3,
            "custom_agent_runtime_flag": "kept",
            "payload_json": {"role": "legacy wrapper"},
        }
    )
    graph["entities"]["tasks"]["tv1"]["payload"].update(
        {
            "description": "Sparse task",
            "expected_output": "Sparse task output",
            "output_type": "Pydantic",
            "output_schema_fields": [{"name": "caption", "type": "str", "required": True}],
            "custom_task_runtime_flag": "kept",
            "payload_json": {"description": "legacy wrapper"},
        }
    )
    crew_payload = graph["entities"]["crews"]["cv1"]["payload"]
    crew_payload.pop("manager_llm", None)
    crew_payload.update(
        {
            "process": "sequential",
            "cache": False,
            "tracing": True,
            "custom_crew_runtime_flag": "kept",
            "payload_json": {"process": "legacy wrapper"},
        }
    )

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    agent = snapshot["runtime_agents"]["av1"]
    assert agent["role"] == "Sparse Researcher"
    assert agent["goal"] == "Investigate sparse runtime attributes"
    assert agent["backstory"] == "Carries only explicitly stored fields."
    assert agent["cache"] is False
    assert agent["max_retry_limit"] == 3
    assert agent["custom_agent_runtime_flag"] == "kept"
    assert "payload_json" not in agent

    task = snapshot["runtime_tasks"]["tv1"]
    assert task["description"] == "Sparse task"
    assert task["expected_output"] == "Sparse task output"
    assert task["output_type"] == "Pydantic"
    assert task["output_schema_fields"] == [{"name": "caption", "type": "str", "required": True}]
    assert task["custom_task_runtime_flag"] == "kept"
    assert "payload_json" not in task

    crew = snapshot["runtime_crew"]
    assert crew["process"] == "sequential"
    assert crew["cache"] is False
    assert crew["tracing"] is True
    assert crew["custom_crew_runtime_flag"] == "kept"
    assert "manager_llm" not in crew
    assert "manager_agent_asset_id" not in crew
    assert "payload_json" not in crew


def test_crew_graph_loader_keeps_omitted_and_legacy_config_fields_out_of_runtime_snapshot():
    graph = make_valid_hydrated_publish_graph()
    agent_payload = graph["entities"]["agents"]["av1"]["payload"]
    agent_payload.pop("llm", None)
    agent_payload["llm_config_json"] = {"provider": "openai", "model": "legacy-agent"}
    agent_payload["function_calling_llm_config_json"] = {
        "provider": "openai",
        "model": "legacy-tools",
    }
    crew_payload = graph["entities"]["crews"]["cv1"]["payload"]
    crew_payload.pop("manager_llm", None)
    crew_payload.pop("payload_json", None)
    crew_payload["manager_llm_config_json"] = {"provider": "openai", "model": "legacy-manager"}
    crew_payload["function_calling_llm_config_json"] = {
        "provider": "openai",
        "model": "legacy-crew-tools",
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    agent = snapshot["runtime_agents"]["av1"]
    assert "llm" not in agent
    assert "function_calling_llm" not in agent
    assert "verbose" not in agent
    assert "payload_json" not in agent
    assert "config_json" not in agent

    task = snapshot["runtime_tasks"]["tv1"]
    assert "async_execution" not in task
    assert "allow_crewai_trigger_context" not in task
    assert "payload_json" not in task
    assert "config_json" not in task

    crew = snapshot["runtime_crew"]
    assert "manager_llm" not in crew
    assert "function_calling_llm" not in crew
    assert "verbose" not in crew
    assert "planning" not in crew
    assert "memory" not in crew
    assert "payload_json" not in crew
    assert "config_json" not in crew


@pytest.mark.parametrize(
    "manager_llm",
    [
        {},
        "   ",
        {"provider": "openai"},
        {"provider": "openai", "model": "   "},
        {"provider": "openai", "main_model": "   ", "model": "gpt-4o-mini"},
        1,
    ],
)
def test_crew_graph_loader_rejects_unusable_hierarchical_manager_llm_payload(manager_llm):
    graph = make_valid_hydrated_publish_graph(hierarchical=True)
    graph["entities"]["crews"]["cv1"]["payload"].pop("manager_agent_asset_id", None)
    graph["entities"]["crews"]["cv1"]["payload"]["manager_llm"] = manager_llm

    with pytest.raises(ValueError, match="hierarchical Crew must define manager_llm"):
        CrewGraphLoader().validate_publish_graph(graph)


@pytest.mark.parametrize(
    "manager_llm",
    [
        "gpt-4o-mini",
        {"provider": "openai", "model": "gpt-4o-mini"},
        {"provider": "openai", "main_model": "gpt-4o-mini"},
    ],
)
def test_crew_graph_loader_accepts_usable_hierarchical_manager_llm_payload(manager_llm):
    graph = make_valid_hydrated_publish_graph(hierarchical=True)
    graph["entities"]["crews"]["cv1"]["payload"].pop("manager_agent_asset_id", None)
    graph["entities"]["crews"]["cv1"]["payload"]["manager_llm"] = manager_llm

    CrewGraphLoader().validate_publish_graph(graph)
    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["runtime_crew"]["process"] == "hierarchical"
    assert snapshot["runtime_crew"]["manager_llm"] == manager_llm


def test_crew_graph_document_rejects_independent_tool_nodes():
    graph = make_valid_hydrated_publish_graph(include_tool=True)
    graph["nodes"].append(_node("tool:search_docs", "tool", {"toolKey": "search_docs"}))

    with pytest.raises(ValidationError):
        CrewGraphDocument.model_validate(graph)


def test_crew_graph_document_accepts_layout_metadata():
    document = CrewGraphDocument.model_validate(
        {
            "schemaVersion": 1,
            "layoutDirection": "LR",
            "viewport": {"x": 10, "y": 20, "zoom": 0.8},
            "nodes": [],
            "edges": [],
        }
    )

    assert document.layoutDirection == "LR"
    assert document.viewport.model_dump() == {"x": 10.0, "y": 20.0, "zoom": 0.8}


def test_crew_graph_document_accepts_editor_node_metadata():
    document = CrewGraphDocument.model_validate(
        {
            "schemaVersion": 1,
            "nodes": [
                {
                    "id": "agent:1",
                    "type": "agent",
                    "position": {"x": 0, "y": 0},
                    "data": {
                        "assetId": "a1",
                        "versionId": "av1",
                        "name": "Research Agent",
                        "label": "Research",
                        "kind": "editor",
                    },
                }
            ],
            "edges": [],
        }
    )

    assert document.nodes[0].data.name == "Research Agent"
    assert document.nodes[0].data.label == "Research"
    assert document.nodes[0].data.kind == "editor"


def test_runtime_snapshot_includes_agent_knowledge_links():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["knowledge"] = {
        "k1": {
            "id": "k1",
            "name": "Product FAQ",
            "status": "ready",
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "attachments": [{"version_id": "av1", "sort_order": 0}],
        }
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["agent_knowledge_links"] == {"av1": ["k1"]}
    assert snapshot["runtime_knowledge"]["k1"] == {
        "id": "k1",
        "name": "Product FAQ",
        "status": "ready",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
    }


def test_runtime_snapshot_orders_agent_knowledge_links_by_sort_order_then_id():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["knowledge"] = {
        "k3": _knowledge_entity(
            "k3",
            attachments=[{"version_id": "av1", "sort_order": 2}],
        ),
        "k2": _knowledge_entity(
            "k2",
            attachments=[{"version_id": "av1", "sort_order": 1}],
        ),
        "k1": _knowledge_entity(
            "k1",
            attachments=[{"version_id": "av1", "sort_order": 1}],
        ),
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["agent_knowledge_links"] == {"av1": ["k1", "k2", "k3"]}


def test_runtime_snapshot_excludes_non_agent_knowledge_attachments():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["knowledge"] = {
        "k1": _knowledge_entity("k1", attachments=[{"version_id": "tv1", "sort_order": 0}]),
        "k2": _knowledge_entity(
            "k2",
            attachments=[{"version_id": "unknown-version", "sort_order": 0}],
        ),
        "k3": _knowledge_entity(
            "k3",
            status="draft",
            attachments=[{"version_id": "tv2", "sort_order": 0}],
        ),
        "k4": _knowledge_entity("k4", attachments=[{"version_id": "av1", "sort_order": 0}]),
    }

    snapshot = CrewGraphLoader().build_runtime_snapshot(graph)

    assert snapshot["agent_knowledge_links"] == {"av1": ["k4"]}
    assert set(snapshot["runtime_knowledge"]) == {"k4"}


def test_runtime_snapshot_rejects_non_ready_referenced_agent_knowledge():
    graph = make_valid_hydrated_publish_graph()
    graph["entities"]["knowledge"] = {
        "k1": _knowledge_entity(
            "k1",
            status="draft",
            attachments=[{"version_id": "av1", "sort_order": 0}],
        ),
    }

    with pytest.raises(ValueError, match="Knowledge item k1 is not ready"):
        CrewGraphLoader().build_runtime_snapshot(graph)


def test_runtime_snapshot_includes_empty_knowledge_fields_without_knowledge():
    snapshot = CrewGraphLoader().build_runtime_snapshot(make_valid_hydrated_publish_graph())

    assert snapshot["agent_knowledge_links"] == {}
    assert snapshot["runtime_knowledge"] == {}
