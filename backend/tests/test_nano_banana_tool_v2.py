from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from api.db import models
from api.db.models import Asset, AssetVersion, FlowRun
from api.integrations.google_genai_images import (
    DEFAULT_NANO_BANANA_MODEL,
    GoogleGenAIImageClient,
)
from api.tools.nano_banana_image_tool import (
    AXNanoBananaImageTool,
    NanoBananaImageInput,
    nano_banana_artifact_runtime_context,
    stage_generated_image,
)


def _create_flow_run(
    db,
    *,
    owner_user_id: str,
    run_id: str = "33333333-3333-4333-8333-333333333333",
) -> FlowRun:
    asset = Asset(
        asset_type="flow",
        workspace_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        owner_user_id=owner_user_id,
        name=f"Flow {run_id}",
    )
    db.add(asset)
    db.flush()
    asset_version = AssetVersion(
        asset_id=asset.id,
        version_number=1,
        status="published",
        created_by=owner_user_id,
        payload_json={"type": "flow"},
        metadata_json={"type": "flow"},
    )
    db.add(asset_version)
    db.flush()
    flow_run = FlowRun(
        id=run_id,
        flow_version_id=asset_version.id,
        status="running",
        input_json={},
    )
    db.add(flow_run)
    db.flush()
    return flow_run


class FakeImageClient:
    def generate_image(self, *, prompt: str, model: str, aspect_ratio: str, image_size: str | None):
        return {
            "mime_type": "image/png",
            "bytes": b"png-bytes",
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        }


def _force_local_artifact_storage(monkeypatch):
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.supabase_public_artifact_storage_configured",
        lambda: False,
    )


def test_nano_banana_tool_returns_compact_artifact_output(monkeypatch):
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FakeImageClient(),
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.stage_generated_image",
        lambda **kwargs: {
            "artifact_id": "artifact-1",
            "id": "artifact-1",
            "run_id": "run-1",
            "node_id": "node-1",
            "artifact_type": "image",
            "mime_type": kwargs["mime_type"],
            "media_type": kwargs["mime_type"],
            "sha256": "hash",
            "size_bytes": 9,
            "storage_backend": "temporary",
            "source_tool": "nano_banana",
            "source_capability": "image_generation",
            "retention_mode": "temporary",
            "expires_at": "2026-05-11T00:00:00+00:00",
            "retention_expires_at": "2026-05-11T00:00:00+00:00",
            "preview_url": "/api/run-artifacts/artifact-1/content",
            "download_url": "/api/run-artifacts/artifact-1/content",
            "status": "available",
            "metadata_json": {
                "model": DEFAULT_NANO_BANANA_MODEL,
                "artifact_storage_mode": "temporary_only",
                "preview_url": "/api/run-artifacts/artifact-1/content",
                "download_url": "/api/run-artifacts/artifact-1/content",
                "aspect_ratio": "1:1",
                "image_size": "1K",
            },
            "self_delete_supported": False,
            "created_at": "2026-05-04T00:00:00+00:00",
            "updated_at": "2026-05-04T00:00:00+00:00",
            "prompt_sha256": hashlib.sha256(b"Create a product image").hexdigest(),
            "prompt_length": len("Create a product image"),
        },
    )
    tool = AXNanoBananaImageTool()

    result = tool._run(prompt="Create a product image")

    assert result == {
        "artifact_id": "artifact-1",
        "preview_url": "/api/run-artifacts/artifact-1/content",
        "download_url": "/api/run-artifacts/artifact-1/content",
        "mime_type": "image/png",
        "model": DEFAULT_NANO_BANANA_MODEL,
        "aspect_ratio": "1:1",
        "image_size": "1K",
        "reused_existing_artifact": False,
        "prompt_sha256": hashlib.sha256(b"Create a product image").hexdigest(),
        "prompt_length": len("Create a product image"),
    }
    assert "metadata_json" not in result
    assert "storage_backend" not in result
    assert "retention_mode" not in result
    assert "created_at" not in result
    assert "updated_at" not in result
    assert "prompt" not in result
    assert "bytes" not in result
    assert "image_bytes" not in result


