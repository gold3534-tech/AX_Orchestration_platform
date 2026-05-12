from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

PREVIEW_TEXT_LIMIT = 500
PREVIEW_MAX_DEPTH = 3
NANO_BANANA_PROVIDER = "google_genai"
NANO_BANANA_SECRET_PROMPT_MARKERS = (
    "sk-",
    "secret",
    "password",
    "token",
    "api key",
    "api_key",
)
NANO_BANANA_SECRET_PROMPT_PATTERNS = (
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bghp_[0-9A-Za-z_]{20,}\b", re.IGNORECASE),
    re.compile(r"\bgithub_pat_[0-9A-Za-z_]{10,}\b", re.IGNORECASE),
    re.compile(r"\bxox[abp]-[0-9A-Za-z-]{10,}\b", re.IGNORECASE),
    re.compile(
        r"\bbearer\s+(?:"
        r"eyJ[0-9A-Za-z_-]+(?:\.[0-9A-Za-z_-]+){1,2}"
        r"|[0-9A-Za-z._~+/=-]{20,}"
        r")(?=$|[\s,;:)\]}])",
        re.IGNORECASE,
    ),
)

ASK_QUESTION_TOOL_NAMES = {
    "ask question to coworker",
    "ask_question_to_coworker",
    "askquestiontool",
}
DELEGATE_WORK_TOOL_NAMES = {
    "delegate work to coworker",
    "delegate_work_to_coworker",
    "delegateworktool",
}


def preview_text(value: object, *, limit: int = PREVIEW_TEXT_LIMIT) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[truncated]"


def _normalized_tool_name(tool_name: object) -> str:
    value = "" if tool_name is None else str(tool_name)
    return value.strip().lower()


def _is_nano_banana_tool(tool_name: object) -> bool:
    normalized_name = _normalized_tool_name(tool_name)
    return "nano" in normalized_name and "banana" in normalized_name


def _string_value(record: Mapping[str, Any], key: str) -> str | None:
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _mapping_from_json_text(value: str) -> Mapping[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, Mapping):
        return parsed
    return None


def _mapping_from_object(value: object) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip():
        return _mapping_from_json_text(value)
    return None


def _as_prompt_list(value: object) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _nano_banana_prompts(
    tool_args: Mapping[str, Any] | str | None,
) -> tuple[str | None, list[str] | None]:
    args = _mapping_from_object(tool_args)
    if args is None:
        return None, None
    single_prompt = args.get("prompt")
    prompt = single_prompt if isinstance(single_prompt, str) and single_prompt.strip() else None
    batch_prompts = _as_prompt_list(args.get("image_prompts")) if "image_prompts" in args else None
    return prompt, batch_prompts


def _looks_secret_like_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(marker in lowered for marker in NANO_BANANA_SECRET_PROMPT_MARKERS) or any(
        pattern.search(prompt) for pattern in NANO_BANANA_SECRET_PROMPT_PATTERNS
    )


def _nano_banana_prompt_preview(
    raw_tool_name: object,
    tool_args: Mapping[str, Any] | str | None,
) -> dict[str, str]:
    if not _is_nano_banana_tool(raw_tool_name):
        return {}
    prompt, batch_prompts = _nano_banana_prompts(tool_args)
    if batch_prompts is not None:
        return {}
    if prompt is None or _looks_secret_like_prompt(prompt):
        return {}
    return {"prompt_preview": preview_text(prompt)}


def _nano_banana_image_generation_metadata(raw_tool_name: object, status: str) -> dict[str, Any]:
    if not _is_nano_banana_tool(raw_tool_name):
        return {}
    return {
        "image_generation": True,
        "provider": NANO_BANANA_PROVIDER,
        "status": status,
    }


