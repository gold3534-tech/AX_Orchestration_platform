import pytest

from api.db import models
from api.runtime.artifacts import create_artifact_metadata
from api.integrations.meta_instagram import MetaInstagramClient
from api.integrations.meta_instagram import MetaInstagramIntegrationError
from api.runtime.execution_actions import ExecutionActionRequest
from api.runtime.execution_actions import execute_execution_action
from api.runtime.execution_actions import instagram_publish_executor


class FakeInstagramClient:
    def __init__(self) -> None:
        self.published = []

    def publish_image(self, *, image_url: str, caption: str):
        self.published.append({"image_url": image_url, "caption": caption})
        return {
            "ig_container_id": "container-1",
            "ig_media_id": "media-1",
            "status": "published",
            "ignored_token": "must-not-return",
        }


class FailingInstagramClient:
    def publish_image(self, *, image_url: str, caption: str):
        raise RuntimeError("Meta publish failed")


def test_instagram_publish_executor_uses_provider_media_url(monkeypatch):
    fake_client = FakeInstagramClient()
    monkeypatch.setattr(
        "api.runtime.execution_actions.provider_media_url_for_artifact",
        lambda **_kwargs: "https://media.example/image.png",
    )
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_meta_instagram_client",
        lambda *_args, **_kwargs: fake_client,
    )

    output = instagram_publish_executor(
        ExecutionActionRequest(
            run_id="run-1",
            node_id="execution_action:instagram",
            action_key="ax.instagram_publish",
            owner_user_id="test-user",
            inputs={"artifact_id": "artifact-1", "caption": "Hello AX"},
            config={},
            approval_mode="never",
            artifact_ids=["artifact-1"],
        )
    )

    assert output == {
        "ig_container_id": "container-1",
        "ig_media_id": "media-1",
        "status": "published",
    }
    assert fake_client.published == [
        {
            "image_url": "https://media.example/image.png",
            "caption": "Hello AX",
        }
    ]


def test_instagram_publish_executor_requires_artifact_id():
    with pytest.raises(ValueError, match="artifact_id is required"):
        instagram_publish_executor(
            ExecutionActionRequest(
                run_id="run-1",
                node_id="execution_action:instagram",
                action_key="ax.instagram_publish",
                owner_user_id="test-user",
                inputs={"caption": "Hello AX"},
                config={},
                approval_mode="never",
                artifact_ids=[],
            )
        )


def test_instagram_publish_executor_requires_absolute_http_media_url(monkeypatch):
    from api.runtime.provider_media_urls import absolute_http_provider_media_url

    monkeypatch.setattr(
        "api.runtime.execution_actions.provider_media_url_for_artifact",
        lambda **_kwargs: absolute_http_provider_media_url("/private/image.png"),
    )
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_meta_instagram_client",
        lambda *_args, **_kwargs: FakeInstagramClient(),
    )

    with pytest.raises(ValueError, match="absolute http"):
        instagram_publish_executor(
            ExecutionActionRequest(
                run_id="run-1",
                node_id="execution_action:instagram",
                action_key="ax.instagram_publish",
                owner_user_id="test-user",
                inputs={"artifact_id": "artifact-1", "caption": "Hello AX"},
                config={},
                approval_mode="never",
                artifact_ids=["artifact-1"],
            )
        )


@pytest.mark.parametrize(
    "media_url",
    [
        "https://user:pass@media.example/image.png",
        "https://media.example/image.png?access_token=secret-token",
        "https://media.example/private/%61ccess_token/image.png",
        "https://token-cdn.example/image.png",
        "http://127.0.0.1/image.png",
        "http://localhost/image.png",
        "http://10.0.0.2/image.png",
        "http://2130706433/image.png",
        "http://0x7f000001/image.png",
        "http://127.1/image.png",
        "http://167772162/image.png",
        "http://0300.0250.0001.0001/image.png",
        "http://0010.0010.0010.0010/image.png",
    ],
)
def test_instagram_publish_executor_rejects_secret_bearing_or_private_media_urls(
    monkeypatch,
    media_url,
):
    from api.runtime.provider_media_urls import absolute_http_provider_media_url

    monkeypatch.setattr(
        "api.runtime.execution_actions.provider_media_url_for_artifact",
        lambda **_kwargs: absolute_http_provider_media_url(media_url),
    )
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_meta_instagram_client",
        lambda *_args, **_kwargs: FakeInstagramClient(),
    )

    with pytest.raises(ValueError, match="provider media URL"):
        instagram_publish_executor(
            ExecutionActionRequest(
                run_id="run-1",
                node_id="execution_action:instagram",
                action_key="ax.instagram_publish",
                owner_user_id="test-user",
                inputs={"artifact_id": "artifact-1", "caption": "Hello AX"},
                config={},
                approval_mode="never",
                artifact_ids=["artifact-1"],
            )
        )