def test_nano_banana_tool_rejects_empty_prompt(monkeypatch):
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FakeImageClient(),
    )
    tool = AXNanoBananaImageTool()

    with pytest.raises(ValueError, match="prompt must not be empty"):
        tool._run(prompt="  ")


def test_nano_banana_tool_rejects_prompt_and_image_prompts_together(monkeypatch):
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FakeImageClient(),
    )
    tool = AXNanoBananaImageTool()

    with pytest.raises(ValueError, match="Use either prompt or image_prompts"):
        tool._run(prompt="Single prompt", image_prompts=["Batch prompt"])

    with pytest.raises(ValueError, match="Use either prompt or image_prompts"):
        tool._run(prompt="  ", image_prompts=["Batch prompt"])


def test_nano_banana_tool_rejects_missing_prompt_inputs(monkeypatch):
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FakeImageClient(),
    )
    tool = AXNanoBananaImageTool()

    with pytest.raises(ValueError, match="prompt or image_prompts is required"):
        tool._run()


def test_nano_banana_tool_rejects_empty_image_prompts(monkeypatch):
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FakeImageClient(),
    )
    tool = AXNanoBananaImageTool()

    with pytest.raises(ValueError, match="image_prompts must include at least one prompt"):
        tool._run(image_prompts=[])

    with pytest.raises(ValueError, match="prompt must not be empty"):
        tool._run(image_prompts=["First prompt", "   "])


def test_nano_banana_tool_rejects_delay_outside_safe_range(monkeypatch):
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FakeImageClient(),
    )
    tool = AXNanoBananaImageTool()

    with pytest.raises(ValueError, match="delay_seconds must be between 0 and 30"):
        tool._run(image_prompts=["First prompt"], delay_seconds=-1)

    with pytest.raises(ValueError, match="delay_seconds must be between 0 and 30"):
        tool._run(image_prompts=["First prompt"], delay_seconds=31)


def test_nano_banana_tool_rejects_non_finite_delay(monkeypatch):
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FakeImageClient(),
    )
    tool = AXNanoBananaImageTool()

    with pytest.raises(ValueError, match="delay_seconds must be between 0 and 30"):
        tool._run(image_prompts=["First prompt"], delay_seconds=float("nan"))


def test_nano_banana_tool_generates_batch_sequentially_with_default_delay(monkeypatch):
    events: list[tuple[str, object]] = []

    class RecordingImageClient:
        def __init__(self):
            self.calls: list[str] = []

        def generate_image(self, *, prompt: str, model: str, aspect_ratio: str, image_size: str | None):
            self.calls.append(prompt)
            events.append(("generate", prompt))
            return {
                "mime_type": "image/png",
                "bytes": f"bytes-{prompt}".encode("utf-8"),
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
            }

    recording_client = RecordingImageClient()
    staged_prompts: list[str] = []
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: recording_client,
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.time.sleep",
        lambda delay: events.append(("sleep", delay)),
    )

    def fake_stage_generated_image(**kwargs):
        staged_prompts.append(kwargs["prompt"])
        events.append(("stage", kwargs["prompt"]))
        index = len(staged_prompts)
        return {
            "artifact_id": f"artifact-{index}",
            "mime_type": kwargs["mime_type"],
            "preview_url": f"/api/run-artifacts/artifact-{index}/content",
            "download_url": f"/api/run-artifacts/artifact-{index}/content",
            "prompt_sha256": hashlib.sha256(kwargs["prompt"].encode("utf-8")).hexdigest(),
            "prompt_length": len(kwargs["prompt"]),
        }

    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.stage_generated_image",
        fake_stage_generated_image,
    )
    tool = AXNanoBananaImageTool()

    result = tool._run(image_prompts=["Prompt 1", "Prompt 2", "Prompt 3"])

    assert recording_client.calls == ["Prompt 1", "Prompt 2", "Prompt 3"]
    assert staged_prompts == ["Prompt 1", "Prompt 2", "Prompt 3"]
    assert events == [
        ("generate", "Prompt 1"),
        ("stage", "Prompt 1"),
        ("sleep", 10.0),
        ("generate", "Prompt 2"),
        ("stage", "Prompt 2"),
        ("sleep", 10.0),
        ("generate", "Prompt 3"),
        ("stage", "Prompt 3"),
    ]
    assert result["count"] == 3
    assert [image["artifact_id"] for image in result["images"]] == [
        "artifact-1",
        "artifact-2",
        "artifact-3",
    ]
    assert all("metadata_json" not in image for image in result["images"])


