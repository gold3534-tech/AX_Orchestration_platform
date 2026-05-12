from __future__ import annotations

import hashlib

from api.runtime.run_events import (
    classify_tool_activity,
    preview_text,
    semantic_tool_failed_payload,
    semantic_tool_finished_payload,
    semantic_tool_started_payload,
)


def test_classify_ask_question_collaboration_from_sanitized_name():
    activity = classify_tool_activity(
        tool_name="ask_question_to_coworker",
        tool_args={
            "question": "What should we verify?",
            "context": "Need another agent opinion",
            "coworker": "Reviewer",
        },
    )

    assert activity == {
        "activity_kind": "collaboration",
        "collaboration_kind": "ask_question",
        "to_agent_role": "Reviewer",
    }


def test_classify_delegate_work_collaboration_from_display_name():
    activity = classify_tool_activity(
        tool_name="Delegate work to coworker",
        tool_args={
            "task": "Summarize the source material",
            "context": "Use the current report draft",
            "coworker": "Researcher",
        },
    )

    assert activity == {
        "activity_kind": "collaboration",
        "collaboration_kind": "delegate_work",
        "to_agent_role": "Researcher",
    }


def test_classify_normal_tool_usage():
    activity = classify_tool_activity(
        tool_name="serper_search",
        tool_args={"search_query": "CrewAI collaboration tools"},
    )

    assert activity == {"activity_kind": "tool"}


def test_preview_text_truncates_long_values():
    assert preview_text("x" * 130, limit=12) == "xxxxxxxxxxxx...[truncated]"


def test_semantic_tool_started_payload_splits_collaboration():
    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="delegate_work_to_coworker",
        tool_args={
            "task": "Draft a section",
            "context": "Use the outline",
            "coworker": "Writer",
        },
        agent_role="Lead",
        task_id="task-1",
        task_name="Write report",
    )

    assert payload["type"] == "collaboration_started"
    assert payload["activity_kind"] == "collaboration"
    assert payload["collaboration_kind"] == "delegate_work"
    assert payload["from_agent_role"] == "Lead"
    assert payload["to_agent_role"] == "Writer"
    assert payload["task"] == "Draft a section"
    assert payload["context_preview"] == "Use the outline"


def test_semantic_tool_started_payload_previews_normal_tool_args():
    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="serper_search",
        tool_args={
            "search_query": "x" * 530,
            "options": {"region": "kr", "note": "y" * 530},
            "count": 3,
        },
    )

    assert payload["type"] == "tool_execution_started"
    assert payload["tool_args_preview"] == {
        "search_query": f"{'x' * 500}...[truncated]",
        "options": {
            "region": "kr",
            "note": f"{'y' * 500}...[truncated]",
        },
        "count": 3,
    }


def test_semantic_tool_started_payload_redacts_nano_banana_prompt_preview():
    prompt = "Create an image using sk-live-1234567890abcdef"

    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={"prompt": prompt, "artifact_storage_mode": "temporary_only"},
    )

    assert payload["type"] == "tool_execution_started"
    assert payload["tool_args_preview"] == {
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_length": len(prompt),
        "artifact_storage_mode": "temporary_only",
    }
    assert prompt not in str(payload)
    assert "sk-live-1234567890abcdef" not in str(payload)


def test_semantic_tool_started_payload_enriches_nano_banana_image_generation_metadata():
    prompt = "Create a bright cyberpunk banana mascot holding a camera"

    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={"prompt": prompt, "artifact_storage_mode": "temporary_only"},
    )

    assert payload["type"] == "tool_execution_started"
    assert payload["image_generation"] is True
    assert payload["provider"] == "google_genai"
    assert payload["status"] == "generating"
    assert payload["prompt_preview"] == prompt
    assert payload["tool_args_preview"] == {
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_length": len(prompt),
        "artifact_storage_mode": "temporary_only",
    }


def test_semantic_tool_started_payload_omits_secret_like_nano_banana_prompt_preview():
    prompt = "Create a launch poster with the api key in the corner"

    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={"prompt": prompt, "artifact_storage_mode": "temporary_only"},
    )

    assert payload["image_generation"] is True
    assert "prompt_preview" not in payload
    assert payload["tool_args_preview"]["prompt_sha256"] == hashlib.sha256(
        prompt.encode("utf-8")
    ).hexdigest()
    assert payload["tool_args_preview"]["prompt_length"] == len(prompt)
    assert prompt not in str(payload)