def test_instagram_publish_executor_uses_artifact_provider_media_url(db, monkeypatch):
    owner_user_id = "91111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="execution_action:drive",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/drive-file-1",
        retention_mode="temporary",
        metadata_json={
            "provider_media_url": "https://media.example/image.png",
            "external_resource_url": "https://media.example/image.png",
        },
    )
    fake_client = FakeInstagramClient()
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_meta_instagram_client",
        lambda *_args, **_kwargs: fake_client,
    )

    output = instagram_publish_executor(
        ExecutionActionRequest(
            run_id=str(run.id),
            node_id="execution_action:instagram",
            action_key="ax.instagram_publish",
            owner_user_id=owner_user_id,
            inputs={"artifact_id": str(artifact.id), "caption": "Hello AX"},
            config={},
            approval_mode="never",
            artifact_ids=[str(artifact.id)],
            db=db,
        )
    )

    assert output["status"] == "published"
    assert fake_client.published == [
        {
            "image_url": "https://media.example/image.png",
            "caption": "Hello AX",
        }
    ]


def test_instagram_publish_executor_rejects_artifact_without_provider_media_url(db, monkeypatch):
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
        storage_reference="generated/image.png",
        storage_path="generated/image.png",
    )
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_meta_instagram_client",
        lambda *_args, **_kwargs: FakeInstagramClient(),
    )

    with pytest.raises(ValueError, match="Provider media URL is unavailable"):
        instagram_publish_executor(
            ExecutionActionRequest(
                run_id=str(run.id),
                node_id="execution_action:instagram",
                action_key="ax.instagram_publish",
                owner_user_id=owner_user_id,
                inputs={"artifact_id": str(artifact.id), "caption": "Hello AX"},
                config={},
                approval_mode="never",
                artifact_ids=[str(artifact.id)],
                db=db,
            )
        )


def test_provider_media_url_helper_uses_artifact_provider_media_url(db):
    from api.runtime.provider_media_urls import provider_media_url_for_artifact

    owner_user_id = "91111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/drive-file-1",
        retention_mode="temporary",
        metadata_json={"provider_media_url": "https://media.example/image.png"},
    )

    assert provider_media_url_for_artifact(
        artifact_id=str(artifact.id),
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        db=db,
    ) == "https://media.example/image.png"


def test_provider_media_url_helper_builds_public_url_for_ax_hosted_artifact(
    db,
    monkeypatch,
):
    from api.runtime.provider_media_urls import provider_media_url_for_artifact

    monkeypatch.setenv("AX_PUBLIC_BASE_URL", "https://media.example")
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
        metadata_json={
            "preview_url": "https://existing.example/ignored.png",
            "download_url": "https://existing.example/ignored.png",
        },
    )
    artifact.metadata_json = {
        "preview_url": f"/api/run-artifacts/{artifact.id}/content",
        "download_url": f"/api/run-artifacts/{artifact.id}/content",
    }
    db.add(artifact)
    db.flush()

    assert provider_media_url_for_artifact(
        artifact_id=str(artifact.id),
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        db=db,
    ) == f"https://media.example/api/public/run-artifacts/{artifact.id}/content"


def test_provider_media_url_helper_promotes_ax_hosted_artifact_to_supabase(
    db,
    monkeypatch,
    tmp_path,
):
    from api.runtime import provider_media_urls

    monkeypatch.delenv("AX_PUBLIC_BASE_URL", raising=False)
    image_path = tmp_path / "generated.png"
    image_path.write_bytes(b"image-bytes")
    upload_calls: list[dict[str, object]] = []

    class Uploaded:
        bucket = "ax-public-artifacts"
        object_path = "artifacts/run-1/generated.png"
        public_url = "https://cdn.example/storage/v1/object/public/ax-public-artifacts/artifacts/run-1/generated.png"

    def fake_upload_public_artifact_file(**kwargs):
        upload_calls.append(kwargs)
        return Uploaded()

    monkeypatch.setattr(
        provider_media_urls,
        "upload_public_artifact_file",
        fake_upload_public_artifact_file,
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
        storage_reference=str(image_path),
        storage_path=str(image_path),
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={
            "preview_url": f"/api/run-artifacts/00000000-0000-0000-0000-000000000000/content",
        },
    )
    artifact.metadata_json = {
        "preview_url": f"/api/run-artifacts/{artifact.id}/content",
        "download_url": f"/api/run-artifacts/{artifact.id}/content",
    }
    db.add(artifact)
    db.flush()

    assert provider_media_urls.provider_media_url_for_artifact(
        artifact_id=str(artifact.id),
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        db=db,
    ) == Uploaded.public_url

    db.refresh(artifact)
    assert artifact.metadata_json["provider_media_url"] == Uploaded.public_url
    assert artifact.metadata_json["external_resource_url"] == Uploaded.public_url
    assert artifact.metadata_json["supabase_bucket"] == Uploaded.bucket
    assert artifact.metadata_json["supabase_object_path"] == Uploaded.object_path
    assert upload_calls == [
        {
            "path": image_path,
            "media_type": "image/png",
            "owner_user_id": owner_user_id,
            "run_id": str(run.id),
        }
    ]