def test_nano_banana_tool_uses_custom_batch_delay_without_trailing_sleep(monkeypatch):
    class RecordingImageClient:
        def generate_image(self, *, prompt: str, model: str, aspect_ratio: str, image_size: str | None):
            return {
                "mime_type": "image/png",
                "bytes": prompt.encode("utf-8"),
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
            }

    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: RecordingImageClient(),
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.time.sleep",
        lambda delay: sleep_calls.append(delay),
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.stage_generated_image",
        lambda **kwargs: {
            "artifact_id": f"artifact-{kwargs['prompt']}",
            "mime_type": kwargs["mime_type"],
            "prompt_sha256": hashlib.sha256(kwargs["prompt"].encode("utf-8")).hexdigest(),
            "prompt_length": len(kwargs["prompt"]),
        },
    )
    tool = AXNanoBananaImageTool()

    result = tool._run(image_prompts=["A", "B"], delay_seconds=2)

    assert sleep_calls == [2.0]
    assert result["count"] == 2
    assert [image["artifact_id"] for image in result["images"]] == ["artifact-A", "artifact-B"]


def test_nano_banana_image_input_validates_exclusive_prompt_contract():
    with pytest.raises(ValidationError, match="Use either prompt or image_prompts"):
        NanoBananaImageInput(prompt="Single prompt", image_prompts=["Batch prompt"])

    with pytest.raises(ValidationError, match="prompt or image_prompts is required"):
        NanoBananaImageInput()


def test_nano_banana_image_input_validates_image_prompts_contract():
    with pytest.raises(ValidationError, match="image_prompts must include at least one prompt"):
        NanoBananaImageInput(image_prompts=[])

    with pytest.raises(ValidationError, match="prompt must not be empty"):
        NanoBananaImageInput(image_prompts=["First prompt", "   "])

    with pytest.raises(ValidationError):
        NanoBananaImageInput(image_prompts=["First prompt"], delay_seconds=31)


def test_nano_banana_tool_generates_each_batch_prompt(monkeypatch):
    generated_prompts: list[str] = []

    class RecordingImageClient:
        def generate_image(
            self,
            *,
            prompt: str,
            model: str,
            aspect_ratio: str,
            image_size: str | None,
        ):
            generated_prompts.append(prompt)
            return {
                "mime_type": "image/png",
                "bytes": f"png-bytes-{len(generated_prompts)}".encode("utf-8"),
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
            }

    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: RecordingImageClient(),
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.stage_generated_image",
        lambda **kwargs: {
            "artifact_id": f"artifact-{len(generated_prompts)}",
            "preview_url": f"/api/run-artifacts/artifact-{len(generated_prompts)}/content",
            "download_url": f"/api/run-artifacts/artifact-{len(generated_prompts)}/content",
            "mime_type": kwargs["mime_type"],
            "prompt_sha256": hashlib.sha256(kwargs["prompt"].encode("utf-8")).hexdigest(),
            "prompt_length": len(kwargs["prompt"]),
        },
    )
    tool = AXNanoBananaImageTool()

    result = tool._run(image_prompts=["First prompt", "Second prompt"], delay_seconds=0)

    assert generated_prompts == ["First prompt", "Second prompt"]
    assert result["count"] == 2
    assert [image["artifact_id"] for image in result["images"]] == ["artifact-1", "artifact-2"]
    assert [image["prompt_length"] for image in result["images"]] == [
        len("First prompt"),
        len("Second prompt"),
    ]