def test_semantic_tool_started_payload_keeps_safe_bearer_prose_prompt_preview():
    prompt = "Create a standard bearer illustration with a ceremonial flag"

    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={"prompt": prompt, "artifact_storage_mode": "temporary_only"},
    )

    assert payload["image_generation"] is True
    assert payload["prompt_preview"] == prompt
    assert payload["tool_args_preview"]["prompt_sha256"] == hashlib.sha256(
        prompt.encode("utf-8")
    ).hexdigest()
    assert payload["tool_args_preview"]["prompt_length"] == len(prompt)


def test_semantic_tool_started_payload_omits_credential_shaped_nano_banana_prompt_preview():
    prompts = (
        "Create a poster that includes " + "AIza" + "SyD1234567890abcdefghijklmnopq",
        "Create a poster that includes " + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456",
        "Create a poster that includes " + "github_pat_" + "11AA22BB33CC44DD55EE",
        "Create a poster that includes " + "xoxb" + "-123456789012-123456789012-abcdefghijklmnop",
        "Create a poster that includes " + "xoxp" + "-123456789012-123456789012-abcdefghijklmnop",
        "Create a poster that includes " + "xoxa" + "-123456789012-123456789012-abcdefghijklmnop",
        "Create a poster that includes Bearer abcdefghijklmnopqrstuvwxyz0123456789",
        "Create a poster that includes Bearer abcdefghijklmnopqrs/",
        "Create a poster that includes Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature",
    )

    for prompt in prompts:
        payload = semantic_tool_started_payload(
            run_id="run-1",
            node_id="crew:alpha",
            raw_tool_name="AX Nano Banana Image",
            tool_args={"prompt": prompt, "artifact_storage_mode": "temporary_only"},
        )

        assert payload["image_generation"] is True
        assert "prompt_preview" not in payload
        assert payload["tool_args_preview"]["prompt_sha256"] == hashlib.sha256(
            prompt.encode("utf-8")
        ).hexdigest()
        assert payload["tool_args_preview"]["prompt_length"] == len(prompt)
        assert prompt not in str(payload)


def test_semantic_tool_started_payload_redacts_nano_banana_string_args():
    prompt = "Create using sk-live-SECRET-TOKEN"
    tool_args = '{"prompt":"Create using sk-live-SECRET-TOKEN","artifact_storage_mode":"temporary_only"}'

    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args=tool_args,
    )

    assert payload["type"] == "tool_execution_started"
    assert payload["tool_args_preview"] == {
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_length": len(prompt),
        "artifact_storage_mode": "temporary_only",
    }
    assert prompt not in str(payload)
    assert "sk-live-SECRET-TOKEN" not in str(payload)


def test_semantic_tool_started_payload_redacts_nano_banana_image_prompts_mapping_args():
    image_prompts = [
        "Create using sk-live-BATCH-SECRET-ONE",
        "Create using token BATCH-SECRET-TWO",
    ]

    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={
            "image_prompts": image_prompts,
            "artifact_storage_mode": "temporary_only",
            "delay_seconds": 10,
        },
    )

    assert payload["type"] == "tool_execution_started"
    assert "prompt_preview" not in payload
    assert payload["tool_args_preview"] == {
        "artifact_storage_mode": "temporary_only",
        "delay_seconds": 10,
        "image_prompt_count": 2,
        "image_prompt_sha256s": [
            hashlib.sha256(prompt.encode("utf-8")).hexdigest() for prompt in image_prompts
        ],
        "image_prompt_lengths": [len(prompt) for prompt in image_prompts],
    }
    assert "sk-live-BATCH-SECRET-ONE" not in str(payload)
    assert "BATCH-SECRET-TWO" not in str(payload)


def test_semantic_tool_started_payload_redacts_nano_banana_image_prompts_json_string_args():
    image_prompts = [
        "Create using sk-live-BATCH-SECRET-ONE",
        "Create using password BATCH-SECRET-TWO",
    ]
    tool_args = (
        '{"image_prompts":["Create using sk-live-BATCH-SECRET-ONE",'
        '"Create using password BATCH-SECRET-TWO"],'
        '"artifact_storage_mode":"temporary_only"}'
    )

    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args=tool_args,
    )

    assert payload["type"] == "tool_execution_started"
    assert "prompt_preview" not in payload
    assert payload["tool_args_preview"] == {
        "artifact_storage_mode": "temporary_only",
        "image_prompt_count": 2,
        "image_prompt_sha256s": [
            hashlib.sha256(prompt.encode("utf-8")).hexdigest() for prompt in image_prompts
        ],
        "image_prompt_lengths": [len(prompt) for prompt in image_prompts],
    }
    assert "sk-live-BATCH-SECRET-ONE" not in str(payload)
    assert "BATCH-SECRET-TWO" not in str(payload)


