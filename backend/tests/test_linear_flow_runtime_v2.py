from __future__ import annotations

import pytest

from api.runtime.linear_flow_runtime import (
    UnsupportedGraphError,
    build_crew_inputs,
    build_linear_path,
    build_output_payload,
    crew_runtime_snapshot_for_node,
    normalize_crew_output,
    read_path,
)


def _linear_snapshot() -> dict:
    return {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "input:main", "type": "input", "data": {}},
                {"id": "start:main", "type": "start", "data": {}},
                {
                    "id": "crew:research",
                    "type": "crew",
                    "data": {"versionId": "crew-version-1"},
                },
                {
                    "id": "hitl:review",
                    "type": "hitl",
                    "data": {"prompt": "Review this output"},
                },
                {
                    "id": "output:main",
                    "type": "output",
                    "data": {},
                },
            ],
            "edges": [
                {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
                {"id": "edge:start:crew", "source": "start:main", "target": "crew:research", "type": "flow"},
                {"id": "edge:crew:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
                {"id": "edge:hitl:output", "source": "hitl:review", "target": "output:main", "type": "flow"},
            ],
        },
        "crew_input_mappings": {
            "crew:research": {
                "topic": {"source": "state", "path": "topic"},
                "tone": {"source": "literal", "value": "concise"},
            }
        },
        "output_fields": [
            {"label": "Final answer", "source": "node", "nodeId": "crew:research", "path": "output.final_answer"},
            {"label": "Topic", "source": "state", "path": "topic"},
        ],
    }


def test_build_linear_path_skips_input_and_starts_at_start_successor():
    path = build_linear_path(_linear_snapshot())

    assert [node["id"] for node in path] == [
        "crew:research",
        "hitl:review",
        "output:main",
    ]


def test_build_linear_path_rejects_branching():
    snapshot = _linear_snapshot()
    snapshot["graph"]["edges"].append(
        {"id": "edge:start:extra", "source": "start:main", "target": "output:extra", "type": "flow"}
    )
    snapshot["graph"]["nodes"].append({"id": "output:extra", "type": "output", "data": {}})

    with pytest.raises(UnsupportedGraphError, match="multiple outgoing edges"):
        build_linear_path(snapshot)


def test_build_linear_path_rejects_nodes_after_output():
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "start:main", "type": "start", "data": {}},
                {"id": "output:main", "type": "output", "data": {}},
                {"id": "hitl:review", "type": "hitl", "data": {}},
            ],
            "edges": [
                {"id": "edge:start:output", "source": "start:main", "target": "output:main", "type": "flow"},
                {"id": "edge:output:hitl", "source": "output:main", "target": "hitl:review", "type": "flow"},
            ],
        },
    }

    with pytest.raises(UnsupportedGraphError, match="output node must terminate the linear path"):
        build_linear_path(snapshot)


def test_build_linear_path_rejects_input_after_output():
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "start:main", "type": "start", "data": {}},
                {"id": "output:main", "type": "output", "data": {}},
                {"id": "input:late", "type": "input", "data": {}},
            ],
            "edges": [
                {"id": "edge:start:output", "source": "start:main", "target": "output:main", "type": "flow"},
                {"id": "edge:output:input", "source": "output:main", "target": "input:late", "type": "flow"},
            ],
        },
    }

    with pytest.raises(UnsupportedGraphError, match="Input nodes are not executable after start"):
        build_linear_path(snapshot)


def test_build_linear_path_rejects_unknown_node_kind():
    snapshot = {
        "schemaVersion": 1,
        "graph": {
            "nodes": [
                {"id": "start:main", "type": "start", "data": {}},
                {"id": "mystery:main", "type": "mystery", "data": {}},
                {"id": "output:main", "type": "output", "data": {}},
            ],
            "edges": [
                {"id": "edge:start:mystery", "source": "start:main", "target": "mystery:main", "type": "flow"},
                {"id": "edge:mystery:output", "source": "mystery:main", "target": "output:main", "type": "flow"},
            ],
        },
    }

    with pytest.raises(UnsupportedGraphError, match="Unsupported flow runtime node type: mystery"):
        build_linear_path(snapshot)


def test_build_linear_path_allows_hitl_between_crews():
    snapshot = _linear_snapshot()
    snapshot["graph"]["nodes"].append(
        {"id": "crew:revision", "type": "crew", "data": {"versionId": "crew-version-2"}}
    )
    snapshot["graph"]["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:crew", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:crew:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:revision", "source": "hitl:review", "target": "crew:revision", "type": "flow"},
        {"id": "edge:revision:output", "source": "crew:revision", "target": "output:main", "type": "flow"},
    ]

    path = build_linear_path(snapshot)

    assert [node["id"] for node in path] == [
        "crew:research",
        "hitl:review",
        "crew:revision",
        "output:main",
    ]