def test_stage_generated_image_writes_safe_temporary_artifact(monkeypatch, tmp_path, db):
    owner_user_id = "11111111-1111-1111-1111-111111111111"
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id=owner_user_id, run_id=run_id)
    monkeypatch.setenv("AX_ARTIFACT_STORAGE_ROOT", str(tmp_path))
    _force_local_artifact_storage(monkeypatch)

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate:image",
    ):
        result = stage_generated_image(
            image_bytes=b"png-bytes",
            mime_type="image/png",
            prompt="Create a product image",
            model=DEFAULT_NANO_BANANA_MODEL,
            artifact_storage_mode="temporary_only",
        )

    artifact_path = tmp_path / "generated" / run_id / "generate-image" / f"{result['sha256']}.png"
    assert artifact_path.read_bytes() == b"png-bytes"
    assert result["artifact_id"] == result["id"]
    assert result["mime_type"] == "image/png"
    assert result["storage_backend"] == "temporary"
    assert result["preview_url"] == f"/api/run-artifacts/{result['artifact_id']}/content"
    assert result["download_url"] == f"/api/run-artifacts/{result['artifact_id']}/content"
    assert result["retention_mode"] == "temporary"
    assert result["self_delete_supported"] is False
    assert "bytes" not in result


def test_secret_like_prompt_is_not_returned_or_stored_in_public_metadata(monkeypatch, tmp_path, db):
    secret_prompt = "Generate this credential card: sk-live-1234567890abcdef"
    owner_user_id = "11111111-1111-1111-1111-111111111111"
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id=owner_user_id, run_id=run_id)
    monkeypatch.setenv("AX_ARTIFACT_STORAGE_ROOT", str(tmp_path))
    _force_local_artifact_storage(monkeypatch)
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FakeImageClient(),
    )
    tool = AXNanoBananaImageTool()

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate:image",
    ):
        result = tool._run(prompt=secret_prompt)

    assert result["artifact_id"]
    assert result["mime_type"] == "image/png"
    assert result["model"] == DEFAULT_NANO_BANANA_MODEL
    assert result["prompt_sha256"]
    assert result["prompt_length"] == len(secret_prompt)
    assert "prompt" not in result
    assert secret_prompt not in str(result)
    assert "sk-live-1234567890abcdef" not in str(result)
    artifact = (
        db.query(models.RunArtifact)
        .filter(models.RunArtifact.id == result["artifact_id"])
        .one()
    )
    assert artifact.metadata_json == {
        "model": DEFAULT_NANO_BANANA_MODEL,
        "prompt_sha256": result["prompt_sha256"],
        "prompt_length": len(secret_prompt),
        "artifact_storage_mode": "temporary_only",
        "preview_url": f"/api/run-artifacts/{result['artifact_id']}/content",
        "download_url": f"/api/run-artifacts/{result['artifact_id']}/content",
        "aspect_ratio": "1:1",
        "image_size": "1K",
    }
    assert "metadata_json" not in result


def test_nano_banana_tool_reuses_current_run_artifact_for_same_prompt(monkeypatch, tmp_path, db):
    owner_user_id = "11111111-1111-1111-1111-111111111111"
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id=owner_user_id, run_id=run_id)
    monkeypatch.setenv("AX_ARTIFACT_STORAGE_ROOT", str(tmp_path))
    _force_local_artifact_storage(monkeypatch)

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate:image",
    ):
        staged = stage_generated_image(
            image_bytes=b"existing-png-bytes",
            mime_type="image/png",
            prompt="Create a product image",
            model=DEFAULT_NANO_BANANA_MODEL,
            artifact_storage_mode="temporary_only",
            generation_config={"aspect_ratio": "1:1", "image_size": "1K"},
        )

    class FailingImageClient:
        def generate_image(self, **kwargs):
            raise AssertionError("provider should not be called")

    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: FailingImageClient(),
    )
    tool = AXNanoBananaImageTool()

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate:image",
    ):
        result = tool._run(prompt="Create a product image")

    assert result["artifact_id"] == staged["artifact_id"]
    assert result["reused_existing_artifact"] is True
    assert result["model"] == DEFAULT_NANO_BANANA_MODEL
    assert result["aspect_ratio"] == "1:1"
    assert result["image_size"] == "1K"
    assert result["prompt_sha256"] == staged["prompt_sha256"]