def test_instagram_publish_failure_after_supabase_promotion_rolls_back_action_run(
    db,
    monkeypatch,
    tmp_path,
):
    from api.runtime import provider_media_urls

    monkeypatch.delenv("AX_PUBLIC_BASE_URL", raising=False)
    image_path = tmp_path / "generated.png"
    image_path.write_bytes(b"image-bytes")

    class Uploaded:
        bucket = "ax-public-artifacts"
        object_path = "artifacts/run-1/generated.png"
        public_url = "https://cdn.example/storage/v1/object/public/ax-public-artifacts/artifacts/run-1/generated.png"

    monkeypatch.setattr(
        provider_media_urls,
        "upload_public_artifact_file",
        lambda **_kwargs: Uploaded(),
    )
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_meta_instagram_client",
        lambda *_args, **_kwargs: FailingInstagramClient(),
    )

    owner_user_id = "91111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    run_id = str(run.id)
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=run_id,
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(image_path),
        storage_path=str(image_path),
        source_tool="nano_banana",
        source_capability="image_generation",
    )
    artifact.metadata_json = {
        "preview_url": f"/api/run-artifacts/{artifact.id}/content",
        "download_url": f"/api/run-artifacts/{artifact.id}/content",
    }
    db.add(artifact)
    db.flush()

    request = ExecutionActionRequest(
        run_id=run_id,
        node_id="execution_action:instagram",
        action_key="ax.instagram_publish",
        owner_user_id=owner_user_id,
        inputs={"artifact_id": str(artifact.id), "caption": "Hello AX"},
        config={},
        approval_mode="never",
        artifact_ids=[str(artifact.id)],
    )

    with pytest.raises(RuntimeError, match="Meta publish failed"):
        execute_execution_action(db, request)

    db.rollback()

    assert (
        db.query(models.ExecutionActionRun)
        .filter_by(
            run_id=run_id,
            node_id="execution_action:instagram",
            action_key="ax.instagram_publish",
        )
        .one_or_none()
        is None
    )


def test_provider_media_url_helper_rejects_artifact_secret_query(db):
    from api.runtime.provider_media_urls import provider_media_url_for_artifact

    owner_user_id = "91111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/drive-file-1",
        retention_mode="temporary",
    )
    artifact.metadata_json = {
        "provider_media_url": "https://media.example/image.png?access_token=secret"
    }
    db.add(artifact)
    db.flush()

    with pytest.raises(ValueError, match="safe provider media URL"):
        provider_media_url_for_artifact(
            artifact_id=str(artifact.id),
            owner_user_id=owner_user_id,
            run_id=str(run.id),
            db=db,
        )


def test_absolute_http_provider_media_url_rejects_secret_query():
    from api.runtime.provider_media_urls import absolute_http_provider_media_url

    with pytest.raises(ValueError, match="safe provider media URL"):
        absolute_http_provider_media_url("https://media.example/image.png?access_token=secret")


class FakeMetaResponse:
    def __init__(
        self,
        payload,
        *,
        status_code: int = 200,
        text: str = "",
        json_error: Exception | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text
        self._json_error = json_error

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def raise_for_status(self) -> None:
        if not self.ok:
            raise AssertionError("MetaInstagramClient should not call raise_for_status()")

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_meta_instagram_client_raises_sanitized_error_for_invalid_create_response(monkeypatch):
    access_token = "meta-access-token-secret"

    def fake_post(*_args, **_kwargs):
        return FakeMetaResponse({"id": ""})

    monkeypatch.setattr("api.integrations.meta_instagram.requests.post", fake_post)

    client = MetaInstagramClient(ig_user_id="ig-user-1", access_token=access_token)
    with pytest.raises(MetaInstagramIntegrationError) as exc_info:
        client.publish_image(image_url="https://media.example/image.png", caption="Hello AX")

    assert "media container id" in str(exc_info.value)
    assert access_token not in str(exc_info.value)


@pytest.mark.parametrize(
    "publish_response",
    [
        FakeMetaResponse({"unexpected": "shape"}),
        FakeMetaResponse(None, json_error=ValueError("not json")),
    ],
)
def test_meta_instagram_client_returns_ambiguous_status_for_invalid_publish_response(
    monkeypatch,
    publish_response,
):
    calls = []

    def fake_post(url, **_kwargs):
        calls.append(url)
        if url.endswith("/media"):
            return FakeMetaResponse({"id": "container-1"})
        return publish_response

    monkeypatch.setattr("api.integrations.meta_instagram.requests.post", fake_post)
    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.get",
        lambda *_args, **_kwargs: FakeMetaResponse({"status_code": "FINISHED"}),
    )

    client = MetaInstagramClient(ig_user_id="ig-user-1", access_token="meta-access-token-secret")
    output = client.publish_image(image_url="https://media.example/image.png", caption="Hello AX")

    assert output == {
        "ig_container_id": "container-1",
        "ig_media_id": None,
        "status": "publish_state_ambiguous",
    }
    assert len(calls) == 2