def test_build_linear_path_rejects_hitl_without_previous_crew():
    snapshot = _linear_snapshot()
    snapshot["graph"]["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:hitl", "source": "start:main", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:crew", "source": "hitl:review", "target": "crew:research", "type": "flow"},
        {"id": "edge:crew:output", "source": "crew:research", "target": "output:main", "type": "flow"},
    ]

    with pytest.raises(UnsupportedGraphError, match="HITL node hitl:review must follow a Crew node"):
        build_linear_path(snapshot)


def test_build_linear_path_rejects_input_between_hitl_and_output():
    snapshot = _linear_snapshot()
    snapshot["graph"]["nodes"].append({"id": "input:late", "type": "input", "data": {}})
    snapshot["graph"]["edges"] = [
        {"id": "edge:input:start", "source": "input:main", "target": "start:main", "type": "flow"},
        {"id": "edge:start:crew", "source": "start:main", "target": "crew:research", "type": "flow"},
        {"id": "edge:crew:hitl", "source": "crew:research", "target": "hitl:review", "type": "flow"},
        {"id": "edge:hitl:input", "source": "hitl:review", "target": "input:late", "type": "flow"},
        {"id": "edge:input:output", "source": "input:late", "target": "output:main", "type": "flow"},
    ]

    with pytest.raises(UnsupportedGraphError, match="HITL node hitl:review must be followed by Crew or Output"):
        build_linear_path(snapshot)


def test_read_path_reads_nested_dicts_and_output_prefix():
    payload = {"output": {"final_answer": "Done", "nested": {"score": 9}}}

    assert read_path(payload, "output.final_answer") == "Done"
    assert read_path(payload, "output.nested.score") == 9
    assert read_path(payload, "missing.path") is None


def test_build_crew_inputs_maps_state_literal_and_node_output():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["prior"] = {
        "source": "node",
        "nodeId": "crew:previous",
        "path": "output.summary",
    }
    state = {"topic": "AI orchestration"}
    node_outputs = {"crew:previous": {"summary": "Earlier result"}}

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:research",
        state=state,
        node_outputs=node_outputs,
    )

    assert inputs == {
        "topic": "AI orchestration",
        "tone": "concise",
        "prior": "Earlier result",
    }


def test_build_crew_inputs_injects_runtime_context_after_user_mappings():
    snapshot = {
        "crew_input_mappings": {
            "crew:visual": {
                "topic": {"source": "state", "path": "topic"},
            }
        }
    }
    state = {"topic": "AI news"}
    runtime_context = {
        "human_feedback": {
            "outcome": "needs_revision",
            "feedback": "Make it sharper",
            "previous_output_ref": {"node_id": "crew:content", "version": 1},
            "attempt_number": 1,
        }
    }

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:visual",
        state=state,
        node_outputs={},
        runtime_context=runtime_context,
    )

    assert inputs["topic"] == "AI news"
    assert inputs["human_feedback"] == runtime_context["human_feedback"]


def test_build_crew_inputs_returns_runtime_context_when_mappings_missing():
    runtime_context = {"human_feedback": {"outcome": "approved", "feedback": ""}}

    inputs = build_crew_inputs(
        snapshot={"crew_input_mappings": {}},
        crew_node_id="crew:visual",
        state={},
        node_outputs={},
        runtime_context=runtime_context,
    )

    assert inputs == runtime_context
    assert inputs is not runtime_context


@pytest.mark.parametrize(
    ("snapshot", "crew_node"),
    [
        (
            {"graph": {"entities": {"crews": {}}}},
            {"id": "crew:research", "data": "not-a-dict"},
        ),
        (
            {"graph": "not-a-dict"},
            {"id": "crew:research", "data": {"versionId": "crew-version-1"}},
        ),
        (
            {"graph": {"entities": "not-a-dict"}},
            {"id": "crew:research", "data": {"versionId": "crew-version-1"}},
        ),
        (
            {"graph": {"entities": {"crews": "not-a-dict"}}},
            {"id": "crew:research", "data": {"versionId": "crew-version-1"}},
        ),
    ],
)
def test_crew_runtime_snapshot_for_node_rejects_invalid_snapshot_shapes(snapshot, crew_node):
    with pytest.raises(UnsupportedGraphError):
        crew_runtime_snapshot_for_node(snapshot, crew_node)


def test_build_output_payload_projects_configured_fields():
    snapshot = _linear_snapshot()
    state = {"topic": "AI orchestration"}
    node_outputs = {"crew:research": {"final_answer": "Crew result"}}

    output = build_output_payload(snapshot=snapshot, state=state, node_outputs=node_outputs)

    assert output == {
        "Final answer": "Crew result",
        "Topic": "AI orchestration",
    }