def test_nano_banana_batch_reuses_existing_current_run_artifacts(monkeypatch, tmp_path, db):
    owner_user_id = "11111111-1111-1111-1111-111111111111"
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id=owner_user_id, run_id=run_id)
    monkeypatch.setenv("AX_ARTIFACT_STORAGE_ROOT", str(tmp_path))
    _force_local_artifact_storage(monkeypatch)

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate:image",
    ):
        staged = stage_generated_image(
            image_bytes=b"existing-png-bytes",
            mime_type="image/png",
            prompt="Prompt 1",
            model=DEFAULT_NANO_BANANA_MODEL,
            artifact_storage_mode="temporary_only",
            generation_config={"aspect_ratio": "1:1", "image_size": "1K"},
        )

    class RecordingImageClient:
        def __init__(self):
            self.calls: list[str] = []

        def generate_image(self, *, prompt: str, model: str, aspect_ratio: str, image_size: str | None):
            self.calls.append(prompt)
            return {
                "mime_type": "image/png",
                "bytes": b"new-png-bytes",
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
            }

    recording_client = RecordingImageClient()
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: recording_client,
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.time.sleep",
        lambda delay: sleep_calls.append(delay),
    )
    tool = AXNanoBananaImageTool()

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate:image",
    ):
        result = tool._run(image_prompts=["Prompt 1", "Prompt 2"], delay_seconds=0)

    assert recording_client.calls == ["Prompt 2"]
    assert sleep_calls == []
    assert result["count"] == 2
    assert result["images"][0]["artifact_id"] == staged["artifact_id"]
    assert result["images"][0]["reused_existing_artifact"] is True
    assert result["images"][1]["reused_existing_artifact"] is False
    assert result["images"][1]["prompt_sha256"] == hashlib.sha256(b"Prompt 2").hexdigest()


def test_nano_banana_tool_does_not_reuse_current_run_artifact_for_different_prompt(
    monkeypatch, tmp_path, db
):
    owner_user_id = "11111111-1111-1111-1111-111111111111"
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id=owner_user_id, run_id=run_id)
    monkeypatch.setenv("AX_ARTIFACT_STORAGE_ROOT", str(tmp_path))
    _force_local_artifact_storage(monkeypatch)

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate:image",
    ):
        staged = stage_generated_image(
            image_bytes=b"existing-png-bytes",
            mime_type="image/png",
            prompt="Create a product image",
            model=DEFAULT_NANO_BANANA_MODEL,
            artifact_storage_mode="temporary_only",
            generation_config={"aspect_ratio": "1:1", "image_size": "1K"},
        )

    class RecordingImageClient:
        def __init__(self):
            self.calls = []

        def generate_image(self, *, prompt: str, model: str, aspect_ratio: str, image_size: str | None):
            self.calls.append(prompt)
            return {
                "mime_type": "image/png",
                "bytes": b"new-png-bytes",
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
            }

    recording_client = RecordingImageClient()
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: recording_client,
    )
    tool = AXNanoBananaImageTool()

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate:image",
    ):
        result = tool._run(prompt="Create a different product image")

    assert recording_client.calls == ["Create a different product image"]
    assert result["reused_existing_artifact"] is False
    assert result["artifact_id"] != staged["artifact_id"]
    artifact = (
        db.query(models.RunArtifact)
        .filter(models.RunArtifact.id == result["artifact_id"])
        .one()
    )
    assert artifact.sha256 != hashlib.sha256(b"existing-png-bytes").hexdigest()


class FakeInlineData:
    mime_type = "image/png"
    data = b"png-bytes"


class FakePart:
    inline_data = FakeInlineData()


class FakeContent:
    parts = [FakePart()]


class FakeCandidate:
    content = FakeContent()


class FakeResponse:
    candidates = [FakeCandidate()]


class FakeImageConfig:
    def __init__(self, *, aspect_ratio=None, image_size=None):
        self.aspect_ratio = aspect_ratio
        self.image_size = image_size


class FakeGenerateContentConfig:
    def __init__(self, *, image_config=None):
        self.image_config = image_config


class FakeGoogleGenAITypes:
    ImageConfig = FakeImageConfig
    GenerateContentConfig = FakeGenerateContentConfig


class RecordingModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, *, model: str, contents: str, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return FakeResponse()


class RecordingGenAIClient:
    def __init__(self):
        self.models = RecordingModels()


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, *, model: str, contents: str, config=None):
        self.calls.append((model, contents))
        return FakeResponse()


class FakeGenAIClient:
    def __init__(self):
        self.models = FakeModels()


def test_google_genai_image_client_extracts_inline_image_bytes():
    genai_client = FakeGenAIClient()
    client = GoogleGenAIImageClient(genai_client)

    result = client.generate_image(prompt="A clean product image")

    assert result == {
        "mime_type": "image/png",
        "bytes": b"png-bytes",
        "model": DEFAULT_NANO_BANANA_MODEL,
        "prompt": "A clean product image",
        "aspect_ratio": "1:1",
        "image_size": "1K",
    }
    assert genai_client.models.calls == [
        (DEFAULT_NANO_BANANA_MODEL, "A clean product image")
    ]


def test_google_genai_image_client_passes_image_config_for_gemini3(monkeypatch):
    monkeypatch.setattr(
        "api.integrations.google_genai_images._google_genai_types",
        lambda: FakeGoogleGenAITypes,
    )
    genai_client = RecordingGenAIClient()
    client = GoogleGenAIImageClient(genai_client)

    result = client.generate_image(
        prompt="A clean product image",
        model="gemini-3.1-flash-image-preview",
        aspect_ratio="16:9",
        image_size="2K",
    )

    call = genai_client.models.calls[0]
    assert call["model"] == "gemini-3.1-flash-image-preview"
    assert call["contents"] == "A clean product image"
    assert call["config"].image_config.aspect_ratio == "16:9"
    assert call["config"].image_config.image_size == "2K"
    assert result["aspect_ratio"] == "16:9"
    assert result["image_size"] == "2K"


def test_google_genai_image_client_omits_image_size_for_legacy_model(monkeypatch):
    monkeypatch.setattr(
        "api.integrations.google_genai_images._google_genai_types",
        lambda: FakeGoogleGenAITypes,
    )
    genai_client = RecordingGenAIClient()
    client = GoogleGenAIImageClient(genai_client)

    result = client.generate_image(
        prompt="A clean product image",
        model="gemini-2.5-flash-image",
        aspect_ratio="9:16",
        image_size="4K",
    )

    call = genai_client.models.calls[0]
    assert call["config"].image_config.aspect_ratio == "9:16"
    assert call["config"].image_config.image_size is None
    assert result["aspect_ratio"] == "9:16"
    assert "image_size" not in result


def test_google_genai_image_client_retries_transient_unavailable_and_succeeds(monkeypatch):
    monkeypatch.setattr(
        "api.integrations.google_genai_images._google_genai_types",
        lambda: FakeGoogleGenAITypes,
    )
    sleep_calls = []
    monkeypatch.setattr(
        "api.integrations.google_genai_images.time.sleep",
        lambda delay: sleep_calls.append(delay),
    )

    class FlakyModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, *, model: str, contents: str, config=None):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("503 UNAVAILABLE: service is under high demand")
            return FakeResponse()

    class FlakyGenAIClient:
        def __init__(self):
            self.models = FlakyModels()

    genai_client = FlakyGenAIClient()
    client = GoogleGenAIImageClient(genai_client, retry_base_delay_seconds=0.25)

    result = client.generate_image(prompt="A clean product image")

    assert result["bytes"] == b"png-bytes"
    assert genai_client.models.calls == 3
    assert sleep_calls == [0.25, 0.5]


def test_google_genai_image_client_does_not_retry_non_transient_unavailable(monkeypatch):
    monkeypatch.setattr(
        "api.integrations.google_genai_images._google_genai_types",
        lambda: FakeGoogleGenAITypes,
    )
    sleep_calls = []
    monkeypatch.setattr(
        "api.integrations.google_genai_images.time.sleep",
        lambda delay: sleep_calls.append(delay),
    )

    class NonTransientUnavailableModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, *, model: str, contents: str, config=None):
            self.calls += 1
            raise ValueError("requested model is unavailable for this account")

    class NonTransientUnavailableGenAIClient:
        def __init__(self):
            self.models = NonTransientUnavailableModels()

    genai_client = NonTransientUnavailableGenAIClient()
    client = GoogleGenAIImageClient(genai_client, retry_base_delay_seconds=0.25)

    with pytest.raises(ValueError, match="unavailable for this account"):
        client.generate_image(prompt="A clean product image")

    assert genai_client.models.calls == 1
    assert sleep_calls == []