def test_meta_instagram_client_waits_for_single_image_container_before_publish(monkeypatch):
    calls = []
    sleeps = []
    post_responses = iter(
        [
            FakeMetaResponse({"id": "container-1"}),
            FakeMetaResponse({"id": "media-1"}),
        ]
    )
    get_responses = iter(
        [
            FakeMetaResponse({"status_code": "IN_PROGRESS", "status": "Processing"}),
            FakeMetaResponse({"status_code": "FINISHED", "status": "Finished"}),
        ]
    )

    def fake_post(url, **kwargs):
        calls.append({"method": "POST", "url": url, "data": kwargs["data"]})
        return next(post_responses)

    def fake_get(url, **kwargs):
        calls.append({"method": "GET", "url": url, "params": kwargs["params"]})
        return next(get_responses)

    monkeypatch.setattr("api.integrations.meta_instagram.requests.post", fake_post)
    monkeypatch.setattr("api.integrations.meta_instagram.requests.get", fake_get)

    client = MetaInstagramClient(
        ig_user_id="ig-user-1",
        access_token="meta-access-token-secret",
        poll_timeout_seconds=10,
        poll_interval_seconds=2,
        sleeper=sleeps.append,
    )
    output = client.publish_image(image_url="https://media.example/image.png", caption="Hello AX")

    assert output == {
        "ig_container_id": "container-1",
        "ig_media_id": "media-1",
        "status": "published",
    }
    assert [call["method"] for call in calls] == ["POST", "GET", "GET", "POST"]
    assert calls[1] == {
        "method": "GET",
        "url": "https://graph.facebook.com/v24.0/container-1",
        "params": {
            "fields": "status_code,status",
            "access_token": "meta-access-token-secret",
        },
    }
    assert [
        call["params"] for call in calls if call["method"] == "GET"
    ] == [
        {
            "fields": "status_code,status",
            "access_token": "meta-access-token-secret",
        },
        {
            "fields": "status_code,status",
            "access_token": "meta-access-token-secret",
        },
    ]
    assert sleeps == [2]


def test_meta_instagram_client_raises_sanitized_error_for_publish_http_error(monkeypatch):
    access_token = "meta-access-token-secret"
    calls = []
    post_responses = iter(
        [
            FakeMetaResponse({"id": "container-1"}),
            FakeMetaResponse(
                {
                    "error": {
                        "message": f"Media ID is not available for {access_token}",
                        "type": "OAuthException",
                        "code": 9007,
                        "error_subcode": 2207053,
                        "status_code": 400,
                        "fbtrace_id": "trace-1",
                    }
                },
                status_code=400,
            ),
        ]
    )

    def fake_post(url, **kwargs):
        calls.append({"method": "POST", "url": url, "data": kwargs["data"]})
        return next(post_responses)

    def fake_get(url, **kwargs):
        calls.append({"method": "GET", "url": url, "params": kwargs["params"]})
        return FakeMetaResponse({"status_code": "FINISHED"})

    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.post",
        fake_post,
    )
    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.get",
        fake_get,
    )

    client = MetaInstagramClient(
        ig_user_id="ig-user-1",
        access_token=access_token,
        poll_timeout_seconds=5,
        poll_interval_seconds=1,
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(MetaInstagramIntegrationError) as exc_info:
        client.publish_image(image_url="https://media.example/image.png", caption="Hello AX")

    assert [call["method"] for call in calls] == ["POST", "GET", "POST"]
    assert calls[0]["url"] == "https://graph.facebook.com/v24.0/ig-user-1/media"
    assert calls[1] == {
        "method": "GET",
        "url": "https://graph.facebook.com/v24.0/container-1",
        "params": {
            "fields": "status_code,status",
            "access_token": access_token,
        },
    }
    assert calls[2]["url"] == "https://graph.facebook.com/v24.0/ig-user-1/media_publish"
    message = str(exc_info.value)
    assert "publish failed" in message
    assert "HTTP 400" in message
    assert "Media ID is not available" in message
    assert "OAuthException" in message
    assert "9007" in message
    assert "2207053" in message
    assert "status_code=400" in message
    assert "trace-1" in message
    assert access_token not in message


def test_meta_instagram_client_redacts_url_encoded_access_token_from_meta_error(monkeypatch):
    from urllib.parse import quote

    access_token = "meta/access token+secret"
    encoded_token = quote(access_token, safe="")
    post_responses = iter(
        [
            FakeMetaResponse({"id": "container-1"}),
            FakeMetaResponse(
                {
                    "error": {
                        "message": f"Debug URL https://graph.facebook.com/me?access_token={encoded_token}",
                        "type": "OAuthException",
                        "code": 190,
                    }
                },
                status_code=400,
            ),
        ]
    )

    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.post",
        lambda *_args, **_kwargs: next(post_responses),
    )
    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.get",
        lambda *_args, **_kwargs: FakeMetaResponse({"status_code": "FINISHED"}),
    )

    client = MetaInstagramClient(ig_user_id="ig-user-1", access_token=access_token)

    with pytest.raises(MetaInstagramIntegrationError) as exc_info:
        client.publish_image(image_url="https://media.example/image.png", caption="Hello AX")

    message = str(exc_info.value)
    assert "[REDACTED]" in message
    assert access_token not in message
    assert encoded_token not in message