def test_build_output_payload_projects_duplicate_crew_outputs_with_unique_labels():
    snapshot = _linear_snapshot()
    snapshot["output_fields"] = [
        {
            "label": "Research Crew (crew:research-a) / raw",
            "source": "node",
            "nodeId": "crew:research-a",
            "path": "output.raw",
        },
        {
            "label": "Research Crew (crew:research-b) / raw",
            "source": "node",
            "nodeId": "crew:research-b",
            "path": "output.raw",
        },
    ]
    node_outputs = {
        "crew:research-a": {"raw": "first crew output"},
        "crew:research-b": {"raw": "second crew output"},
    }

    output = build_output_payload(snapshot=snapshot, state={}, node_outputs=node_outputs)

    assert output == {
        "Research Crew (crew:research-a) / raw": "first crew output",
        "Research Crew (crew:research-b) / raw": "second crew output",
    }


def test_normalized_json_crew_output_preserves_raw_for_projection():
    class CrewOutputLike:
        json_dict = {"answer": "structured"}
        raw = "raw text"

    normalized = normalize_crew_output(CrewOutputLike())
    snapshot = _linear_snapshot()
    snapshot["output_fields"] = [
        {
            "label": "Answer",
            "source": "node",
            "nodeId": "crew:research",
            "path": "output.answer",
        },
        {
            "label": "Raw",
            "source": "node",
            "nodeId": "crew:research",
            "path": "output.raw",
        },
    ]

    output = build_output_payload(snapshot=snapshot, state={}, node_outputs={"crew:research": normalized})

    assert normalized == {"answer": "structured", "raw": "raw text"}
    assert output == {"Answer": "structured", "Raw": "raw text"}


def test_normalized_json_crew_output_does_not_overwrite_structured_raw():
    class CrewOutputLike:
        json_dict = {"answer": "structured", "raw": "structured raw"}
        raw = "crew raw"

    assert normalize_crew_output(CrewOutputLike()) == {
        "answer": "structured",
        "raw": "structured raw",
    }


def test_normalized_crew_output_accumulates_structured_task_outputs():
    class TaskOutputLike:
        def __init__(self, json_dict=None, raw=""):
            self.json_dict = json_dict
            self.pydantic = None
            self.raw = raw

    class CrewOutputLike:
        tasks_output = [
            TaskOutputLike({"row_number": 4, "partner_link": "https://example.test/item"}),
            TaskOutputLike(raw='{"content_plan":true}'),
        ]
        json_dict = None
        pydantic = None
        raw = '{"content_plan":true}'

    assert normalize_crew_output(CrewOutputLike()) == {
        "row_number": 4,
        "partner_link": "https://example.test/item",
        "raw": '{"content_plan":true}',
    }


def test_normalized_pydantic_crew_output_preserves_raw_for_projection():
    class PydanticOutputLike:
        def model_dump(self):
            return {"answer": "pydantic structured"}

    class CrewOutputLike:
        pydantic = PydanticOutputLike()
        raw = "pydantic raw text"

    normalized = normalize_crew_output(CrewOutputLike())
    snapshot = _linear_snapshot()
    snapshot["output_fields"] = [
        {
            "label": "Answer",
            "source": "node",
            "nodeId": "crew:research",
            "path": "output.answer",
        },
        {
            "label": "Raw",
            "source": "node",
            "nodeId": "crew:research",
            "path": "output.raw",
        },
    ]

    output = build_output_payload(snapshot=snapshot, state={}, node_outputs={"crew:research": normalized})

    assert normalized == {"answer": "pydantic structured", "raw": "pydantic raw text"}
    assert output == {"Answer": "pydantic structured", "Raw": "pydantic raw text"}


def test_build_crew_inputs_resolves_card_news_transform():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["card_news_slides"] = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.title_slide", "output.body_slides", "output.outro_slide"],
        "transform": "join_card_news_slides_v1",
        "maxChars": 8000,
        "overflow": "fail",
    }
    node_outputs = {
        "crew:content": {
            "title_slide": "Launch AI Ops",
            "body_slides": [
                {"subtitle": "Why now", "bullet_points": ["Faster feedback", "Less manual routing"]},
                {"subtitle": "How", "bullet_points": ["Bind outputs", "Validate before publish"]},
            ],
            "outro_slide": "Start with one flow",
        }
    }

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:research",
        state={"topic": "AI orchestration"},
        node_outputs=node_outputs,
    )

    assert inputs["card_news_slides"] == (
        "Launch AI Ops\n\n"
        "Why now\n"
        "- Faster feedback\n"
        "- Less manual routing\n\n"
        "How\n"
        "- Bind outputs\n"
        "- Validate before publish\n\n"
        "Start with one flow"
    )