def test_google_genai_image_client_retries_deadline_exceeded_status(monkeypatch):
    monkeypatch.setattr(
        "api.integrations.google_genai_images._google_genai_types",
        lambda: FakeGoogleGenAITypes,
    )
    sleep_calls = []
    monkeypatch.setattr(
        "api.integrations.google_genai_images.time.sleep",
        lambda delay: sleep_calls.append(delay),
    )

    class DeadlineExceededError(RuntimeError):
        status = "DEADLINE_EXCEEDED"

    class DeadlineExceededModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, *, model: str, contents: str, config=None):
            self.calls += 1
            if self.calls == 1:
                raise DeadlineExceededError("provider deadline-expired")
            return FakeResponse()

    class DeadlineExceededGenAIClient:
        def __init__(self):
            self.models = DeadlineExceededModels()

    genai_client = DeadlineExceededGenAIClient()
    client = GoogleGenAIImageClient(genai_client, retry_base_delay_seconds=0.25)

    result = client.generate_image(prompt="A clean product image")

    assert result["bytes"] == b"png-bytes"
    assert genai_client.models.calls == 2
    assert sleep_calls == [0.25]


def test_google_genai_image_client_stops_retry_after_budget(monkeypatch):
    monkeypatch.setattr(
        "api.integrations.google_genai_images._google_genai_types",
        lambda: FakeGoogleGenAITypes,
    )
    sleep_calls = []
    monkeypatch.setattr(
        "api.integrations.google_genai_images.time.sleep",
        lambda delay: sleep_calls.append(delay),
    )

    class AlwaysUnavailableModels:
        def __init__(self):
            self.calls = 0

        def generate_content(self, *, model: str, contents: str, config=None):
            self.calls += 1
            raise RuntimeError("deadline expired while the provider was unavailable")

    class AlwaysUnavailableGenAIClient:
        def __init__(self):
            self.models = AlwaysUnavailableModels()

    genai_client = AlwaysUnavailableGenAIClient()
    client = GoogleGenAIImageClient(genai_client, retry_base_delay_seconds=0.25)

    with pytest.raises(RuntimeError, match="deadline expired"):
        client.generate_image(prompt="A clean product image")

    assert genai_client.models.calls == 3
    assert sleep_calls == [0.25, 0.5]


def test_nano_banana_tool_forwards_config_and_returns_safe_metadata(monkeypatch):
    class RecordingImageClient:
        def __init__(self):
            self.calls = []

        def generate_image(self, *, prompt: str, model: str, aspect_ratio: str, image_size: str | None):
            self.calls.append(
                {
                    "prompt": prompt,
                    "model": model,
                    "aspect_ratio": aspect_ratio,
                    "image_size": image_size,
                }
            )
            return {
                "mime_type": "image/png",
                "bytes": b"png-bytes",
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "image_size": image_size,
            }

    recording_client = RecordingImageClient()
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: recording_client,
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.stage_generated_image",
        lambda **kwargs: {
            "artifact_id": "artifact-1",
            "mime_type": kwargs["mime_type"],
            "sha256": "hash",
            "metadata_json": kwargs["generation_config"],
        },
    )
    tool = AXNanoBananaImageTool(
        model="gemini-3-pro-image-preview",
        aspect_ratio="9:16",
        image_size="2K",
    )

    result = tool._run(prompt="Create a portrait product image")

    assert recording_client.calls == [
        {
            "prompt": "Create a portrait product image",
            "model": "gemini-3-pro-image-preview",
            "aspect_ratio": "9:16",
            "image_size": "2K",
        }
    ]
    assert result == {
        "artifact_id": "artifact-1",
        "mime_type": "image/png",
        "model": "gemini-3-pro-image-preview",
        "aspect_ratio": "9:16",
        "image_size": "2K",
        "reused_existing_artifact": False,
        "prompt_sha256": hashlib.sha256(b"Create a portrait product image").hexdigest(),
        "prompt_length": len("Create a portrait product image"),
    }