def test_meta_instagram_client_publishes_three_image_carousel(monkeypatch):
    calls = []
    responses = iter(
        [
            FakeMetaResponse({"id": "child-1"}),
            FakeMetaResponse({"id": "child-2"}),
            FakeMetaResponse({"id": "child-3"}),
            FakeMetaResponse({"id": "parent-1"}),
            FakeMetaResponse({"id": "media-1"}),
        ]
    )

    def fake_post(url, **kwargs):
        calls.append({"url": url, "data": kwargs["data"]})
        return next(responses)

    monkeypatch.setattr("api.integrations.meta_instagram.requests.post", fake_post)
    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.get",
        lambda *_args, **_kwargs: FakeMetaResponse({"status_code": "FINISHED"}),
    )

    client = MetaInstagramClient(ig_user_id="ig-user-1", access_token="meta-access-token-secret")
    output = client.publish_carousel(
        image_urls=[
            "https://media.example/one.png",
            "https://media.example/two.png",
            "https://media.example/three.png",
        ],
        caption="Carousel caption",
    )

    assert output == {
        "ig_container_id": "parent-1",
        "ig_media_id": "media-1",
        "status": "published",
    }
    assert [call["url"] for call in calls] == [
        "https://graph.facebook.com/v24.0/ig-user-1/media",
        "https://graph.facebook.com/v24.0/ig-user-1/media",
        "https://graph.facebook.com/v24.0/ig-user-1/media",
        "https://graph.facebook.com/v24.0/ig-user-1/media",
        "https://graph.facebook.com/v24.0/ig-user-1/media_publish",
    ]
    assert calls[0]["data"] == {
        "image_url": "https://media.example/one.png",
        "is_carousel_item": "true",
        "access_token": "meta-access-token-secret",
    }
    assert calls[1]["data"] == {
        "image_url": "https://media.example/two.png",
        "is_carousel_item": "true",
        "access_token": "meta-access-token-secret",
    }
    assert calls[2]["data"] == {
        "image_url": "https://media.example/three.png",
        "is_carousel_item": "true",
        "access_token": "meta-access-token-secret",
    }
    assert calls[3]["data"] == {
        "media_type": "CAROUSEL",
        "children": "child-1,child-2,child-3",
        "caption": "Carousel caption",
        "access_token": "meta-access-token-secret",
    }
    assert calls[4]["data"] == {
        "creation_id": "parent-1",
        "access_token": "meta-access-token-secret",
    }


def test_meta_instagram_client_waits_for_carousel_parent_container_before_publish(monkeypatch):
    calls = []
    sleeps = []
    post_responses = iter(
        [
            FakeMetaResponse({"id": "child-1"}),
            FakeMetaResponse({"id": "child-2"}),
            FakeMetaResponse({"id": "child-3"}),
            FakeMetaResponse({"id": "parent-1"}),
            FakeMetaResponse({"id": "media-1"}),
        ]
    )
    get_responses = iter(
        [
            FakeMetaResponse({"status_code": "IN_PROGRESS"}),
            FakeMetaResponse({"status_code": "FINISHED"}),
        ]
    )

    def fake_post(url, **kwargs):
        calls.append({"method": "POST", "url": url, "data": kwargs["data"]})
        return next(post_responses)

    def fake_get(url, **kwargs):
        calls.append({"method": "GET", "url": url, "params": kwargs["params"]})
        return next(get_responses)

    monkeypatch.setattr("api.integrations.meta_instagram.requests.post", fake_post)
    monkeypatch.setattr("api.integrations.meta_instagram.requests.get", fake_get)

    client = MetaInstagramClient(
        ig_user_id="ig-user-1",
        access_token="meta-access-token-secret",
        poll_timeout_seconds=10,
        poll_interval_seconds=2,
        sleeper=sleeps.append,
    )
    output = client.publish_carousel(
        image_urls=[
            "https://media.example/one.png",
            "https://media.example/two.png",
            "https://media.example/three.png",
        ],
        caption="Carousel caption",
    )

    assert output["status"] == "published"
    assert output["ig_container_id"] == "parent-1"
    assert [call["method"] for call in calls] == [
        "POST",
        "POST",
        "POST",
        "POST",
        "GET",
        "GET",
        "POST",
    ]
    assert calls[4]["url"] == "https://graph.facebook.com/v24.0/parent-1"
    assert sleeps == [2]


