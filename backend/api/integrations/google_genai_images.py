from __future__ import annotations

import os
import time
from typing import Any


DEFAULT_NANO_BANANA_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_NANO_BANANA_ASPECT_RATIO = "1:1"
DEFAULT_NANO_BANANA_IMAGE_SIZE = "1K"
LEGACY_NANO_BANANA_MODEL = "gemini-2.5-flash-image"


def _google_genai_types():
    try:
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise ValueError("google-genai is required for Google GenAI image generation.") from exc
    return types


class GoogleGenAIImageClient:
    def __init__(
        self,
        genai_client: Any,
        *,
        max_retries: int = 2,
        retry_base_delay_seconds: float = 1.0,
    ) -> None:
        self._client = genai_client
        self._max_retries = max(0, int(max_retries))
        self._retry_base_delay_seconds = max(0.0, float(retry_base_delay_seconds))

    def generate_image(
        self,
        *,
        prompt: str,
        model: str = DEFAULT_NANO_BANANA_MODEL,
        aspect_ratio: str = DEFAULT_NANO_BANANA_ASPECT_RATIO,
        image_size: str | None = DEFAULT_NANO_BANANA_IMAGE_SIZE,
    ) -> dict[str, Any]:
        config = self._generate_content_config(
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )
        response = self._generate_content_with_retry(
            model=model,
            contents=prompt,
            config=config,
        )
        effective_config = {"aspect_ratio": aspect_ratio}
        if model != LEGACY_NANO_BANANA_MODEL and image_size:
            effective_config["image_size"] = image_size
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                inline_data = getattr(part, "inline_data", None)
                if inline_data is not None:
                    return {
                        "mime_type": inline_data.mime_type,
                        "bytes": inline_data.data,
                        "model": model,
                        "prompt": prompt,
                        **effective_config,
                    }
        raise ValueError("Google GenAI image response did not include image bytes.")

    def _generate_content_config(
        self,
        *,
        model: str,
        aspect_ratio: str,
        image_size: str | None,
    ) -> Any:
        types = _google_genai_types()
        image_config_kwargs: dict[str, Any] = {"aspect_ratio": aspect_ratio}
        if model != LEGACY_NANO_BANANA_MODEL and image_size:
            image_config_kwargs["image_size"] = image_size
        return types.GenerateContentConfig(
            image_config=types.ImageConfig(**image_config_kwargs)
        )

    def _generate_content_with_retry(self, *, model: str, contents: str, config: Any) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                return self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                if attempt >= self._max_retries or not _is_transient_provider_error(exc):
                    raise
                time.sleep(self._retry_base_delay_seconds * (2**attempt))

        raise RuntimeError("unreachable retry state")


def _is_transient_provider_error(exc: Exception) -> bool:
    status_details = _normalized_error_details(
        getattr(exc, "code", None),
        getattr(exc, "status", None),
        getattr(exc, "status_code", None),
        getattr(exc, "reason", None),
    )
    if _has_transient_status_signal(status_details):
        return True

    message_details = _normalized_error_details(exc)
    return any(
        fragment in message_details
        for fragment in (
            "503",
            "deadline expired",
            "deadline_exceeded",
            "deadline-exceeded",
            "deadline-expired",
            "high demand",
            "temporarily unavailable",
        )
    )


def _normalized_error_details(*values: object) -> str:
    return " ".join(str(value) for value in values if value is not None).lower()


def _has_transient_status_signal(details: str) -> bool:
    normalized = details.replace("-", "_")
    return any(
        fragment in normalized
        for fragment in (
            "503",
            "unavailable",
            "deadline_exceeded",
            "deadline_expired",
        )
    )


def build_google_genai_image_client_from_env() -> GoogleGenAIImageClient:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("GOOGLE_API_KEY is required for Google GenAI image generation.")

    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise ValueError("google-genai is required for Google GenAI image generation.") from exc

    return GoogleGenAIImageClient(genai.Client(api_key=api_key.strip()))
