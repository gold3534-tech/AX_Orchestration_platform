import pytest

from api.runtime.loaders import FlowGraphLoader
from api.schemas.flow_graph import FlowGraphDocument


def _crew_node(*, node_id: str = "crew-node-1", asset_id: str = "c1", version_id: str = "cv1") -> dict:
    return {
        "id": node_id,
        "node_type": "crew",
        "ref": {"asset_id": asset_id, "version_id": version_id},
        "position": {"x": 0, "y": 0},
        "display_order": 0,
    }


def test_flow_graph_loader_accepts_published_crew_reference_without_deep_snapshot_validation():
    graph = {"nodes": [_crew_node()], "edges": []}

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        assert asset_id == "c1"
        assert version_id == "cv1"
        # This is intentionally minimal. Flow validation should trust that a
        # published crew's runtime snapshot exists without re-validating the
        # internal snapshot shape.
        return {
            "asset_id": asset_id,
            "version_id": version_id,
            "latest_version_id": version_id,
            "runtime_snapshot_json": {"schemaVersion": 1},
        }

    loaded = FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)

    assert loaded["graph"] is graph
    assert loaded["crew_refs"] == [
        {
            "node_id": "crew-node-1",
            "asset_id": "c1",
            "version_id": "cv1",
            "latest_version_id": "cv1",
            "status": "latest",
        }
    ]


def test_flow_graph_loader_marks_new_version_available_when_latest_differs():
    graph = {"nodes": [_crew_node(version_id="cv1")], "edges": []}

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        return {
            "asset_id": asset_id,
            "version_id": version_id,
            "latest_version_id": "cv2",
            "runtime_snapshot_json": {"schemaVersion": 1},
        }

    loaded = FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)

    assert loaded["crew_refs"][0]["status"] == "new_version_available"
    assert loaded["crew_refs"][0]["latest_version_id"] == "cv2"


@pytest.mark.parametrize("ref_override", [{}, {"asset_id": "c1"}, {"version_id": "cv1"}])
def test_flow_graph_loader_rejects_crew_nodes_missing_pinned_asset_and_version(ref_override: dict):
    node = _crew_node()
    node["ref"] = dict(ref_override)
    graph = {"nodes": [node], "edges": []}

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        raise AssertionError("published_crew_lookup should not be called for invalid pinned refs.")

    with pytest.raises(ValueError, match="missing a pinned asset_id and version_id"):
        FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)


def test_flow_graph_loader_rejects_unpublished_crew_reference():
    graph = {"nodes": [_crew_node(asset_id="c1", version_id="cv1")], "edges": []}

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        return None

    with pytest.raises(ValueError, match="unpublished crew version"):
        FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)


def test_flow_graph_loader_rejects_published_crew_without_runtime_snapshot():
    graph = {"nodes": [_crew_node(asset_id="c1", version_id="cv1")], "edges": []}

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        return {
            "asset_id": asset_id,
            "version_id": version_id,
            "latest_version_id": version_id,
            "runtime_snapshot_json": {},
        }

    with pytest.raises(ValueError, match="missing runtime_snapshot_json"):
        FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)


def test_flow_graph_loader_rejects_crew_node_with_non_object_ref():
    graph = {"nodes": [{"id": "crew-node-1", "node_type": "crew", "ref": "not-a-dict"}], "edges": []}

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        raise AssertionError("published_crew_lookup should not be called for invalid crew refs.")

    with pytest.raises(ValueError, match="ref must be an object"):
        FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)


def test_flow_graph_loader_crew_reference_status_is_latest_when_pinned_matches_latest():
    assert FlowGraphLoader.crew_reference_status("cv1", "cv1") == "latest"


def test_flow_graph_loader_crew_reference_status_is_new_version_available_when_pinned_differs():
    assert FlowGraphLoader.crew_reference_status("cv1", "cv2") == "new_version_available"