@pytest.mark.parametrize("status_code", ["ERROR", "EXPIRED"])
def test_meta_instagram_client_raises_sanitized_error_for_terminal_container_status(
    monkeypatch,
    status_code,
):
    access_token = "meta-access-token-secret"

    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.post",
        lambda *_args, **_kwargs: FakeMetaResponse({"id": "container-1"}),
    )
    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.get",
        lambda *_args, **_kwargs: FakeMetaResponse(
            {
                "status_code": status_code,
                "status": "Failed",
                "errors": [{"message": f"token {access_token} cannot process media"}],
            }
        ),
    )

    client = MetaInstagramClient(
        ig_user_id="ig-user-1",
        access_token=access_token,
        poll_timeout_seconds=5,
        poll_interval_seconds=1,
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(MetaInstagramIntegrationError) as exc_info:
        client.publish_image(image_url="https://media.example/image.png", caption="Hello AX")

    message = str(exc_info.value)
    assert status_code in message
    assert "Failed" in message
    assert access_token not in message


def test_meta_instagram_client_times_out_waiting_for_container_readiness(monkeypatch):
    access_token = "meta-access-token-secret"
    sleeps = []

    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.post",
        lambda *_args, **_kwargs: FakeMetaResponse({"id": "container-1"}),
    )
    monkeypatch.setattr(
        "api.integrations.meta_instagram.requests.get",
        lambda *_args, **_kwargs: FakeMetaResponse(
            {"status_code": "IN_PROGRESS", "status": "Still processing"}
        ),
    )

    client = MetaInstagramClient(
        ig_user_id="ig-user-1",
        access_token=access_token,
        poll_timeout_seconds=2,
        poll_interval_seconds=1,
        sleeper=sleeps.append,
        monotonic_clock=iter([0, 1, 2, 3]).__next__,
    )

    with pytest.raises(MetaInstagramIntegrationError) as exc_info:
        client.publish_image(image_url="https://media.example/image.png", caption="Hello AX")

    message = str(exc_info.value)
    assert "timed out after 2 seconds" in message
    assert "IN_PROGRESS" in message
    assert "Still processing" in message
    assert access_token not in message
    assert sleeps == [1]


@pytest.mark.parametrize(
    "image_urls",
    [
        [],
        ["https://media.example/one.png", "https://media.example/two.png"],
        [
            "https://media.example/one.png",
            "https://media.example/two.png",
            "https://media.example/three.png",
            "https://media.example/four.png",
        ],
    ],
)
def test_meta_instagram_client_rejects_non_three_image_carousel(image_urls):
    client = MetaInstagramClient(ig_user_id="ig-user-1", access_token="meta-access-token-secret")

    with pytest.raises(ValueError, match="exactly 3 image URLs"):
        client.publish_carousel(image_urls=image_urls, caption="Carousel caption")


def test_meta_instagram_runtime_context_reuses_preresolved_token(monkeypatch):
    from api.integrations.meta_instagram import (
        build_meta_instagram_client_from_runtime,
        meta_instagram_runtime_context,
    )
    from api.runtime.oauth_clients import RuntimeOAuthToken

    db = object()
    token = RuntimeOAuthToken(
        credential_id="credential-1",
        provider="meta_instagram",
        access_token="pre-resolved-token",
        expires_at=None,
        scopes=["instagram_basic", "instagram_content_publish"],
        provider_account_id="ig-user-1",
        provider_account_label="creator",
    )
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return "client"

    def fail_resolver(*args, **kwargs):
        raise AssertionError("resolver should not run when context has a token")

    monkeypatch.setattr("api.integrations.meta_instagram.MetaInstagramClient", fake_client)
    monkeypatch.setattr(
        "api.integrations.meta_instagram.resolve_oauth_token_payload",
        fail_resolver,
    )

    with meta_instagram_runtime_context(
        db=db,
        owner_user_id="user-1",
        run_id="run-1",
        token=token,
    ):
        client = build_meta_instagram_client_from_runtime()

    assert client == "client"
    assert captured == {
        "ig_user_id": "ig-user-1",
        "access_token": "pre-resolved-token",
        "poll_timeout_seconds": 60,
        "poll_interval_seconds": 3,
    }


