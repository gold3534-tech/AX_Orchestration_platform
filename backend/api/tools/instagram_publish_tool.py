from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator, model_validator

from api.integrations.meta_instagram import (
    build_meta_instagram_client_from_runtime,
    current_meta_instagram_runtime_context,
)
from api.runtime.provider_media_urls import provider_media_url_for_artifact

_SUPPORTED_PUBLISH_MODES = frozenset({1, 3})


class InstagramPublishInput(BaseModel):
    artifact_ids: list[str] = Field(min_length=1, max_length=3)
    caption: str = Field(min_length=1)


class AXInstagramPublishTool(BaseTool):
    name: str = "AX Instagram Publish"
    description: str = (
        "Publish AX image artifacts to Instagram. Provide artifact_ids from generated image "
        "tool results and caption as the Instagram post body text."
    )
    args_schema: type[BaseModel] = InstagramPublishInput

    publish_mode: int = 3
    poll_timeout_seconds: int = 60
    poll_interval_seconds: int = 3

    @field_validator("publish_mode", mode="before")
    @classmethod
    def _validate_publish_mode(cls, publish_mode: object) -> int:
        if (
            not isinstance(publish_mode, int)
            or isinstance(publish_mode, bool)
            or publish_mode not in _SUPPORTED_PUBLISH_MODES
        ):
            raise ValueError("publish_mode must be one of: 1, 3")
        return publish_mode

    @field_validator("poll_timeout_seconds", mode="before")
    @classmethod
    def _validate_poll_timeout_seconds(cls, value: object) -> int:
        if type(value) is not int or not 1 <= value <= 300:
            raise ValueError("poll_timeout_seconds must be between 1 and 300")
        return value

    @field_validator("poll_interval_seconds", mode="before")
    @classmethod
    def _validate_poll_interval_seconds(cls, value: object) -> int:
        if type(value) is not int or not 1 <= value <= 60:
            raise ValueError("poll_interval_seconds must be between 1 and 60")
        return value

    @model_validator(mode="after")
    def _validate_polling_order(self):
        if self.poll_interval_seconds > self.poll_timeout_seconds:
            raise ValueError("poll_interval_seconds must not exceed poll_timeout_seconds")
        return self

    def _run(self, artifact_ids: list[str], caption: str) -> dict[str, Any]:
        artifact_ids = self._validated_artifact_ids(artifact_ids)
        caption = self._validated_caption(caption)
        context = current_meta_instagram_runtime_context()
        image_urls = [
            provider_media_url_for_artifact(
                artifact_id=artifact_id,
                owner_user_id=context.owner_user_id,
                run_id=context.run_id,
                db=context.db,
            )
            for artifact_id in artifact_ids
        ]
        client = build_meta_instagram_client_from_runtime(
            poll_timeout_seconds=self.poll_timeout_seconds,
            poll_interval_seconds=self.poll_interval_seconds,
        )
        resolved_publish_mode = len(artifact_ids)
        if resolved_publish_mode == 1:
            result = client.publish_image(image_url=image_urls[0], caption=caption)
        elif resolved_publish_mode == 3:
            result = client.publish_carousel(image_urls=image_urls, caption=caption)
        else:
            raise ValueError("Instagram publish requires either 1 or 3 unique artifact ids.")
        return {
            "status": result.get("status"),
            "publish_mode": resolved_publish_mode,
            "ig_container_id": result.get("ig_container_id"),
            "ig_media_id": result.get("ig_media_id"),
            "artifact_ids": artifact_ids,
        }

    def _validated_artifact_ids(self, artifact_ids: list[str]) -> list[str]:
        if not isinstance(artifact_ids, list):
            raise ValueError("Instagram publish requires either 1 or 3 unique artifact ids.")
        normalized = [
            artifact_id.strip() for artifact_id in artifact_ids if isinstance(artifact_id, str)
        ]
        if len(normalized) != len(artifact_ids) or any(
            not artifact_id for artifact_id in normalized
        ):
            raise ValueError("artifact_ids must be non-empty strings.")

        unique_artifact_ids = list(dict.fromkeys(normalized))
        if len(unique_artifact_ids) not in {1, 3}:
            raise ValueError("Instagram publish requires either 1 or 3 unique artifact ids.")
        return unique_artifact_ids

    def _validated_caption(self, caption: str) -> str:
        if not isinstance(caption, str) or not caption.strip():
            raise ValueError("caption must not be empty")
        return caption.strip()
