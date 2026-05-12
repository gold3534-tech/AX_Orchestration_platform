from __future__ import annotations

import hashlib
import math
import os
import re
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from api.db.models import RunArtifact
from api.integrations.google_genai_images import (
    DEFAULT_NANO_BANANA_ASPECT_RATIO,
    DEFAULT_NANO_BANANA_IMAGE_SIZE,
    DEFAULT_NANO_BANANA_MODEL,
    build_google_genai_image_client_from_env,
)
from api.runtime.artifacts import create_artifact_metadata, staging_artifact_metadata
from api.runtime.supabase_artifact_storage import (
    supabase_public_artifact_storage_configured,
    upload_public_artifact_bytes,
)


_ALLOWED_ARTIFACT_STORAGE_MODES = frozenset({"temporary_only"})
DEFAULT_BATCH_DELAY_SECONDS = 10.0
MAX_BATCH_DELAY_SECONDS = 30.0
_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class NanoBananaArtifactRuntimeContext:
    db: Session
    owner_user_id: str
    run_id: str
    node_id: str | None = None


_artifact_runtime_context: ContextVar[NanoBananaArtifactRuntimeContext | None] = ContextVar(
    "nano_banana_artifact_runtime_context",
    default=None,
)


class NanoBananaImageInput(BaseModel):
    prompt: str | None = Field(default=None, min_length=1)
    image_prompts: list[str] | None = None
    delay_seconds: float = Field(
        default=DEFAULT_BATCH_DELAY_SECONDS,
        ge=0,
        le=MAX_BATCH_DELAY_SECONDS,
    )
    artifact_storage_mode: str = "temporary_only"

    @field_validator("prompt")
    @classmethod
    def _validate_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("prompt must not be empty")
        return stripped

    @field_validator("image_prompts")
    @classmethod
    def _validate_image_prompts(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) == 0:
            raise ValueError("image_prompts must include at least one prompt")
        prompts: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("prompt must not be empty")
            prompts.append(item.strip())
        return prompts

    @model_validator(mode="after")
    def _validate_prompt_contract(self) -> "NanoBananaImageInput":
        has_prompt = self.prompt is not None
        has_batch = self.image_prompts is not None
        if has_prompt and has_batch:
            raise ValueError("Use either prompt or image_prompts, not both")
        if not has_prompt and not has_batch:
            raise ValueError("prompt or image_prompts is required")
        return self


@contextmanager
def nano_banana_artifact_runtime_context(
    *,
    db: Session,
    owner_user_id: str,
    run_id: str,
    node_id: str | None = None,
) -> Iterator[None]:
    token = _artifact_runtime_context.set(
        NanoBananaArtifactRuntimeContext(
            db=db,
            owner_user_id=owner_user_id,
            run_id=run_id,
            node_id=node_id,
        )
    )
    try:
        yield
    finally:
        _artifact_runtime_context.reset(token)


def build_image_client_from_runtime():
    return build_google_genai_image_client_from_env()


COMPACT_OUTPUT_KEYS = (
    "artifact_id",
    "preview_url",
    "download_url",
    "mime_type",
    "model",
    "aspect_ratio",
    "image_size",
    "reused_existing_artifact",
    "prompt_sha256",
    "prompt_length",
)


def _compact_image_result(
    *,
    artifact: dict[str, Any],
    reused_existing_artifact: bool,
    model: str,
    generation_config: dict[str, Any],
    prompt_metadata: dict[str, Any],
) -> dict[str, Any]:
    compact: dict[str, Any] = {
        "artifact_id": str(artifact.get("artifact_id") or artifact.get("id")),
        "preview_url": artifact.get("preview_url"),
        "download_url": artifact.get("download_url"),
        "mime_type": artifact.get("mime_type") or artifact.get("media_type"),
        "model": model,
        "reused_existing_artifact": reused_existing_artifact,
        **generation_config,
        **prompt_metadata,
    }
    return {key: compact[key] for key in COMPACT_OUTPUT_KEYS if compact.get(key) is not None}


