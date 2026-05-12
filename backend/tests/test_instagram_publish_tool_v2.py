from __future__ import annotations

import pytest

from api.db import models
from api.integrations.meta_instagram import meta_instagram_runtime_context
from api.runtime.artifacts import create_artifact_metadata
from api.runtime.oauth_clients import RuntimeOAuthToken
from api.tools.instagram_publish_tool import AXInstagramPublishTool


class FakeInstagramClient:
    def __init__(self) -> None:
        self.single_calls = []
        self.carousel_calls = []

    def publish_image(self, *, image_url: str, caption: str):
        self.single_calls.append({"image_url": image_url, "caption": caption})
        return {
            "ig_container_id": "container-1",
            "ig_media_id": "media-1",
            "status": "published",
            "access_token": "must-not-leak",
        }

    def publish_carousel(self, *, image_urls: list[str], caption: str):
        self.carousel_calls.append({"image_urls": image_urls, "caption": caption})
        return {
            "ig_container_id": "parent-1",
            "ig_media_id": "media-1",
            "status": "published",
            "provider_media_urls": image_urls,
        }


def _token() -> RuntimeOAuthToken:
    return RuntimeOAuthToken(
        credential_id="credential-1",
        provider="meta_instagram",
        access_token="pre-resolved-token",
        expires_at=None,
        scopes=["instagram_basic", "instagram_content_publish"],
        provider_account_id="ig-user-1",
        provider_account_label="creator",
    )


@pytest.mark.parametrize(
    "artifact_ids",
    [
        [],
        ["artifact-1", "artifact-2"],
    ],
)
def test_instagram_publish_tool_rejects_unsupported_unique_artifact_count(artifact_ids):
    tool = AXInstagramPublishTool(publish_mode=3)

    with pytest.raises(ValueError, match="requires either 1 or 3 unique artifact ids"):
        tool._run(artifact_ids=artifact_ids, caption="Hello AX")


def test_instagram_publish_tool_rejects_empty_caption():
    tool = AXInstagramPublishTool(publish_mode=1)

    with pytest.raises(ValueError, match="caption must not be empty"):
        tool._run(artifact_ids=["artifact-1"], caption=" ")


@pytest.mark.parametrize("publish_mode", [0, 2, 4, "1", True, False])
def test_instagram_publish_tool_rejects_unsupported_publish_mode(publish_mode):
    with pytest.raises(ValueError, match="publish_mode must be one of: 1, 3"):
        AXInstagramPublishTool(publish_mode=publish_mode)


@pytest.mark.parametrize(
    "config,match",
    [
        ({"poll_timeout_seconds": 0}, "poll_timeout_seconds must be between 1 and 300"),
        ({"poll_timeout_seconds": 301}, "poll_timeout_seconds must be between 1 and 300"),
        ({"poll_interval_seconds": 0}, "poll_interval_seconds must be between 1 and 60"),
        ({"poll_interval_seconds": 61}, "poll_interval_seconds must be between 1 and 60"),
        (
            {"poll_timeout_seconds": 2, "poll_interval_seconds": 3},
            "poll_interval_seconds must not exceed poll_timeout_seconds",
        ),
    ],
)
def test_instagram_publish_tool_rejects_invalid_polling_config(config, match):
    with pytest.raises(ValueError, match=match):
        AXInstagramPublishTool(publish_mode=1, **config)


def test_instagram_publish_tool_publishes_single_image(monkeypatch):
    fake_client = FakeInstagramClient()
    resolver_calls = []

    def fake_resolver(**kwargs):
        resolver_calls.append(kwargs)
        return "https://media.example/image-1.png"

    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.provider_media_url_for_artifact",
        fake_resolver,
    )
    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.build_meta_instagram_client_from_runtime",
        lambda **_kwargs: fake_client,
    )

    with meta_instagram_runtime_context(
        db=object(),
        owner_user_id="user-1",
        run_id="run-1",
        token=_token(),
    ):
        result = AXInstagramPublishTool(publish_mode=1)._run(
            artifact_ids=["artifact-1"],
            caption="Hello AX",
        )

    assert result == {
        "status": "published",
        "publish_mode": 1,
        "ig_container_id": "container-1",
        "ig_media_id": "media-1",
        "artifact_ids": ["artifact-1"],
    }
    assert resolver_calls == [
        {
            "artifact_id": "artifact-1",
            "owner_user_id": "user-1",
            "run_id": "run-1",
            "db": resolver_calls[0]["db"],
        }
    ]
    assert fake_client.single_calls == [
        {"image_url": "https://media.example/image-1.png", "caption": "Hello AX"}
    ]
    assert "must-not-leak" not in str(result)


def test_instagram_publish_tool_passes_polling_config_to_runtime_client(monkeypatch):
    captured = {}

    class CapturingInstagramClient(FakeInstagramClient):
        def publish_image(self, *, image_url: str, caption: str):
            return super().publish_image(image_url=image_url, caption=caption)

    def fake_client_builder(**kwargs):
        captured.update(kwargs)
        return CapturingInstagramClient()

    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.provider_media_url_for_artifact",
        lambda **kwargs: f"https://media.example/{kwargs['artifact_id']}.png",
    )
    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.build_meta_instagram_client_from_runtime",
        fake_client_builder,
    )

    with meta_instagram_runtime_context(
        db=object(),
        owner_user_id="user-1",
        run_id="run-1",
        token=_token(),
    ):
        result = AXInstagramPublishTool(
            publish_mode=1,
            poll_timeout_seconds=90,
            poll_interval_seconds=5,
        )._run(
            artifact_ids=["artifact-1"],
            caption="Hello AX",
        )

    assert result["status"] == "published"
    assert captured == {
        "poll_timeout_seconds": 90,
        "poll_interval_seconds": 5,
    }