def test_meta_instagram_client_from_runtime_forwards_polling_options(monkeypatch):
    from api.integrations.meta_instagram import (
        build_meta_instagram_client_from_runtime,
        meta_instagram_runtime_context,
    )
    from api.runtime.oauth_clients import RuntimeOAuthToken

    token = RuntimeOAuthToken(
        credential_id="credential-1",
        provider="meta_instagram",
        access_token="pre-resolved-token",
        expires_at=None,
        scopes=["instagram_basic", "instagram_content_publish"],
        provider_account_id="ig-user-1",
        provider_account_label="creator",
    )
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return "client"

    monkeypatch.setattr("api.integrations.meta_instagram.MetaInstagramClient", fake_client)

    with meta_instagram_runtime_context(
        db=object(),
        owner_user_id="user-1",
        run_id="run-1",
        token=token,
    ):
        client = build_meta_instagram_client_from_runtime(
            poll_timeout_seconds=90,
            poll_interval_seconds=5,
        )

    assert client == "client"
    assert captured == {
        "ig_user_id": "ig-user-1",
        "access_token": "pre-resolved-token",
        "poll_timeout_seconds": 90,
        "poll_interval_seconds": 5,
    }


def test_meta_instagram_client_from_runtime_resolves_token_without_context(monkeypatch):
    from api.integrations.meta_instagram import build_meta_instagram_client_from_runtime
    from api.runtime.oauth_clients import RuntimeOAuthToken

    db = object()
    token = RuntimeOAuthToken(
        credential_id="credential-1",
        provider="meta_instagram",
        access_token="resolved-token",
        expires_at=None,
        scopes=["instagram_basic", "instagram_content_publish"],
        provider_account_id="ig-user-1",
        provider_account_label="creator",
    )
    captured = {}

    def fake_resolver(*args, **kwargs):
        captured["resolver_args"] = args
        captured["resolver_kwargs"] = kwargs
        return token

    def fake_client(**kwargs):
        captured["client_kwargs"] = kwargs
        return "client"

    monkeypatch.setattr(
        "api.integrations.meta_instagram.resolve_oauth_token_payload",
        fake_resolver,
    )
    monkeypatch.setattr("api.integrations.meta_instagram.MetaInstagramClient", fake_client)

    client = build_meta_instagram_client_from_runtime(db=db, owner_user_id="user-1")

    assert client == "client"
    assert captured == {
        "resolver_args": (db,),
        "resolver_kwargs": {
            "owner_user_id": "user-1",
            "provider": "meta_instagram",
            "required_scopes": ["instagram_basic", "instagram_content_publish"],
        },
        "client_kwargs": {
            "ig_user_id": "ig-user-1",
            "access_token": "resolved-token",
            "poll_timeout_seconds": 60,
            "poll_interval_seconds": 3,
        },
    }


def test_meta_instagram_client_from_runtime_rejects_missing_account_id_without_context(
    monkeypatch,
):
    from api.integrations.meta_instagram import build_meta_instagram_client_from_runtime
    from api.runtime.credential_resolver import CredentialResolutionError
    from api.runtime.oauth_clients import RuntimeOAuthToken

    token = RuntimeOAuthToken(
        credential_id="credential-1",
        provider="meta_instagram",
        access_token="resolved-token",
        expires_at=None,
        scopes=["instagram_basic", "instagram_content_publish"],
        provider_account_id=None,
        provider_account_label="creator",
    )

    monkeypatch.setattr(
        "api.integrations.meta_instagram.resolve_oauth_token_payload",
        lambda *_args, **_kwargs: token,
    )

    with pytest.raises(CredentialResolutionError, match="Instagram account id is unavailable"):
        build_meta_instagram_client_from_runtime(db=object(), owner_user_id="user-1")


def test_meta_instagram_client_from_runtime_rejects_missing_context_account_id():
    from api.integrations.meta_instagram import (
        build_meta_instagram_client_from_runtime,
        meta_instagram_runtime_context,
    )
    from api.runtime.credential_resolver import CredentialResolutionError
    from api.runtime.oauth_clients import RuntimeOAuthToken

    token = RuntimeOAuthToken(
        credential_id="credential-1",
        provider="meta_instagram",
        access_token="pre-resolved-token",
        expires_at=None,
        scopes=["instagram_basic", "instagram_content_publish"],
        provider_account_id=None,
        provider_account_label="creator",
    )

    with meta_instagram_runtime_context(
        db=object(),
        owner_user_id="user-1",
        run_id="run-1",
        token=token,
    ):
        with pytest.raises(CredentialResolutionError, match="Instagram account id is unavailable"):
            build_meta_instagram_client_from_runtime()