def test_semantic_tool_started_payload_redacts_unparseable_nano_banana_string_args():
    tool_args = 'prompt="Create using sk-live-SECRET-TOKEN"'

    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args=tool_args,
    )

    assert payload["type"] == "tool_execution_started"
    assert payload["tool_args_preview"] == {"redacted": True, "reason": "nano_banana_prompt"}
    assert "sk-live-SECRET-TOKEN" not in str(payload)


def test_semantic_tool_started_payload_previews_non_mapping_args():
    payload = semantic_tool_started_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="plain_tool",
        tool_args="z" * 530,
    )

    assert payload["tool_args_preview"] == f"{'z' * 500}...[truncated]"


def test_semantic_tool_finished_payload_maps_normal_tool_completed():
    payload = semantic_tool_finished_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="serper_search",
        tool_args={"search_query": "CrewAI collaboration tools"},
        output="x" * 530,
    )

    assert payload["type"] == "tool_execution_completed"
    assert payload["activity_kind"] == "tool"
    assert payload["output_preview"] == f"{'x' * 500}...[truncated]"


def test_semantic_tool_finished_payload_redacts_nano_banana_prompt_preview():
    prompt = "Create an image using sk-live-1234567890abcdef"

    payload = semantic_tool_finished_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={"prompt": prompt, "artifact_storage_mode": "temporary_only"},
        output={"artifact_id": "artifact-1", "mime_type": "image/png"},
    )

    assert payload["type"] == "tool_execution_completed"
    assert payload["tool_args_preview"]["prompt_sha256"] == hashlib.sha256(
        prompt.encode("utf-8")
    ).hexdigest()
    assert payload["tool_args_preview"]["prompt_length"] == len(prompt)
    assert payload["tool_args_preview"]["artifact_storage_mode"] == "temporary_only"
    assert prompt not in str(payload)
    assert "sk-live-1234567890abcdef" not in str(payload)


def test_semantic_tool_finished_payload_redacts_nano_banana_string_args():
    prompt = "Create using sk-live-SECRET-TOKEN"
    tool_args = '{"prompt":"Create using sk-live-SECRET-TOKEN","artifact_storage_mode":"temporary_only"}'

    payload = semantic_tool_finished_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args=tool_args,
        output={"artifact_id": "artifact-1", "mime_type": "image/png"},
    )

    assert payload["type"] == "tool_execution_completed"
    assert payload["tool_args_preview"]["prompt_sha256"] == hashlib.sha256(
        prompt.encode("utf-8")
    ).hexdigest()
    assert payload["tool_args_preview"]["prompt_length"] == len(prompt)
    assert payload["tool_args_preview"]["artifact_storage_mode"] == "temporary_only"
    assert prompt not in str(payload)
    assert "sk-live-SECRET-TOKEN" not in str(payload)


def test_semantic_tool_finished_payload_enriches_nano_banana_completed_artifact_metadata():
    payload = semantic_tool_finished_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={"prompt": "Draw a studio product shot of a yellow backpack"},
        output={
            "artifact_id": "artifact-1",
            "preview_url": "https://cdn.example.test/preview.png",
            "download_url": "https://cdn.example.test/download.png",
            "mime_type": "image/png",
        },
    )

    assert payload["type"] == "tool_execution_completed"
    assert payload["image_generation"] is True
    assert payload["provider"] == "google_genai"
    assert payload["status"] == "completed"
    assert payload["artifact_id"] == "artifact-1"
    assert payload["preview_url"] == "https://cdn.example.test/preview.png"
    assert payload["download_url"] == "https://cdn.example.test/download.png"
    assert payload["mime_type"] == "image/png"