def test_instagram_publish_tool_publishes_three_image_carousel(monkeypatch):
    fake_client = FakeInstagramClient()

    def fake_resolver(**kwargs):
        return f"https://media.example/{kwargs['artifact_id']}.png"

    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.provider_media_url_for_artifact",
        fake_resolver,
    )
    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.build_meta_instagram_client_from_runtime",
        lambda **_kwargs: fake_client,
    )

    with meta_instagram_runtime_context(
        db=object(),
        owner_user_id="user-1",
        run_id="run-1",
        token=_token(),
    ):
        result = AXInstagramPublishTool(publish_mode=3)._run(
            artifact_ids=["artifact-1", "artifact-2", "artifact-3"],
            caption="Carousel body",
        )

    assert result == {
        "status": "published",
        "publish_mode": 3,
        "ig_container_id": "parent-1",
        "ig_media_id": "media-1",
        "artifact_ids": ["artifact-1", "artifact-2", "artifact-3"],
    }
    assert fake_client.carousel_calls == [
        {
            "image_urls": [
                "https://media.example/artifact-1.png",
                "https://media.example/artifact-2.png",
                "https://media.example/artifact-3.png",
            ],
            "caption": "Carousel body",
        }
    ]
    assert "provider_media_urls" not in result
    assert "https://media.example" not in str(result)


def test_instagram_publish_tool_infers_single_post_from_one_unique_artifact(monkeypatch):
    fake_client = FakeInstagramClient()

    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.provider_media_url_for_artifact",
        lambda **kwargs: f"https://media.example/{kwargs['artifact_id']}.png",
    )
    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.build_meta_instagram_client_from_runtime",
        lambda **_kwargs: fake_client,
    )

    with meta_instagram_runtime_context(
        db=object(),
        owner_user_id="user-1",
        run_id="run-1",
        token=_token(),
    ):
        result = AXInstagramPublishTool(publish_mode=3)._run(
            artifact_ids=["artifact-1"],
            caption="Single image caption",
        )

    assert result["publish_mode"] == 1
    assert result["artifact_ids"] == ["artifact-1"]
    assert fake_client.single_calls == [
        {
            "image_url": "https://media.example/artifact-1.png",
            "caption": "Single image caption",
        }
    ]
    assert fake_client.carousel_calls == []


def test_instagram_publish_tool_dedupes_repeated_single_artifact_id(monkeypatch):
    fake_client = FakeInstagramClient()
    resolver_calls: list[str] = []

    def fake_resolver(**kwargs):
        resolver_calls.append(kwargs["artifact_id"])
        return f"https://media.example/{kwargs['artifact_id']}.png"

    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.provider_media_url_for_artifact",
        fake_resolver,
    )
    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.build_meta_instagram_client_from_runtime",
        lambda **_kwargs: fake_client,
    )

    with meta_instagram_runtime_context(
        db=object(),
        owner_user_id="user-1",
        run_id="run-1",
        token=_token(),
    ):
        result = AXInstagramPublishTool(publish_mode=3)._run(
            artifact_ids=["artifact-1", "artifact-1", "artifact-1"],
            caption="Deduped caption",
        )

    assert result["publish_mode"] == 1
    assert result["artifact_ids"] == ["artifact-1"]
    assert resolver_calls == ["artifact-1"]
    assert fake_client.single_calls == [
        {
            "image_url": "https://media.example/artifact-1.png",
            "caption": "Deduped caption",
        }
    ]


def test_instagram_publish_tool_publishes_nano_banana_artifact_with_public_base_url(
    db,
    monkeypatch,
):
    fake_client = FakeInstagramClient()
    monkeypatch.setenv("AX_PUBLIC_BASE_URL", "https://media.example")
    monkeypatch.setattr(
        "api.tools.instagram_publish_tool.build_meta_instagram_client_from_runtime",
        lambda **_kwargs: fake_client,
    )

    owner_user_id = "91111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference="/tmp/generated.png",
        storage_path="/tmp/generated.png",
        source_tool="nano_banana",
        source_capability="image_generation",
    )
    artifact.metadata_json = {
        "preview_url": f"/api/run-artifacts/{artifact.id}/content",
        "download_url": f"/api/run-artifacts/{artifact.id}/content",
    }
    db.add(artifact)
    db.flush()

    with meta_instagram_runtime_context(
        db=db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        token=_token(),
    ):
        result = AXInstagramPublishTool(publish_mode=1)._run(
            artifact_ids=[str(artifact.id)],
            caption="Nano Banana caption",
        )

    assert result["artifact_ids"] == [str(artifact.id)]
    assert fake_client.single_calls == [
        {
            "image_url": f"https://media.example/api/public/run-artifacts/{artifact.id}/content",
            "caption": "Nano Banana caption",
        }
    ]


def _create_flow_run(db, *, owner_user_id: str) -> models.FlowRun:
    asset = models.Asset(
        id="92222222-2222-4222-8222-222222222223",
        asset_type="flow",
        workspace_id="93333333-3333-4333-8333-333333333334",
        owner_user_id=owner_user_id,
        name="Instagram Publish Tool Flow",
    )
    version = models.AssetVersion(
        id="94444444-4444-4444-8444-444444444445",
        asset_id=asset.id,
        version_number=1,
        status="published",
        created_by=owner_user_id,
        payload_json={},
    )
    run = models.FlowRun(
        id="95555555-5555-4555-8555-555555555556",
        flow_version_id=version.id,
        status="running",
        input_json={},
    )
    db.add_all([asset, version, run])
    db.flush()
    return run