def _compact_artifact_metadata(record: Mapping[str, Any]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key in ("artifact_id", "preview_url", "download_url", "mime_type"):
        value = _string_value(record, key)
        if value is not None:
            metadata[key] = value
    return metadata


def _nano_banana_artifact_metadata(raw_tool_name: object, output: object) -> dict[str, Any]:
    if not _is_nano_banana_tool(raw_tool_name):
        return {}
    record = _mapping_from_object(output)
    if record is None:
        return {}
    images = record.get("images")
    if isinstance(images, list):
        artifacts: list[dict[str, str]] = []
        for item in images:
            if not isinstance(item, Mapping):
                continue
            artifact = _compact_artifact_metadata(item)
            if artifact:
                artifacts.append(artifact)
        count = record.get("count")
        image_count = count if isinstance(count, int) and not isinstance(count, bool) else len(artifacts)
        return {"image_count": image_count, "artifacts": artifacts}
    return _compact_artifact_metadata(record)


def _classify_nano_banana_failure(raw_tool_name: object, error: object) -> dict[str, Any]:
    if not _is_nano_banana_tool(raw_tool_name):
        return {}
    error_text = str(error).lower()
    if (
        "503" in error_text
        or "unavailable" in error_text
        or "high demand" in error_text
        or "deadline expired" in error_text
        or "deadline-expired" in error_text
        or "deadline_exceeded" in error_text
    ):
        return {
            "failure_kind": "provider_unavailable",
            "retryable": True,
            "friendly_error": "Temporary provider capacity issue",
        }
    return {
        "failure_kind": "provider_error",
        "retryable": False,
        "friendly_error": "Image generation failed",
    }


def _preview_value(value: object, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return preview_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    if depth >= PREVIEW_MAX_DEPTH:
        return preview_text(value)
    if isinstance(value, Mapping):
        return {
            preview_text(key): _preview_value(nested_value, depth=depth + 1)
            for key, nested_value in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [_preview_value(item, depth=depth + 1) for item in value]
    return preview_text(value)


def preview_mapping_values(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        preview_text(key): _preview_value(value, depth=1)
        for key, value in record.items()
    }


def preview_tool_args(raw_tool_name: object, tool_args: Mapping[str, Any]) -> dict[str, Any]:
    if not _is_nano_banana_tool(raw_tool_name) or (
        "prompt" not in tool_args and "image_prompts" not in tool_args
    ):
        return preview_mapping_values(tool_args)

    preview = {
        preview_text(key): _preview_value(value, depth=1)
        for key, value in tool_args.items()
        if key not in {"prompt", "image_prompts"}
    }
    prompt, batch_prompts = _nano_banana_prompts(tool_args)
    if prompt is not None:
        preview["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        preview["prompt_length"] = len(prompt)
    if batch_prompts is not None:
        preview["image_prompt_count"] = len(batch_prompts)
        preview["image_prompt_sha256s"] = [
            hashlib.sha256(prompt.encode("utf-8")).hexdigest() for prompt in batch_prompts
        ]
        preview["image_prompt_lengths"] = [len(prompt) for prompt in batch_prompts]
    return preview


def preview_non_mapping_tool_args(raw_tool_name: object, tool_args: object) -> Any:
    if not _is_nano_banana_tool(raw_tool_name):
        return preview_text(tool_args)
    if isinstance(tool_args, str) and tool_args.strip():
        parsed = _mapping_from_json_text(tool_args)
        if isinstance(parsed, Mapping):
            return preview_tool_args(raw_tool_name, parsed)
    return {"redacted": True, "reason": "nano_banana_prompt"}


def classify_tool_activity(
    *,
    tool_name: object,
    tool_args: Mapping[str, Any] | str | None,
) -> dict[str, str]:
    normalized_name = _normalized_tool_name(tool_name)
    args = tool_args if isinstance(tool_args, Mapping) else {}

    # CrewAI built-in collaboration events can arrive with variant tool names,
    # so fall back to the argument shape when all collaboration fields exist.
    if normalized_name in ASK_QUESTION_TOOL_NAMES or (
        "question" in args and "context" in args and "coworker" in args
    ):
        activity = {
            "activity_kind": "collaboration",
            "collaboration_kind": "ask_question",
        }
        coworker = _string_value(args, "coworker")
        if coworker is not None:
            activity["to_agent_role"] = coworker
        return activity

    if normalized_name in DELEGATE_WORK_TOOL_NAMES or (
        "task" in args and "context" in args and "coworker" in args
    ):
        activity = {
            "activity_kind": "collaboration",
            "collaboration_kind": "delegate_work",
        }
        coworker = _string_value(args, "coworker")
        if coworker is not None:
            activity["to_agent_role"] = coworker
        return activity

    return {"activity_kind": "tool"}


def semantic_tool_started_payload(
    *,
    run_id: str,
    node_id: str | None,
    raw_tool_name: object,
    tool_args: Mapping[str, Any] | str | None,
    agent_role: str | None = None,
    task_id: str | None = None,
    task_name: str | None = None,
) -> dict[str, Any]:
    classification = classify_tool_activity(tool_name=raw_tool_name, tool_args=tool_args)
    base: dict[str, Any] = {
        "run_id": run_id,
        "node_id": node_id,
    }
    if agent_role:
        base["agent_role"] = agent_role
    if task_id:
        base["task_id"] = task_id
    if task_name:
        base["task_name"] = task_name

    if classification["activity_kind"] == "collaboration":
        args = tool_args if isinstance(tool_args, Mapping) else {}
        payload = {
            **base,
            "type": "collaboration_started",
            "activity_kind": "collaboration",
            "collaboration_kind": classification["collaboration_kind"],
            "raw_tool_name": str(raw_tool_name),
        }
        if agent_role:
            payload["from_agent_role"] = agent_role
        if "to_agent_role" in classification:
            payload["to_agent_role"] = classification["to_agent_role"]
        question = _string_value(args, "question")
        if question is not None:
            payload["question"] = preview_text(question)
        task = _string_value(args, "task")
        if task is not None:
            payload["task"] = preview_text(task)
        context = _string_value(args, "context")
        if context is not None:
            payload["context_preview"] = preview_text(context)
        return payload

    return {
        **base,
        "type": "tool_execution_started",
        "activity_kind": "tool",
        "tool_name": str(raw_tool_name),
        "tool_args_preview": preview_tool_args(raw_tool_name, tool_args)
        if isinstance(tool_args, Mapping)
        else preview_non_mapping_tool_args(raw_tool_name, tool_args),
        **_nano_banana_image_generation_metadata(raw_tool_name, "generating"),
        **_nano_banana_prompt_preview(raw_tool_name, tool_args),
    }


def semantic_tool_finished_payload(
    *,
    run_id: str,
    node_id: str | None,
    raw_tool_name: object,
    tool_args: Mapping[str, Any] | str | None,
    output: object,
    agent_role: str | None = None,
    task_id: str | None = None,
    task_name: str | None = None,
) -> dict[str, Any]:
    started = semantic_tool_started_payload(
        run_id=run_id,
        node_id=node_id,
        raw_tool_name=raw_tool_name,
        tool_args=tool_args,
        agent_role=agent_role,
        task_id=task_id,
        task_name=task_name,
    )
    if started["type"] == "collaboration_started":
        started["type"] = "collaboration_completed"
        started["output_preview"] = preview_text(output)
        return started
    started["type"] = "tool_execution_completed"
    started.update(_nano_banana_image_generation_metadata(raw_tool_name, "completed"))
    artifact_metadata = _nano_banana_artifact_metadata(raw_tool_name, output)
    started.update(artifact_metadata)
    if "artifacts" in artifact_metadata:
        started["output_preview"] = preview_text(
            {
                "images": artifact_metadata["artifacts"],
                "count": artifact_metadata.get("image_count", 0),
            }
        )
    else:
        started["output_preview"] = preview_text(output)
    return started


def semantic_tool_failed_payload(
    *,
    run_id: str,
    node_id: str | None,
    raw_tool_name: object,
    tool_args: Mapping[str, Any] | str | None,
    error: object,
    agent_role: str | None = None,
    task_id: str | None = None,
    task_name: str | None = None,
    fatal: bool | None = None,
) -> dict[str, Any]:
    started = semantic_tool_started_payload(
        run_id=run_id,
        node_id=node_id,
        raw_tool_name=raw_tool_name,
        tool_args=tool_args,
        agent_role=agent_role,
        task_id=task_id,
        task_name=task_name,
    )
    if started["type"] == "collaboration_started":
        started["type"] = "collaboration_failed"
    else:
        started["type"] = "tool_execution_failed"
        started.update(_nano_banana_image_generation_metadata(raw_tool_name, "failed"))
        started.update(_classify_nano_banana_failure(raw_tool_name, error))
    started["error_message"] = preview_text(error)
    if fatal is not None:
        started["fatal"] = fatal
    return started