def test_nano_banana_tool_preserves_configured_image_size_for_legacy_response(monkeypatch):
    class RecordingLegacyImageClient:
        def __init__(self):
            self.calls = []

        def generate_image(self, *, prompt: str, model: str, aspect_ratio: str, image_size: str | None):
            self.calls.append(
                {
                    "prompt": prompt,
                    "model": model,
                    "aspect_ratio": aspect_ratio,
                    "image_size": image_size,
                }
            )
            return {
                "mime_type": "image/png",
                "bytes": b"png-bytes",
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
            }

    recording_client = RecordingLegacyImageClient()
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.build_image_client_from_runtime",
        lambda: recording_client,
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.stage_generated_image",
        lambda **kwargs: {
            "artifact_id": "artifact-legacy",
            "mime_type": kwargs["mime_type"],
            "sha256": "hash",
            "metadata_json": kwargs["generation_config"],
        },
    )
    tool = AXNanoBananaImageTool(
        model="gemini-2.5-flash-image",
        aspect_ratio="9:16",
        image_size="4K",
    )

    result = tool._run(prompt="Create a legacy portrait product image")

    assert recording_client.calls == [
        {
            "prompt": "Create a legacy portrait product image",
            "model": "gemini-2.5-flash-image",
            "aspect_ratio": "9:16",
            "image_size": "4K",
        }
    ]
    assert result["artifact_id"] == "artifact-legacy"
    assert result["model"] == "gemini-2.5-flash-image"
    assert result["aspect_ratio"] == "9:16"
    assert result["image_size"] == "4K"
    assert "metadata_json" not in result
    assert "prompt" not in result
    assert "bytes" not in result


def test_stage_generated_image_uses_supabase_public_storage_when_configured(monkeypatch, tmp_path, db):
    owner_user_id = "91111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    upload_calls: list[dict[str, object]] = []

    class Uploaded:
        bucket = "ax-public-artifacts"
        object_path = "artifacts/run-1/image.png"
        public_url = "https://cdn.example/storage/v1/object/public/ax-public-artifacts/artifacts/run-1/image.png"

    def fake_upload_public_artifact_bytes(**kwargs):
        upload_calls.append(kwargs)
        return Uploaded()

    monkeypatch.setenv("AX_SUPABASE_ARTIFACT_BUCKET", "ax-public-artifacts")
    monkeypatch.setenv("AX_ARTIFACT_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.supabase_public_artifact_storage_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "api.tools.nano_banana_image_tool.upload_public_artifact_bytes",
        fake_upload_public_artifact_bytes,
    )

    with nano_banana_artifact_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
    ):
        result = stage_generated_image(
            image_bytes=b"image-bytes",
            mime_type="image/png",
            prompt="Draw a square image",
            model="gemini-3.1-flash-image-preview",
            artifact_storage_mode="temporary_only",
            generation_config={"aspect_ratio": "1:1"},
        )

    artifact = db.query(models.RunArtifact).filter(models.RunArtifact.id == result["artifact_id"]).one()
    assert artifact.storage_backend == "ax_managed"
    assert artifact.retention_mode == "ax_managed"
    assert artifact.storage_bucket == "ax-public-artifacts"
    assert artifact.storage_path == "artifacts/run-1/image.png"
    assert artifact.storage_reference == "supabase://ax-public-artifacts/artifacts/run-1/image.png"
    assert artifact.metadata_json["provider_media_url"] == Uploaded.public_url
    assert result["preview_url"] == Uploaded.public_url
    assert result["download_url"] == Uploaded.public_url
    assert not (tmp_path / "generated").exists()
    assert upload_calls == [
        {
            "image_bytes": b"image-bytes",
            "media_type": "image/png",
            "owner_user_id": owner_user_id,
            "run_id": str(run.id),
            "object_suffix": ".png",
        }
    ]