def test_meta_instagram_runtime_context_rejects_missing_preresolved_token(monkeypatch):
    from api.integrations.meta_instagram import (
        build_meta_instagram_client_from_runtime,
        meta_instagram_runtime_context,
    )
    from api.runtime.credential_resolver import CredentialResolutionError

    def fail_resolver(*args, **kwargs):
        raise AssertionError("resolver should not run inside runtime context")

    monkeypatch.setattr(
        "api.integrations.meta_instagram.resolve_oauth_token_payload",
        fail_resolver,
    )

    with meta_instagram_runtime_context(
        db=object(),
        owner_user_id="user-1",
        run_id="run-1",
    ):
        with pytest.raises(
            CredentialResolutionError,
            match="Meta Instagram OAuth token was not prepared",
        ):
            build_meta_instagram_client_from_runtime()


@pytest.mark.parametrize(
    ("crew_snapshot", "expected"),
    [
        (
            {
                "runtime_crew": {"agent_version_ids": ["agent-1"]},
                "agent_tool_links": {"agent-1": ["ax.instagram_publish_tool"]},
                "runtime_tools": {},
            },
            True,
        ),
        (
            {
                "runtime_crew": {"agent_version_ids": ["agent-1"]},
                "agent_tool_links": {"agent-1": ["tool-1"]},
                "runtime_tools": {
                    "tool-1": {
                        "module_path": "api.tools.instagram_publish_tool",
                        "class_name": "AXInstagramPublishTool",
                    }
                },
            },
            True,
        ),
        (
            {
                "runtime_crew": {"agent_version_ids": ["agent-1"]},
                "agent_tool_links": {"agent-1": ["tool-1"]},
                "runtime_tools": {
                    "tool-1": {
                        "credentials": [
                            {
                                "provider": "meta_instagram",
                                "required": True,
                            }
                        ],
                    }
                },
            },
            True,
        ),
        (
            {
                "runtime_crew": {"agent_version_ids": ["agent-1"]},
                "agent_tool_links": {"agent-1": ["tool-1"]},
                "runtime_tools": {
                    "tool-1": {
                        "credentials": [
                            {
                                "provider": "meta_instagram",
                                "required": False,
                            }
                        ],
                    }
                },
            },
            False,
        ),
        (
            {
                "runtime_crew": {"agent_version_ids": ["agent-1"]},
                "agent_tool_links": {"agent-1": ["tool-1"]},
                "runtime_tools": {
                    "tool-1": {
                        "credential_requirements": [
                            {
                                "provider": "meta_instagram",
                                "injection": "runtime_context",
                                "required": False,
                            }
                        ],
                    }
                },
            },
            False,
        ),
        (
            {
                "runtime_crew": {"agent_version_ids": ["agent-1"]},
                "agent_tool_links": {"agent-1": ["tool-1"]},
                "runtime_tools": {
                    "tool-1": {
                        "credential_requirements": [
                            {
                                "provider": "meta_instagram",
                                "injection": "runtime_context",
                            }
                        ],
                    }
                },
            },
            True,
        ),
        (
            {
                "runtime_crew": {"agent_version_ids": ["agent-1"]},
                "agent_tool_links": {"agent-1": ["tool-1"]},
                "runtime_tools": {
                    "tool-1": {
                        "module_path": "api.tools.slack_tool",
                        "class_name": "AXSlackTool",
                    }
                },
            },
            False,
        ),
    ],
)
def test_crew_snapshot_uses_meta_instagram_detects_supported_tool_shapes(
    crew_snapshot,
    expected,
):
    from api.integrations.meta_instagram import crew_snapshot_uses_meta_instagram

    assert crew_snapshot_uses_meta_instagram(crew_snapshot) is expected


def _create_flow_run(db, *, owner_user_id: str) -> models.FlowRun:
    asset = models.Asset(
        id="92222222-2222-4222-8222-222222222222",
        asset_type="flow",
        workspace_id="93333333-3333-4333-8333-333333333333",
        owner_user_id=owner_user_id,
        name="Instagram Action Flow",
    )
    version = models.AssetVersion(
        id="94444444-4444-4444-8444-444444444444",
        asset_id=asset.id,
        version_number=1,
        status="published",
        created_by=owner_user_id,
        payload_json={},
    )
    run = models.FlowRun(
        id="95555555-5555-4555-8555-555555555555",
        flow_version_id=version.id,
        status="running",
        input_json={},
    )
    db.add_all([asset, version, run])
    db.flush()
    return run