def stage_generated_image(
    *,
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    model: str,
    artifact_storage_mode: str,
    generation_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if artifact_storage_mode not in _ALLOWED_ARTIFACT_STORAGE_MODES:
        raise ValueError("Nano Banana only supports temporary_only artifact storage.")
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("image_bytes must not be empty")

    context = _artifact_runtime_context.get()
    if context is None:
        raise ValueError("Nano Banana artifact staging requires runtime artifact context.")

    sha256 = hashlib.sha256(image_bytes).hexdigest()
    prompt_metadata = _prompt_metadata(prompt)
    content_url = f"/api/run-artifacts/{{artifact_id}}/content"
    supabase_upload = None
    if supabase_public_artifact_storage_configured():
        supabase_upload = upload_public_artifact_bytes(
            image_bytes=image_bytes,
            media_type=mime_type,
            owner_user_id=context.owner_user_id,
            run_id=context.run_id,
            object_suffix=_extension_for_mime_type(mime_type),
        )

    if supabase_upload is not None:
        artifact = create_artifact_metadata(
            context.db,
            owner_user_id=context.owner_user_id,
            run_id=context.run_id,
            node_id=context.node_id,
            artifact_type="image",
            media_type=mime_type,
            storage_backend="ax_managed",
            storage_reference=f"supabase://{supabase_upload.bucket}/{supabase_upload.object_path}",
            storage_bucket=supabase_upload.bucket,
            storage_path=supabase_upload.object_path,
            source_tool="nano_banana",
            source_capability="image_generation",
            sha256=sha256,
            size_bytes=len(image_bytes),
            metadata_json={
                "model": model,
                **prompt_metadata,
                "artifact_storage_mode": artifact_storage_mode,
                "provider_media_url": supabase_upload.public_url,
                "external_resource_url": supabase_upload.public_url,
                "preview_url": supabase_upload.public_url,
                "download_url": supabase_upload.public_url,
                **dict(generation_config or {}),
            },
        )
    else:
        storage_root = _artifact_storage_root()
        node_segment = _safe_path_segment(context.node_id or "nano_banana_image")
        relative_path = (
            Path("generated")
            / context.run_id
            / node_segment
            / f"{sha256}{_extension_for_mime_type(mime_type)}"
        )
        artifact_path = (storage_root / relative_path).resolve(strict=False)
        if not _is_path_within_root(artifact_path, storage_root):
            raise ValueError("Generated image artifact path is outside the artifact storage root.")

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(image_bytes)

        artifact = create_artifact_metadata(
            context.db,
            owner_user_id=context.owner_user_id,
            run_id=context.run_id,
            node_id=context.node_id,
            artifact_type="image",
            media_type=mime_type,
            storage_backend="temporary",
            storage_reference=str(artifact_path),
            storage_path=str(artifact_path),
            source_tool="nano_banana",
            source_capability="image_generation",
            sha256=sha256,
            size_bytes=len(image_bytes),
            metadata_json={
                "model": model,
                **prompt_metadata,
                "artifact_storage_mode": artifact_storage_mode,
                **dict(generation_config or {}),
            },
        )
        content_url = content_url.format(artifact_id=artifact.id)
        metadata_json = dict(artifact.metadata_json or {})
        metadata_json.update({"preview_url": content_url, "download_url": content_url})
        artifact.metadata_json = metadata_json
        context.db.add(artifact)
        context.db.commit()
        context.db.refresh(artifact)
    metadata = staging_artifact_metadata(artifact)
    return {"artifact_id": metadata["id"], **metadata, **prompt_metadata}


class AXNanoBananaImageTool(BaseTool):
    name: str = "AX Nano Banana Image"
    description: str = "Generate images with Google Nano Banana 2 and stage them as AX artifacts."
    args_schema: type[BaseModel] = NanoBananaImageInput

    model: str = DEFAULT_NANO_BANANA_MODEL
    aspect_ratio: str = DEFAULT_NANO_BANANA_ASPECT_RATIO
    image_size: str | None = DEFAULT_NANO_BANANA_IMAGE_SIZE

    def _run(
        self,
        prompt: str | None = None,
        image_prompts: list[str] | None = None,
        delay_seconds: float = DEFAULT_BATCH_DELAY_SECONDS,
        artifact_storage_mode: str = "temporary_only",
    ) -> dict[str, Any]:
        is_batch, prompts = _resolve_prompt_batch(prompt=prompt, image_prompts=image_prompts)
        delay = _validated_delay_seconds(delay_seconds)
        if not is_batch:
            return self._generate_one_image(
                prompt=prompts[0],
                artifact_storage_mode=artifact_storage_mode,
            )
        return self._generate_image_batch(
            prompts=prompts,
            artifact_storage_mode=artifact_storage_mode,
            delay_seconds=delay,
        )

    def _generate_one_image(self, *, prompt: str, artifact_storage_mode: str) -> dict[str, Any]:
        prompt = _required_prompt(prompt)
        prompt_metadata = _prompt_metadata(prompt)
        reusable_artifact = _find_current_run_reusable_artifact(
            prompt_metadata=prompt_metadata,
            model=self.model,
            aspect_ratio=self.aspect_ratio,
            image_size=self.image_size,
            artifact_storage_mode=artifact_storage_mode,
        )
        if reusable_artifact is not None:
            metadata = staging_artifact_metadata(reusable_artifact)
            generation_config = _generation_config_from_metadata(
                metadata.get("metadata_json"),
                aspect_ratio=self.aspect_ratio,
                image_size=self.image_size,
            )
            return _compact_image_result(
                artifact={"artifact_id": metadata["id"], **metadata},
                reused_existing_artifact=True,
                model=self.model,
                generation_config=generation_config,
                prompt_metadata=prompt_metadata,
            )

        image = build_image_client_from_runtime().generate_image(
            prompt=prompt,
            model=self.model,
            aspect_ratio=self.aspect_ratio,
            image_size=self.image_size,
        )
        generation_config = {"aspect_ratio": image.get("aspect_ratio", self.aspect_ratio)}
        image_size = image.get("image_size") or self.image_size
        if image_size:
            generation_config["image_size"] = image_size
        artifact = stage_generated_image(
            image_bytes=image["bytes"],
            mime_type=image["mime_type"],
            prompt=prompt,
            model=self.model,
            artifact_storage_mode=artifact_storage_mode,
            generation_config=generation_config,
        )
        return _compact_image_result(
            artifact=artifact,
            reused_existing_artifact=False,
            model=self.model,
            generation_config=generation_config,
            prompt_metadata=prompt_metadata,
        )

    def _generate_image_batch(
        self,
        *,
        prompts: list[str],
        artifact_storage_mode: str,
        delay_seconds: float,
    ) -> dict[str, Any]:
        images: list[dict[str, Any]] = []
        for index, item in enumerate(prompts):
            images.append(
                self._generate_one_image(
                    prompt=item,
                    artifact_storage_mode=artifact_storage_mode,
                )
            )
            if index < len(prompts) - 1 and delay_seconds > 0:
                time.sleep(delay_seconds)
        return {"images": images, "count": len(images)}


def _required_prompt(prompt: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must not be empty")
    return prompt.strip()


def _resolve_prompt_batch(
    *,
    prompt: str | None,
    image_prompts: list[str] | None,
) -> tuple[bool, list[str]]:
    has_prompt_input = prompt is not None
    has_batch = image_prompts is not None
    if has_prompt_input and has_batch:
        raise ValueError("Use either prompt or image_prompts, not both.")
    if not has_prompt_input and not has_batch:
        raise ValueError("prompt or image_prompts is required.")
    if has_prompt_input:
        return False, [_required_prompt(prompt or "")]
    if not isinstance(image_prompts, list) or len(image_prompts) == 0:
        raise ValueError("image_prompts must include at least one prompt.")
    return True, [_required_prompt(item) for item in image_prompts]


def _validated_delay_seconds(delay_seconds: float) -> float:
    try:
        value = float(delay_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("delay_seconds must be between 0 and 30 seconds.") from exc
    if not math.isfinite(value) or value < 0 or value > MAX_BATCH_DELAY_SECONDS:
        raise ValueError("delay_seconds must be between 0 and 30 seconds.")
    return value


def _prompt_metadata(prompt: str) -> dict[str, Any]:
    return {
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_length": len(prompt),
    }


def _find_current_run_reusable_artifact(
    *,
    prompt_metadata: dict[str, Any],
    model: str,
    aspect_ratio: str,
    image_size: str | None,
    artifact_storage_mode: str,
) -> RunArtifact | None:
    context = _artifact_runtime_context.get()
    if context is None:
        return None

    artifacts = (
        context.db.query(RunArtifact)
        .filter(
            RunArtifact.owner_user_id == context.owner_user_id,
            RunArtifact.run_id == context.run_id,
            RunArtifact.node_id == context.node_id,
            RunArtifact.artifact_type == "image",
            RunArtifact.source_tool == "nano_banana",
            RunArtifact.source_capability == "image_generation",
            RunArtifact.status == "available",
        )
        .order_by(RunArtifact.created_at.desc(), RunArtifact.id.desc())
        .all()
    )
    for artifact in artifacts:
        metadata_json = artifact.metadata_json if isinstance(artifact.metadata_json, dict) else {}
        if _artifact_metadata_matches_generation(
            metadata_json,
            prompt_metadata=prompt_metadata,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            artifact_storage_mode=artifact_storage_mode,
        ):
            return artifact
    return None


def _artifact_metadata_matches_generation(
    metadata_json: dict[str, Any],
    *,
    prompt_metadata: dict[str, Any],
    model: str,
    aspect_ratio: str,
    image_size: str | None,
    artifact_storage_mode: str,
) -> bool:
    if metadata_json.get("model") != model:
        return False
    if metadata_json.get("prompt_sha256") != prompt_metadata["prompt_sha256"]:
        return False
    if metadata_json.get("prompt_length") != prompt_metadata["prompt_length"]:
        return False
    if metadata_json.get("aspect_ratio") != aspect_ratio:
        return False
    if metadata_json.get("artifact_storage_mode") != artifact_storage_mode:
        return False
    return metadata_json.get("image_size") == image_size


def _generation_config_from_metadata(
    metadata_json: object,
    *,
    aspect_ratio: str,
    image_size: str | None,
) -> dict[str, Any]:
    metadata = metadata_json if isinstance(metadata_json, dict) else {}
    generation_config = {"aspect_ratio": metadata.get("aspect_ratio", aspect_ratio)}
    resolved_image_size = metadata.get("image_size", image_size)
    if resolved_image_size:
        generation_config["image_size"] = resolved_image_size
    return generation_config


def _artifact_storage_root() -> Path:
    configured = os.getenv("AX_ARTIFACT_STORAGE_ROOT")
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser().resolve(strict=False)
    return (Path(tempfile.gettempdir()) / "ax-artifacts").resolve(strict=False)


def _extension_for_mime_type(mime_type: str) -> str:
    return _MIME_EXTENSIONS.get(mime_type, ".bin")


def _safe_path_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return segment or "nano_banana_image"


def _is_path_within_root(path: Path, root: Path) -> bool:
    return path == root or root in path.parents