def test_semantic_tool_finished_payload_enriches_nano_banana_batch_artifact_metadata():
    payload = semantic_tool_finished_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={
            "image_prompts": ["Raw prompt one", "Raw prompt two"],
            "delay_seconds": 10,
        },
        output={
            "images": [
                {
                    "artifact_id": "artifact-1",
                    "preview_url": "/api/run-artifacts/artifact-1/content",
                    "download_url": "/api/run-artifacts/artifact-1/content",
                    "mime_type": "image/png",
                    "metadata_json": {"prompt": "Raw prompt one"},
                },
                {
                    "artifact_id": "artifact-2",
                    "preview_url": "/api/run-artifacts/artifact-2/content",
                    "download_url": "/api/run-artifacts/artifact-2/content",
                    "mime_type": "image/png",
                    "metadata_json": {"prompt": "Raw prompt two"},
                },
            ],
            "count": 2,
        },
    )

    assert payload["type"] == "tool_execution_completed"
    assert payload["image_generation"] is True
    assert payload["status"] == "completed"
    assert payload["image_count"] == 2
    assert payload["artifacts"] == [
        {
            "artifact_id": "artifact-1",
            "preview_url": "/api/run-artifacts/artifact-1/content",
            "download_url": "/api/run-artifacts/artifact-1/content",
            "mime_type": "image/png",
        },
        {
            "artifact_id": "artifact-2",
            "preview_url": "/api/run-artifacts/artifact-2/content",
            "download_url": "/api/run-artifacts/artifact-2/content",
            "mime_type": "image/png",
        },
    ]
    assert "Raw prompt one" not in str(payload)
    assert "Raw prompt two" not in str(payload)
    assert "metadata_json" not in str(payload)


def test_semantic_tool_failed_payload_maps_collaboration_failed_with_fatal():
    payload = semantic_tool_failed_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="ask_question_to_coworker",
        tool_args={
            "question": "What should we verify?",
            "context": "Need another agent opinion",
            "coworker": "Reviewer",
        },
        error="Could not reach coworker",
        fatal=True,
    )

    assert payload["type"] == "collaboration_failed"
    assert payload["activity_kind"] == "collaboration"
    assert payload["collaboration_kind"] == "ask_question"
    assert payload["error_message"] == "Could not reach coworker"
    assert payload["fatal"] is True


def test_semantic_tool_failed_payload_enriches_nano_banana_provider_failure_metadata():
    payload = semantic_tool_failed_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={"prompt": "Draw a banana-shaped camera"},
        error="Google GenAI returned 400 INVALID_ARGUMENT",
        fatal=False,
    )

    assert payload["type"] == "tool_execution_failed"
    assert payload["image_generation"] is True
    assert payload["provider"] == "google_genai"
    assert payload["status"] == "failed"
    assert payload["failure_kind"] == "provider_error"
    assert payload["retryable"] is False
    assert payload["friendly_error"] == "Image generation failed"
    assert payload["fatal"] is False


def test_semantic_tool_failed_payload_classifies_nano_banana_capacity_errors_as_retryable():
    payload = semantic_tool_failed_payload(
        run_id="run-1",
        node_id="crew:alpha",
        raw_tool_name="AX Nano Banana Image",
        tool_args={"prompt": "Draw a banana-shaped camera"},
        error="Google GenAI 503 UNAVAILABLE: model is in high demand",
    )

    assert payload["type"] == "tool_execution_failed"
    assert payload["image_generation"] is True
    assert payload["provider"] == "google_genai"
    assert payload["status"] == "failed"
    assert payload["failure_kind"] == "provider_unavailable"
    assert payload["retryable"] is True
    assert payload["friendly_error"] == "Temporary provider capacity issue"


def test_semantic_tool_failed_payload_classifies_nano_banana_deadline_errors_as_retryable():
    for error in (
        "Google GenAI DEADLINE_EXCEEDED: deadline expired",
        "Google GenAI deadline-expired while waiting for image generation",
    ):
        payload = semantic_tool_failed_payload(
            run_id="run-1",
            node_id="crew:alpha",
            raw_tool_name="AX Nano Banana Image",
            tool_args={"prompt": "Draw a banana-shaped camera"},
            error=error,
        )

        assert payload["type"] == "tool_execution_failed"
        assert payload["image_generation"] is True
        assert payload["provider"] == "google_genai"
        assert payload["status"] == "failed"
        assert payload["failure_kind"] == "provider_unavailable"
        assert payload["retryable"] is True
        assert payload["friendly_error"] == "Temporary provider capacity issue"