def test_card_news_slides_remains_normal_transform_target():
    snapshot = _linear_snapshot()
    mapping = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.title_slide", "output.body_slides", "output.outro_slide"],
        "transform": "join_card_news_slides_v1",
    }
    snapshot["crew_input_mappings"]["crew:research"] = {
        "card_news_slides": mapping,
        "custom_slide_prompt": dict(mapping),
    }
    node_outputs = {
        "crew:content": {
            "title_slide": "Launch AI Ops",
            "body_slides": [{"subtitle": "Why now", "bullet_points": ["Faster feedback"]}],
            "outro_slide": "Start with one flow",
        }
    }

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:research",
        state={},
        node_outputs=node_outputs,
    )

    expected = "Launch AI Ops\n\nWhy now\n- Faster feedback\n\nStart with one flow"
    assert inputs["card_news_slides"] == expected
    assert inputs["custom_slide_prompt"] == expected


def test_build_crew_inputs_fails_when_transfer_value_exceeds_max_chars():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["summary"] = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.raw"],
        "transform": "identity_v1",
        "maxChars": 3,
        "overflow": "fail",
    }

    with pytest.raises(ValueError, match="crew:research.summary exceeds maxChars 3"):
        build_crew_inputs(
            snapshot=snapshot,
            crew_node_id="crew:research",
            state={"topic": "AI orchestration"},
            node_outputs={"crew:content": {"raw": "1234"}},
        )


def test_build_crew_inputs_truncates_when_overflow_policy_is_truncate():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["summary"] = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.raw"],
        "transform": "identity_v1",
        "maxChars": 3,
        "overflow": "truncate",
    }

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:research",
        state={"topic": "AI orchestration"},
        node_outputs={"crew:content": {"raw": "1234"}},
    )

    assert inputs["summary"] == "123"


def test_build_crew_inputs_join_text_transform_uses_single_newline_between_chunks():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["summary"] = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.intro", "output.details"],
        "transform": "join_text_v1",
        "maxChars": 8000,
        "overflow": "fail",
    }

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:research",
        state={"topic": "AI orchestration"},
        node_outputs={"crew:content": {"intro": "Intro", "details": {"next": "Details"}}},
    )

    assert inputs["summary"] == 'Intro\n{\n  "next": "Details"\n}'


def test_build_crew_inputs_identity_transform_preserves_non_string_without_text_limit():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["payload"] = {
        "source": "transform",
        "inputType": "json",
        "nodeId": "crew:content",
        "paths": ["output.payload"],
        "transform": "identity_v1",
        "maxChars": 1,
        "overflow": "fail",
    }
    payload = {"items": ["alpha", "beta"]}

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:research",
        state={"topic": "AI orchestration"},
        node_outputs={"crew:content": {"payload": payload}},
    )

    assert inputs["payload"] == payload


def test_build_crew_inputs_json_stringify_transform_compacts_structured_value():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["payload"] = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.payload"],
        "transform": "json_stringify_v1",
        "maxChars": 8000,
        "overflow": "fail",
    }

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:research",
        state={"topic": "AI orchestration"},
        node_outputs={"crew:content": {"payload": {"title": "런치", "items": [1, 2]}}},
    )

    assert inputs["payload"] == '{"title":"런치","items":[1,2]}'


def test_build_crew_inputs_wraps_non_serializable_transform_value_as_value_error():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["payload"] = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.payload"],
        "transform": "json_stringify_v1",
        "maxChars": 8000,
        "overflow": "fail",
    }

    with pytest.raises(ValueError, match="crew:research.payload failed to serialize transform value"):
        build_crew_inputs(
            snapshot=snapshot,
            crew_node_id="crew:research",
            state={"topic": "AI orchestration"},
            node_outputs={"crew:content": {"payload": {"bad": object()}}},
        )


def test_build_crew_inputs_wraps_circular_transform_value_as_value_error():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["payload"] = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.payload"],
        "transform": "json_stringify_v1",
        "maxChars": 8000,
        "overflow": "fail",
    }
    payload = {}
    payload["self"] = payload

    with pytest.raises(ValueError, match="crew:research.payload failed to serialize transform value"):
        build_crew_inputs(
            snapshot=snapshot,
            crew_node_id="crew:research",
            state={"topic": "AI orchestration"},
            node_outputs={"crew:content": {"payload": payload}},
        )


def test_build_crew_inputs_defaults_missing_transform_to_identity():
    snapshot = _linear_snapshot()
    snapshot["crew_input_mappings"]["crew:research"]["summary"] = {
        "source": "transform",
        "inputType": "text",
        "nodeId": "crew:content",
        "paths": ["output.raw"],
        "maxChars": 8000,
        "overflow": "fail",
    }

    inputs = build_crew_inputs(
        snapshot=snapshot,
        crew_node_id="crew:research",
        state={"topic": "AI orchestration"},
        node_outputs={"crew:content": {"raw": "default identity"}},
    )

    assert inputs["summary"] == "default identity"
