from __future__ import annotations

import json
from typing import Any


class TransferTransformError(ValueError):
    pass


DEFAULT_MAX_CHARS = 8000


def read_path(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    current = payload
    for segment in [part for part in path.split(".") if part]:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
            continue
        return None
    return current


def resolve_transform_mapping(
    *,
    target_node_id: str,
    target_input: str,
    mapping: dict[str, Any],
    node_outputs: dict[str, Any],
) -> Any:
    node_id = str(mapping.get("nodeId") or "")
    source_payload = {"output": node_outputs.get(node_id)}
    paths = mapping.get("paths")
    if isinstance(paths, list):
        values = [read_path(source_payload, path) for path in paths if isinstance(path, str)]
    else:
        values = [read_path(source_payload, mapping.get("path"))]

    transform = mapping.get("transform") or "identity_v1"
    if transform == "identity_v1":
        resolved = values[0] if values else None
    elif transform == "join_text_v1":
        resolved = _join_text(values, target_node_id=target_node_id, target_input=target_input)
    elif transform == "join_card_news_slides_v1":
        resolved = _join_card_news_slides(values, target_node_id=target_node_id, target_input=target_input)
    elif transform == "json_stringify_v1":
        source = values[0] if len(values) == 1 else values
        resolved = _json_dumps(
            source,
            target_node_id=target_node_id,
            target_input=target_input,
            separators=(",", ":"),
        )
    else:
        raise TransferTransformError(f"Unsupported transfer transform: {transform}.")

    return _apply_text_limit(
        value=resolved,
        max_chars=mapping.get("maxChars"),
        overflow=mapping.get("overflow"),
        target_node_id=target_node_id,
        target_input=target_input,
    )


def _json_dumps(
    value: Any,
    *,
    target_node_id: str,
    target_input: str,
    indent: int | None = None,
    separators: tuple[str, str] | None = None,
) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=indent, separators=separators)
    except (TypeError, ValueError) as exc:
        raise TransferTransformError(
            f"{target_node_id}.{target_input} failed to serialize transform value."
        ) from exc


def _join_text(values: list[Any], *, target_node_id: str, target_input: str) -> str:
    parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            rendered = value
        else:
            rendered = _json_dumps(
                value,
                target_node_id=target_node_id,
                target_input=target_input,
                indent=2,
            )
        if rendered:
            parts.append(rendered)
    return "\n".join(parts)


def _join_card_news_slides(values: list[Any], *, target_node_id: str, target_input: str) -> str:
    title = _string_or_empty(
        values[0] if len(values) > 0 else None,
        target_node_id=target_node_id,
        target_input=target_input,
    )
    slides = values[1] if len(values) > 1 else None
    outro = _string_or_empty(
        values[2] if len(values) > 2 else None,
        target_node_id=target_node_id,
        target_input=target_input,
    )

    blocks: list[str] = []
    if title:
        blocks.append(title)

    if isinstance(slides, list):
        for slide in slides:
            block = _format_card_news_slide(slide, target_node_id=target_node_id, target_input=target_input)
            if block:
                blocks.append(block)
    else:
        slide_text = _string_or_empty(slides, target_node_id=target_node_id, target_input=target_input)
        if slide_text:
            blocks.append(slide_text)

    if outro:
        blocks.append(outro)
    return "\n\n".join(blocks)


def _format_card_news_slide(slide: Any, *, target_node_id: str, target_input: str) -> str:
    if not isinstance(slide, dict):
        return _string_or_empty(slide, target_node_id=target_node_id, target_input=target_input)

    heading = _string_or_empty(
        slide.get("subtitle") or slide.get("title"),
        target_node_id=target_node_id,
        target_input=target_input,
    )
    bullets = slide.get("bullet_points")
    if bullets is None:
        bullets = slide.get("bullets")

    lines: list[str] = []
    if heading:
        lines.append(heading)
    if isinstance(bullets, list):
        for bullet in bullets:
            bullet_text = _string_or_empty(
                bullet,
                target_node_id=target_node_id,
                target_input=target_input,
            )
            if bullet_text:
                lines.append(f"- {bullet_text}")
    else:
        bullet_text = _string_or_empty(bullets, target_node_id=target_node_id, target_input=target_input)
        if bullet_text:
            lines.append(f"- {bullet_text}")
    return "\n".join(lines)


def _string_or_empty(value: Any, *, target_node_id: str | None = None, target_input: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        if target_node_id is not None and target_input is not None:
            return _json_dumps(
                value,
                target_node_id=target_node_id,
                target_input=target_input,
                separators=(",", ":"),
            )
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _apply_text_limit(
    *,
    value: Any,
    max_chars: Any,
    overflow: Any,
    target_node_id: str,
    target_input: str,
) -> Any:
    if not isinstance(value, str):
        return value

    try:
        limit = int(max_chars)
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_CHARS
    if limit <= 0:
        limit = DEFAULT_MAX_CHARS

    if len(value) <= limit:
        return value
    if overflow == "truncate":
        return value[:limit]
    raise TransferTransformError(f"{target_node_id}.{target_input} exceeds maxChars {limit}.")