def make_flow_graph() -> dict:
    return {
        "schemaVersion": 1,
        "layoutDirection": "LR",
        "nodes": [
            {
                "id": "input:main",
                "type": "input",
                "position": {"x": 64, "y": 160},
                "data": {
                    "fields": [
                        {"name": "topic", "type": "string", "required": True, "description": "Research topic"}
                    ]
                },
            },
            {"id": "start:main", "type": "start", "position": {"x": 320, "y": 160}, "data": {"triggerType": "manual"}},
            {
                "id": "crew:research",
                "type": "crew",
                "position": {"x": 600, "y": 160},
                "data": {
                    "assetId": "crew-asset-id",
                    "versionId": "crew-version-id",
                    "inputMappings": {"topic": {"source": "state", "path": "topic"}},
                },
            },
            {
                "id": "output:main",
                "type": "output",
                "position": {"x": 900, "y": 160},
                "data": {
                    "fields": [
                        {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"}
                    ]
                },
            },
        ],
        "edges": [
            {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
            {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
            {"id": "edge:research:output", "source": "crew:research", "target": "output:main", "type": "flow"},
        ],
        "entities": {
            "crews": {
                "crew-version-id": {
                    "asset_id": "crew-asset-id",
                    "version_id": "crew-version-id",
                    "version_no": 3,
                    "name": "Research Crew",
                    "status": "published",
                    "runtime_snapshot_json": {
                        "schemaVersion": 1,
                        "required_inputs": ["topic"],
                        "output_schema": {
                            "type": "object",
                            "properties": {"final_answer": {"type": "string"}},
                        },
                    },
                }
            }
        },
    }


def make_flow_graph_without_input() -> dict:
    graph = make_flow_graph()
    graph["nodes"] = [node for node in graph["nodes"] if node["type"] != "input"]
    graph["edges"] = [edge for edge in graph["edges"] if edge["source"] != "input:main" and edge["target"] != "input:main"]
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"]["inputMappings"] = {}
    return graph


def test_flow_graph_schema_accepts_canvas_first_nodes():
    document = FlowGraphDocument.model_validate(make_flow_graph())

    assert document.schemaVersion == 1
    assert [node.type for node in document.nodes] == ["input", "start", "crew", "output"]
    assert document.entities.crews["crew-version-id"].runtime_snapshot_json["schemaVersion"] == 1


def _published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
    if asset_id != "crew-asset-id" or version_id != "crew-version-id":
        return None
    return {
        "asset_id": asset_id,
        "version_id": version_id,
        "latest_version_id": version_id,
        "runtime_snapshot_json": {
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "output_schema": {
                "type": "object",
                "properties": {
                    "final_answer": {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def _published_crew_lookup_without_required_inputs(*, asset_id: str, version_id: str) -> dict | None:
    lookup = _published_crew_lookup(asset_id=asset_id, version_id=version_id)
    if lookup is None:
        return None
    lookup["runtime_snapshot_json"] = {
        **lookup["runtime_snapshot_json"],
        "required_inputs": [],
    }
    return lookup


def test_flow_graph_loader_builds_canvas_first_runtime_snapshot():
    graph = make_flow_graph()

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["schemaVersion"] == 1
    assert snapshot["state_schema"]["properties"]["topic"]["type"] == "string"
    assert snapshot["crew_refs"] == [
        {
            "node_id": "crew:research",
            "asset_id": "crew-asset-id",
            "version_id": "crew-version-id",
            "latest_version_id": "crew-version-id",
            "status": "latest",
        }
    ]
    assert snapshot["crew_input_mappings"]["crew:research"]["topic"] == {"source": "state", "path": "topic"}
    assert snapshot["output_fields"][0]["label"] == "Final answer"


def test_flow_graph_loader_adds_implicit_topic_when_input_node_has_no_fields():
    graph = make_flow_graph()
    input_node = next(node for node in graph["nodes"] if node["type"] == "input")
    input_node["data"]["fields"] = []
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"]["inputMappings"] = {}

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["state_schema"] == {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Runtime keyword supplied from the Run page.",
            }
        },
        "required": [],
    }
    assert snapshot["crew_input_mappings"]["crew:research"]["topic"] == {"source": "state", "path": "topic"}


def test_flow_graph_loader_preserves_explicit_topic_field_metadata():
    graph = make_flow_graph()
    input_node = next(node for node in graph["nodes"] if node["type"] == "input")
    input_node["data"]["fields"] = [
        {
            "name": "topic",
            "type": "string",
            "required": True,
            "description": "Custom topic prompt",
            "default": "climate risk",
        }
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["state_schema"]["properties"]["topic"] == {
        "type": "string",
        "description": "Custom topic prompt",
        "default": "climate risk",
    }
    assert snapshot["state_schema"]["required"] == ["topic"]


def test_flow_graph_loader_auto_maps_missing_same_name_required_inputs():
    graph = make_flow_graph()
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"]["inputMappings"] = {}

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["crew_input_mappings"]["crew:research"]["topic"] == {"source": "state", "path": "topic"}


def test_flow_graph_loader_rejects_unmapped_non_reserved_dynamic_prompt_tokens():
    graph = make_flow_graph()
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"]["inputMappings"] = {}

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        lookup = _published_crew_lookup(asset_id=asset_id, version_id=version_id)
        if lookup is None:
            return None
        lookup["runtime_snapshot_json"] = {
            **lookup["runtime_snapshot_json"],
            "required_inputs": ["topic", "card_news_slides"],
        }
        return lookup

    with pytest.raises(ValueError, match="missing required input mapping: card_news_slides"):
        FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)


def test_flow_graph_loader_keeps_explicit_required_input_mapping():
    graph = make_flow_graph()
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"]["inputMappings"] = {"topic": {"source": "literal", "value": "fixed topic"}}

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["crew_input_mappings"]["crew:research"]["topic"] == {
        "source": "literal",
        "value": "fixed topic",
    }


def test_flow_graph_loader_rejects_required_crew_input_without_flow_state_field():
    graph = make_flow_graph_without_input()

    with pytest.raises(ValueError, match="missing required input mapping: topic"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_accepts_canvas_first_runtime_without_input_node():
    graph = make_flow_graph_without_input()

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_without_required_inputs)

    assert snapshot["state_schema"] == {"type": "object", "properties": {}, "required": []}
    assert snapshot["crew_refs"][0]["node_id"] == "crew:research"
    assert snapshot["output_fields"][0]["label"] == "Final answer"


def test_flow_graph_loader_accepts_visual_tool_nodes_outside_execution_path():
    graph = make_flow_graph()
    graph["nodes"].append(
        {
            "id": "tool:crewai.dalle",
            "type": "tool",
            "position": {"x": 760, "y": 320},
            "data": {"label": "DALL-E Tool", "toolKey": "crewai.dalle"},
        }
    )
    graph["edges"].append(
        {
            "id": "edge:research:dalle-tool",
            "source": "crew:research",
            "target": "tool:crewai.dalle",
            "type": "tool_reference",
        }
    )

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert [ref["node_id"] for ref in snapshot["crew_refs"]] == ["crew:research"]


def test_flow_graph_loader_accepts_internal_crew_runtime_tools_without_visual_tool_nodes():
    graph = make_flow_graph()

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        lookup = _published_crew_lookup(asset_id=asset_id, version_id=version_id)
        if lookup is None:
            return None
        lookup["runtime_snapshot_json"] = {
            **lookup["runtime_snapshot_json"],
            "runtime_crew": {"task_version_ids": ["task-version-1"]},
            "runtime_tasks": {"task-version-1": {"task_name": "Generate image"}},
            "runtime_agents": {"agent-version-1": {"agent_name": "Research agent"}},
            "task_agent_links": {"task-version-1": "agent-version-1"},
            "agent_tool_links": {"agent-version-1": ["crewai.directory_read"]},
            "task_tool_links": {"task-version-1": ["crewai.dalle"]},
            "runtime_tools": {
                "crewai.directory_read": {"name": "Directory Read"},
                "crewai.dalle": {"name": "DALL-E Tool"},
            },
        }
        return lookup

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)

    assert all(node["type"] != "tool" for node in snapshot["graph"]["nodes"])
    assert all(edge["type"] != "tool_reference" for edge in snapshot["graph"]["edges"])
    assert snapshot["crew_refs"][0]["node_id"] == "crew:research"


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("router:quality", "tool:crewai.dalle"),
        ("tool:crewai.dalle", "output:main"),
    ],
)
def test_flow_graph_loader_rejects_malformed_tool_reference_edges(source: str, target: str):
    graph = make_flow_graph()
    graph["nodes"].extend(
        [
            {
                "id": "router:quality",
                "type": "router",
                "position": {"x": 760, "y": 260},
                "data": {"conditions": []},
            },
            {
                "id": "tool:crewai.dalle",
                "type": "tool",
                "position": {"x": 760, "y": 320},
                "data": {"label": "DALL-E Tool", "toolKey": "crewai.dalle"},
            },
        ]
    )
    graph["edges"].append(
        {
            "id": "edge:bad-tool-reference",
            "source": source,
            "target": target,
            "type": "tool_reference",
        }
    )

    with pytest.raises(ValueError, match="tool_reference edges must connect Crew -> Tool"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_tool_nodes_on_execution_path():
    graph = make_flow_graph()
    graph["nodes"].append(
        {
            "id": "tool:crewai.dalle",
            "type": "tool",
            "position": {"x": 760, "y": 320},
            "data": {"label": "DALL-E Tool", "toolKey": "crewai.dalle"},
        }
    )
    graph["edges"].append(
        {
            "id": "edge:research:dalle-tool",
            "source": "crew:research",
            "target": "tool:crewai.dalle",
            "type": "flow",
        }
    )

    with pytest.raises(ValueError, match="Tool nodes are visual-only"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_route_edge_into_tool_node():
    graph = make_flow_graph()
    graph["nodes"].append(
        {
            "id": "router:quality",
            "type": "router",
            "position": {"x": 760, "y": 260},
            "data": {
                "conditions": [
                    {
                        "source": {"nodeId": "crew:research", "path": "output.risk_level"},
                        "operator": "equals",
                        "value": "high",
                        "route": "needs_review",
                    }
                ]
            },
        }
    )
    graph["nodes"].append(
        {
            "id": "tool:crewai.dalle",
            "type": "tool",
            "position": {"x": 920, "y": 260},
            "data": {"label": "DALL-E Tool", "toolKey": "crewai.dalle"},
        }
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:router", "source": "crew:research", "target": "router:quality", "type": "flow"},
        {
            "id": "edge:router:dalle-tool",
            "source": "router:quality",
            "target": "tool:crewai.dalle",
            "type": "route",
            "data": {"route": "needs_review"},
        },
    ]

    with pytest.raises(ValueError, match="Tool nodes are visual-only"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_flow_edge_out_of_tool_node():
    graph = make_flow_graph()
    graph["nodes"].append(
        {
            "id": "tool:crewai.dalle",
            "type": "tool",
            "position": {"x": 760, "y": 320},
            "data": {"label": "DALL-E Tool", "toolKey": "crewai.dalle"},
        }
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:dalle-tool", "source": "crew:research", "target": "tool:crewai.dalle", "type": "tool_reference"},
        {"id": "edge:dalle-tool:output", "source": "tool:crewai.dalle", "target": "output:main", "type": "flow"},
    ]

    with pytest.raises(ValueError, match="Tool nodes are visual-only"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_ignores_unreachable_optional_hitl_node_without_prompt():
    graph = make_flow_graph()
    graph["nodes"].append(
        {
            "id": "hitl:draft",
            "type": "hitl",
            "position": {"x": 760, "y": 320},
            "data": {},
        }
    )

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["hitl_contracts"] == {}


def test_flow_graph_loader_accepts_hitl_with_only_max_attempts():
    graph = make_flow_graph()
    graph["nodes"].insert(
        -1,
        {
            "id": "hitl:review",
            "type": "hitl",
            "position": {"x": 760, "y": 160},
            "data": {"maxAttempts": 2},
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["hitl_contracts"]["hitl:review"] == {"maxAttempts": 2}


def test_flow_graph_loader_ignores_legacy_hitl_fields():
    graph = make_flow_graph()
    graph["nodes"].insert(
        -1,
        {
            "id": "hitl:review",
            "type": "hitl",
            "position": {"x": 760, "y": 160},
            "data": {
                "prompt": "",
                "allowedDecisions": [],
                "feedbackPropagation": "none",
                "onNeedsRevision": "continue_with_feedback",
                "maxAttempts": 4,
            },
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["hitl_contracts"]["hitl:review"] == {"maxAttempts": 4}


def test_flow_graph_loader_ignores_invalid_shaped_legacy_hitl_fields():
    graph = make_flow_graph()
    graph["nodes"].insert(
        -1,
        {
            "id": "hitl:review",
            "type": "hitl",
            "position": {"x": 760, "y": 160},
            "data": {
                "prompt": {"template": "Review draft"},
                "allowedDecisions": "approved",
                "feedbackPropagation": {"policy": "none"},
                "onNeedsRevision": ["continue_with_feedback"],
                "maxAttempts": 5,
            },
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["hitl_contracts"]["hitl:review"] == {"maxAttempts": 5}


def test_flow_graph_loader_emits_normalized_hitl_graph_data():
    graph = make_flow_graph()
    graph["nodes"].insert(
        -1,
        {
            "id": "hitl:review",
            "type": "hitl",
            "position": {"x": 760, "y": 160},
            "data": {
                "prompt": "Legacy prompt",
                "allowedDecisions": ["approved"],
                "feedbackPropagation": "all_decisions",
                "onNeedsRevision": "continue_with_feedback",
                "maxAttempts": 6,
            },
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)
    hitl_node = next(node for node in snapshot["graph"]["nodes"] if node["id"] == "hitl:review")

    assert hitl_node["data"] == {"maxAttempts": 6}


def test_flow_graph_loader_accepts_hitl_between_crews_with_default_max_attempts():
    graph = make_flow_graph()
    graph["entities"]["crews"]["crew-version-2"] = {
        **graph["entities"]["crews"]["crew-version-id"],
        "asset_id": "crew-asset-2",
        "version_id": "crew-version-2",
    }
    graph["nodes"].insert(
        3,
        {"id": "hitl:review", "type": "hitl", "position": {"x": 760, "y": 160}, "data": {"prompt": "Review draft"}},
    )
    graph["nodes"].insert(
        4,
        {
            "id": "crew:visual",
            "type": "crew",
            "position": {"x": 940, "y": 160},
            "data": {
                "assetId": "crew-asset-2",
                "versionId": "crew-version-2",
                "inputMappings": {"topic": {"source": "state", "path": "topic"}},
            },
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:visual", "source": "hitl:review", "target": "crew:visual", "type": "flow"},
        {"id": "edge:visual:output", "source": "crew:visual", "target": "output:main", "type": "flow"},
    ]
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"][0]["nodeId"] = "crew:visual"

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        if asset_id == "crew-asset-2" and version_id == "crew-version-2":
            lookup = _published_crew_lookup(asset_id="crew-asset-id", version_id="crew-version-id")
            return None if lookup is None else {**lookup, "asset_id": asset_id, "version_id": version_id}
        return _published_crew_lookup(asset_id=asset_id, version_id=version_id)

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)

    assert snapshot["hitl_contracts"]["hitl:review"] == {"maxAttempts": 3}


def test_flow_graph_loader_ignores_invalid_legacy_hitl_policy():
    graph = make_flow_graph()
    graph["nodes"].insert(
        3,
        {
            "id": "hitl:review",
            "type": "hitl",
            "position": {"x": 760, "y": 160},
            "data": {"prompt": "Review draft", "onNeedsRevision": "reroute_somewhere"},
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["hitl_contracts"]["hitl:review"] == {"maxAttempts": 3}


def test_flow_graph_loader_rejects_bool_hitl_max_attempts():
    graph = make_flow_graph()
    graph["nodes"].insert(
        3,
        {
            "id": "hitl:review",
            "type": "hitl",
            "position": {"x": 760, "y": 160},
            "data": {"prompt": "Review draft", "maxAttempts": True},
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
    ]

    with pytest.raises(ValueError, match="maxAttempts"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_ignores_empty_legacy_hitl_allowed_decisions():
    graph = make_flow_graph()
    graph["nodes"].insert(
        3,
        {
            "id": "hitl:review",
            "type": "hitl",
            "position": {"x": 760, "y": 160},
            "data": {"prompt": "Review draft", "allowedDecisions": []},
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["hitl_contracts"]["hitl:review"] == {"maxAttempts": 3}


def test_flow_graph_loader_rejects_human_feedback_input_mapping():
    graph = make_flow_graph()
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"].setdefault("inputMappings", {})["human_feedback"] = {
        "source": "literal",
        "value": "manual value",
    }

    with pytest.raises(ValueError, match="human_feedback is reserved"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def _hitl_downstream_human_feedback_graph(
    *,
    feedback_propagation: str = "needs_revision_only",
    on_needs_revision: str = "retry_previous",
    allowed_decisions: list[str] | None = None,
) -> dict:
    graph = make_flow_graph()
    hitl_data = {
        "prompt": "Review draft",
        "feedbackPropagation": feedback_propagation,
        "onNeedsRevision": on_needs_revision,
    }
    if allowed_decisions is not None:
        hitl_data["allowedDecisions"] = allowed_decisions
    graph["nodes"].insert(
        3,
        {
            "id": "hitl:review",
            "type": "hitl",
            "position": {"x": 760, "y": 160},
            "data": hitl_data,
        },
    )
    graph["nodes"].insert(
        4,
        {
            "id": "crew:visual",
            "type": "crew",
            "position": {"x": 1040, "y": 160},
            "data": {
                "assetId": "visual-crew",
                "versionId": "visual-v1",
                "inputMappings": {},
            },
        },
    )
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = [
        {"label": "Visual", "source": "node", "nodeId": "crew:visual", "path": "output.raw"}
    ]
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:visual", "source": "hitl:review", "target": "crew:visual", "type": "flow"},
        {"id": "edge:visual:output", "source": "crew:visual", "target": "output:main", "type": "flow"},
    ]
    return graph


def _published_crew_lookup_for_hitl_downstream(*, asset_id: str, version_id: str) -> dict | None:
    if asset_id == "crew-asset-id" and version_id == "crew-version-id":
        return _published_crew_lookup(asset_id=asset_id, version_id=version_id)
    if asset_id == "visual-crew" and version_id == "visual-v1":
        return {
            "asset_id": asset_id,
            "version_id": version_id,
            "latest_version_id": version_id,
            "runtime_snapshot_json": {
                "schemaVersion": 1,
                "required_inputs": ["human_feedback"],
                "output_schema": {"type": "object", "properties": {"raw": {"type": "string"}}},
            },
        }
    return None


def test_flow_graph_loader_allows_authored_human_feedback_prompt_token_without_mapping():
    graph = _hitl_downstream_human_feedback_graph()

    snapshot = FlowGraphLoader().validate(
        graph,
        published_crew_lookup=_published_crew_lookup_for_hitl_downstream,
    )

    assert snapshot["crew_input_mappings"]["crew:visual"] == {}


def test_flow_graph_loader_allows_authored_human_feedback_prompt_token_with_legacy_feedback_propagation():
    graph = _hitl_downstream_human_feedback_graph(
        feedback_propagation="approved_and_needs_revision",
        on_needs_revision="continue_with_feedback",
    )

    snapshot = FlowGraphLoader().validate(
        graph,
        published_crew_lookup=_published_crew_lookup_for_hitl_downstream,
    )

    assert snapshot["crew_input_mappings"]["crew:visual"] == {}


def test_flow_graph_loader_allows_authored_human_feedback_prompt_token_with_legacy_allowed_decisions():
    graph = _hitl_downstream_human_feedback_graph(
        on_needs_revision="continue_with_feedback",
        allowed_decisions=["needs_revision"],
    )

    snapshot = FlowGraphLoader().validate(
        graph,
        published_crew_lookup=_published_crew_lookup_for_hitl_downstream,
    )

    assert snapshot["crew_input_mappings"]["crew:visual"] == {}


def test_flow_graph_loader_allows_authored_human_feedback_prompt_token_with_legacy_non_injecting_policy():
    graph = _hitl_downstream_human_feedback_graph(feedback_propagation="none")

    snapshot = FlowGraphLoader().validate(
        graph,
        published_crew_lookup=_published_crew_lookup_for_hitl_downstream,
    )

    assert snapshot["crew_input_mappings"]["crew:visual"] == {}


def test_flow_graph_loader_rejects_hitl_without_previous_crew():
    graph = make_flow_graph()
    graph["nodes"].insert(
        2,
        {"id": "hitl:review", "type": "hitl", "position": {"x": 460, "y": 160}, "data": {"prompt": "Review draft"}},
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:hitl", "source": "start:main", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:research", "source": "hitl:review", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:output", "source": "crew:research", "target": "output:main", "type": "flow"},
    ]

    with pytest.raises(ValueError, match="HITL node hitl:review must follow a Crew node"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_hitl_connected_to_input():
    graph = make_flow_graph()
    graph["nodes"].insert(
        3,
        {"id": "hitl:review", "type": "hitl", "position": {"x": 760, "y": 160}, "data": {"prompt": "Review draft"}},
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:input", "source": "hitl:review", "target": "input:main", "type": "flow"},
        {"id": "edge:input:output", "source": "input:main", "target": "output:main", "type": "flow"},
    ]

    with pytest.raises(ValueError, match="HITL node hitl:review must connect to a Crew or Output node"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_accepts_required_output_node_without_selected_fields():
    graph = make_flow_graph()
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = []

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["output_fields"] == []


def test_flow_graph_loader_accepts_raw_output_field_without_output_schema():
    graph = make_flow_graph()
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = [
        {"label": "Research Crew / raw", "source": "node", "nodeId": "crew:research", "path": "output.raw"}
    ]

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        lookup = _published_crew_lookup(asset_id=asset_id, version_id=version_id)
        if lookup is None:
            return None
        lookup["runtime_snapshot_json"] = {
            "schemaVersion": 1,
            "required_inputs": ["topic"],
        }
        return lookup

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)

    assert snapshot["output_fields"] == [
        {"label": "Research Crew / raw", "source": "node", "nodeId": "crew:research", "path": "output.raw"}
    ]


def test_flow_graph_loader_rejects_duplicate_output_field_labels():
    graph = make_flow_graph()
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = [
        {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"},
        {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.raw"},
    ]

    with pytest.raises(
        ValueError,
        match="Output node output:main has duplicate output field label 'Final answer'",
    ):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


@pytest.mark.parametrize("label", ["", "   "])
def test_flow_graph_loader_rejects_blank_output_field_labels(label: str):
    graph = make_flow_graph()
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = [
        {"label": label, "source": "node", "nodeId": "crew:research", "path": "output.final_answer"},
    ]

    with pytest.raises(
        ValueError,
        match="Output node output:main field label must not be blank.",
    ):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_duplicate_output_field_labels_after_trimming():
    graph = make_flow_graph()
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = [
        {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"},
        {"label": " Final answer ", "source": "node", "nodeId": "crew:research", "path": "output.raw"},
    ]

    with pytest.raises(
        ValueError,
        match="Output node output:main has duplicate output field label 'Final answer'",
    ):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_duplicate_output_field_labels_across_output_nodes():
    graph = make_flow_graph()
    graph["nodes"].append(
        {
            "id": "output:secondary",
            "type": "output",
            "position": {"x": 900, "y": 280},
            "data": {
                "fields": [
                    {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.risk_level"}
                ]
            },
        }
    )
    graph["edges"].append(
        {"id": "edge:research:output-secondary", "source": "crew:research", "target": "output:secondary", "type": "flow"}
    )

    with pytest.raises(
        ValueError,
        match="Output node output:secondary has duplicate output field label 'Final answer'",
    ):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_treats_empty_schema_version_one_graph_as_canvas_first():
    graph = {"schemaVersion": 1, "nodes": [], "edges": []}

    def published_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
        raise AssertionError("published_crew_lookup should not be called without crew nodes.")

    with pytest.raises(ValueError, match="exactly one Start node is required"):
        FlowGraphLoader().validate(graph, published_crew_lookup=published_crew_lookup)


def test_flow_graph_loader_treats_type_crew_only_schema_version_one_graph_as_canvas_first():
    graph = {
        "schemaVersion": 1,
        "nodes": [
            {
                "id": "crew:research",
                "type": "crew",
                "position": {"x": 600, "y": 160},
                "data": {"assetId": "crew-asset-id", "versionId": "crew-version-id"},
            }
        ],
        "edges": [],
    }

    with pytest.raises(ValueError, match="exactly one Start node is required"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_missing_required_crew_input_mapping():
    graph = make_flow_graph_without_input()

    with pytest.raises(ValueError, match="missing required input mapping"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


@pytest.mark.parametrize(
    "field_override",
    [
        {"source": "node", "path": "output.final_answer"},
        {"source": "node", "nodeId": "crew:unknown", "path": "output.final_answer"},
    ],
)
def test_flow_graph_loader_rejects_output_node_with_unresolvable_node_source(field_override: dict):
    graph = make_flow_graph()
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = [{"label": "Final answer", **field_override}]

    with pytest.raises(ValueError, match="references unknown node output source"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_required_crew_input_mapping_with_unknown_state_path():
    graph = make_flow_graph()
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"]["inputMappings"] = {"topic": {"source": "state", "path": "toipc"}}

    with pytest.raises(ValueError, match="references unknown state input field"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_required_crew_input_mapping_with_unknown_node_output_field():
    graph = make_flow_graph()
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"]["inputMappings"] = {
        "topic": {"source": "node", "nodeId": "crew:research", "path": "output.missing_answer"}
    }

    with pytest.raises(ValueError, match="references unknown node output field"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_output_node_with_nested_path_through_string_field():
    graph = make_flow_graph()
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = [
        {
            "label": "Invalid final answer detail",
            "source": "node",
            "nodeId": "crew:research",
            "path": "output.final_answer.missing",
        }
    ]

    with pytest.raises(ValueError, match="references nonexistent output field"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_rejects_crew_input_mapping_with_nested_path_through_string_field():
    graph = make_flow_graph()
    crew_node = next(node for node in graph["nodes"] if node["type"] == "crew")
    crew_node["data"]["inputMappings"] = {
        "topic": {"source": "node", "nodeId": "crew:research", "path": "output.final_answer.missing"}
    }

    with pytest.raises(ValueError, match="references unknown node output field"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def test_flow_graph_loader_accepts_output_node_with_nested_object_path():
    graph = make_flow_graph()
    output_node = next(node for node in graph["nodes"] if node["type"] == "output")
    output_node["data"]["fields"] = [
        {
            "label": "Metadata summary",
            "source": "node",
            "nodeId": "crew:research",
            "path": "output.metadata.summary",
        }
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["output_fields"][0]["path"] == "output.metadata.summary"


def test_flow_graph_loader_accepts_router_against_structured_output_field():
    graph = make_flow_graph()
    graph["nodes"].insert(
        3,
        {
            "id": "router:quality",
            "type": "router",
            "position": {"x": 760, "y": 260},
            "data": {
                "conditions": [
                    {
                        "source": {"nodeId": "crew:research", "path": "output.risk_level"},
                        "operator": "equals",
                        "value": "high",
                        "route": "needs_review",
                    }
                ]
            },
        },
    )
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:research", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:research:router", "source": "crew:research", "target": "router:quality", "type": "flow"},
        {
            "id": "edge:router:output",
            "source": "router:quality",
            "target": "output:main",
            "type": "route",
            "data": {"route": "default"},
        },
    ]

    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)

    assert snapshot["router_conditions"]["router:quality"][0]["route"] == "needs_review"


def test_flow_graph_loader_rejects_router_against_missing_output_schema_field():
    graph = make_flow_graph()
    graph["nodes"].append(
        {
            "id": "router:quality",
            "type": "router",
            "position": {"x": 760, "y": 260},
            "data": {
                "conditions": [
                    {
                        "source": {"nodeId": "crew:research", "path": "output.unknown_score"},
                        "operator": "equals",
                        "value": "high",
                        "route": "needs_review",
                    }
                ]
            },
        }
    )
    graph["edges"].append(
        {"id": "edge:research:router", "source": "crew:research", "target": "router:quality", "type": "flow"}
    )

    with pytest.raises(ValueError, match="references unknown structured output field"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup)


def make_transfer_flow_graph(*, target_input_mappings: dict | None = None) -> dict:
    graph = make_flow_graph()
    graph["nodes"] = [
        {
            "id": "input:main",
            "type": "input",
            "position": {"x": 64, "y": 160},
            "data": {"fields": [{"name": "topic", "type": "string", "required": True}]},
        },
        {"id": "start:main", "type": "start", "position": {"x": 320, "y": 160}, "data": {"triggerType": "manual"}},
        {
            "id": "crew:content",
            "type": "crew",
            "position": {"x": 600, "y": 160},
            "data": {
                "assetId": "content-crew",
                "versionId": "content-v1",
                "inputMappings": {"topic": {"source": "state", "path": "topic"}},
            },
        },
        {
            "id": "crew:visual",
            "type": "crew",
            "position": {"x": 1040, "y": 160},
            "data": {
                "assetId": "visual-crew",
                "versionId": "visual-v1",
                "inputMappings": target_input_mappings or {},
            },
        },
        {
            "id": "output:main",
            "type": "output",
            "position": {"x": 1480, "y": 160},
            "data": {"fields": [{"label": "Visual", "source": "node", "nodeId": "crew:visual", "path": "output.raw"}]},
        },
    ]
    graph["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:content", "source": "start:main", "target": "crew:content", "type": "flow"},
        {"id": "edge:content:visual", "source": "crew:content", "target": "crew:visual", "type": "flow"},
        {"id": "edge:visual:output", "source": "crew:visual", "target": "output:main", "type": "flow"},
    ]
    return graph


def _published_crew_lookup_for_transfer(*, asset_id: str, version_id: str) -> dict | None:
    snapshots = {
        ("content-crew", "content-v1"): {
            "schemaVersion": 1,
            "required_inputs": ["topic"],
            "output_schema": {
                "type": "object",
                "properties": {
                    "title_slide": {"type": "string"},
                    "body_slides": {"type": "array"},
                    "outro_slide": {"type": "string"},
                },
            },
        },
        ("visual-crew", "visual-v1"): {
            "schemaVersion": 1,
            "required_inputs": ["card_news_slides"],
            "output_schema": {"type": "object", "properties": {"raw": {"type": "string"}}},
        },
    }
    snapshot = snapshots.get((asset_id, version_id))
    if snapshot is None:
        return None
    return {
        "asset_id": asset_id,
        "version_id": version_id,
        "latest_version_id": version_id,
        "runtime_snapshot_json": snapshot,
    }


def test_flow_graph_loader_rejects_unresolved_non_reserved_required_input():
    graph = make_transfer_flow_graph()

    with pytest.raises(ValueError, match="Crew node crew:visual is missing required input mapping: card_news_slides"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)


def test_flow_graph_loader_accepts_transform_input_mapping():
    graph = make_transfer_flow_graph(
        target_input_mappings={
            "card_news_slides": {
                "source": "transform",
                "inputType": "text",
                "nodeId": "crew:content",
                "paths": ["output.title_slide", "output.body_slides", "output.outro_slide"],
                "transform": "join_card_news_slides_v1",
                "maxChars": 8000,
                "overflow": "fail",
            }
        }
    )

    loaded = FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)

    assert loaded["crew_input_mappings"]["crew:visual"]["card_news_slides"] == {
        "source": "transform",
        "paths": ["output.title_slide", "output.body_slides", "output.outro_slide"],
        "nodeId": "crew:content",
        "inputType": "text",
        "transform": "join_card_news_slides_v1",
        "maxChars": 8000,
        "overflow": "fail",
    }


def test_flow_graph_loader_rejects_transform_mapping_with_unknown_output_path():
    graph = make_transfer_flow_graph(
        target_input_mappings={
            "card_news_slides": {
                "source": "transform",
                "inputType": "text",
                "nodeId": "crew:content",
                "paths": ["output.nope"],
                "transform": "join_text_v1",
            }
        }
    )

    with pytest.raises(ValueError, match="references unknown node output field: output.nope"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)


def test_flow_graph_loader_rejects_transform_mapping_from_same_target_node():
    graph = make_transfer_flow_graph(
        target_input_mappings={
            "card_news_slides": {
                "source": "transform",
                "inputType": "text",
                "nodeId": "crew:visual",
                "paths": ["output.raw"],
                "transform": "identity_v1",
            }
        }
    )

    with pytest.raises(
        ValueError,
        match="references non-upstream node output source: crew:visual",
    ):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)


def test_flow_graph_loader_rejects_transform_mapping_from_downstream_node():
    graph = make_transfer_flow_graph(
        target_input_mappings={
            "card_news_slides": {
                "source": "transform",
                "inputType": "text",
                "nodeId": "crew:content",
                "paths": ["output.title_slide"],
                "transform": "identity_v1",
            }
        }
    )
    content_node = next(node for node in graph["nodes"] if node["id"] == "crew:content")
    content_node["data"]["inputMappings"] = {
        "topic": {
            "source": "transform",
            "inputType": "text",
            "nodeId": "crew:visual",
            "paths": ["output.raw"],
            "transform": "identity_v1",
        }
    }

    with pytest.raises(
        ValueError,
        match="references non-upstream node output source: crew:visual",
    ):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)


def test_flow_graph_loader_rejects_transform_file_media_input_type():
    graph = make_transfer_flow_graph(
        target_input_mappings={
            "card_news_slides": {
                "source": "transform",
                "inputType": "image",
                "nodeId": "crew:content",
                "paths": ["output.title_slide"],
                "transform": "identity_v1",
            }
        }
    )

    with pytest.raises(ValueError, match="file/media transfer"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)


def test_flow_graph_loader_rejects_transform_mapping_with_unknown_source_node():
    graph = make_transfer_flow_graph(
        target_input_mappings={
            "card_news_slides": {
                "source": "transform",
                "inputType": "text",
                "nodeId": "crew:unknown",
                "paths": ["output.title_slide"],
                "transform": "identity_v1",
            }
        }
    )

    with pytest.raises(ValueError, match="references unknown node output source"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)


def test_flow_graph_loader_rejects_transform_mapping_with_blank_paths():
    graph = make_transfer_flow_graph(
        target_input_mappings={
            "card_news_slides": {
                "source": "transform",
                "inputType": "text",
                "nodeId": "crew:content",
                "paths": [" ", ""],
                "transform": "identity_v1",
            }
        }
    )

    with pytest.raises(ValueError, match="must define at least one source path"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)


def test_flow_graph_loader_rejects_transform_mapping_with_non_positive_max_chars():
    graph = make_transfer_flow_graph(
        target_input_mappings={
            "card_news_slides": {
                "source": "transform",
                "inputType": "text",
                "nodeId": "crew:content",
                "paths": ["output.title_slide"],
                "transform": "identity_v1",
                "maxChars": 0,
            }
        }
    )

    with pytest.raises(ValueError, match="maxChars must be greater than zero"):
        FlowGraphLoader().validate(graph, published_crew_lookup=_published_crew_lookup_for_transfer)
